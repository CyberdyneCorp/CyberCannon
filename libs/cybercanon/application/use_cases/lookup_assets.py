"""`where_is`, `list_assets` and `search_assets` — the questions that started this.

A developer does not know where the concept, the `.blend`, the export or the
engine path for an asset live. These three use cases answer that from the
derived index, and the shapes they return are deliberately structural rather
than prose: an inbound adapter renders them (D1 keeps the MCP adapter a
formatter), and two surfaces rendering the same values cannot disagree about
what the answer was.

Three properties the specification fixes, and they are all mechanical here:

* **An unrecorded location is reported, never omitted** — every location is a
  :class:`Location`, and one with no value still renders, as
  :data:`~cybercanon.application.ports.search_index.ABSENT`. An answer that
  silently drops the engine path is indistinguishable from one that says there
  is none, and the second is what a reader needs.
* **Ranking is the fixed five-pass cascade of D9**, which lives once in the
  port (`exact id → name prefix → alias → tag → description substring`) and is
  applied by every implementation. Nothing here re-orders results.
* **Every name a reader sees is resolved through the project's actor mapping**
  (D12, D14). A mapped owner renders as their display name, an unmapped one as
  the raw email marked unmapped, and the same person renders identically
  wherever they appear — because all three paths go through one resolution.

Reads need no identity, no network and no services: the only collaborators are
the specification store and the index, and both are local.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.search_index import (
    ABSENT,
    IndexedAsset,
    RecordedMiss,
    SearchHit,
    SearchIndex,
)
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.use_cases.index_assets import (
    Fingerprinter,
    current_entry,
    no_fingerprints,
)
from cybercanon.domain.actors import ActorMapping, resolve_git_author
from cybercanon.domain.identity import Actor

DIRECTORY = "directory"
SOURCE_FILE = "source file"
VALIDATED_EXPORT = "latest validated export"
VALIDATED_AT = "validated"
ENGINE_PATH = "engine path"
DISCUSSION = "discussion"
DESIGN_DOCUMENT = "design document"

LOCATION_LABELS: tuple[str, ...] = (
    DIRECTORY,
    SOURCE_FILE,
    VALIDATED_EXPORT,
    VALIDATED_AT,
    ENGINE_PATH,
    DISCUSSION,
    DESIGN_DOCUMENT,
)
"""Every location a location answer carries, in the order it presents them.

The list is fixed so that the answer's *shape* does not depend on what the
specification happens to record: an asset with no engine path produces the same
seven entries as one with every link, and one of them says the path is not
recorded.
"""

ART = "art"
DESIGN = "design"
CODE = "code"

DISCIPLINES: tuple[str, ...] = (ART, DESIGN, CODE)
"""The three owners, in the order every surface names them."""

NEAREST_LIMIT = 5
"""How many near-misses a failed lookup offers. Enough to recognise, few enough to read."""

NEAREST_CUTOFF = 0.4
"""How alike two identifiers must be before one is offered as the other's near-miss."""

STALE_NOTICE = (
    "the indexed specification file has changed on disk and could not be re-read, "
    "so this answer may be out of date"
)


class UnknownAsset(OperationFailed):
    """Nothing is indexed for that identifier.

    A named failure rather than an empty answer: the surface that asks about an
    asset by name is expected to offer the nearest matches, and it can only do
    that if "no such asset" is distinguishable from "an asset with nothing
    recorded".
    """

    def __init__(self, asset_id: str, project: str | None = None) -> None:
        scope = f" in project {project!r}" if project else ""
        super().__init__(
            f"no asset {asset_id!r} is indexed{scope}; rebuild the index or search for it",
            asset_id,
        )


@dataclass(frozen=True)
class Location:
    """One place an asset's artifact lives, recorded or explicitly not."""

    label: str
    value: str | None = None

    @property
    def is_recorded(self) -> bool:
        return bool(self.value)

    @property
    def text(self) -> str:
        """What a reader is shown — the value, or that it is not recorded."""
        return self.value if self.value else ABSENT

    def __str__(self) -> str:
        return f"{self.label}: {self.text}"


@dataclass(frozen=True)
class OwnerPresentation:
    """One discipline's owner, resolved through the project's actor mapping.

    `recorded` is what the specification file says — an email, usually — and
    `actor` is who that is. The distinction matters for an unmapped owner: the
    raw address is still shown, because it is the evidence somebody needs to add
    the missing mapping entry.
    """

    discipline: str
    recorded: str | None = None
    actor: Actor | None = None

    @property
    def is_recorded(self) -> bool:
        return bool(self.recorded)

    @property
    def is_unmapped(self) -> bool:
        return self.actor is not None and self.actor.is_unmapped

    @property
    def display(self) -> str:
        """The person's name, the raw address marked unmapped, or *not recorded*."""
        return self.actor.display if self.actor is not None else ABSENT

    def __str__(self) -> str:
        return f"{self.discipline} owner: {self.display}"


