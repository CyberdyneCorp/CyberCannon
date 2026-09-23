"""What an automated caller may write, and the three limits on writing it.

The product's sharpest rule lives here: **agents read constraints, agents never
write constraints** (`openspec/project.md`). An agent that flags an unreachable
budget is worth the whole system; an agent that edits the budget so its own
export passes is how trust in it dies in week two. So an agent-authored
annotation is an **observation** — D8's *"ordinary annotation with an author
kind, not a parallel record type"* — and everything below exists to make the
second thing unconstructible rather than merely discouraged.

Four decisions are implemented here, all of them pure, none of them aware of a
file, a clock, a token or a tool:

* **the vocabulary** — :func:`annotation_kind_of` and
  :func:`observation_kind_of`, each refusing an unrecognised value by naming the
  permitted ones. Two fields, two closed sets, and the `asset-spec` set is
  consumed rather than extended (`mcp-write-surface`);
* **what an automated caller may do at all** — :data:`OBSERVATION_ONLY`, an
  explicit registry of the mutating operations it is refused, and
  :func:`may_only_observe`, which refuses them *for every role in turn* rather
  than for the roles somebody remembered;
* **how much it may write** — :func:`write_allowance` (D9), a pure function over
  the actor, the asset, what is already recorded and a clock, returning either
  permission or a refusal naming the limit and the moment it resets;
* **whether this is the same thing again** — :func:`duplicate_of` (D10), which
  compares normalised text against the caller's own **open** observations only,
  so a restarted agent contributes one thread and a person who resolved
  something can still be told it recurred.

The anchoring rule is the fifth and it is a refusal to guess: an observation
naming a target the asset does not have is recorded *unanchored, with the target
preserved as given*. `openspec/project.md` forbids the silently mis-placed
annotation by name, and "the nearest part" is exactly how one arrives.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from cybercanon.domain.annotations import (
    Anchor3D,
    AnchorState,
    Annotation,
    AnnotationKind,
    AuthorKind,
    ObservationKind,
)
from cybercanon.domain.authorization import ALLOWED, Decision
from cybercanon.domain.identity import Actor, AgentId, Role
from cybercanon.domain.policy import MUTATING, Operation

# --------------------------------------------------------------------------
# The two closed vocabularies, and the refusal that names them
# --------------------------------------------------------------------------


class ObservationRefused(ValueError):
    """The observation cannot be constructed, and this is what would have to change.

    A `ValueError` for the reason
    :class:`~cybercanon.domain.triage.PromotionRefused` is one: this is the
    domain declining to produce a state, and the application turns it into the
    outcome vocabulary. Nothing here knows what a status code is.
    """

    def __init__(self, reason: str, subject: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.subject = subject


def annotation_kind_of(declared: str) -> AnnotationKind:
    """The `asset-spec` kind this text names, or a refusal listing that set.

    The set is **not** widened for observations: *"it SHALL NOT redefine, extend
    or narrow that set"*. An agent that sends `unattainable_constraint` here is
    told what `asset-spec` permits and where its own vocabulary goes, because a
    refusal that only says no leaves the caller guessing which of two fields it
    got wrong.
    """
    kind = next(
        (member for member in AnnotationKind if member.value == declared.strip()),
        None,
    )
    if kind is None:
        raise ObservationRefused(
            f"{declared.strip()!r} is not an annotation kind; the permitted kinds are "
            f"{_listed(member.value for member in AnnotationKind)}. An observation's own "
            f"vocabulary is `observation_kind`, whose values are "
            f"{_listed(ObservationKind.values())}",
            "kind",
        )
    return kind


def observation_kind_of(declared: str) -> ObservationKind:
    """The observation kind this text names, or a refusal listing the permitted ones.

    *"An unrecognised value in either field SHALL be refused with a message
    listing the permitted values, and SHALL NOT be recorded as a free-form
    value."* So there is no path through this function that returns something
    outside the enumeration, and therefore none through the write.
    """
    kind = ObservationKind.from_value(declared)
    if kind is None:
        raise ObservationRefused(
            f"{declared.strip()!r} is not an observation kind; the permitted kinds are "
            f"{_listed(ObservationKind.values())}",
            "observation_kind",
        )
    return kind


def _listed(values: Iterable[str]) -> str:
    return ", ".join(f"`{value}`" for value in values)


# --------------------------------------------------------------------------
# What an automated caller may do — an explicit registry, checked for every role
# --------------------------------------------------------------------------


OBSERVATION_ONLY: frozenset[Operation] = frozenset(MUTATING - {Operation.CREATE_ANNOTATION})
"""Every mutating operation an automated caller is refused. Derived, not listed.

