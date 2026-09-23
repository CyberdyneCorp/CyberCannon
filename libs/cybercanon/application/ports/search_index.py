"""The `SearchIndex` port — the rebuildable lookup over the repository (D7).

The index is **derived and disposable**: git is the source of truth, so deleting
this and re-scanning the specification files is always a valid recovery, and
nothing here is ever the place a fact originates. That is why the port's write
side is a single `upsert` — there is no partial edit, because there is no
authoring.

Seven questions, which is exactly what `asset-lookup` asks for:

* **upsert** one asset's indexed row;
* **get** an asset by identifier;
* **list** a project's assets, filtered by status, owner or tag;
* **search** a term, ranked by the fixed cascade of D9;
* **record** a query that matched nothing, and **list** those misses (D11);
* **check staleness** of one row against the file it was built from (D8).

**Ranking is defined once, here, as data.** :class:`MatchKind` declares the six
passes in the order the specification fixes — exact identifier, name prefix,
alias, tag, description substring, and last of all an unaccepted suggested alias
— and :func:`rank` is the pure function every implementation sorts with. An
in-memory fake and a SQLite adapter that each invented their own ordering would
be two search engines, and the conformance suite would be the only thing that
noticed.

`IndexedAsset` carries two fields the domain `Asset` does not have — `tags` and
`description`. That is deliberate and it is the boundary `project.md` draws:
derived metadata lives in the rebuildable index keyed by content, never in
`asset.yaml` and never in the compiled briefing.

**`add-derived-metadata` put the generated half here rather than in a store of
its own**, because that boundary is exactly where the specification puts it:
generated descriptions, tags and suggested aliases live *in the rebuildable
index*, keyed by the content hash of the image they came from, and the sixth
ranking pass has to join them to a row anyway. Six methods carry it — store a
record, read one by its image, list them, record a person's decision about one
suggested value, read those decisions, and drop the lot. Nothing about them is
authoritative: :meth:`SearchIndex.clear_derived` is a supported operation with
no recovery step, because there is nothing to recover.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from cybercanon.domain.derived import (
    SUGGESTION_NOTICE,
    DerivedRecord,
    SuggestionDecision,
    suggestions_by_asset,
)

ABSENT = "not recorded"
"""What an unrecorded location reads as. `asset-lookup` forbids omitting it."""


class MatchKind(Enum):
    """Why a term matched, in the exact order the ranking cascade runs (D9).

    Declaration order *is* the ranking, so `list(MatchKind)` is the cascade and
    there is no second place to change it. A relevance score was rejected: it
    would need tuning, and its results would move under people for reasons
    nobody could explain.
    """

    EXACT_ID = "exact_id"
    NAME_PREFIX = "name_prefix"
    ALIAS = "alias"
    TAG = "tag"
    DESCRIPTION = "description"
    SUGGESTED_ALIAS = "suggested_alias"

    @property
    def pass_number(self) -> int:
        """Which pass of the cascade this is — 0 is the strongest."""
        return CASCADE.index(self)

    @property
    def is_suggestion(self) -> bool:
        """Whether this pass matched on something no person has accepted (D9)."""
        return self is MatchKind.SUGGESTED_ALIAS


CASCADE: tuple[MatchKind, ...] = tuple(MatchKind)
"""The six passes, in order. The whole ranking rule, as data.