@dataclass(frozen=True)
class LocationAnswer:
    """Where every artifact of one asset lives, plus its status and owners."""

    asset_id: str
    name: str
    status: str
    locations: tuple[Location, ...] = ()
    owners: tuple[OwnerPresentation, ...] = ()
    project: str = ""
    stale: bool = False
    notice: str = ""

    def location(self, label: str) -> Location:
        """The entry for that label. Always present — that is the point."""
        found = next((entry for entry in self.locations if entry.label == label), None)
        return found if found is not None else Location(label=label)

    def owner(self, discipline: str) -> OwnerPresentation:
        """The owner for that discipline, recorded or not."""
        found = next((entry for entry in self.owners if entry.discipline == discipline), None)
        return found if found is not None else OwnerPresentation(discipline=discipline)

    @property
    def recorded(self) -> tuple[Location, ...]:
        return tuple(entry for entry in self.locations if entry.is_recorded)

    @property
    def unrecorded(self) -> tuple[Location, ...]:
        return tuple(entry for entry in self.locations if not entry.is_recorded)


@dataclass(frozen=True)
class AssetRow:
    """One line of a listing: the indexed asset with its owners resolved."""

    entry: IndexedAsset
    owners: tuple[OwnerPresentation, ...] = ()

    @property
    def asset_id(self) -> str:
        return self.entry.asset_id

    @property
    def name(self) -> str:
        return self.entry.name

    @property
    def status(self) -> str:
        return self.entry.status or ABSENT

    def owner(self, discipline: str) -> OwnerPresentation:
        found = next((entry for entry in self.owners if entry.discipline == discipline), None)
        return found if found is not None else OwnerPresentation(discipline=discipline)


