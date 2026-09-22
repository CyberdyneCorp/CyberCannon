"""The two exits, and the queue that decides which annotations get taken through.

`openspec/project.md` states the rule this module implements: *"Every annotation
has exactly two exits: promoted to a rule (general and permanent → moves into
`constraints` / `silhouette_rules`, annotation retired) or resolved as an issue
(specific and transient → archived and excluded from the compiled spec)."* It is
the loop that makes a team converge instead of recording its disagreements more
neatly, and it is the heart of the product rather than a feature of it.

Four things live here, and every one of them is a pure function of value
objects:

* **the exits themselves** (:data:`EXITS`, :func:`exits_for`) — a closed pair, so
  *"the system SHALL NOT offer any other terminal state"* is a fact about the
  type rather than a rule somebody keeps;
* **the promotion target** (:class:`PromotionTarget`) — `constraints` or
  `concept.silhouette_rules`, named in the refusal when a promotion arrives with
  neither;
* **the promotion itself** (:func:`promote`) — one transformation producing the
  rule *and* the retired annotation, so D6's *"no path produces one without the
  other"* is enforced by there being one function with one return value;
* **the queue** (:class:`TriageEntry`, :func:`triage_order`) — the ordering that
  lifts feedback repeating across a project above a one-off, which is what makes
  the art director's periodic pass a promotion pass rather than a reading pass.

Nothing here reads a file, and nothing here knows what YAML is. A promotion into
`constraints` is expressed as a **declaration** — `tri_budget: 8000` — parsed by
:func:`parse_rule` into the field it sets, because a triangle budget that
arrived as prose would be a rule the validator cannot enforce, and the golden
rule of the `design` block applies to a promoted rule exactly as it applies to
an authored one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from cybercanon.domain.annotations import (
    Annotation,
    AnnotationKind,
    AnnotationState,
    replaced,
    thread_of,
)
from cybercanon.domain.asset import Asset
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig, Texture


class Exit(Enum):
    """The two ways out of the open state. There is no third, by construction."""

    PROMOTE = "promote"
    RESOLVE = "resolve"

    def __str__(self) -> str:
        return self.value


EXITS: tuple[Exit, ...] = (Exit.PROMOTE, Exit.RESOLVE)
"""Every exit an open annotation is offered, in the order a surface lists them.

*"Exactly two SHALL be offered: promote and resolve."* A tuple rather than a
sentence in a handler, so a surface that offered a third would have to write it
down here first.
"""


def exits_for(annotation: Annotation) -> tuple[Exit, ...]:
    """The exits available for this annotation — both, or none for one that took one.

    An annotation that has already exited is offered nothing, which is the other
    half of *"SHALL NOT allow an annotation to be both"*: the refusal of a
    second exit is stated by the same function that offers the first.
    """
    return EXITS if annotation.is_open else ()


class PromotionTarget(Enum):
    """Where a promoted rule lands. Two destinations, named in every refusal."""

    CONSTRAINTS = "constraints"
    SILHOUETTE_RULES = "concept.silhouette_rules"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def from_value(cls, declared: str) -> PromotionTarget | None:
        """The destination this text names, or ``None`` when it names none."""
        return _TARGETS_BY_VALUE.get(declared.strip())

    @classmethod
    def listed(cls) -> str:
        """`constraints` and `concept.silhouette_rules` — what a refusal states."""
        return " and ".join(f"`{value}`" for value in cls.values())

    def __str__(self) -> str:
        return self.value


_TARGETS_BY_VALUE = {member.value: member for member in PromotionTarget}


class PromotionRefused(ValueError):
    """The promotion cannot be applied, and this is what would have to change.

    A `ValueError` because it is the domain refusing to produce a state, exactly
    as :class:`~cybercanon.domain.views.InvalidSlotName` is; the application
    turns it into the outcome vocabulary, and nothing here knows what a status
    code is.
    """

    def __init__(self, reason: str, subject: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.subject = subject


NO_DESTINATION = (
    f"a promotion states where the rule belongs; the destinations are {PromotionTarget.listed()}"
)

EMPTY_RULE = (
    "a promotion states the durable rule text; an empty rule would retire the "
    "annotation and write nothing"
)


# --------------------------------------------------------------------------
# What a rule means in each destination
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Declaration:
    """One constraint field a promoted rule sets: where it goes, and to what.

    `path` is the dotted location as `asset.yaml` spells it, so the refusal a
    validator produces and the destination a person chose are named the same way
    in both directions.
    """

    path: str
    value: object

    def __str__(self) -> str:
        return f"{self.path}: {_rendered(self.value)}"


def _rendered(value: object) -> str:
    if isinstance(value, tuple):
        return ", ".join(str(entry) for entry in value)
    return str(value)


def _integer(text: str) -> object:
    return int(text)


def _number(text: str) -> object:
    return float(text)


def _text(text: str) -> object:
    """The value as written, trimmed.

    The space after the colon is punctuation, not content: a rule promoted as
    `collider: convex` must set the collider to `convex`, and a value carrying a
    leading space would fail every comparison the validator makes against it
    while looking identical in the file.
    """
    return text.strip()


def _flag(text: str) -> object:
    lowered = text.strip().lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    raise ValueError(f"{text!r} is not true or false")


def _integers(text: str) -> object:
    return tuple(int(part) for part in _parts(text))


def _words(text: str) -> object:
    return tuple(_parts(text))


def _parts(text: str) -> tuple[str, ...]:
    stripped = text.strip().strip("[]")
    return tuple(part.strip() for part in stripped.split(",") if part.strip())


FIELDS: Mapping[str, Callable[[str], object]] = {
    "tri_budget": _integer,
    "lods": _integers,
    "collider": _text,
    "pivot": _text,
    "up_axis": _text,
    "unit_scale": _number,
    "naming": _text,
    "texture.size": _integer,
    "texture.sets": _integer,
    "texture.channels": _words,
    "rig.skeleton": _text,
    "rig.max_bones": _integer,
    "rig.skinned": _flag,
    "animation.frame_rate": _number,
    "animation.clip_naming": _text,
}
"""Every engineering constraint a promotion may set, and how its value is read.