The sixth arrived with `add-derived-metadata` and is deliberately **last and
disclosed** (D9): an unaccepted suggestion is the system guessing, so it may
rescue a search that would otherwise return nothing — which is the entire point
of suggesting aliases at all — and it may never quietly outrank something a
person wrote. `derived-metadata`: *"a suggested alias SHALL be usable only as a
lowest-priority fallback, and any result it produces SHALL be marked as matched
on an unaccepted suggestion"*.
"""


@dataclass(frozen=True)
class FileFingerprint:
    """What a specification file looked like when it was indexed (D8).

    Size and modification time rather than a content hash: the read path checks
    this on every lookup, so it must cost one stat call. A hash is what the
    rebuild compares, and a rebuild is a command.
    """

    path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class IndexedAsset:
    """One asset as the index holds it — everything a lookup answers from.

    Every location is optional and ``None`` means *not recorded*, which the
    renderer states rather than omits: an answer that silently drops the engine
    path is indistinguishable from one that says there is none.

    **A generated description or tag never lands in `tags` or `description`,
    and that is deliberate.** Those two are the fourth and fifth passes of the
    cascade, above the sixth; a generated term written into them would rank as
    though a person had authored it and would match with no disclosure, which
    is exactly what D9 grants one extra, flagged pass in order to avoid. A
    derived record's own description and tags stay in the derived row, where
    they are presented and never ranked. `upsert` writes what `asset.yaml`
    says; nothing else has a way in.
    """

    asset_id: str
    name: str
    project: str = ""
    status: str | None = None
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    description: str = ""
    spec_path: str = ""
    directory: str = ""
    source_file: str | None = None
    engine_path: str | None = None
    discussion: str | None = None
    design_doc: str | None = None
    owner_art: str | None = None
    owner_design: str | None = None
    owner_code: str | None = None
    validated_export: str | None = None
    validated_at: str | None = None
    fingerprint: FileFingerprint | None = None

    @property
    def owners(self) -> tuple[str | None, str | None, str | None]:
        """The three owners, in the order every surface names them."""
        return (self.owner_art, self.owner_design, self.owner_code)

    def owned_by(self, owner: str) -> bool:
        """Whether this person is any of the three owners, compared case-insensitively."""
        wanted = owner.strip().lower()
        return any(held and held.strip().lower() == wanted for held in self.owners)


@dataclass(frozen=True)
class SearchHit:
    """One result and the pass that found it, so ranking stays inspectable."""

    entry: IndexedAsset
    kind: MatchKind
    matched: str = ""
    """The suggested term this hit came from, for the sixth pass only.

    Empty for every other pass, because every other pass matched on something
    the row already carries and a reader can see. A suggestion is not in the
    specification, so the disclosure has to name it.
    """

    @property
    def asset_id(self) -> str:
        return self.entry.asset_id

    @property
    def is_suggestion(self) -> bool:
        """Whether a person still has to accept what produced this result (D9)."""
        return self.kind.is_suggestion

    @property
    def notice(self) -> str:
        """The disclosure a surface prints beside this result, or nothing."""
        if not self.is_suggestion:
            return ""
        return f"{SUGGESTION_NOTICE}: {self.matched}" if self.matched else SUGGESTION_NOTICE


@dataclass(frozen=True)
class RecordedMiss:
    """A search term that matched nothing, and how often (D11).

    Never leaves the machine. The value is somebody reading the list and
    deciding which aliases to add; shipping it anywhere would buy a privacy
    conversation and nothing else.
    """

    term: str
    project: str = ""
    count: int = 1


NO_SUGGESTIONS: Mapping[str, tuple[str, ...]] = {}
"""What ranking is given when no derived row has anything to offer.

