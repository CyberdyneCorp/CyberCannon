"""Derived metadata: proposals a person either promotes or leaves out of the canon.

`project.md` fixes the rule this module implements and the reason for it:
*"The system MAY generate descriptions, tags and suggested aliases from a
concept view or a preview mesh. That output is **derived**, and derived content
lives in the rebuildable index keyed by the blob's content hash — never in
`asset.yaml`, never in the compiled `art-spec.md`."*

Four ideas live here, and each is a sentence of `derived-metadata` or
`metadata-acceptance` rather than a convenience:

* **A record is its source image** (D5). :class:`DerivedRecord` is keyed by the
  content hash of the bytes it was generated from, and equality is that hash and
  nothing else — so regenerating an unchanged image yields *the same record*,
  and a replaced image can never inherit the description of the one before it.
  A record keyed by an asset or by a path would silently do exactly that the
  first time somebody overwrote `concept/front.png`.
* **Normalisation and exclusion are arithmetic, not a polite request** (D11).
  Lowercasing, trimming, deduplication and dropping terms the specification
  already carries are pure functions applied *after* the model answers. Asking a
  model not to repeat existing aliases is a suggestion; filtering afterwards is
  a guarantee, and it is testable with no model anywhere.
* **A malformed answer is refused whole** (D10). :func:`parse_aliases` returns
  ``None`` for anything it cannot read as a list of short terms, because a
  half-parsed alias list is worse than none — somebody would accept the half.
* **A decision is about `(source hash, value)`** (D6), never about the asset.
  A term rejected for an image stays rejected for that image across every
  regeneration, and an acceptance survives the derived rows being deleted
  because the accepted value is no longer here: it is in the specification file,
  as ordinary authored content.

Nothing here knows what YAML, an index row, an HTTP status or a model is. The
domain imports the standard library only, and this module imports five of it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

GENERATED = "generated"
"""What generated content is labelled as, wherever it is presented.

`derived-metadata`: *"it SHALL be identified as generated and not attributed to
a person"*. One constant, so the command line, the agent surface and the web
application cannot each invent their own word for it — and so the *absence* of a
person is a property of the type rather than of a renderer's discipline.
"""

GENERATED_NOTICE = "generated, not authored — accept it to make it yours"
"""The sentence a surface prints beside a proposal. Never a person's name."""

SUGGESTION_NOTICE = "matched on an unaccepted suggestion"
"""How a search result produced only by the sixth pass discloses itself (D9)."""

MAX_ALIAS_LENGTH = 32
"""How long a suggested alias may be. It is a search term somebody types."""

MAX_SUGGESTIONS = 8
"""How many aliases one image may propose.

A constant rather than a setting: the open question the design records is *how
many*, and the answer is a number in code that a later batch moves, not a
configuration surface nobody would tune twice.
"""

ALIAS_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
"""The form an alias takes in a specification, as a whole-string match.

Deliberately narrow, and narrower than YAML would allow: an alias is a term a
person types into a search box and a term the deterministic cascade compares
case-insensitively, so anything a shell, a URL or a YAML scalar would need
quoting for is not one.
"""

_SEPARATORS = re.compile(r"[\s/]+")
_DISALLOWED = re.compile(r"[^a-z0-9_-]+")
_LIST_SPLIT = re.compile(r"[,\n;]+")
_ORNAMENT = re.compile(r"^[\s\-*\d.)\]\[\"'`]+|[\s\"'`.\]]+$")
_PROSE = re.compile(r"[:?!]")

MAX_TERM_WORDS = 2
"""How many words one entry may have before it stops being a search term.

Two, because `scout mech` is a term somebody types and *"here are some terms"*
is a sentence. It is the cheap, honest way to tell a list from a model that
answered in prose, and it is what makes :func:`parse_aliases` report `malformed`
instead of quietly writing `here_are_some_terms` into somebody's search index.
"""


