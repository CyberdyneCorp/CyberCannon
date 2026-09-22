"""What every `ImageInspector` SHALL do, whoever implements it (task 2.1).

The port is `add-concept-ingestion`'s D1 boundary: reading is here, rules are
domain. So the contract asserts exactly the properties the domain depends on and
deliberately asserts nothing about pixels — what an image *looks like* is not
something a specification has an opinion about.

What every implementation owes its caller:

* the **format read from the content**, which is the clause
  `concept-ingestion` states twice — *"Format SHALL be determined from the
  file's own content, not from its filename extension"* — and which the TIFF
  called `.png` is the whole test of;
* the **dimensions and the byte size** the acceptance rules are evaluated
  against, so a limit is compared with an observation rather than with a guess;
* a **content hash of the bytes it was handed**, because that digest is the blob
  key, the freshness token and the precondition of a replacement, all at once;
* the **same answer twice** for the same bytes — an inspector that drifted
  between runs would make a re-upload look like a revision;
* a **named refusal** for bytes that are not an image, never facts about
  nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from canon_fixtures import image as fixtures
from cybercanon.application.ports.image_inspector import ImageInspector, ImageUnreadable
from cybercanon.domain.revisions import ContentHash


@dataclass(frozen=True)
class ImageFixture:
    """One image every implementation of the port is seeded with."""

    name: str
    image_format: str
    encoded_as: str
    width: int
    height: int
    alpha: bool = False

    @property
    def content(self) -> bytes:
        return fixtures.image_bytes(self.encoded_as, self.width, self.height, alpha=self.alpha)


BOARD_PNG = ImageFixture("front.png", "png", fixtures.PNG, 1024, 768, alpha=True)
BOARD_JPEG = ImageFixture("side.jpg", "jpeg", fixtures.JPEG, 800, 600)
BOARD_WEBP = ImageFixture("back.webp", "webp", fixtures.WEBP, 640, 640)
MISLABELLED = ImageFixture("front.png", "tiff", fixtures.TIFF, 320, 240)
"""A TIFF whose file name ends in `.png`. The clause, as a fixture."""

CORPUS = (BOARD_PNG, BOARD_JPEG, BOARD_WEBP, MISLABELLED)


class ImageInspectorContract:
    """The behaviour every image inspector shares."""

    def test_the_format_comes_from_the_content(self, implementation: ImageInspector) -> None:
        facts = implementation.inspect(BOARD_PNG.content, name=BOARD_PNG.name)

        assert facts.format == BOARD_PNG.image_format

    def test_a_tiff_named_png_is_reported_as_a_tiff(self, implementation: ImageInspector) -> None:
        """*"Content decides, not the extension."* The name says `.png`; it is a TIFF."""
        facts = implementation.inspect(MISLABELLED.content, name=MISLABELLED.name)

        assert facts.format == "tiff"

    @pytest.mark.parametrize("fixture", CORPUS, ids=lambda fixture: fixture.image_format)
    def test_the_dimensions_are_the_images_own(
        self, implementation: ImageInspector, fixture: ImageFixture
    ) -> None:
        facts = implementation.inspect(fixture.content, name=fixture.name)

        assert (facts.width, facts.height) == (fixture.width, fixture.height)

    def test_the_byte_size_is_the_bytes_it_was_handed(self, implementation: ImageInspector) -> None:
        content = BOARD_JPEG.content

        assert implementation.inspect(content).byte_size == len(content)

    def test_the_content_hash_is_the_digest_of_those_bytes(
        self, implementation: ImageInspector
    ) -> None:
        """The blob key, the freshness token and the precondition are this one value."""
        content = BOARD_WEBP.content

        assert implementation.inspect(content).content_hash == ContentHash.of(content)

    def test_alpha_is_reported_when_the_image_carries_it(
        self, implementation: ImageInspector
    ) -> None:
        assert implementation.inspect(BOARD_PNG.content).has_alpha
        assert not implementation.inspect(BOARD_JPEG.content).has_alpha

    def test_the_same_bytes_inspect_the_same_way_twice(
        self, implementation: ImageInspector
    ) -> None:
        """An inspector that drifted would make a re-upload look like a revision."""
        content = BOARD_PNG.content

        assert implementation.inspect(content) == implementation.inspect(content)

    def test_bytes_that_are_not_an_image_are_refused_by_name(
        self, implementation: ImageInspector
    ) -> None:
        with pytest.raises(ImageUnreadable):
            implementation.inspect(fixtures.not_an_image(), name="notes.png")
