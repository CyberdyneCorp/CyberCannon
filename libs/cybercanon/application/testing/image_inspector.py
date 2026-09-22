"""The in-memory `ImageInspector` — facts handed to it, never read from bytes.

The same shape as :class:`~cybercanon.application.testing.mesh_inspector.InMemoryMeshInspector`,
and for the same reason: D1's whole payoff is that every rule test is a
constructed value object with no file anywhere, and a fake that decoded images
would quietly re-introduce the dependency the port exists to remove.

Images are registered **by their bytes**, keyed by the digest of those bytes, so
a test hands the same `content` to the use case that it seeded here and the
inspector answers the facts it was told. That keying is also what makes the
conformance suite honest: the contract seeds this fake with the facts of the
very fixtures it writes for the real adapter, so the two are answering about the
same images.

It records what it was asked, because *"a rejected upload inspected nothing it
did not have to"* is an assertion rather than a hope.
"""

from __future__ import annotations

from cybercanon.application.ports.image_inspector import ImageUnreadable
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.views import ImageFacts


class InMemoryImageInspector:
    """Images registered by their bytes, each with the facts it yields."""

    def __init__(self) -> None:
        self._facts: dict[str, ImageFacts] = {}
        self._unreadable: dict[str, str] = {}
        self.inspected: list[str] = []

    # -- seeding ---------------------------------------------------------

    def add(self, content: bytes, facts: ImageFacts) -> ImageFacts:
        """An image this inspector can read, and the facts it answers with.

        The **content hash is always recomputed** from the bytes and is never
        the caller's to state: it is the blob key, the freshness token and the
        precondition of a replacement, and a fake that let a test choose it
        would let every one of those three agree about something that is not
        true.

        Everything else — format, dimensions, byte size, alpha — is registered
        exactly as the caller stated it, which is D1's whole payoff: a 41 MB
        upload is staged as a *fact*, so the size rule is exercised without 41
        MB of anything. The real adapter is pinned to the truth by the port
        conformance suite, which is where that belongs.
        """
        stated = ImageFacts(
            format=facts.format,
            width=facts.width,
            height=facts.height,
            byte_size=facts.byte_size,
            content_hash=ContentHash.of(content),
            has_alpha=facts.has_alpha,
        )
        self._facts[stated.content_hash.value] = stated
        return stated

    def add_unreadable(self, content: bytes, reason: str = "not an image") -> None:
        """Bytes that are not an image: :class:`ImageUnreadable` on inspect."""
        self._unreadable[ContentHash.of(content).value] = reason

    # -- port ------------------------------------------------------------

    def inspect(self, content: bytes, *, name: str = "") -> ImageFacts:
        digest = ContentHash.of(content)
        self.inspected.append(digest.value)
        reason = self._unreadable.get(digest.value)
        if reason is not None:
            raise ImageUnreadable(name or digest.short, reason)
        facts = self._facts.get(digest.value)
        if facts is None:
            raise ImageUnreadable(name or digest.short, "these bytes were never registered")
        return facts


__all__ = ["InMemoryImageInspector"]