# --------------------------------------------------------------------------
# Provenance and the record itself
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    """Which model said this, when, and about which bytes.

    `derived-metadata` requires all three to be retrievable *wherever the
    derived content is presented*, so they travel with the record rather than
    being looked up beside it. `model` is the configured identifier verbatim —
    the system never interprets it, and a record that outlived a configuration
    change still says what produced it.
    """

    model: str
    generated_at: datetime
    source_hash: str

    def __post_init__(self) -> None:
        if not self.source_hash:
            raise ValueError("a derived record must name the content it came from")

    @property
    def described(self) -> str:
        """One line a surface prints: the model, the moment, the source."""
        return f"{GENERATED} by {self.model} at {self.generated_at.isoformat()} from {self.short}"

    @property
    def short(self) -> str:
        """The source hash abbreviated, as a log line carries it."""
        return self.source_hash[:12]


@dataclass(frozen=True, eq=False)
class DerivedRecord:
    """A description, tags and suggested aliases for one image. A proposal (D5).

    **Equality is the source content hash and nothing else.** Two records for
    the same bytes are the same record however they were worded, which is what
    makes *"an unchanged image is not regenerated"* exact rather than a
    comparison somebody has to remember to write, and what makes a replaced
    image a genuinely new record.

    There is deliberately no `accepted` member and no `author`. Acceptance is
    recorded against `(source hash, value)` in :class:`SuggestionDecision`, and
    an accepted value stops being derived content altogether: it becomes a line
    in `asset.yaml` that nothing distinguishes from a hand-typed one.
    """

    provenance: Provenance
    asset_id: str = ""
    source_path: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    suggested_aliases: tuple[str, ...] = ()

    @property
    def source_hash(self) -> str:
        return self.provenance.source_hash

    @property
    def model(self) -> str:
        return self.provenance.model

    @property
    def generated_at(self) -> datetime:
        return self.provenance.generated_at

    @property
    def label(self) -> str:
        """What this content is. Never a person (`derived-metadata`)."""
        return GENERATED

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DerivedRecord):
            return NotImplemented
        return self.source_hash == other.source_hash

    def __hash__(self) -> int:
        return hash(self.source_hash)


# --------------------------------------------------------------------------
# Decisions — the bridge, keyed by (source hash, value) (D6)
# --------------------------------------------------------------------------


class SuggestionState(Enum):
    """Where one suggested value stands. Three, and no fourth.

    A value is proposed, a person took it, or a person refused it. There is no
    *deferred*: a suggestion nobody has looked at is `PENDING`, which is the
    same thing and does not need a second name.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SuggestionDecision:
    """One person's answer to one suggested value, for one image (D6).

    `value` is the suggestion as it was proposed and `written` is what actually
    went into the specification — the same thing unless the person edited it
    before accepting, which `metadata-acceptance` requires to be possible and
    requires to be attributed to the person who did it.

    The key is `(source_hash, value)` rather than the asset, because the
    specification says a rejected suggestion *"SHALL NOT be presented again for
    the same unchanged source"*: keyed by the asset, a rebuild of the derived
    row would resurrect every rejection the team had already worked through.
    """

    source_hash: str
    value: str
    state: SuggestionState
    actor: str = ""
    at: datetime | None = None
    written: str = ""

    def __post_init__(self) -> None:
        if not self.source_hash or not self.value:
            raise ValueError("a decision names the image it is about and the value it decides")
        if self.state is SuggestionState.PENDING:
            raise ValueError("a recorded decision is an acceptance or a rejection, never pending")

    @property
    def key(self) -> tuple[str, str]:
        """What this decision is filed under — the whole of D6."""
        return (self.source_hash, self.value)

    @property
    def accepted(self) -> bool:
        return self.state is SuggestionState.ACCEPTED

    @property
    def recorded(self) -> str:
        """The value that reached the specification, edited or not."""
        return self.written or self.value


def accepted_decision(
    source_hash: str, value: str, actor: str, at: datetime, written: str = ""
) -> SuggestionDecision:
    """A person took this suggestion. The attribution is not optional (D8)."""
    if not actor:
        raise ValueError("an acceptance is attributed to the person who made it")
    return SuggestionDecision(
        source_hash=source_hash,
        value=value,
        state=SuggestionState.ACCEPTED,
        actor=actor,
        at=at,
        written=written or value,
    )


def rejected_decision(
    source_hash: str, value: str, actor: str = "", at: datetime | None = None
) -> SuggestionDecision:
    """A person refused this suggestion, for this image, permanently."""
    return SuggestionDecision(
        source_hash=source_hash,
        value=value,
        state=SuggestionState.REJECTED,
        actor=actor,
        at=at,
    )


@dataclass(frozen=True)
class Suggestion:
    """One suggested value as a surface shows it: the term, and where it stands."""

    value: str
    state: SuggestionState = SuggestionState.PENDING
    actor: str = ""
    at: datetime | None = None
    written: str = ""

    @property
    def is_pending(self) -> bool:
        return self.state is SuggestionState.PENDING

    @property
    def label(self) -> str:
        """Generated while it is pending; once accepted it is the person's."""
        return GENERATED if self.is_pending else str(self.state)

    def __str__(self) -> str:
        return self.value


