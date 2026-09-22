"""Task 2.1 — the `ThumbnailRenderer` contract against every implementation.

The fake derives a deterministic stand-in and the real one derives a WebP, and
one body runs over both. The asymmetry is the point: every ingestion test in
this repository runs against the fake, so a fake whose output varied per call
would make *"the mirror is rebuildable"* a green build over a cache that can
never be reproduced.
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from thumbnail_renderer_contract import ThumbnailRendererContract

from cybercanon.adapters.outbound.image.thumbnails import PillowThumbnailRenderer
from cybercanon.application.testing.thumbnail_renderer import InMemoryThumbnailRenderer


def in_memory(directory: Path) -> InMemoryThumbnailRenderer:
    return InMemoryThumbnailRenderer()


def real(directory: Path) -> PillowThumbnailRenderer:
    return PillowThumbnailRenderer()


implementation = implementation_fixture(fake=in_memory, real=real)


class TestThumbnailRenderer(ThumbnailRendererContract):
    """The contract, against the fake and against Pillow."""
