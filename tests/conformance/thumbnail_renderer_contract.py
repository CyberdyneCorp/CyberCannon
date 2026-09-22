"""What every `ThumbnailRenderer` SHALL do, whoever implements it (task 2.1).

One property carries this contract and it is the one `concept-ingestion` states:
*"Derivation SHALL be deterministic: deriving twice from the same source image
SHALL produce thumbnails with the same content hash."* Without it a wiped
thumbnail cache could not be rebuilt onto the keys it had, and the recovery
`blob-storage` documents would restore *something* rather than *the same thing*.

The rest follows from D9: a renderer takes bytes and answers bytes, one per
requested size, and has no way to name a path in a working copy — so a thumbnail
cannot reach the repository by any route this port offers.
"""

from __future__ import annotations

from canon_fixtures import image as fixtures
from cybercanon.application.ports.thumbnail_renderer import (
    DEFAULT_SIZES,
    ThumbnailRenderer,
)

SOURCE = fixtures.image_bytes(fixtures.PNG, 1024, 768)
OTHER = fixtures.image_bytes(fixtures.PNG, 1024, 768, seed=7)


class ThumbnailRendererContract:
    """The behaviour every thumbnail renderer shares."""

    def test_one_thumbnail_is_derived_per_requested_size(
        self, implementation: ThumbnailRenderer
    ) -> None:
        derived = implementation.derive(SOURCE, DEFAULT_SIZES)

        assert tuple(thumbnail.size for thumbnail in derived) == DEFAULT_SIZES

    def test_deriving_twice_produces_the_same_content_hashes(
        self, implementation: ThumbnailRenderer
    ) -> None:
        """The property a rebuild after total loss depends on."""
        first = implementation.derive(SOURCE, DEFAULT_SIZES)
        second = implementation.derive(SOURCE, DEFAULT_SIZES)

        assert [thumbnail.digest for thumbnail in first] == [
            thumbnail.digest for thumbnail in second
        ]

    def test_a_different_source_derives_different_thumbnails(
        self, implementation: ThumbnailRenderer
    ) -> None:
        """Determinism that ignored its input would be a constant, not a derivation."""
        derived = implementation.derive(SOURCE, (256,))
        other = implementation.derive(OTHER, (256,))

        assert derived[0].digest != other[0].digest

    def test_every_thumbnail_carries_bytes_and_a_type(
        self, implementation: ThumbnailRenderer
    ) -> None:
        for thumbnail in implementation.derive(SOURCE, (256,)):
            assert thumbnail.content
            assert thumbnail.byte_size == len(thumbnail.content)
            assert thumbnail.content_type.startswith("image/")

    def test_a_requested_size_set_of_one_derives_one(
        self, implementation: ThumbnailRenderer
    ) -> None:
        assert len(implementation.derive(SOURCE, (128,))) == 1