def decided(
    record: DerivedRecord, decisions: Iterable[SuggestionDecision]
) -> tuple[Suggestion, ...]:
    """This record's suggestions, each carrying whatever was decided about it.

    Rejected values are **not** dropped here: the caller that presents pending
    work uses :func:`pending`, and a caller showing a person what they already
    refused wants to see it. One function that hid them would make the two
    questions indistinguishable.
    """
    taken = {
        decision.value: decision
        for decision in decisions
        if decision.source_hash == record.source_hash
    }
    return tuple(
        Suggestion(
            value=value,
            state=taken[value].state if value in taken else SuggestionState.PENDING,
            actor=taken[value].actor if value in taken else "",
            at=taken[value].at if value in taken else None,
            written=taken[value].recorded if value in taken else "",
        )
        for value in record.suggested_aliases
    )


def pending(record: DerivedRecord, decisions: Iterable[SuggestionDecision]) -> tuple[str, ...]:
    """The suggested aliases nobody has accepted or rejected yet.

    This is what a surface offers and what the sixth search pass may match on
    (D9): an accepted value is already an alias and ranks as one, and a rejected
    value is gone for this image for good.
    """
    return tuple(entry.value for entry in decided(record, decisions) if entry.is_pending)


def suggestions_by_asset(
    records: Iterable[DerivedRecord], decisions: Iterable[SuggestionDecision]
) -> dict[str, tuple[str, ...]]:
    """Every asset's pending suggested aliases, deduplicated across its images.

    The join the ranked cascade's sixth pass needs, written once so that the
    in-memory index, SQLite and PostgreSQL cannot answer it three ways — the
    same reason `rank` itself lives in the port.
    """
    taken = tuple(decisions)
    found: dict[str, list[str]] = {}
    for record in records:
        if not record.asset_id:
            continue
        held = found.setdefault(record.asset_id, [])
        held.extend(value for value in pending(record, taken) if value not in held)
    return {asset_id: tuple(values) for asset_id, values in found.items()}


# --------------------------------------------------------------------------
# Normalisation and exclusion (D11)
# --------------------------------------------------------------------------


def normalise(value: str) -> str:
    """One proposed term in the form a specification's aliases take.

    Trimmed, lower-cased, inner whitespace and slashes folded to `_`, anything
    outside the alias alphabet dropped, and truncated to the length an alias may
    have. Returns ``""`` for anything that is left with nothing usable, which
    every caller treats as *not a term* rather than as an empty alias.
    """
    folded = _SEPARATORS.sub("_", value.strip().lower())
    kept = _DISALLOWED.sub("", folded).strip("_-")[:MAX_ALIAS_LENGTH].strip("_-")
    return kept if is_normalised(kept) else ""


def is_normalised(value: str) -> bool:
    """Whether this text is already in specification form. The test's question."""
    return bool(value) and len(value) <= MAX_ALIAS_LENGTH and ALIAS_PATTERN.match(value) is not None


def excluded_terms(asset_id: str, name: str, aliases: Sequence[str]) -> frozenset[str]:
    """What a suggestion may never repeat: the id, the name and every alias.

    Compared in normalised form, so `Scout Mech` excludes `scout_mech` and
    `MECH` excludes `mech`. `derived-metadata` requires the exclusion; doing it
    on the normalised form is what makes it hold for the shapes a model actually
    produces.
    """
    declared = (asset_id, name, *aliases)
    return frozenset(term for term in (normalise(value) for value in declared) if term)


