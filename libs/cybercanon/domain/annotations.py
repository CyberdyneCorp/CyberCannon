"""Annotations and their anchors — the durable-anchoring rule, as types.

Anchoring is the hard part, not the viewer (openspec/project.md). A pin stored
as a triangle index plus barycentric coordinates is precise and worthless the
moment the mesh is re-exported — exactly when the feedback needs to survive. So
the anchors here are **dual**: the durable key is a named thing (a concept
`view` for 2D, a mesh `part` and optionally a `bone` for 3D), while `point` and
`normal` are positioning *hints* and the `camera` restores the viewing angle.

That rule is enforced structurally rather than by comment: no anchor type
carries a triangle index or a barycentric coordinate, `ANCHOR_TYPES` enumerates
every anchor so a new one cannot escape the check, and
`tests/unit/test_domain_annotations.py` asserts it over the fields themselves.
A renamed or deleted part therefore yields an orphan annotation — resolution is
`anchor-resolution`'s job, but it can only ever answer "the named part is gone",
never "the point landed on something else".

Every annotation has exactly two exits: **promoted** into a durable rule, or
**resolved** as a transient issue. `state` records which one it took, and the
compiled briefing carries rules plus open annotations only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

Point = tuple[float, float, float]
"""A position in object space. A hint, never an identity."""


class AnnotationKind(Enum):
    """Which discipline is speaking."""

    ART_DIRECTION = "art-direction"
    TECHNICAL = "technical"
    DESIGN = "design"

    def __str__(self) -> str:
        return self.value


class AnnotationState(Enum):
    """The two exits, plus the one state that is not an exit."""

    OPEN = "open"
    PROMOTED = "promoted"
    RESOLVED = "resolved"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Camera:
    """The viewing angle an annotation was authored from, so it can be restored."""

    position: Point
    target: Point
    fov_deg: float


@dataclass(frozen=True)
class Anchor2D:
    """A point on a concept view, in normalized coordinates.

    The durable key is the view name: a view is a named artifact of the concept
    block, and `u`/`v` are meaningful only within it.
    """

    view: str
    u: float
    v: float

    def __post_init__(self) -> None:
        for axis, value in (("u", self.u), ("v", self.v)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{axis}={value} is outside the normalized range 0.0-1.0")

    @property
    def durable_key(self) -> str:
        """What identifies this anchor across re-exports of the concept."""
        return self.view


@dataclass(frozen=True)
class Anchor3D:
    """A point on a mesh, keyed by the named part it sits on.

    `part` is the identity. `bone`, `point`, `normal` and `camera` are optional
    and carry no identity: a retopologised mesh moves every vertex, and the
    annotation must survive that with the part name alone.
    """

    part: str
    bone: str | None = None
    point: Point | None = None
    normal: Point | None = None
    camera: Camera | None = None

    @property
    def durable_key(self) -> str:
        """What identifies this anchor across re-exports of the mesh."""
        return self.part

    def with_hints(self, point: Point | None, normal: Point | None) -> Anchor3D:
        """The same anchor with different hints — the durable key is untouched."""
        return replace(self, point=point, normal=normal)


Anchor = Anchor2D | Anchor3D

ANCHOR_TYPES: tuple[type, ...] = (Anchor2D, Anchor3D)
"""Every anchor type. The no-triangle-index test reads this, not a hand list."""


@dataclass(frozen=True)
class Annotation:
    """One piece of feedback, anchored durably, with exactly two ways out."""

    id: str
    author: str
    kind: AnnotationKind
    text: str
    target: Anchor
    state: AnnotationState = AnnotationState.OPEN

    @property
    def is_open(self) -> bool:
        return self.state is AnnotationState.OPEN

    @property
    def has_exited(self) -> bool:
        """Promoted or resolved — either way it is out of the open set."""
        return not self.is_open

    @property
    def durable_key(self) -> str:
        """What this annotation is attached to, whichever anchor form it uses."""
        return self.target.durable_key

    def promoted(self) -> Annotation:
        """Exit one: its content became a durable rule and it is retired."""
        return replace(self, state=AnnotationState.PROMOTED)

    def resolved(self) -> Annotation:
        """Exit two: it was a transient issue and it has been addressed."""
        return replace(self, state=AnnotationState.RESOLVED)


def open_annotations(annotations: tuple[Annotation, ...]) -> tuple[Annotation, ...]:
    """The annotations the compiled briefing carries; the exits stay in git history."""
    return tuple(annotation for annotation in annotations if annotation.is_open)


__all__ = [
    "ANCHOR_TYPES",
    "Anchor",
    "Anchor2D",
    "Anchor3D",
    "Annotation",
    "AnnotationKind",
    "AnnotationState",
    "Camera",
    "Point",
    "open_annotations",
]
