"""The `ThumbnailRenderer` port — derived bytes that never enter the repository (D9).

A thumbnail is the cheapest possible derived artifact and it is still governed
by the rule every derived artifact in this system is governed by: **the
repository is the source, and the derivation writes nowhere near it.** D9 makes
that structural rather than a `.gitignore` entry — *"a `.gitignore` entry is a
rule someone can violate; a code path that never writes to the working tree
cannot"* — so this port takes bytes and returns bytes, and has no way to name a
path in a working copy.

`concept-ingestion` adds one requirement that is a property of the
implementation rather than of the interface, and the conformance suite is where
it is asserted: **derivation is deterministic.** Deriving twice from the same
source image produces thumbnails with the same content hash, which is what makes
a re-derivation after a wiped cache land on the keys it had.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.domain.revisions import ContentHash

DEFAULT_SIZES: tuple[int, ...] = (256, 1024)
"""The fixed size set every derivation produces, longest side in pixels.

Fixed rather than requested per call, because two callers asking for different
sizes would produce two caches of the same image and neither would be the one a
surface looks in. A grid tile and a detail pane are the two sizes that exist.
"""

THUMBNAIL_TYPE = "image/webp"
"""What a thumbnail is encoded as. One encoder, one setting, one answer."""


@dataclass(frozen=True)
class Thumbnail:
    """One derived image: its bytes, what it hashes to, and how big it is.

    `size` is the requested longest side rather than the produced width, so a
    caller can address *the 256 thumbnail* without knowing the source's aspect
    ratio — which it cannot, because a thumbnail preserves it.
    """

    size: int
    width: int
    height: int
    content: bytes
    content_type: str = THUMBNAIL_TYPE

    @property
    def digest(self) -> ContentHash:
        """The key these bytes are stored under. Derived, never supplied."""
        return ContentHash.of(self.content)

    @property
    def byte_size(self) -> int:
        return len(self.content)


class ThumbnailFailed(OperationFailed):
    """Derivation could not run — and, after a commit, that is a pending step.

    Unavailable rather than invalid: `concept-ingestion` requires a post-commit
    derived failure to be reported as *"ingested with thumbnail derivation
    pending"*, which is only a coherent sentence if the condition is one that
    resolves by being retried.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "thumbnail.failed"

    def __init__(self, subject: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"thumbnails for {subject} could not be derived{detail}", subject)
        self.reason = reason


class ThumbnailRenderer(Protocol):
    """Derives fixed-size thumbnails from an image's bytes. Writes nothing."""

    def derive(
        self, content: bytes, sizes: tuple[int, ...] = DEFAULT_SIZES
    ) -> tuple[Thumbnail, ...]:
        """One thumbnail per requested size, deterministically.

        Raises :class:`ThumbnailFailed` when the bytes cannot be decoded. Never
        touches a working copy: there is no path in this signature, and D9 is
        the reason.
        """
        ...


__all__ = [
    "DEFAULT_SIZES",
    "THUMBNAIL_TYPE",
    "Thumbnail",
    "ThumbnailFailed",
    "ThumbnailRenderer",
]
