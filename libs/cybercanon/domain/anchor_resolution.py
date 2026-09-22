"""Whether a 3D anchor still names something, answered without a renderer (D6).

`add-viewer-3d`'s D6 splits the question a stored anchor asks in two, and the
split is the whole reason this module is in the domain:

* **"is this anchor's part present in this export?"** is a question about
  *names*, and the names are already in :class:`~cybercanon.domain.mesh_facts.MeshFacts`.
  It is answered here, purely, so the asset page, the agent read surface and the
  compiled briefing can all say *"four annotations are orphaned on the current
  export"* with no GPU anywhere;
* **"where on that part does the pin go?"** is a question about *geometry*, and
  it needs the mesh. It stays in the browser, behind the scene module's
  interface, and nothing about it enters the domain — there is no triangle here,
  no bounding volume and no camera.

*"An orphan list that requires a GPU is a list nobody sees."*

Three outcomes and no fourth:

* ``resolved`` — the named part is present, and so is the named bone if one was
  recorded;
* ``partial`` — the part is present and the recorded bone is not. `anchor-resolution`
  requires this to *narrow to the part* rather than orphan: a rig changing its
  bone names must not throw away a still-valid part reference;
* ``orphaned`` — the part is not present. The expected name travels with the
  outcome, because *"naming the part it expected"* is what makes the report
  actionable, and nothing here ever proposes a substitute.

**Nothing resolves an orphan automatically.** :func:`resolve` has no parameter
that could hold a candidate, compares nothing but exact names, and returns the
same ``orphaned`` outcome whether the export contains a near-identical part name
or nothing at all. `project.md` forbids the silently relocated annotation by
name, and the way that stays true is that the substitution has nowhere to happen.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from cybercanon.domain.annotations import NO_SUCH_PART, Anchor, Anchor2D, Anchor3D

NO_SUCH_BONE = "the bone it named is not in this export, so it is placed on its part alone"
"""Why a partially resolved anchor is partial, in the words a surface renders."""

RESOLVES = ""
"""The reason a fully resolved anchor carries: none. Resolution is not an event."""


class Resolution(Enum):
    """What became of one anchor against one export. A closed set of three."""

    RESOLVED = "resolved"
    PARTIAL = "partial"
    ORPHANED = "orphaned"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AnchorResolution:
    """One anchor's standing against one export: the outcome, and what it named.

    `part` and `bone` are what the *anchor* expected rather than what the export
    holds, which is the difference between a report a modeller can act on and a
    report that says something is missing without saying what.
    """

    outcome: Resolution
    part: str
    bone: str = ""
    reason: str = RESOLVES

    @property
    def is_resolved(self) -> bool:
        """Whether the pin can be placed at all — partial counts, orphaned does not."""
        return self.outcome is not Resolution.ORPHANED

    @property
    def is_orphaned(self) -> bool:
        return self.outcome is Resolution.ORPHANED

    @property
    def is_partial(self) -> bool:
        return self.outcome is Resolution.PARTIAL

    def __str__(self) -> str:
        return str(self.outcome)


def resolve(
    anchor: Anchor3D,
    parts: Iterable[str],
    bones: Iterable[str] | None = None,
) -> AnchorResolution:
    """This anchor's standing against those part and bone names, and nothing else.

    Exact comparison, deliberately: `anchor-resolution` requires a renamed part
    to orphan *"naming the part it expected"* rather than land on its successor,
    and case folding or prefix matching would be the relocation arriving through
    a side door.

    ``bones=None`` means *this caller does not know the bone set*, which is not
    the same as an export with no bones — the distinction
    :func:`~cybercanon.domain.annotations.orphan_reason` already makes for view
    and part names, for the same reason: a caller that simply had not looked
    must not report every bone-naming anchor as partial.
    """
    known_parts = frozenset(parts)
    if anchor.part not in known_parts:
        return AnchorResolution(
            outcome=Resolution.ORPHANED,
            part=anchor.part,
            bone=anchor.bone or "",
            reason=NO_SUCH_PART,
        )
    if anchor.bone and bones is not None and anchor.bone not in frozenset(bones):
        return AnchorResolution(
            outcome=Resolution.PARTIAL,
            part=anchor.part,
            bone=anchor.bone,
            reason=NO_SUCH_BONE,
        )
    return AnchorResolution(outcome=Resolution.RESOLVED, part=anchor.part, bone=anchor.bone or "")


def resolution_of(
    anchor: Anchor,
    parts: Iterable[str],
    bones: Iterable[str] | None = None,
) -> AnchorResolution | None:
    """The same answer for any anchor, or ``None`` for one that is not a mesh anchor.

    A 2D anchor resolves against a concept view's *slots*, which is
    `view-versioning`'s question and not this module's. Answering ``None``
    rather than inventing a fourth outcome keeps the three the specification
    names from acquiring a fourth meaning nobody wrote down.
    """
    if isinstance(anchor, Anchor2D):
        return None
    return resolve(anchor, parts, bones)


__all__ = [
    "NO_SUCH_BONE",
    "RESOLVES",
    "AnchorResolution",
    "Resolution",
    "resolution_of",
    "resolve",
]