The default rather than ``None`` so that the sixth pass is *always* run and
simply matches nothing — a pass that exists only when a caller remembers to pass
an argument is a pass two implementations would disagree about.
"""


def match_kind(entry: IndexedAsset, term: str, suggested: tuple[str, ...] = ()) -> MatchKind | None:
    """The strongest pass that matches this entry, or ``None`` when none does.

    One definition, shared by every implementation. Comparison is
    case-insensitive throughout, because a person searching for `Mech_Scout`
    means the asset called `mech_scout`.

    `suggested` is this asset's **pending** suggested aliases — the ones no
    person has accepted or rejected — and it is checked last, after every pass
    over authored content has failed. An accepted suggestion is not here: it is
    an alias in the specification by then, and it matches on the third pass like
    any other.
    """
    wanted = term.strip().lower()
    if not wanted:
        return None
    if entry.asset_id.lower() == wanted:
        return MatchKind.EXACT_ID
    if entry.name.lower().startswith(wanted):
        return MatchKind.NAME_PREFIX
    if _contains(entry.aliases, wanted):
        return MatchKind.ALIAS
    if _contains(entry.tags, wanted):
        return MatchKind.TAG
    if wanted in entry.description.lower():
        return MatchKind.DESCRIPTION
    if _contains(suggested, wanted):
        return MatchKind.SUGGESTED_ALIAS
    return None


def rank(
    entries: Iterable[IndexedAsset],
    term: str,
    suggestions: Mapping[str, tuple[str, ...]] = NO_SUGGESTIONS,
) -> tuple[SearchHit, ...]:
    """Every matching entry, strongest pass first and by identifier within it.

    Deterministic by construction: two runs over the same rows return the same
    order, and an entry matched by two passes appears once, under the stronger.

    `suggestions` maps an asset identifier to its pending suggested aliases, and
    is how the sixth pass reaches rows whose derived content is stored beside
    them rather than in them. It is an argument rather than a field on
    :class:`IndexedAsset` on purpose: the row is a projection of `asset.yaml`,
    and a member on it that `upsert` could write would be a door for generated
    content into the thing the index rebuilds *from*.
    """
    hits = [
        SearchHit(entry=entry, kind=kind, matched=_disclosed(kind, term))
        for entry in entries
        if (kind := match_kind(entry, term, suggestions.get(entry.asset_id, ()))) is not None
    ]
    return tuple(sorted(hits, key=lambda hit: (hit.kind.pass_number, hit.asset_id)))


def _disclosed(kind: MatchKind, term: str) -> str:
    """What the sixth pass matched on, so the result can say so. Nothing otherwise."""
    return term.strip().lower() if kind.is_suggestion else ""


def suggesting(suggestions: Mapping[str, tuple[str, ...]], term: str) -> tuple[str, ...]:
    """The asset identifiers whose pending suggestions carry this term.

    What a store narrowing by full text needs before it ranks: a suggestion is
    not in the indexed row, so a candidate set built only from the row would
    never include the asset the sixth pass exists to rescue.
    """
    wanted = term.strip().lower()
    if not wanted:
        return ()
    return tuple(
        sorted(asset_id for asset_id, values in suggestions.items() if _contains(values, wanted))
    )


def pending_suggestions(
    records: Iterable[DerivedRecord], decisions: Iterable[SuggestionDecision]
) -> Mapping[str, tuple[str, ...]]:
    """Every asset's pending suggested aliases, from its rows and their decisions.

    A thin name over :func:`~cybercanon.domain.derived.suggestions_by_asset`, so
    a store composes the sixth pass from the domain's own join rather than
    writing a third one in SQL.
    """
    return suggestions_by_asset(records, decisions)


def _contains(values: tuple[str, ...], wanted: str) -> bool:
    return any(value.strip().lower() == wanted for value in values)


LIST_SEPARATOR = "\n"
"""How an ordered list of aliases or tags becomes one stored value.