@dataclass(frozen=True)
class AssetListing:
    """A project's assets under the filters that were asked for."""

    rows: tuple[AssetRow, ...] = ()
    project: str | None = None
    status: str | None = None
    owner: str | None = None
    tag: str | None = None

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(row.asset_id for row in self.rows)

    def __len__(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class SearchAnswer:
    """What a search matched, in cascade order, and whether it was a miss (D11)."""

    term: str
    hits: tuple[SearchHit, ...] = ()
    project: str | None = None
    recorded_as_miss: bool = False

    @property
    def asset_ids(self) -> tuple[str, ...]:
        """The matched identifiers, strongest pass first."""
        return tuple(hit.asset_id for hit in self.hits)

    @property
    def is_empty(self) -> bool:
        return not self.hits

    def __len__(self) -> int:
        return len(self.hits)


def where_is(
    asset_id: str,
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    fingerprints: Fingerprinter = no_fingerprints,
    project: str | None = None,
    root: str = "",
) -> LocationAnswer:
    """Every recorded location of one asset, with the unrecorded ones named.

    The read path self-heals first (D8), so a specification edited since the
    last rebuild is answered from the file rather than from the row.
    """
    fresh = current_entry(
        asset_id,
        spec_store=spec_store,
        search_index=search_index,
        fingerprints=fingerprints,
        project=project,
    )
    entry = fresh.entry
    if entry is None:
        raise UnknownAsset(asset_id, project)
    mapping = spec_store.load_actor_mapping(root).mapping
    return LocationAnswer(
        asset_id=entry.asset_id,
        name=entry.name,
        status=entry.status or ABSENT,
        locations=locations_of(entry),
        owners=owners_of(entry, mapping),
        project=entry.project,
        stale=fresh.stale,
        notice=STALE_NOTICE if fresh.stale else "",
    )


def list_assets(
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    project: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    tag: str | None = None,
    root: str = "",
) -> AssetListing:
    """The project's assets, narrowed by every filter that was given.

    Filters combine rather than widen: asking for status `modeling` *and* an art
    owner returns the assets matching both, which is what a person asking the
    question means.
    """
    mapping = spec_store.load_actor_mapping(root).mapping
    entries = search_index.list_assets(project=project, status=status, owner=owner, tag=tag)
    return AssetListing(
        rows=tuple(AssetRow(entry=entry, owners=owners_of(entry, mapping)) for entry in entries),
        project=project,
        status=status,
        owner=owner,
        tag=tag,
    )


def search_assets(
    term: str,
    *,
    search_index: SearchIndex,
    project: str | None = None,
) -> SearchAnswer:
    """The ranked cascade of D9, with a zero-result term recorded locally (D11).

    The recording is deliberately one-sided: a term that matched is not
    interesting, and a term that matched nothing is the evidence for adding an
    alias. Nothing is transmitted anywhere — the only collaborator is the local
    index.
    """
    hits = search_index.search(term, project)
    if not hits:
        search_index.record_miss(term, project)
    return SearchAnswer(term=term, hits=hits, project=project, recorded_as_miss=not hits)


def recorded_owners(listing: AssetListing) -> tuple[str, ...]:
    """Every owner a listing records, verbatim and once, in first-seen order.

    The raw recorded value rather than the resolved display name, because this
    feeds the question *which addresses does the mapping not bind* — and an
    address already bound to a person is exactly the one that must not appear.
    """
    recorded = [who.recorded for row in listing.rows for who in row.owners if who.recorded]
    return tuple(dict.fromkeys(recorded))


def recorded_misses(
    *,
    search_index: SearchIndex,
    project: str | None = None,
) -> tuple[RecordedMiss, ...]:
    """Every search term that matched nothing, with how often it was asked (D11).

    Retrievable by specification: the value of the log is somebody reading it
    and deciding which aliases to add, and a log nobody can read buys nothing.
    """
    return search_index.misses(project)


def spec_path_for(
    asset_id: str,
    *,
    spec_store: SpecStore,
    search_index: SearchIndex,
    fingerprints: Fingerprinter = no_fingerprints,
    project: str | None = None,
) -> str:
    """The specification file one asset is written in, by identifier.

    Every read surface that takes an asset identifier — a lensed specification,
    the constraints, the open threads, a difference since a revision — needs the
    path behind it, and none of them may work it out from the identifier by
    string arithmetic: where a specification lives is the index's answer, and
    the index self-heals first (D8) exactly as `where_is` does.
    """
    fresh = current_entry(
        asset_id,
        spec_store=spec_store,
        search_index=search_index,
        fingerprints=fingerprints,
        project=project,
    )
    if fresh.entry is None or not fresh.entry.spec_path:
        raise UnknownAsset(asset_id, project)
    return fresh.entry.spec_path


def nearest_ids(
    asset_id: str,
    *,
    search_index: SearchIndex,
    project: str | None = None,
    limit: int = NEAREST_LIMIT,
) -> tuple[str, ...]:
    """The indexed identifiers closest to one nobody recognised.

    `mcp-server` requires a failed lookup to offer the closest matching
    identifiers rather than an empty answer, and a surface may not invent its
    own notion of *close*: the comparison lives here, beside
    :class:`UnknownAsset`, so the command line and the agent suggest the same
    names for the same typo. A term nothing resembles yields nothing, which is
    an honest answer and not an error.
    """
    known = sorted(entry.asset_id for entry in search_index.list_assets(project=project))
    return tuple(get_close_matches(asset_id, known, n=limit, cutoff=NEAREST_CUTOFF))


def locations_of(entry: IndexedAsset) -> tuple[Location, ...]:
    """The seven locations, in a fixed order, recorded or explicitly absent."""
    values = {
        DIRECTORY: entry.directory,
        SOURCE_FILE: entry.source_file,
        VALIDATED_EXPORT: entry.validated_export,
        VALIDATED_AT: entry.validated_at,
        ENGINE_PATH: entry.engine_path,
        DISCUSSION: entry.discussion,
        DESIGN_DOCUMENT: entry.design_doc,
    }
    return tuple(Location(label=label, value=values[label]) for label in LOCATION_LABELS)


def owners_of(entry: IndexedAsset, mapping: ActorMapping) -> tuple[OwnerPresentation, ...]:
    """The three owners, each resolved through the mapping before rendering (D12)."""
    return tuple(
        _owner(discipline, recorded, mapping)
        for discipline, recorded in zip(DISCIPLINES, entry.owners, strict=True)
    )


def _owner(discipline: str, recorded: str | None, mapping: ActorMapping) -> OwnerPresentation:
    """One owner. An unrecorded owner has no actor; an unmatched one is unmapped."""
    if not recorded:
        return OwnerPresentation(discipline=discipline)
    return OwnerPresentation(
        discipline=discipline,
        recorded=recorded,
        actor=resolve_git_author(mapping, recorded),
    )


__all__ = [
    "ART",
    "CODE",
    "DESIGN",
    "DESIGN_DOCUMENT",
    "DIRECTORY",
    "DISCIPLINES",
    "DISCUSSION",
    "ENGINE_PATH",
    "LOCATION_LABELS",
    "NEAREST_CUTOFF",
    "NEAREST_LIMIT",
    "SOURCE_FILE",
    "STALE_NOTICE",
    "VALIDATED_AT",
    "VALIDATED_EXPORT",
    "AssetListing",
    "AssetRow",
    "Location",
    "LocationAnswer",
    "OwnerPresentation",
    "SearchAnswer",
    "UnknownAsset",
    "list_assets",
    "locations_of",
    "nearest_ids",
    "owners_of",
    "recorded_misses",
    "recorded_owners",
    "search_assets",
    "spec_path_for",
    "where_is",
]