The write surface offers exactly one operation that changes recorded state on an
asset — recording an annotation — so this set is *everything else that mutates*,
computed from :data:`~cybercanon.domain.policy.MUTATING` rather than enumerated.
A mutating operation added tomorrow is prohibited for an agent the moment it is
declared, which is the safe direction to be wrong in and the only one that keeps
`mcp-write-surface`'s prohibition true without anybody remembering it.

It is a superset of the requirement's own list — *"SHALL NOT create, modify or
delete any constraint, budget, rule, silhouette rule, status or owner, and SHALL
NOT resolve, promote, close or reopen any annotation, including its own"* — and
deliberately so: the requirement names the ways an agent could become an author
of the canon, and the registry names the ways it could change anything at all.
"""

ONLY_OBSERVES = (
    "an automated caller records observations and nothing else: it may not "
    "create, modify or delete a constraint, rule, budget, status or owner, and "
    "may not resolve, promote, close or reopen any annotation, including its own"
)
"""The sentence every refusal of an automated write carries, whatever refused it."""


def may_only_observe(actor: Actor, operation: Operation, *, via: AgentId | None = None) -> Decision:
    """Whether an automated caller may perform this operation. Roles do not help.

    The refusal does not consult :attr:`~cybercanon.domain.identity.Actor.roles`
    at all, and that is the requirement rather than an optimisation: *"regardless
    of the roles held by the actor the caller acts as"*. An art director's agent
    is refused promotion by the same line that refuses an artist's, so there is
    no role list a future change could add a member to and quietly open the door.

    A caller that is neither an automation nor acting through an agent is not
    this function's business: it answers `ALLOWED` and leaves the ordinary
    matrix (:func:`~cybercanon.domain.policy.decide`) to decide.
    """
    if not _automated(actor, via):
        return ALLOWED
    if operation not in OBSERVATION_ONLY:
        return ALLOWED
    return Decision(
        allowed=False, reason=f"{_caller(actor, via)} may not {operation}: {ONLY_OBSERVES}"
    )


def _automated(actor: Actor, via: AgentId | None) -> bool:
    """Whether the caller is a machine — an automation, or a person's instrument."""
    return actor.is_automation or via is not None


def _caller(actor: Actor, via: AgentId | None) -> str:
    """How a refusal names an automated caller: the instrument, or the actor."""
    return f"{via}, acting as {actor.display}," if via is not None else actor.display


def prohibited_for_every_role() -> tuple[Role, ...]:
    """Every role the prohibition is asserted against — the whole set, in order.

    A function rather than a literal in the test, so that a role added to
    :class:`~cybercanon.domain.identity.Role` is walked by the prohibition suite
    the day it is added rather than the day somebody notices.
    """
    return tuple(Role)


# --------------------------------------------------------------------------
# The target — anchored, or preserved as given and reported unanchored
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservationTarget:
    """The subject an agent named, and whether the asset actually has it.

    `given` is kept **verbatim**, resolved or not, for the same reason
    :func:`~cybercanon.domain.identity.unmapped_actor` keeps an unmatched email
    verbatim: it is the evidence a person needs in order to work out what the
    agent meant, and a normalised or substituted value destroys it.
    """

    given: str
    anchored: bool

    @property
    def anchor(self) -> Anchor3D:
        """The durable anchor this target produces — a named part, and nothing else.

        An agent has a part name and no pixel coordinates, so the anchor carries
        the name alone. That is the whole of :class:`Anchor3D`'s durable key,
        and the optional hints stay empty rather than being invented: a point
        nobody measured is worse than no point.
        """
        return Anchor3D(part=self.given)

    @property
    def anchor_state(self) -> AnchorState:
        """Carried when the asset has this subject, orphaned when it does not.

        An unresolvable target is not a second kind of anchor and not a reason to
        discard the write: it is the ordinary orphan state every reader already
        renders, which is what makes *"reading it SHALL report it as
        unanchored"* true on surfaces written before observations existed.
        """
        return AnchorState.CARRIED if self.anchored else AnchorState.ORPHANED


def target_for(given: str, known: Sequence[str] | None = None) -> ObservationTarget:
    """The target an observation anchors to, resolved against what the asset has.

    `known` is the subjects the asset holds — its parts, its views, or both.
    ``None`` means *this caller does not know the set*, which is different from
    an empty one and answers *anchored*, exactly as
    :func:`~cybercanon.domain.annotations.orphan_reason` treats it: a surface
    with no mesh in hand must not declare every part anchor dead.

    A target that is empty or only whitespace is refused rather than recorded,
    because an observation anchored to nothing at all is not the unanchored case
    — it is a caller that forgot an argument.
    """
    named = given.strip()
    if not named:
        raise ObservationRefused(
            "an observation names the target it is about; this one names nothing",
            "target",
        )
    return ObservationTarget(given=named, anchored=known is None or named in set(known))


