"""The `ImageInspector` port — bytes in, :class:`ImageFacts` out (D1).

The same boundary :mod:`cybercanon.application.ports.mesh_inspector` draws, for
the same reason and with the same payoff. An inspector reads bytes and answers
six dumb facts; the **domain** decides whether those facts are acceptable
against the project's
:class:`~cybercanon.domain.views.IngestionLimits`. Nothing here knows what a
limit is, and nothing in the domain knows what Pillow is.

Two clauses of `concept-ingestion` are structural in this port rather than
checked by a caller:

* **Format is determined from the file's own content, not from its filename
  extension.** :meth:`ImageInspector.inspect` takes bytes and, at most, a name
  to put in a message — there is no parameter through which an extension could
  decide the answer, so *"a TIFF whose filename ends in `.png` SHALL be rejected
  as a TIFF"* holds by construction.
* **Unreadable is an answer, not a crash.** A file that is not an image at all
  raises :class:`ImageUnreadable`, which carries the subject, so a request
  naming three files is refused naming the one that was not an image.
"""

from __future__ import annotations

from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.domain.views import ImageFacts


class ImageUnreadable(OperationFailed):
    """These bytes are not an image this inspector can read.

    Invalid rather than unavailable: the caller sent something, and no retry
    will turn it into an image. The fix is a different file.
    """

    kind = FailureKind.INVALID
    identifier = "image.unreadable"

    def __init__(self, subject: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"{subject} could not be read as an image{detail}", subject)
        self.reason = reason


class ImageInspector(Protocol):
    """Reads an image's facts. Decides nothing."""

    def inspect(self, content: bytes, *, name: str = "") -> ImageFacts:
        """The six facts about these bytes.

        `name` is for the message an :class:`ImageUnreadable` carries and for
        nothing else — in particular it never decides the format, because that
        is the one thing `concept-ingestion` says must come from the content.
        """
        ...


__all__ = ["ImageInspector", "ImageUnreadable"]