def normalised_aliases(
    values: Iterable[str], excluding: Iterable[str] = (), limit: int = MAX_SUGGESTIONS
) -> tuple[str, ...]:
    """The proposed terms as a specification would carry them (D11).

    Trimmed, lower-cased, deduplicated in first-seen order, with everything the
    asset already declares removed, and capped. Order is preserved because the
    model's first answer is its best one and a set would throw that away.
    """
    forbidden = frozenset(term for term in (normalise(value) for value in excluding) if term)
    kept: list[str] = []
    for value in values:
        term = normalise(value)
        if term and term not in forbidden and term not in kept:
            kept.append(term)
    return tuple(kept[:limit])


# --------------------------------------------------------------------------
# Reading what the model said (D10)
# --------------------------------------------------------------------------


def parse_aliases(text: str) -> tuple[str, ...] | None:
    """The terms in a model's answer, or ``None`` when it is not a list of terms.

    Provider-agnostic means no structured-output mode and no function calling
    (`llm-integration` forbids depending on either), so the answer is text and
    has to be read. It is read **defensively and whole**: a response with any
    unusable entry in it is `None`, which the caller reports as `malformed`,
    because a half-parsed alias list is the one outcome worse than no list — it
    is the one somebody accepts.
    """
    stripped = text.strip()
    if not stripped:
        return None
    body = _delisted(stripped).strip().strip(",;")
    candidates = [_unornamented(part) for part in _LIST_SPLIT.split(body)]
    if not candidates or len(candidates) > MAX_SUGGESTIONS * 2:
        return None
    if any(not _is_term(part) for part in candidates):
        return None
    terms = tuple(normalise(part) for part in candidates)
    if any(not term for term in terms):
        return None
    return terms


def _is_term(part: str) -> bool:
    """Whether one entry is a search term rather than a fragment of a sentence."""
    return bool(part) and not _PROSE.search(part) and len(part.split()) <= MAX_TERM_WORDS


def _delisted(text: str) -> str:
    """A bracketed list, unwrapped. Anything else, untouched."""
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1]
    return text


def _unornamented(part: str) -> str:
    """One entry without the bullets, numbering and quotation a model adds."""
    return _ORNAMENT.sub("", part.strip())


# --------------------------------------------------------------------------
# What a caller is told when there is nothing to describe
# --------------------------------------------------------------------------

NO_DESCRIBABLE_SOURCE = (
    "this asset has no concept view to describe; facts about a mesh come from "
    "mesh inspection, and a mesh is never rendered in order to describe it"
)
"""Why generation declined. `derived-metadata`'s *"Generation targets images only"*.

The sentence lives here rather than in a use case because four surfaces print
it, and because the reason is a rule — `MeshFacts` are facts and a description
is a guess — rather than an implementation limit somebody might lift.
"""


@dataclass(frozen=True)
class Generation:
    """What one generation run produced, and whether the model was called at all.

    `reused` is the whole of D5's *"an unchanged image is not regenerated"*: the
    record is the same either way, and the caller that wants to know whether it
    paid for it asks this rather than comparing timestamps.
    """

    record: DerivedRecord
    reused: bool = False
    suggestions: tuple[Suggestion, ...] = field(default_factory=tuple)

    @property
    def source_hash(self) -> str:
        return self.record.source_hash

    @property
    def pending(self) -> tuple[str, ...]:
        return tuple(entry.value for entry in self.suggestions if entry.is_pending)


__all__ = [
    "ALIAS_PATTERN",
    "GENERATED",
    "GENERATED_NOTICE",
    "MAX_ALIAS_LENGTH",
    "MAX_SUGGESTIONS",
    "MAX_TERM_WORDS",
    "NO_DESCRIBABLE_SOURCE",
    "SUGGESTION_NOTICE",
    "DerivedRecord",
    "Generation",
    "Provenance",
    "Suggestion",
    "SuggestionDecision",
    "SuggestionState",
    "accepted_decision",
    "decided",
    "excluded_terms",
    "is_normalised",
    "normalise",
    "normalised_aliases",
    "parse_aliases",
    "pending",
    "rejected_decision",
    "suggestions_by_asset",
]