# --------------------------------------------------------------------------
# The rate limit (D9) — a pure function over what is already recorded
# --------------------------------------------------------------------------


DEFAULT_OBSERVATION_LIMIT = 10
DEFAULT_WINDOW_SECONDS = 3600.0
"""The starting numbers. The *behaviour* is specified; the values are configuration.

The design says so in as many words — *"the limit is specified; the values are
configuration, and the first real Blender-agent session is what sets them"*
(task 6.6). They live here so one default is shared by every surface rather than
each composition root inventing its own.
"""


@dataclass(frozen=True)
class WriteLimits:
    """How many observations one caller may record against one asset, and how often.

    Per `(actor, asset)` and not global, because `mcp-write-surface` requires an
    agent throttled on one asset to keep working on another: *"a single global
    per-process limit ... throttles an agent's work on asset B because of its
    loop on asset A"* (D9).
    """

    observations: int = DEFAULT_OBSERVATION_LIMIT
    window_seconds: float = DEFAULT_WINDOW_SECONDS

    def __post_init__(self) -> None:
        if self.observations < 1:
            raise ValueError("a write limit permits at least one write")
        if self.window_seconds <= 0:
            raise ValueError("a write limit spans a positive period")

    @property
    def window(self) -> timedelta:
        return timedelta(seconds=self.window_seconds)


DEFAULT_LIMITS = WriteLimits()
"""The limits a caller that named none is held to. One object, shared."""


@dataclass(frozen=True)
class Allowance:
    """Whether this write may happen, and — when it may not — when it may.

    `resets_at` is populated only on a refusal, and it is not decoration: the
    requirement is that a throttled write be refused *"with a message naming the
    limit and when writing will be possible again"*, and a caller that was told
    only "too many" has no choice but to poll.
    """

    allowed: bool
    limit: int
    recorded: int
    reason: str = ""
    resets_at: datetime | None = None

    @property
    def refused(self) -> bool:
        return not self.allowed

    @property
    def remaining(self) -> int:
        return max(self.limit - self.recorded, 0)

    def __bool__(self) -> bool:
        return self.allowed


def write_allowance(
    *,
    actor: Actor,
    asset_id: str,
    recorded: Sequence[Annotation],
    now: datetime,
    limits: WriteLimits | None = None,
) -> Allowance:
    """Whether this caller may record another observation on this asset (D9).

    Pure, and derived from **what is already recorded** rather than from a
    counter: *"a purely in-process limiter resets when a looping agent crashes
    and restarts — which is the exact failure being defended against"*. An
    in-process bucket is a cheap gate in front of this; it is never the
    protection.

    `recorded` is this asset's annotations, whatever a caller has in hand. Only
    the observations this actor wrote inside the window count, so a human
    thread never consumes an agent's allowance and an agent never consumes a
    human's.
    """
    limits = limits or DEFAULT_LIMITS
    window = tuple(_within(recorded, actor, now, limits.window))
    if len(window) < limits.observations:
        return Allowance(allowed=True, limit=limits.observations, recorded=len(window))
    resets_at = min(_stamped(entry) or now for entry in window) + limits.window
    return Allowance(
        allowed=False,
        limit=limits.observations,
        recorded=len(window),
        reason=(
            f"{actor.display} has recorded {len(window)} observations on {asset_id} "
            f"within {limits.window_seconds:g}s, which is the limit of "
            f"{limits.observations}; writing is possible again at {resets_at.isoformat()}"
        ),
        resets_at=resets_at,
    )


def _within(
    recorded: Sequence[Annotation], actor: Actor, now: datetime, window: timedelta
) -> Iterable[Annotation]:
    """This actor's observations that fall inside the window ending now.

    An observation carrying no creation time is counted as inside it. The
    conservative direction: an agent that wrote its way around the limit by
    omitting a timestamp would be the whole failure this defends against,
    arriving through a field nobody validates.
    """
    since = now - window
    for entry in recorded:
        if not entry.is_agent_authored or entry.author != actor.subject:
            continue
        stamped = _stamped(entry)
        if stamped is None or since <= stamped <= now:
            yield entry


