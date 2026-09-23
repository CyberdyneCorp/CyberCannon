"""Linked long-form documents: the reference, its display state, and the boundary.

CyberCanon does not host prose. A design document lives on a document platform
that owns its body, its history and its comments, and what this product keeps is
a **reference** — authored content in the repository, versioned beside the asset
it explains (D1).

Four things are decided here and nowhere else (D11):

* **What a reference is.** :class:`DocumentRef` is a frozen value object with
  well-formedness rules, so a malformed one is a reported violation rather than
  a link that fails mysteriously at the moment somebody clicks it.
* **What a failure to resolve one means.** :class:`DocumentState` is a closed
  set of four: readable, unreachable, missing, forbidden. Collapsing the last
  three into "broken" is exactly the behaviour the specification forbids —
  *"the system SHALL distinguish, for each link it fails to resolve, whether the
  document platform was unavailable, the document no longer exists, or the
  viewer is not permitted to see it"*.
* **That a forbidden card discloses nothing.** :class:`DocumentCard` clears its
  own title and summary when its state is `FORBIDDEN`, so the rule holds
  *regardless of how the card was constructed* rather than because every
  construction site remembered it.
* **Where a statement belongs.** :func:`placement_of` is the golden rule as a
  pure predicate: a statement that constrains art, constrains code or is
  checkable belongs in the specification; everything else is rationale and
  belongs in the document.

There is deliberately **no field, no parameter and no function here that could
carry a document's body** (D9). The arrow points one way: a reference goes out,
a title and a short summary come back for display, and nothing a document says
ever becomes a specification field.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from itertools import pairwise, takewhile

SUMMARY_MAX_CHARS = 400
"""How much of a summary is *"a short summary of at most a few lines"*.

A ceiling rather than a target: the platform decides what a summary says, and
this is the point past which a display cache would be holding the document.
"""

ALLOWED_SCHEMES = ("https://", "http://")
"""What an address may begin with. A link is something a browser can open."""


class DocumentState(Enum):
    """Why a reference does or does not read, as a closed set of four.

    `UNREACHABLE`, `MISSING` and `FORBIDDEN` are three different sentences to
    the person looking at the link — *come back later*, *somebody deleted it*,
    *ask for access* — and a surface that showed one message for all three would
    be telling two thirds of its viewers something false.
    """

    READABLE = "readable"
    UNREACHABLE = "unreachable"
    MISSING = "missing"
    FORBIDDEN = "forbidden"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @property
    def is_resolved(self) -> bool:
        return self is DocumentState.READABLE

    def __str__(self) -> str:
        return self.value


class DocumentScope(Enum):
    """Whether a link was authored on one asset or on the project as a whole."""

    ASSET = "asset"
    PROJECT = "project"

    def __str__(self) -> str:
        return self.value


class ResultProvenance(Enum):
    """Where a search result came from: an exact index, or an approximate one.

    Deliberately **not** ordered and deliberately carrying **no score** (D6).
    `semantic-search-delegation` requires that no ordering value rank a semantic
    result against an exact one, and the cheapest way to satisfy that
    permanently is for the comparison to be unwritable — there is nothing here
    to compare with.
    """

    EXACT = "exact"
    SEMANTIC = "semantic"

    def __str__(self) -> str:
        return self.value


PROVENANCE_ORDER: tuple[ResultProvenance, ...] = (
    ResultProvenance.EXACT,
    ResultProvenance.SEMANTIC,
)
"""The order the two groups are presented in. Between groups, never within one."""


class MalformedReference(ValueError):
    """A document reference that is not well formed, said in one sentence."""


class ContentPlacement(Enum):
    """The two non-overlapping homes a statement can have."""

    SPECIFICATION = "specification"
    DOCUMENT = "document"

    def __str__(self) -> str:
        return self.value


PLACEMENT_GUIDANCE = (
    "A statement that constrains art, constrains code, or can be checked by the "
    "validator belongs in the asset's specification. Rationale, exploration and "
    "discussion belong in the linked document."
)
"""What a person is told at the point they choose where to write something.

