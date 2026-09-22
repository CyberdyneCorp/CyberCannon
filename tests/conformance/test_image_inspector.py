"""Task 2.1 — the `ImageInspector` contract against every implementation.

The fake is seeded with facts; `PillowImageInspector` is seeded with *files* —
written from `canon_fixtures.image`, so nothing binary lives in git. Running
both through one body catches the divergence that matters: a fake that reported
a format from a file name would make every extension test green and every real
rejection wrong, which is exactly the clause `concept-ingestion` states twice.
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from image_inspector_contract import CORPUS, ImageInspectorContract

from canon_fixtures import image as fixtures
from cybercanon.adapters.outbound.image.inspector import PillowImageInspector
from cybercanon.application.testing.image_inspector import InMemoryImageInspector
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.views import ImageFacts


def in_memory(directory: Path) -> InMemoryImageInspector:
    """The fake, holding exactly the images the contract asks about."""
    inspector = InMemoryImageInspector()
    for fixture in CORPUS:
        content = fixture.content
        inspector.add(
            content,
            ImageFacts(
                format=fixture.image_format,
                width=fixture.width,
                height=fixture.height,
                byte_size=len(content),
                content_hash=ContentHash.of(content),
                has_alpha=fixture.alpha,
            ),
        )
    inspector.add_unreadable(fixtures.not_an_image(), "it is not a recognised image")
    return inspector


def real(directory: Path) -> PillowImageInspector:
    return PillowImageInspector()


implementation = implementation_fixture(fake=in_memory, real=real)


class TestImageInspector(ImageInspectorContract):
    """The contract, against the fake and against Pillow."""