def _stamped(annotation: Annotation) -> datetime | None:
    """When this annotation was created, or ``None`` when that cannot be told.

    ``None`` covers three cases and treats them alike: no recorded time, a time
    that will not parse, and a time with no timezone. The third matters because
    a hand-authored `asset.yaml` may carry `2026-03-01T12:00:00` and comparing
    a naive moment with an aware one raises — a write refused by a `TypeError`
    would be a crash where the specification asks for a decision. All three fall
    through to :func:`_within`'s conservative branch, where they count against
    the limit rather than escaping it.
    """
    if not annotation.created_at:
        return None
    try:
        moment = datetime.fromisoformat(annotation.created_at)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


# --------------------------------------------------------------------------
# Near-duplicate suppression (D10) — open observations, same agent, only
# --------------------------------------------------------------------------


def normalized(text: str) -> str:
    """The text as the duplicate comparison sees it: folded, collapsed, stripped.

    Case-folded, whitespace-collapsed and punctuation-stripped, exactly as D10
    defines *materially the same*. Deliberately not fuzzy: *"fuzzy similarity
    scoring ... needs a threshold nobody can justify and would eventually drop a
    distinct observation"*. Two rephrasings of one problem make two threads, and
    the rate limit bounds the damage.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    kept = "".join(
        character
        for character in folded
        if not unicodedata.category(character).startswith("P")
        and not unicodedata.category(character).startswith("S")
    )
    return " ".join(kept.split())


def materially_same(existing: Annotation, candidate: Annotation) -> bool:
    """Whether these two say the same thing, by D10's definition and no other.

    *"Same asset, same target, same kind, same agent, and normalised text ...
    equal to an existing open observation."* The asset is the caller's scope —
    both annotations come from one asset's list — and the other four are compared
    here. A **resolved** one never suppresses, which is the point of the rule:
    if a person closed it and the agent still hits it, that is new information.
    """
    return (
        existing.is_open
        and existing.is_agent_authored
        and existing.via == candidate.via
        and existing.durable_key == candidate.durable_key
        and existing.kind is candidate.kind
        and existing.observation_kind is candidate.observation_kind
        and normalized(existing.text) == normalized(candidate.text)
    )


def duplicate_of(recorded: Sequence[Annotation], candidate: Annotation) -> Annotation | None:
    """The open observation this one repeats, or ``None`` when it repeats none.

    Returns the existing annotation rather than a boolean because the specified
    behaviour is not silence: *"It SHALL report the existing observation
    instead"*, so the caller needs the thread to point at.
    """
    return next((entry for entry in recorded if materially_same(entry, candidate)), None)


# --------------------------------------------------------------------------
# Building the observation itself
# --------------------------------------------------------------------------


def observation(
    *,
    identifier: str,
    author: str,
    via: AgentId,
    kind: AnnotationKind,
    observation_kind: ObservationKind,
    text: str,
    target: ObservationTarget,
    created_at: str = "",
) -> Annotation:
    """One agent-authored observation, as the asset's annotation list holds it.

    `via` is an :class:`~cybercanon.domain.identity.AgentId` and not an optional
    one, which is D4 made structural: *"the domain exposes no constructor for a
    write attribution without both slots"*. There is no argument here that could
    hold a placeholder agent, so the anonymous record is not something this
    function can be persuaded to produce.

    Nor is there an argument for the exit state, the closing text, or anything
    a constraint is written in. An observation is created open, and the only
    ways out of it are the two a person takes.
    """
    stated = text.strip()
    if not stated:
        raise ObservationRefused("an observation says something; this one is empty", "text")
    if not isinstance(via, AgentId):
        raise ObservationRefused(
            "an observation names the agent that performed it; a write that cannot "
            "name one is refused rather than recorded anonymously",
            "via",
        )
    return Annotation(
        id=identifier,
        author=author,
        kind=kind,
        text=stated,
        target=target.anchor,
        anchor_state=target.anchor_state,
        via=str(via),
        author_kind=AuthorKind.AGENT,
        observation_kind=observation_kind,
        created_at=created_at,
    )


__all__ = [
    "DEFAULT_LIMITS",
    "DEFAULT_OBSERVATION_LIMIT",
    "DEFAULT_WINDOW_SECONDS",
    "OBSERVATION_ONLY",
    "ONLY_OBSERVES",
    "Allowance",
    "ObservationRefused",
    "ObservationTarget",
    "WriteLimits",
    "annotation_kind_of",
    "duplicate_of",
    "materially_same",
    "may_only_observe",
    "normalized",
    "observation",
    "observation_kind_of",
    "prohibited_for_every_role",
    "target_for",
    "write_allowance",
]
