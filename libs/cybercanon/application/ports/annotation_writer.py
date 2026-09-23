"""The `AnnotationWriter` port — where an observation lands (D1, D2).

One port, one destination, and the composition root chooses which: the local
agent server binds it to the git working copy the person is actually editing in,
and the hosted API will bind the same port to its own persistent working copy
when `add-web-backend`'s writer is wired to it. That is D1 in one sentence, and
its reason is the drift this project keeps refusing — *"the tool must behave
identically whether the person is working locally or through the hosted
surface"*, and a tool that chose its destination at call time is two code paths
through one name.

The port has three operations and the shape of them is the interesting part:

* :meth:`AnnotationWriter.locate` answers *does this asset exist here*, so the
  use case can refuse an unknown identifier **before** anything is spent — no
  rate-limit allowance, and above all no file. `mcp-write-surface` requires the
  refusal to leave nothing behind: *"SHALL NOT create an asset, create a
  specification file, or cause one to come into existence as a side effect of a
  write."*
* :meth:`AnnotationWriter.annotations` reads back what the asset already holds,
  which is what the durable half of the rate limit (D9) and the duplicate
  suppression (D10) are computed from. Derived from the record rather than from
  a counter, because *"a purely in-process limiter resets when a looping agent
  crashes and restarts."*
* :meth:`AnnotationWriter.append` adds one annotation to an asset that already
  exists. There is no `replace`, no `remove` and no `edit` — an automated caller
  records observations and takes no exit, and a port with no method for the
  prohibited thing cannot be talked into it.

What the port deliberately cannot express is a *path to write to*. `append`
names an asset and the implementation knows where that asset's specification
is, so nothing above this boundary can point a write at a file of its choosing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.domain.annotations import Annotation

UNCOMMITTED = (
    "the change is in the working copy and is not committed; review it with "
    "`git diff` and commit it with the rest of your work"
)
"""What a local write tells its caller, every time (D2).

*"An observation can be destroyed by `git checkout .` before anyone reads it.
Mitigated by saying so in the response; not mitigated further, because the
alternative costs more."* The sentence lives beside the port so the command
line, the agent surface and the hosted one cannot phrase the risk three ways.
"""


@dataclass(frozen=True)
class WrittenAnnotation:
    """What a write left behind: the annotation, the file, and whether it is safe.

    `committed` is false for the local writer and true for a hosted one, and it
    is a fact about the destination rather than a preference — D2 fixes the
    local behaviour as *"modifies the working copy and does not commit"*, and
    the hosted note in the same decision fixes the other.
    """

    path: str
    annotation: Annotation
    committed: bool = False
    revision: str = ""

    @property
    def id(self) -> str:
        return self.annotation.id

    @property
    def note(self) -> str:
        """What the caller is told about the durability of what just happened."""
        return "" if self.committed else UNCOMMITTED


class AnnotationWriteRefused(OperationFailed):
    """The specification cannot be written right now, and nothing was written.

    A conflicted or unmergeable file is the case this exists for: *"the writer
    refuses on an unmergeable or conflicted specification file, reports the
    condition, and ... the agent is told to retry."* A conflict rather than an
    outage, because the condition is about *this file* and clears when a person
    finishes their rebase.
    """

    kind = FailureKind.CONFLICT
    identifier = "annotation_writer.refused"

    def __init__(self, subject: str, reason: str) -> None:
        super().__init__(f"{subject} could not be written: {reason}", subject)
        self.reason = reason


class AnnotationWriteUnavailable(OperationFailed):
    """The destination could not be reached at all — no repository, no network."""

    kind = FailureKind.UNAVAILABLE
    identifier = "annotation_writer.unavailable"

    def __init__(self, subject: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"annotations cannot be written for {subject}{detail}", subject)
        self.reason = reason


class AnnotationWriter(Protocol):
    """Appends one annotation to an asset that already exists, and nothing else."""

    def locate(self, project: str, asset_id: str) -> str | None:
        """The specification file this asset is written in, or ``None``.

        ``None`` is an ordinary answer — *there is no such asset here* — and
        never a failure, because the refusal that follows it names the unknown
        identifier and offers the closest ones, which is a use case's sentence
        rather than a port's.
        """
        ...

    def annotations(self, project: str, asset_id: str) -> tuple[Annotation, ...]:
        """Every annotation recorded on this asset, in the order the file lists it.

        Raises :class:`AnnotationWriteUnavailable` when the asset cannot be
        read at all. An asset with no annotations answers with an empty tuple,
        which is what a first observation is recorded against.
        """
        ...

    def append(self, project: str, asset_id: str, annotation: Annotation) -> WrittenAnnotation:
        """Add this annotation to that asset's `annotations` block.

        Raises :class:`AnnotationWriteRefused` when the file is conflicted or
        unmergeable and :class:`AnnotationWriteUnavailable` when the destination
        is unreachable. Every other file is left exactly as it was: the only
        permitted change is the annotations block of the asset named here (D3).
        """
        ...


__all__ = [
    "UNCOMMITTED",
    "AnnotationWriteRefused",
    "AnnotationWriteUnavailable",
    "AnnotationWriter",
    "WrittenAnnotation",
]