It names both destinations in one sentence, which is the whole of the
requirement: *"the system SHALL state that constraining or checkable statements
belong in the specification and that rationale belongs in the document"*.
"""

CONSTRAINING_TERMS = (
    "budget",
    "triangle",
    "triangles",
    "tris",
    "socket",
    "sockets",
    "bone",
    "bones",
    "lod",
    "pivot",
    "up axis",
    "up_axis",
    "unit scale",
    "unit_scale",
    "clip",
    "naming",
    "texel",
    "texture",
    "frame rate",
    "frame_rate",
    "collider",
)
"""Vocabulary that names something the validator can check.

A deliberately small, inspectable list rather than a model (the same reasoning
as D7's routing gate): a person must be able to say why a sentence was
classified the way it was, and a classifier nobody can explain would make the
golden rule feel arbitrary the first time it disagreed with somebody.
"""

MEASURED_UNITS = ("m", "cm", "mm", "px", "k", "fps", "hz", "%", "kb", "mb")
"""Units that turn a number in a sentence into a measurement."""


def placement_of(statement: str) -> ContentPlacement:
    """Where this statement belongs — the golden rule, as a pure predicate.

    Two things make a statement specification content: it *names* something the
    validator knows how to check, or it states a *measured quantity*. Everything
    else is rationale. The predicate is total and never raises: an empty string
    is rationale, because nothing about it constrains anything.
    """
    text = statement.strip().lower()
    if not text:
        return ContentPlacement.DOCUMENT
    if _names_a_constraint(text) or _states_a_measurement(text):
        return ContentPlacement.SPECIFICATION
    return ContentPlacement.DOCUMENT


def constrains_or_is_checkable(statement: str) -> bool:
    """Whether this statement constrains art, constrains code, or is checkable."""
    return placement_of(statement) is ContentPlacement.SPECIFICATION


def _names_a_constraint(text: str) -> bool:
    return any(term in text for term in CONSTRAINING_TERMS)


def _states_a_measurement(text: str) -> bool:
    """A number carrying a unit — `25 m`, `2048px`, `12000 tris`, joined or not."""
    words = [word.strip(".,:;()") for word in text.split()]
    joined = any(_unit_after_number(word) for word in words)
    separate = any(
        _is_number(number) and unit in MEASURED_UNITS for number, unit in pairwise(words)
    )
    return joined or separate


def _unit_after_number(word: str) -> bool:
    """`2048px` — digits and then a unit, with nothing between them."""
    digits = "".join(takewhile(str.isdigit, word))
    return bool(digits) and word[len(digits) :] in MEASURED_UNITS


def _is_number(word: str) -> bool:
    return bool(word) and word.replace(".", "", 1).isdigit()


# --------------------------------------------------------------------------
# The reference — authored content, in the repository (D1)
# --------------------------------------------------------------------------


def reference_problem(workspace: str, document_id: str, url: str) -> str | None:
    """Why this would not be a well-formed reference, or ``None`` when it is.

    A function beside the value object rather than only inside it, because the
    caller that needs the answer most is the *parser*: a specification file
    holding a broken reference must still load, with the reference reported by
    name (`asset-spec`'s tolerance rule), and a constructor that raised would
    deny the artist every other finding in the same run.
    """
    for name, value in (("workspace", workspace), ("document id", document_id)):
        if not value or value.strip() != value or any(c.isspace() for c in value):
            return f"its {name} is empty or contains whitespace"
    if not url or url.strip() != url or any(c.isspace() for c in url):
        return "its address is empty or contains whitespace"
    if not url.startswith(ALLOWED_SCHEMES):
        return f"its address does not begin with {' or '.join(ALLOWED_SCHEMES)}"
    return None


@dataclass(frozen=True)
class DocumentRef:
    """One link, exactly as the repository holds it (D1).

    Five members and no sixth: the workspace and the identifier name the
    document, the address opens it, and the two authorship members are what
    makes the link attributable like every other authored change. There is no
    `title` here **on purpose** — a title resolved from the platform is cache,
    and writing it beside the address would make the repository wrong the
    moment somebody renamed the document.
    """

    workspace: str
    document_id: str
    url: str
    linked_by: str = ""
    linked_at: str = ""

    def __post_init__(self) -> None:
        problem = reference_problem(self.workspace, self.document_id, self.url)
        if problem is not None:
            raise MalformedReference(
                f"document reference {self.document_id!r} is not well formed: {problem}"
            )

    @property
    def key(self) -> tuple[str, str]:
        """What identifies the document, independent of how it is addressed."""
        return (self.workspace, self.document_id)

    def attributed(self, linked_by: str, linked_at: str) -> DocumentRef:
        """The same reference, authored by this person at this moment."""
        return DocumentRef(
            workspace=self.workspace,
            document_id=self.document_id,
            url=self.url,
            linked_by=linked_by,
            linked_at=linked_at,
        )


def ordered_refs(refs: Iterable[DocumentRef]) -> tuple[DocumentRef, ...]:
    """References in the one order every listing uses — authored order, de-duplicated.

    Deterministic *without* sorting: the order the specification file declares
    them in is the order a person wrote them in, and re-ordering somebody's file
    for them is the kind of helpfulness that shows up as noise in a diff.
    """
    seen: set[tuple[str, str]] = set()
    kept: list[DocumentRef] = []
    for ref in refs:
        if ref.key in seen:
            continue
        seen.add(ref.key)
        kept.append(ref)
    return tuple(kept)


def without_document(refs: Iterable[DocumentRef], document_id: str) -> tuple[DocumentRef, ...]:
    """Every reference but the one naming that document."""
    return tuple(ref for ref in refs if ref.document_id != document_id)


def find_document(refs: Iterable[DocumentRef], document_id: str) -> DocumentRef | None:
    """The reference naming that document, or ``None``."""
    return next((ref for ref in refs if ref.document_id == document_id), None)


# --------------------------------------------------------------------------
# The card — display cache, and never anything else (D1)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentCard:
    """What a reference looks like right now, to one viewer.

    Held only in rebuildable storage and reconstructible by asking the platform
    again, which is why it carries `resolved_at`: a card is an observation with
    a time on it, not a fact about the repository.

    **A forbidden card discloses nothing**, and that is enforced here rather
    than asked of callers: whatever title or summary is passed in is dropped on
    construction, so there is no way to build one that leaks.
    """

    ref: DocumentRef
    title: str = ""
    summary: str = ""
    state: DocumentState = DocumentState.READABLE
    resolved_at: str = ""

    def __post_init__(self) -> None:
        if self.state is DocumentState.FORBIDDEN:
            object.__setattr__(self, "title", "")
            object.__setattr__(self, "summary", "")
            return
        object.__setattr__(self, "summary", self.summary[:SUMMARY_MAX_CHARS])

    @property
    def address(self) -> str:
        """Where this document is opened. Present in every state."""
        return self.ref.url

    @property
    def is_resolved(self) -> bool:
        return self.state.is_resolved and bool(self.title)

    @property
    def display_title(self) -> str:
        """The title when there is one, otherwise the address (D1's accepted cost)."""
        return self.title if self.is_resolved else self.ref.url

    @property
    def discloses_nothing(self) -> bool:
        """Whether this card carries no content of the document at all."""
        return not self.title and not self.summary


def unresolved_card(ref: DocumentRef, state: DocumentState) -> DocumentCard:
    """A card for a reference that could not be read, in the state that says why."""
    return DocumentCard(ref=ref, state=state)


@dataclass(frozen=True)
class LinkedDocument:
    """One entry of an asset's link list: the reference, its scope and its card.

    The scope travels with the entry because the specification requires it —
    *"each entry SHALL state which scope it came from"* — and because a
    project-scoped link cannot be removed from an asset's own file, so a surface
    has to know which one it is looking at before it offers an action.
    """

    ref: DocumentRef
    scope: DocumentScope
    card: DocumentCard

    @property
    def state(self) -> DocumentState:
        return self.card.state

    @property
    def address(self) -> str:
        return self.ref.url

    @property
    def is_resolved(self) -> bool:
        return self.card.is_resolved


def linked_documents(
    asset_refs: Sequence[DocumentRef],
    project_refs: Sequence[DocumentRef],
    cards: dict[tuple[str, str], DocumentCard],
) -> tuple[LinkedDocument, ...]:
    """The two scopes as one deterministic list — asset links first, then project.

    The order is fixed by construction rather than by a sort key, so *"both
    listings SHALL contain the same links in the same order"* is a property of
    the function instead of a promise about a comparator.
    """
    return tuple(
        LinkedDocument(
            ref=ref,
            scope=scope,
            card=cards.get(ref.key) or unresolved_card(ref, DocumentState.UNREACHABLE),
        )
        for scope, refs in (
            (DocumentScope.ASSET, ordered_refs(asset_refs)),
            (DocumentScope.PROJECT, ordered_refs(project_refs)),
        )
        for ref in refs
    )


# --------------------------------------------------------------------------
# Version history — read through the platform, never copied (the M4 rule)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentRevision:
    """One entry of a linked document's history, as the platform reports it.

    Metadata only, and that is the entire point: an identifier, its position in
    the series, when it was taken and what it is called. A body is not a member
    here and cannot become one without widening the port, which is D9 applied to
    history as well as to content — CyberCanon links to the document platform's
    version history, it does not keep a second one.
    """

    id: str
    seq: int = 0
    created_at: str = ""
    label: str = ""

    @property
    def name(self) -> str:
        """What a list shows: the label the author gave it, or its position."""
        return self.label or f"revision {self.seq}"


@dataclass(frozen=True)
class DocumentHistory:
    """A linked document's revisions, newest first, with where they are read."""

    ref: DocumentRef
    revisions: tuple[DocumentRevision, ...] = ()
    state: DocumentState = DocumentState.READABLE

    @property
    def is_readable(self) -> bool:
        return self.state.is_resolved

    @property
    def size(self) -> int:
        return len(self.revisions)


def newest_first(revisions: Iterable[DocumentRevision]) -> tuple[DocumentRevision, ...]:
    """The series as a reader reads it: the most recent revision at the top."""
    return tuple(sorted(revisions, key=lambda revision: revision.seq, reverse=True))


# --------------------------------------------------------------------------
# Provenance grouping (D6) — groups, never a merge
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProvenanceGroup[T]:
    """One presented group of results, labelled by where they came from."""

    provenance: ResultProvenance
    results: tuple[T, ...] = field(default_factory=tuple)

    @property
    def is_approximate(self) -> bool:
        """Whether this group has to be labelled as approximate when shown."""
        return self.provenance is ResultProvenance.SEMANTIC

    @property
    def size(self) -> int:
        return len(self.results)


def grouped_by_provenance[T](
    exact: Sequence[T],
    semantic: Sequence[T],
) -> tuple[ProvenanceGroup[T], ...]:
    """Exact results, then semantic ones, as two groups that are never merged.

    Both groups are always present, empty or not: a response that dropped the
    semantic group when it was empty would be indistinguishable from one that
    never asked, and *"the reported reason is the distinguishing one"* needs
    somewhere to hang.
    """
    by_provenance = {ResultProvenance.EXACT: exact, ResultProvenance.SEMANTIC: semantic}
    return tuple(
        ProvenanceGroup(provenance=provenance, results=tuple(by_provenance[provenance]))
        for provenance in PROVENANCE_ORDER
    )


__all__ = [
    "ALLOWED_SCHEMES",
    "CONSTRAINING_TERMS",
    "PLACEMENT_GUIDANCE",
    "PROVENANCE_ORDER",
    "SUMMARY_MAX_CHARS",
    "ContentPlacement",
    "DocumentCard",
    "DocumentHistory",
    "DocumentRef",
    "DocumentRevision",
    "DocumentScope",
    "DocumentState",
    "LinkedDocument",
    "MalformedReference",
    "ProvenanceGroup",
    "ResultProvenance",
    "constrains_or_is_checkable",
    "find_document",
    "grouped_by_provenance",
    "linked_documents",
    "newest_first",
    "ordered_refs",
    "placement_of",
    "reference_problem",
    "unresolved_card",
    "without_document",
]
