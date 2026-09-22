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

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
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


class AnchorState(Enum):
    """Whether an anchor still means what it meant. Never an exit (D7).

    `add-concept-ingestion`'s D7 is the whole of this type: *"AnchorState in
    {carried, orphaned} is independent of the annotation's exit state {open,
    promoted, resolved}. Nothing in ingestion may write the exit state."* An
    orphan is an annotation whose view was replaced by something its normalised
    coordinates no longer describe — it is still open, and it still owes one of
    the two exits.

    Auto-resolving orphans would be a way to empty the open-issues list without
    anybody deciding anything, which is exactly the failure the two-exit
    discipline exists to prevent, arriving through a side door.
    """

    CARRIED = "carried"
    ORPHANED = "orphaned"

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
        if not self.view or self.view.strip() != self.view:
            raise ValueError(f"a 2D anchor names a view; {self.view!r} is not one")
        for axis, value in (("u", self.u), ("v", self.v)):
            if not math.isfinite(value):
                raise ValueError(f"{axis}={value} is not a finite normalized coordinate")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{axis}={value} is outside the normalized range 0.0-1.0")

    @property
    def durable_key(self) -> str:
        """What identifies this anchor across re-exports of the concept."""
        return self.view


@dataclass(frozen=True)
class Anchor3D:
    """A point on a mesh, keyed by the named part it sits on.

    `part` is the identity. `bone`, `point`, `normal`, `camera`, `clip` and `t`
    are optional and carry no identity: a retopologised mesh moves every vertex,
    and the annotation must survive that with the part name alone.

    `clip` and `t` are `add-viewer-3d`'s playback hint (D9): *which clip was on
    screen, and how far through it*, so that opening the annotation puts the
    part back in the pose its author was looking at. A **proportion of the
    clip's duration**, never a frame index — frame indices are meaningless
    across a frame-rate change, and `asset-validation` already treats frame rate
    as a fact that can legitimately differ or be unavailable per format. There is
    deliberately no field here that could hold a frame number, so the format
    cannot express the anchor that dies on the next re-export at 24 fps.
    """

    part: str
    bone: str | None = None
    point: Point | None = None
    normal: Point | None = None
    camera: Camera | None = None
    clip: str | None = None
    t: float | None = None

    def __post_init__(self) -> None:
        if self.t is None:
            return
        if not math.isfinite(self.t) or not 0.0 <= self.t <= 1.0:
            raise ValueError(
                f"t={self.t} is not a proportion of a clip's duration; the playback "
                "hint is a value in 0.0-1.0, never a frame index"
            )

    @property
    def durable_key(self) -> str:
        """What identifies this anchor across re-exports of the mesh."""
        return self.part

    @property
    def playback(self) -> tuple[str, float] | None:
        """The clip and position this anchor was authored at, or ``None`` (D9).

        Both or neither: a position with no clip names nothing, and a clip with
        no position is the clip's start, which is a pose nobody chose.
        """
        if not self.clip or self.t is None:
            return None
        return (self.clip, self.t)

    def with_hints(self, point: Point | None, normal: Point | None) -> Anchor3D:
        """The same anchor with different hints — the durable key is untouched."""
        return replace(self, point=point, normal=normal)


Anchor = Anchor2D | Anchor3D

ANCHOR_TYPES: tuple[type, ...] = (Anchor2D, Anchor3D)
"""Every anchor type. The no-triangle-index test reads this, not a hand list."""


# --------------------------------------------------------------------------
# A thread's replies, and the marks drawn beside it (D8)
# --------------------------------------------------------------------------


MAX_STROKE_POINTS = 512
"""How many points one annotation's marks may carry, in total (D8).

A cap rather than a truncation: :func:`simplify` thins a stroke that exceeds it
instead of dropping its tail, because a stroke that stopped halfway is a
different gesture and the person would have no way of knowing it happened.
"""

STROKE_TOLERANCE = 0.002
"""How far a point may sit from the line its neighbours draw and still be dropped.

In normalized image space, so it is two parts in a thousand of the image's
width whatever the rendition it was drawn at — which is the whole reason the
tolerance lives beside the normalized coordinate rather than beside the canvas.
"""


