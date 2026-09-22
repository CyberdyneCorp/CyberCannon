"""The in-memory `ThumbnailRenderer` — deterministic derived bytes, no decoder.

It derives nothing visual and is not meant to: what the use case depends on is
that derivation is a **pure function of the source bytes and the requested
size**, so that deriving twice produces the same content hash and a wiped cache
is restored by running it again. That property is what this fake models, and it
models it the only honest way — by being a function.

`fail_with` is the seam `concept-ingestion`'s *"post-commit derived failure is a
pending step, not a failed upload"* needs: a thumbnail step that raises must
leave the view ingested, and the only way to assert that is to make it raise.
"""

from __future__ import annotations

import hashlib

from cybercanon.application.ports.thumbnail_renderer import (
    DEFAULT_SIZES,
    THUMBNAIL_TYPE,
    Thumbnail,
)


class InMemoryThumbnailRenderer:
    """Derives a deterministic stand-in per requested size, and records the calls."""

    def __init__(self) -> None:
        self._failure: Exception | None = None
        self.derived: list[str] = []

    def fail_with(self, error: Exception | None) -> None:
        """Make every derivation raise — the failing derived step, on demand."""
        self._failure = error

    def derive(
        self, content: bytes, sizes: tuple[int, ...] = DEFAULT_SIZES
    ) -> tuple[Thumbnail, ...]:
        if self._failure is not None:
            raise self._failure
        self.derived.append(hashlib.sha256(content).hexdigest())
        return tuple(_derived(content, size) for size in sizes)


def _derived(content: bytes, size: int) -> Thumbnail:
    """One stand-in thumbnail, derived from the source and the size and nothing else."""
    body = hashlib.sha256(f"{size}:".encode() + content).digest()
    return Thumbnail(
        size=size,
        width=size,
        height=size,
        content=body,
        content_type=THUMBNAIL_TYPE,
    )


__all__ = ["InMemoryThumbnailRenderer"]