Here for the same reason :func:`rank` is here. A store that packs a list its own
way is free to unpack it its own way too, and the day SQLite and PostgreSQL
disagree about whether a tag may contain a comma is the day two adapters answer
one filter differently. The separator is a newline because no tag or alias a
person authors contains one.
"""


def joined(values: tuple[str, ...]) -> str:
    """An ordered list of aliases or tags as one stored value."""
    return LIST_SEPARATOR.join(values)


def unjoined(stored: str) -> tuple[str, ...]:
    """That stored value back as the list it was, empty for an empty column."""
    return tuple(stored.split(LIST_SEPARATOR)) if stored else ()


def tags_key(tags: tuple[str, ...]) -> str:
    """The tags in comparison form, delimited so a filter matches whole tags only.

    `vehicle` never matches an asset tagged `vehicles`, in every store, because
    the delimiters are part of the stored form rather than part of a query
    somebody wrote twice.
    """
    if not tags:
        return ""
    inner = LIST_SEPARATOR.join(tag.strip().lower() for tag in tags)
    return f"{LIST_SEPARATOR}{inner}{LIST_SEPARATOR}"


def tag_needle(tag: str) -> str:
    """What a tag filter looks for inside :func:`tags_key`."""
    return f"{LIST_SEPARATOR}{tag.strip().lower()}{LIST_SEPARATOR}"


def searchable_text(entry: IndexedAsset) -> str:
    """Every searchable field of one row, lower-cased, for the substring pass.

    The substring pass exists because two of the five passes are defined as
    substrings — a name *prefix* and a description *substring* — and no token
    index expresses either. It narrows; :func:`rank` still decides.
    """
    fields = (
        entry.asset_id,
        entry.name,
        joined(entry.aliases),
        joined(entry.tags),
        entry.description,
    )
    return LIST_SEPARATOR.join(fields).lower()


class SearchIndex(Protocol):
    """The derived, rebuildable lookup over a project's specification files."""

    def upsert(self, entry: IndexedAsset) -> None:
        """Write one asset's row, replacing whatever was there for that id."""
        ...

    def get(self, asset_id: str, project: str | None = None) -> IndexedAsset | None:
        """The row for that identifier, or ``None`` when nothing is indexed for it."""
        ...

    def list_assets(
        self,
        project: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
    ) -> tuple[IndexedAsset, ...]:
        """The project's assets matching every filter given, ordered by identifier."""
        ...

    def search(self, term: str, project: str | None = None) -> tuple[SearchHit, ...]:
        """The ranked cascade of D9 — see :func:`rank`, which defines the order."""
        ...

    def record_miss(self, term: str, project: str | None = None) -> None:
        """Record a term that matched nothing. Local only, never transmitted."""
        ...

    def misses(self, project: str | None = None) -> tuple[RecordedMiss, ...]:
        """Every recorded miss, ordered by term, with how often each was asked."""
        ...

    def is_stale(self, asset_id: str, current: FileFingerprint | None) -> bool:
        """Whether the row for that asset no longer matches the file on disk (D8).

        An unindexed asset and a file that has disappeared are both stale: the
        point of the check is *may this row be served as current*, and the
        answer for a row that is not there is no.
        """
        ...

    def forget(self, asset_id: str, project: str | None = None) -> None:
        """Drop one row — a specification that was deleted or renamed."""
        ...

    def clear(self) -> None:
        """Drop everything. The index is disposable by specification."""
        ...

    # -- derived metadata (add-derived-metadata, D5 and D6) ---------------

    def put_derived(self, record: DerivedRecord, project: str = "") -> None:
        """Store one derived record, replacing whatever was held for its image.

        Keyed by the record's **source content hash** and by nothing else (D5),
        so regenerating an unchanged image lands on the row that is already
        there and a replaced image gets its own. Nothing here is authored
        content: dropping every one of these rows loses no project information,
        which is what `derived-metadata`'s *"derived content is disposable"*
        requires and what makes storing it in the index correct in the first
        place.
        """
        ...

    def derived(self, source_hash: str, project: str | None = None) -> DerivedRecord | None:
        """The record generated from those bytes, or ``None`` when there is none."""
        ...

    def derived_records(
        self, project: str | None = None, asset_id: str | None = None
    ) -> tuple[DerivedRecord, ...]:
        """Every derived record, narrowed to a project or an asset, ordered by hash."""
        ...

    def record_decision(self, decision: SuggestionDecision, project: str = "") -> None:
        """Record that a person accepted or rejected one suggested value (D6).

        Keyed by `(source hash, value)`, so a rejection survives the derived row
        being regenerated from the same unchanged image — which is exactly what
        `metadata-acceptance` requires and what keying on the asset would undo
        the first time the row was rebuilt.
        """
        ...

    def decisions(
        self, source_hash: str | None = None, project: str | None = None
    ) -> tuple[SuggestionDecision, ...]:
        """Every recorded acceptance and rejection, narrowed to one image or not."""
        ...

    def clear_derived(self, project: str | None = None) -> None:
        """Drop every derived record and every decision about one.

        Separate from :meth:`clear` because the two answer different questions:
        `clear` empties the whole index and a rebuild restores it, while this
        empties only the generated half — and `derived-metadata` requires that
        doing so loses nothing, because the accepted values are in the
        specification files and the index was never where they lived.
        """
        ...


def stale_paths(
    entries: Iterable[IndexedAsset], current: Mapping[str, FileFingerprint]
) -> tuple[str, ...]:
    """The specification paths whose rows no longer match the files on disk.

    A helper for the rebuild path, kept beside the port so the fake and the
    SQLite adapter answer the staleness question the same way.
    """
    return tuple(
        sorted(
            entry.spec_path
            for entry in entries
            if entry.fingerprint != current.get(entry.spec_path)
        )
    )


__all__ = [
    "ABSENT",
    "CASCADE",
    "LIST_SEPARATOR",
    "NO_SUGGESTIONS",
    "FileFingerprint",
    "IndexedAsset",
    "MatchKind",
    "RecordedMiss",
    "SearchHit",
    "SearchIndex",
    "joined",
    "match_kind",
    "pending_suggestions",
    "rank",
    "searchable_text",
    "stale_paths",
    "suggesting",
    "tag_needle",
    "tags_key",
    "unjoined",
]
