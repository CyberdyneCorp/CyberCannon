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

**Ranking is defined once, here, as data.** :class:`MatchKind` declares the five
passes in the order the specification fixes — exact identifier, name prefix,
alias, tag, description substring — and :func:`rank` is the pure function every
implementation sorts with. An in-memory fake and a SQLite adapter that each
invented their own ordering would be two search engines, and the conformance
suite would be the only thing that noticed.

`IndexedAsset` carries two fields the domain `Asset` does not have — `tags` and
`description`. That is deliberate and it is the boundary `project.md` draws:
derived metadata lives in the rebuildable index keyed by content, never in
`asset.yaml` and never in the compiled briefing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

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

    @property
    def pass_number(self) -> int:
        """Which pass of the cascade this is — 0 is the strongest."""
        return CASCADE.index(self)


CASCADE: tuple[MatchKind, ...] = tuple(MatchKind)
"""The five passes, in order. The whole ranking rule, as data."""


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

    @property
    def asset_id(self) -> str:
        return self.entry.asset_id


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


def match_kind(entry: IndexedAsset, term: str) -> MatchKind | None:
    """The strongest pass that matches this entry, or ``None`` when none does.

    One definition, shared by every implementation. Comparison is
    case-insensitive throughout, because a person searching for `Mech_Scout`
    means the asset called `mech_scout`.
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
    return None


def rank(entries: Iterable[IndexedAsset], term: str) -> tuple[SearchHit, ...]:
    """Every matching entry, strongest pass first and by identifier within it.

    Deterministic by construction: two runs over the same rows return the same
    order, and an entry matched by two passes appears once, under the stronger.
    """
    hits = [
        SearchHit(entry=entry, kind=kind)
        for entry in entries
        if (kind := match_kind(entry, term)) is not None
    ]
    return tuple(sorted(hits, key=lambda hit: (hit.kind.pass_number, hit.asset_id)))


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
    "FileFingerprint",
    "IndexedAsset",
    "MatchKind",
    "RecordedMiss",
    "SearchHit",
    "SearchIndex",
    "joined",
    "match_kind",
    "rank",
    "searchable_text",
    "stale_paths",
    "tag_needle",
    "tags_key",
    "unjoined",
]