A closed table rather than a free-form write into the block: *"Every design
field SHALL either constrain art, constrain code, or be checkable by the
validator"* (`openspec/project.md`), and a promotion that could write an
arbitrary key would be a way to add a field that does none of the three. It is
also what makes the *"invalid resulting constraint refused"* scenario reachable
at all — a triangle budget has to be a number before anything can find it below
the first LOD.
"""

FIELDS_LISTED = ", ".join(f"`{name}`" for name in FIELDS)


def parse_rule(rule_text: str, target: PromotionTarget) -> str | Declaration:
    """What this rule text means in that destination.

    Prose for `concept.silhouette_rules`, because a silhouette rule is read by a
    person and by a model and constrains art rather than an export; a
    :class:`Declaration` for `constraints`, because an engineering constraint is
    read by the validator and prose is not checkable.
    """
    text = rule_text.strip()
    if not text:
        raise PromotionRefused(EMPTY_RULE)
    if target is PromotionTarget.SILHOUETTE_RULES:
        return text
    return _declaration(text)


def _declaration(text: str) -> Declaration:
    name, separator, value = text.partition(":")
    field = name.strip()
    read = FIELDS.get(field)
    if not separator or read is None:
        raise PromotionRefused(
            f"{text!r} does not declare an engineering constraint; a rule promoted "
            f"into `constraints` is written `field: value`, over {FIELDS_LISTED}",
            field or text,
        )
    try:
        return Declaration(path=field, value=read(value))
    except ValueError as error:
        raise PromotionRefused(
            f"{field} cannot be set to {value.strip()!r}: {error}", field
        ) from error


# --------------------------------------------------------------------------
# The promotion itself — one operation, one result (D6)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Promotion:
    """What a promotion produced: the asset after it, and what it wrote.

    One value, because D6 forbids the state in which the rule exists and the
    annotation is still open. Two functions returning two halves is exactly how
    that state arrives — the caller applies the first, something fails, and the
    file is left with a rule nobody agreed to and a thread nobody closed.
    """

    asset: Asset
    annotation: Annotation
    target: PromotionTarget
    rule: str

    @property
    def rule_text(self) -> str:
        """The rule as it now reads in the specification."""
        return self.rule


def promote(
    asset: Asset,
    annotation_id: str,
    rule_text: str,
    target: PromotionTarget,
    *,
    by: str = "",
    at: str = "",
) -> Promotion:
    """Write the rule and retire the annotation, as one transformation (D6).

    There is no ordering to get wrong and no partial application to compensate
    for: the function either returns an asset carrying both changes or raises,
    and a caller that only wanted one of them has no way to ask for it.
    """
    annotation = _promotable(asset, annotation_id)
    rule = parse_rule(rule_text, target)
    retired = annotation.promoted(by=by, at=at)
    written = (
        _with_silhouette_rule(asset, rule)
        if isinstance(rule, str)
        else _with_declaration(asset, rule)
    )
    return Promotion(
        asset=replace(written, annotations=replaced(written.annotations, retired)),
        annotation=retired,
        target=target,
        rule=str(rule),
    )


def _promotable(asset: Asset, annotation_id: str) -> Annotation:
    """The annotation this promotion names, if it is one that may still exit."""
    annotation = thread_of(asset.annotations, annotation_id)
    if annotation is None:
        raise PromotionRefused(
            f"no annotation {annotation_id!r} is recorded on {asset.id}", annotation_id
        )
    if annotation.has_exited:
        raise PromotionRefused(
            f"annotation {annotation_id!r} is already {annotation.state}; "
            "reopen it before taking the other exit",
            annotation_id,
        )
    return annotation


def _with_silhouette_rule(asset: Asset, rule: str) -> Asset:
    """The asset with one more durable silhouette rule, appended in order."""
    concept = asset.concept or Concept()
    if rule in concept.silhouette_rules:
        return asset
    return replace(
        asset,
        concept=replace(concept, silhouette_rules=(*concept.silhouette_rules, rule)),
    )


def _with_declaration(asset: Asset, declaration: Declaration) -> Asset:
    """The asset with one engineering constraint set to what the rule declares."""
    constraints = asset.constraints or Constraints()
    head, _, tail = declaration.path.partition(".")
    if not tail:
        return replace(asset, constraints=replace(constraints, **{head: declaration.value}))
    block = getattr(constraints, head) or _BLOCKS[head]()
    return replace(
        asset,
        constraints=replace(constraints, **{head: replace(block, **{tail: declaration.value})}),
    )


_BLOCKS: Mapping[str, Callable[[], object]] = {
    "texture": Texture,
    "rig": Rig,
    "animation": AnimationDefaults,
}
"""The nested constraint blocks a declaration may reach, built when absent."""


# --------------------------------------------------------------------------
# The queue (D11)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TriageEntry:
    """One open annotation as the art director's pass sees it.

    Every field is a *signal for promotion*: how much company this feedback has
    on its own asset, how much it has across the project, how much argument it
    produced, and how long it has been waiting. None of them is the annotation's
    text, because the ordering must be decidable without reading anything.
    """

    asset: str
    annotation: Annotation
    same_kind_on_asset: int = 0
    same_kind_in_project: int = 0
    age_seconds: float = 0.0
    discipline_owner: str = ""

    @property
    def id(self) -> str:
        return self.annotation.id

    @property
    def kind(self) -> AnnotationKind:
        return self.annotation.kind

    @property
    def replies(self) -> int:
        return self.annotation.reply_count

    @property
    def rank(self) -> tuple[int, int, int, float, str, str]:
        """The total order, as a sortable key.

        Counts descend, then replies descend, then age descends — older first,
        because a question nobody answered for three weeks is the one the pass
        exists to reach — and finally the asset and the identifier, which are
        unique and make the order **total**: two entries with identical signals
        sort the same way on every machine and in every process.
        """
        return (
            -self.same_kind_on_asset,
            -self.same_kind_in_project,
            -self.replies,
            -self.age_seconds,
            self.asset,
            self.id,
        )


def triage_order(entries: Sequence[TriageEntry]) -> tuple[TriageEntry, ...]:
    """The queue, ordered so that recurring feedback rises to the top.

    *"SHALL order it by those counts before age, so that feedback repeating
    across a project rises to the top as a promotion candidate."*
    """
    return tuple(sorted(entries, key=lambda entry: entry.rank))


def same_kind_counts(annotations: Sequence[Annotation], kind: AnnotationKind) -> int:
    """How many open annotations of that kind are in this collection."""
    return sum(
        1
        for annotation in annotations
        if annotation.kind is kind and annotation.state is AnnotationState.OPEN
    )


__all__ = [
    "EMPTY_RULE",
    "EXITS",
    "FIELDS",
    "FIELDS_LISTED",
    "NO_DESTINATION",
    "Declaration",
    "Exit",
    "Promotion",
    "PromotionRefused",
    "PromotionTarget",
    "TriageEntry",
    "exits_for",
    "parse_rule",
    "promote",
    "same_kind_counts",
    "triage_order",
]