@dataclass(frozen=True)
class Stroke:
    """One freehand mark: an ordered list of normalized points, and nothing else.

    D8 is the type: there is no width, no colour, no layer and no z-order here,
    and the absence is the guardrail. A raster overlay would make brushes and
    opacity a feature request away, would produce an un-reviewable diff, and
    would tie the mark's meaning to the resolution it was drawn at. Polylines
    scale with zoom for free and delete cleanly with their annotation.
    """

    points: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        for index, point in enumerate(self.points):
            if len(point) != 2:
                raise ValueError(f"stroke point {index} is not a (u, v) pair: {point!r}")
            for axis, value in zip("uv", point, strict=True):
                if not math.isfinite(value):
                    raise ValueError(f"stroke point {index} has a non-finite {axis}")
                if not 0.0 <= value <= 1.0:
                    raise ValueError(
                        f"stroke point {index} has {axis}={value}, outside the "
                        "normalized range 0.0-1.0"
                    )

    @property
    def length(self) -> int:
        return len(self.points)

    @property
    def is_empty(self) -> bool:
        """A stroke with fewer than two points draws nothing."""
        return self.length < 2


def simplify(
    points: Sequence[tuple[float, float]], tolerance: float = STROKE_TOLERANCE
) -> tuple[tuple[float, float], ...]:
    """Ramer-Douglas-Peucker: the same gesture, with the redundant points gone.

    Iterative rather than recursive so that a long stroke cannot exhaust the
    interpreter's stack — a drawing surface produces thousands of points for one
    flick of a pen, and a recursion limit reached mid-save would lose the mark.
    """
    if len(points) < 3:
        return tuple(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    pending = [(0, len(points) - 1)]
    while pending:
        start, end = pending.pop()
        index, distance = _furthest(points, start, end)
        if index is None or distance <= tolerance:
            continue
        keep[index] = True
        pending.extend(((start, index), (index, end)))
    return tuple(point for point, kept in zip(points, keep, strict=True) if kept)


def _furthest(
    points: Sequence[tuple[float, float]], start: int, end: int
) -> tuple[int | None, float]:
    """Which point between two others is furthest from the line they draw."""
    found, furthest = None, 0.0
    for index in range(start + 1, end):
        distance = _distance(points[index], points[start], points[end])
        if distance > furthest:
            found, furthest = index, distance
    return found, furthest


def _distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    """The perpendicular distance from a point to the segment `start`-`end`."""
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    span = math.hypot(dx, dy)
    if span == 0.0:
        return math.hypot(px - ax, py - ay)
    return abs(dy * (px - ax) - dx * (py - ay)) / span


def capped(
    strokes: Sequence[Stroke],
    limit: int = MAX_STROKE_POINTS,
    tolerance: float = STROKE_TOLERANCE,
) -> tuple[Stroke, ...]:
    """These strokes within the per-annotation point cap, by simplifying (D8).

    *"A stroke exceeding the cap is simplified rather than truncated at the
    end."* The tolerance is doubled until the whole scribble fits, so a person
    who drew slowly loses fidelity and never loses the end of their own line.
    Strokes with fewer than two points are dropped: they are a tap, not a mark.
    """
    drawn = tuple(stroke for stroke in strokes if not stroke.is_empty)
    thinned = tuple(Stroke(simplify(stroke.points, tolerance)) for stroke in drawn)
    while sum(stroke.length for stroke in thinned) > limit and tolerance < 1.0:
        tolerance *= 2
        thinned = tuple(Stroke(simplify(stroke.points, tolerance)) for stroke in drawn)
    return thinned


@dataclass(frozen=True)
class Reply:
    """One contribution to a thread: its own author, its own time, no anchor.

    `annotation-authoring` fixes the shape and the absences are the requirement:
    *"a reply SHALL NOT carry an anchor, a kind or a resolution state of its own
    — a thread has one anchor and one exit, which are the root annotation's"*.
    There is therefore no field here to put one in, which is what makes the
    sentence structural rather than a rule somebody enforces.
    """

    id: str
    author: str
    text: str
    at: str = ""
    via: str = ""
    edited_at: str = ""

    @property
    def attribution(self) -> str:
        """`rafa, via blender-agent` — the person, and the instrument when one acted."""
        return attributed(self.author, self.via)

    def with_text(self, text: str, at: str = "") -> Reply:
        """The same reply, re-worded. Author and attribution are not parameters."""
        return replace(self, text=text, edited_at=at)


def attributed(author: str, via: str = "") -> str:
    """How every surface renders an attribution, decided once.

    `annotation-authoring`: *"presented so that both are visible — for example
    'rafa, via blender-agent'"*. One function, because four renderers phrasing
    it four ways is how a reader learns that the web app and the command line
    disagree about who said something.
    """
    return f"{author}, via {via}" if via else author


@dataclass(frozen=True)
class Annotation:
    """One piece of feedback, anchored durably, with exactly two ways out."""

    id: str
    author: str
    kind: AnnotationKind
    text: str
    target: Anchor
    state: AnnotationState = AnnotationState.OPEN
    authored_against: str = ""
    """The revision of the view or mesh this annotation was placed on.

    `view-versioning` requires it: *"Every annotation anchored to a view SHALL
    record the revision of the view it was authored against"*, and it is what
    makes a carried pin readable as *this predates what you are looking at*
    rather than as a claim about the current image.
    """

    anchor_state: AnchorState = AnchorState.CARRIED
    """Whether the anchor still resolves against the current revision (D6, D7).

    Carried until something replaces the thing it points at. Independent of
    :attr:`state`, and deliberately so — see :class:`AnchorState`.
    """

    reanchored_by: str = ""
    reanchored_at: str = ""
    """Who re-anchored this orphan, and when. Empty for one nobody has.

    `view-versioning` requires re-anchoring to *"record who did it and when"*,
    and requires that nothing re-anchor automatically — so these two fields are
    only ever written by :meth:`reanchored`, which takes a person.
    """

    via: str = ""
    """The agent that acted on the author's behalf, when one did.

    The person in :attr:`author` stays accountable; this names the instrument,
    so a record reads *"rafa, via blender-agent"*. Empty for a person acting
    directly, which is the ordinary case and the only one the sheet produces.
    """

    replies: tuple[Reply, ...] = field(default_factory=tuple)
    """The thread, in creation order. One anchor and one exit, both the root's."""

    strokes: tuple[Stroke, ...] = field(default_factory=tuple)
    """The freehand marks drawn beside this annotation, normalized (D8).

    They belong to the annotation and not to the image: they disappear when it
    takes an exit, and nothing here is ever rasterised onto the view.
    """

    created_at: str = ""
    edited_at: str = ""
    """When it was written, and when its text was last changed. Empty for never."""

    moved_by: str = ""
    moved_at: str = ""
    """Who moved it to a different anchor, and when — `annotation-authoring`.

    *"The annotation SHALL record that it was moved."* Written only by
    :meth:`moved_to`, which takes a person, so no other operation can set them
    as a side effect.
    """

    closed_by: str = ""
    closed_at: str = ""
    closing_text: str = ""
    """Who took the exit, when, and what they concluded.

    *"An annotation whose conclusion is that no change is needed SHALL be
    recorded as resolved with that conclusion as its closing text."*
    """

    @property
    def is_open(self) -> bool:
        return self.state is AnnotationState.OPEN

    @property
    def is_orphaned(self) -> bool:
        """Whether its anchor stopped resolving. Says nothing about its exit."""
        return self.anchor_state is AnchorState.ORPHANED

    @property
    def has_exited(self) -> bool:
        """Promoted or resolved — either way it is out of the open set."""
        return not self.is_open

    @property
    def durable_key(self) -> str:
        """What this annotation is attached to, whichever anchor form it uses."""
        return self.target.durable_key

    @property
    def is_promoted(self) -> bool:
        """Whether its content is now a rule. A rule is not reopenable."""
        return self.state is AnnotationState.PROMOTED

    @property
    def is_resolved(self) -> bool:
        return self.state is AnnotationState.RESOLVED

    @property
    def attribution(self) -> str:
        """`rafa, via blender-agent` — the person, and the agent when one acted."""
        return attributed(self.author, self.via)

    @property
    def reply_count(self) -> int:
        return len(self.replies)

    @property
    def has_replies(self) -> bool:
        """Whether it may still be withdrawn: a thread with replies takes an exit."""
        return bool(self.replies)

    def promoted(self, by: str = "", at: str = "") -> Annotation:
        """Exit one: its content became a durable rule and it is retired.

        The marks go with it, because D8 says they belong to the annotation and
        `annotation-authoring` says they *"disappear with it when it is
        resolved, promoted or deleted"*.
        """
        return replace(
            self,
            state=AnnotationState.PROMOTED,
            strokes=(),
            closed_by=by or self.closed_by,
            closed_at=at or self.closed_at,
        )

    def resolved(self, by: str = "", at: str = "", conclusion: str = "") -> Annotation:
        """Exit two: it was a transient issue and it has been addressed."""
        return replace(
            self,
            state=AnnotationState.RESOLVED,
            strokes=(),
            closed_by=by or self.closed_by,
            closed_at=at or self.closed_at,
            closing_text=conclusion or self.closing_text,
        )

    def reopened(self, by: str = "", at: str = "") -> Annotation:
        """Back to open, and back into the triage queue, attributed.

        Refusing to reopen a *promoted* annotation is the triage policy's
        decision, not this method's: a value object that silently declined would
        make the refusal invisible to the person who asked for it.
        """
        return replace(
            self,
            state=AnnotationState.OPEN,
            closed_by=by or self.closed_by,
            closed_at=at or self.closed_at,
            closing_text="",
        )

    def with_text(self, text: str, at: str = "") -> Annotation:
        """The same annotation, re-worded — anchor, author and state untouched.

        *"A text edit leaves the anchor untouched"*, and neither the anchor nor
        the author is a parameter here, which is how that stays true.
        """
        return replace(self, text=text, edited_at=at)

    def with_reply(self, reply: Reply) -> Annotation:
        """The thread with one more contribution, at the end. Order is creation order."""
        return replace(self, replies=(*self.replies, reply))

    def with_strokes(self, strokes: Sequence[Stroke]) -> Annotation:
        """The same annotation carrying these marks, capped and simplified (D8)."""
        return replace(self, strokes=capped(strokes))

    def moved_to(self, target: Anchor, *, by: str, at: str, revision: str = "") -> Annotation:
        """A person moved this annotation to another anchor, and is recorded.

        Text, kind and exit state are untouched by construction — none of them
        is a parameter — and the anchor state returns to carried because a
        person has just said where it belongs.
        """
        return replace(
            self,
            target=target,
            anchor_state=AnchorState.CARRIED,
            authored_against=revision or self.authored_against,
            moved_by=by,
            moved_at=at,
        )

    def carried_to(self, revision: str) -> Annotation:
        """The same annotation, its anchor still valid against a new revision (D6).

        The exit state is untouched, here and in :meth:`orphaned_by`: ingestion
        has no business writing it, and the way that stops being a rule somebody
        remembers is that neither method takes it as an argument.
        """
        return replace(self, anchor_state=AnchorState.CARRIED, authored_against=revision)

    def orphaned_by(self) -> Annotation:
        """The same annotation, its anchor no longer resolving (D6, D7).

        `authored_against` is *not* moved: an orphan is still readable against
        the revision it was placed on, which `view-versioning` requires —
        *"the revision it was authored against SHALL be retrievable and its
        position on that revision SHALL be shown"*.
        """
        return replace(self, anchor_state=AnchorState.ORPHANED)

    def reanchored(self, target: Anchor, *, revision: str, by: str, at: str) -> Annotation:
        """A person moved this orphan onto the current revision, and is recorded.

        Text and exit state are untouched by construction — neither is a
        parameter — which is how *"its text and its open state SHALL be
        unchanged"* stops being a promise and becomes a signature.
        """
        return replace(
            self,
            target=target,
            anchor_state=AnchorState.CARRIED,
            authored_against=revision,
            reanchored_by=by,
            reanchored_at=at,
        )


# --------------------------------------------------------------------------
# Filtering — medium-agnostic, and never a mutation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AnnotationFilter:
    """Which annotations a surface is asking for. Pure data, applied purely.

    Three independent axes, combining: the kinds wanted, the exit states wanted,
    and whether orphans are included. `kinds` and `states` empty mean *every*
    one, which is what makes the default filter the one `model-sheet-2d`
    specifies — *"open annotations of every kind"* — expressible without a
    special case.
    """

    kinds: frozenset[AnnotationKind] = frozenset()
    states: frozenset[AnnotationState] = frozenset({AnnotationState.OPEN})
    orphans: bool = True

    @classmethod
    def every(cls) -> AnnotationFilter:
        """No filter at all — every kind, every state, orphans included."""
        return cls(kinds=frozenset(), states=frozenset(), orphans=True)

    @classmethod
    def of(
        cls,
        kinds: Iterable[AnnotationKind] = (),
        states: Iterable[AnnotationState] = (AnnotationState.OPEN,),
        orphans: bool = True,
    ) -> AnnotationFilter:
        """A filter from whatever a surface parsed, without it knowing the types."""
        return cls(kinds=frozenset(kinds), states=frozenset(states), orphans=orphans)

    def wants(self, annotation: Annotation) -> bool:
        """Whether this annotation passes every axis of the filter."""
        if self.kinds and annotation.kind not in self.kinds:
            return False
        if self.states and annotation.state not in self.states:
            return False
        return self.orphans or not annotation.is_orphaned

    def apply(self, annotations: Sequence[Annotation]) -> tuple[Annotation, ...]:
        """The annotations this filter wants, in the order they were given.

        Nothing is mutated and nothing is re-ordered: a filter is a question
        about a set, and a filter that sorted would be a second opinion about
        the order a thread list is presented in.
        """
        return tuple(annotation for annotation in annotations if self.wants(annotation))

    def hidden(self, annotations: Sequence[Annotation]) -> int:
        """How many the current filter is keeping off the view (`model-sheet-2d`)."""
        return len(annotations) - len(self.apply(annotations))


DEFAULT_FILTER = AnnotationFilter()
"""What a sheet opened with no filter chosen presents: open work, every kind."""


# --------------------------------------------------------------------------
# Orphans — a named subject that is gone, for either anchor form
# --------------------------------------------------------------------------


NO_SUCH_VIEW = "the view it was anchored to is no longer part of this asset"
NO_SUCH_PART = "the mesh part it was anchored to is no longer in the export"


@dataclass(frozen=True)
class Orphan:
    """One annotation whose anchored subject is gone, and why it is unplaceable.

    The reason travels with it because `model-sheet-2d` requires the thread
    panel to list an orphan *"with the reason they cannot be shown"*, and a
    surface that reconstructed the sentence from the anchor form would be
    deciding what the system means by orphaned.
    """

    annotation: Annotation
    reason: str

    @property
    def subject(self) -> str:
        """The name that no longer resolves — the view, or the part."""
        return self.annotation.durable_key


def orphan_reason(
    annotation: Annotation,
    views: Iterable[str] | None = None,
    parts: Iterable[str] | None = None,
) -> str:
    """Why this annotation cannot be placed, or an empty string when it can.

    One function over both anchor forms, which is the medium-agnostic claim in
    miniature: a 2D anchor resolves against the asset's views and a 3D anchor
    against the export's parts, and *nothing else about the two differs*. It
    never proposes a substitute subject — `project.md` forbids the silently
    mis-placed annotation by name, and an "obvious" nearest match is exactly how
    one arrives.

    ``None`` means *this caller does not know the set*, which is different from
    an empty one and answers *not an orphan*. A surface with no mesh in hand
    must not declare every part anchor dead: whether a named part is still in
    the export is `anchor-resolution`'s question, asked where the geometry is.
    """
    anchor = annotation.target
    if isinstance(anchor, Anchor2D):
        return _absent(anchor.view, views, NO_SUCH_VIEW)
    return _absent(anchor.part, parts, NO_SUCH_PART)


def _absent(subject: str, known: Iterable[str] | None, reason: str) -> str:
    """The reason, when the set is known and does not hold this subject."""
    if known is None:
        return ""
    return "" if subject in set(known) else reason


def orphans(
    annotations: Sequence[Annotation],
    views: Iterable[str] | None = None,
    parts: Iterable[str] | None = None,
) -> tuple[Orphan, ...]:
    """Every annotation of this asset that has nothing left to point at."""
    known_views, known_parts = _known(views), _known(parts)
    found = (
        (annotation, orphan_reason(annotation, known_views, known_parts))
        for annotation in annotations
    )
    return tuple(Orphan(annotation, reason) for annotation, reason in found if reason)


def _known(names: Iterable[str] | None) -> tuple[str, ...] | None:
    """A set the caller knows, as a tuple — or ``None``, which is not a set."""
    return None if names is None else tuple(names)


def placeable(
    annotations: Sequence[Annotation],
    views: Iterable[str] | None = None,
    parts: Iterable[str] | None = None,
) -> tuple[Annotation, ...]:
    """The annotations a surface may draw a pin for — never an orphan.

    *"An orphaned annotation ... SHALL be excluded from the pins presented over
    any view or mesh until a person re-anchors it."*
    """
    known_views, known_parts = _known(views), _known(parts)
    return tuple(
        annotation
        for annotation in annotations
        if not annotation.is_orphaned and not orphan_reason(annotation, known_views, known_parts)
    )


def marked_orphans(
    annotations: Sequence[Annotation],
    views: Iterable[str] | None = None,
    parts: Iterable[str] | None = None,
) -> tuple[Annotation, ...]:
    """The same annotations, with the unplaceable ones carrying the orphan state.

    The exit state is untouched — `AnchorState` and `AnnotationState` are
    independent by construction — so an orphan stays open and still owes one of
    its two exits.
    """
    known_views, known_parts = _known(views), _known(parts)
    return tuple(
        annotation.orphaned_by()
        if orphan_reason(annotation, known_views, known_parts)
        else annotation
        for annotation in annotations
    )


def thread_of(annotations: Sequence[Annotation], annotation_id: str) -> Annotation | None:
    """The annotation with that identifier, or ``None``. One lookup, everywhere."""
    return next((entry for entry in annotations if entry.id == annotation_id), None)


def replaced(annotations: Sequence[Annotation], updated: Annotation) -> tuple[Annotation, ...]:
    """The same list with one annotation swapped for its successor, in place.

    Position is preserved rather than appended-to, because the order of the list
    in `asset.yaml` is the order a reviewer reads the file in, and an edit that
    moved a thread to the end would make every reply a whole-block diff.
    """
    return tuple(updated if entry.id == updated.id else entry for entry in annotations)


def without(annotations: Sequence[Annotation], annotation_id: str) -> tuple[Annotation, ...]:
    """The same list with that annotation gone — what a withdrawal produces."""
    return tuple(entry for entry in annotations if entry.id != annotation_id)


def open_annotations(annotations: tuple[Annotation, ...]) -> tuple[Annotation, ...]:
    """The annotations the compiled briefing carries; the exits stay in git history."""
    return tuple(annotation for annotation in annotations if annotation.is_open)


__all__ = [
    "ANCHOR_TYPES",
    "DEFAULT_FILTER",
    "MAX_STROKE_POINTS",
    "NO_SUCH_PART",
    "NO_SUCH_VIEW",
    "STROKE_TOLERANCE",
    "Anchor",
    "Anchor2D",
    "Anchor3D",
    "AnchorState",
    "Annotation",
    "AnnotationFilter",
    "AnnotationKind",
    "AnnotationState",
    "Camera",
    "Orphan",
    "Point",
    "Reply",
    "Stroke",
    "attributed",
    "capped",
    "marked_orphans",
    "open_annotations",
    "orphan_reason",
    "orphans",
    "placeable",
    "replaced",
    "simplify",
    "thread_of",
    "without",
]
