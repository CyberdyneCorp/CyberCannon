"""Step definitions for `asset-lookup` — locating, listing, searching, diffing.

Group 3 of `add-mcp-read-server` builds the read use cases over the ports group 2
defined: the rebuild that scans the repository and names what it could not read,
the per-file staleness check that re-reads one file on the read path (D8),
`where_is`, `list_assets`, the fixed five-pass search cascade (D9), the local
zero-result log (D11) and `diff_spec` over parsed specifications (D10).

Every scenario here runs against the in-memory specification store and the
in-memory index, which is the point: the index is derived and disposable, so its
behaviour is decidable with no file on disk, and the SQLite adapter is held to
the same contract by the port conformance suite rather than by a second set of
scenarios.

Assertions are on **content** — that the engine path is reported as not
recorded, that the exact identifier ranks first, that the statement carries both
budgets — never on wording, so the prose renderers can be improved without
touching a scenario.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.ports.search_index import (
    ABSENT,
    FileFingerprint,
    IndexedAsset,
    MatchKind,
)
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.diff_spec import UNCHANGED, diff_spec
from cybercanon.application.use_cases.index_assets import current_entry, rebuild_index
from cybercanon.application.use_cases.lookup_assets import (
    ART,
    CODE,
    DESIGN,
    ENGINE_PATH,
    SOURCE_FILE,
    VALIDATED_AT,
    VALIDATED_EXPORT,
    list_assets,
    recorded_misses,
    search_assets,
    where_is,
)
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.status import Status

PROJECT = "cyberdyne-game"
SCOUT_PATH = "characters/mech_scout/asset.yaml"
CRATE_PATH = "props/crate/asset.yaml"
MALFORMED_PATH = "props/broken/asset.yaml"

ART_OWNER = "rafa@cyberdyne.com"
DESIGN_OWNER = "ana@cyberdyne.com"
CODE_OWNER = "joe@cyberdyne.com"

SOURCE = "art/mech_scout.blend"
ENGINE = "/Game/Chars/MechScout"
THREAD = "https://chat.example/threads/17"
EXPORT = "exports/SM_MechScout_LOD0.glb"
VALIDATED_ON = "2026-09-17"

REVISION = "a1b2c3d"
PREVIOUS_BUDGET = 12000
CURRENT_BUDGET = 9000

SCOUT = Asset(
    id=AssetId("mech_scout"),
    name="Scout Mech",
    status=Status.MODELING,
    aliases=("drone",),
    owner_art=ART_OWNER,
    owner_design=DESIGN_OWNER,
    owner_code=CODE_OWNER,
    constraints=Constraints(tri_budget=PREVIOUS_BUDGET),
    links=Links(source=SOURCE, engine=ENGINE, discussion=THREAD),
)
CRATE = Asset(
    id=AssetId("crate"),
    name="Supply Crate",
    status=Status.VALIDATED,
    owner_art=DESIGN_OWNER,
    links=Links(source="art/crate.blend"),
)


@pytest.fixture
def lookup() -> dict[str, Any]:
    """What this scenario indexed, and what the use cases answered."""
    return {}


def a_store(*assets: tuple[str, Asset]) -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.set_project(ProjectConfig(name=PROJECT))
    for path, asset in assets or ((SCOUT_PATH, SCOUT), (CRATE_PATH, CRATE)):
        store.add(path, asset)
    return store


def indexed(lookup: dict[str, Any], store: InMemorySpecStore) -> InMemorySearchIndex:
    """Index that store, and remember both for the steps that follow."""
    index = InMemorySearchIndex()
    lookup["store"] = store
    lookup["index"] = index
    lookup["report"] = rebuild_index(spec_store=store, search_index=index)
    return index


def a_repository(lookup: dict[str, Any]) -> InMemorySearchIndex:
    """The default project: two assets, indexed."""
    return indexed(lookup, a_store())


def answers(lookup: dict[str, Any]) -> dict[str, Any]:
    """Every lookup and search this project answers — what a rebuild must preserve."""
    store, index = lookup["store"], lookup["index"]
    return {
        "where_is": {
            asset_id: where_is(asset_id, spec_store=store, search_index=index)
            for asset_id in ("mech_scout", "crate")
        },
        "search": {
            term: search_assets(term, search_index=index).asset_ids
            for term in ("mech_scout", "drone", "Supply", "crate")
        },
        "list": list_assets(spec_store=store, search_index=index, project=PROJECT).asset_ids,
    }


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "Full location answer")
def test_full_location_answer() -> None: ...


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "Unrecorded location is explicit")
def test_unrecorded_location_is_explicit() -> None: ...


@scenario(
    "../features/add-mcp-read-server/asset-lookup.feature",
    "Validated export is identified as such",
)
def test_validated_export_is_identified_as_such() -> None: ...


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "Filter by status and owner")
def test_filter_by_status_and_owner() -> None: ...


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "Alias finds the asset")
def test_alias_finds_the_asset() -> None: ...


@scenario(
    "../features/add-mcp-read-server/asset-lookup.feature",
    "Exact identifier outranks a substring",
)
def test_exact_identifier_outranks_a_substring() -> None: ...


@scenario(
    "../features/add-mcp-read-server/asset-lookup.feature", "Miss is recorded and retrievable"
)
def test_miss_is_recorded_and_retrievable() -> None: ...


@scenario(
    "../features/add-mcp-read-server/asset-lookup.feature",
    "Successful searches are not recorded as misses",
)
def test_successful_searches_are_not_recorded_as_misses() -> None: ...


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "Deleted index is fully restored")
def test_deleted_index_is_fully_restored() -> None: ...


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "Index is not authoritative")
def test_index_is_not_authoritative() -> None: ...


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "Spec edited after indexing")
def test_spec_edited_after_indexing() -> None: ...


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "Rebuild reports malformed files")
def test_rebuild_reports_malformed_files() -> None: ...


@scenario(
    "../features/add-mcp-read-server/asset-lookup.feature",
    "Constraint changed since a revision",
)
def test_constraint_changed_since_a_revision() -> None: ...


@scenario("../features/add-mcp-read-server/asset-lookup.feature", "No change since the revision")
def test_no_change_since_the_revision() -> None: ...


# --------------------------------------------------------------------------
# Locating an asset
# --------------------------------------------------------------------------


@given("an asset whose specification records a source file, an engine path and a discussion link")
def _an_asset_with_every_location(lookup: dict[str, Any]) -> None:
    a_repository(lookup)
    lookup["asset_id"] = "mech_scout"


@given("an asset whose specification records no engine path")
def _an_asset_with_no_engine_path(lookup: dict[str, Any]) -> None:
    a_repository(lookup)
    lookup["asset_id"] = "crate"


@given("an asset with exports, one of which last passed validation")
def _an_asset_with_a_validated_export(lookup: dict[str, Any]) -> None:
    index = a_repository(lookup)
    entry = index.get("mech_scout")
    assert entry is not None
    index.upsert(replace(entry, validated_export=EXPORT, validated_at=VALIDATED_ON))
    lookup["asset_id"] = "mech_scout"


@when("its location is requested")
def _its_location_is_requested(lookup: dict[str, Any]) -> None:
    lookup["answer"] = where_is(
        lookup["asset_id"],
        spec_store=lookup["store"],
        search_index=lookup["index"],
    )


@then("the response SHALL include all recorded locations, its status and its three owners")
def _the_answer_carries_every_location(lookup: dict[str, Any]) -> None:
    answer = lookup["answer"]

    assert answer.location(SOURCE_FILE).value == SOURCE
    assert answer.location(ENGINE_PATH).value == ENGINE
    assert THREAD in {entry.value for entry in answer.recorded}
    assert answer.status == "modeling"
    assert [owner.discipline for owner in answer.owners] == [ART, DESIGN, CODE]
    assert all(owner.is_recorded for owner in answer.owners)


@then("the response SHALL state that the engine path is not recorded")
def _the_engine_path_is_reported_absent(lookup: dict[str, Any]) -> None:
    engine = lookup["answer"].location(ENGINE_PATH)

    assert not engine.is_recorded
    assert engine.text == ABSENT, "an unrecorded location is stated, never omitted"
    assert ENGINE_PATH in {entry.label for entry in lookup["answer"].unrecorded}


@then("the response SHALL identify which export was validated and when")
def _the_validated_export_is_identified(lookup: dict[str, Any]) -> None:
    answer = lookup["answer"]

    assert answer.location(VALIDATED_EXPORT).value == EXPORT
    assert answer.location(VALIDATED_AT).value == VALIDATED_ON


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


@when("assets are listed filtered by status `modeling` and a given art owner")
def _assets_are_listed_with_two_filters(lookup: dict[str, Any]) -> None:
    index = a_repository(lookup)
    index.upsert(
        IndexedAsset(
            asset_id="hangar",
            name="Hangar",
            project=PROJECT,
            status="modeling",
            owner_art=DESIGN_OWNER,
        )
    )
    lookup["listing"] = list_assets(
        spec_store=lookup["store"],
        search_index=index,
        project=PROJECT,
        status="modeling",
        owner=ART_OWNER,
    )


@then("only assets matching both SHALL be returned")
def _only_assets_matching_both(lookup: dict[str, Any]) -> None:
    listing = lookup["listing"]

    assert listing.asset_ids == ("mech_scout",), "filters combine; they do not widen"
    assert all(row.status == "modeling" for row in listing.rows)


# --------------------------------------------------------------------------
# Search, and the recorded misses (D9, D11)
# --------------------------------------------------------------------------


@given('an asset named "Scout Mech" with aliases including `drone`')
def _an_asset_with_an_alias(lookup: dict[str, Any]) -> None:
    a_repository(lookup)
    assert "drone" in SCOUT.aliases


@given(
    'one asset with identifier `mech_scout` and another whose description contains the word "mech"'
)
def _one_exact_and_one_described(lookup: dict[str, Any]) -> None:
    index = a_repository(lookup)
    index.upsert(
        IndexedAsset(
            asset_id="hangar",
            name="Hangar",
            project=PROJECT,
            description="the bay where a mech_scout is repaired",
        )
    )


@when("a search for `drone` is performed")
def _a_search_for_an_alias(lookup: dict[str, Any]) -> None:
    lookup["answer"] = search_assets("drone", search_index=lookup["index"], project=PROJECT)


@when("a search for `mech_scout` is performed")
def _a_search_for_the_identifier(lookup: dict[str, Any]) -> None:
    lookup["answer"] = search_assets("mech_scout", search_index=lookup["index"], project=PROJECT)


@then("that asset SHALL be returned")
def _that_asset_was_returned(lookup: dict[str, Any]) -> None:
    answer = lookup["answer"]

    assert "mech_scout" in answer.asset_ids
    assert answer.hits[0].kind is MatchKind.ALIAS, "a human-written alias is a ranked pass"


@then("the asset with the exact identifier SHALL rank first")
def _the_exact_identifier_ranks_first(lookup: dict[str, Any]) -> None:
    answer = lookup["answer"]

    assert answer.asset_ids[0] == "mech_scout"
    assert answer.hits[0].kind is MatchKind.EXACT_ID
    assert MatchKind.DESCRIPTION in {hit.kind for hit in answer.hits}, "both matched"


@when("a search term returns no results")
def _a_search_that_matches_nothing(lookup: dict[str, Any]) -> None:
    a_repository(lookup)
    lookup["term"] = "hovercraft"
    lookup["answer"] = search_assets(lookup["term"], search_index=lookup["index"], project=PROJECT)
    assert lookup["answer"].is_empty


@then("the term SHALL be recorded")
def _the_term_was_recorded(lookup: dict[str, Any]) -> None:
    assert lookup["answer"].recorded_as_miss


@then("SHALL appear when recorded misses are retrieved")
def _the_term_is_retrievable(lookup: dict[str, Any]) -> None:
    misses = recorded_misses(search_index=lookup["index"], project=PROJECT)

    assert lookup["term"] in {miss.term for miss in misses}


@when("a search returns at least one result")
def _a_search_that_matches(lookup: dict[str, Any]) -> None:
    a_repository(lookup)
    lookup["term"] = "drone"
    lookup["answer"] = search_assets(lookup["term"], search_index=lookup["index"], project=PROJECT)
    assert not lookup["answer"].is_empty


@then("no miss SHALL be recorded for that term")
def _no_miss_was_recorded(lookup: dict[str, Any]) -> None:
    misses = recorded_misses(search_index=lookup["index"])

    assert not lookup["answer"].recorded_as_miss
    assert lookup["term"] not in {miss.term for miss in misses}


# --------------------------------------------------------------------------
# The index is derived, disposable and never authoritative
# --------------------------------------------------------------------------


@given("an index built from a repository")
def _an_index_built_from_a_repository(lookup: dict[str, Any]) -> None:
    a_repository(lookup)
    lookup["before"] = answers(lookup)


@when("the index is deleted and rebuilt")
def _the_index_is_deleted_and_rebuilt(lookup: dict[str, Any]) -> None:
    index: InMemorySearchIndex = lookup["index"]
    index.clear()
    assert index.list_assets() == (), "the index really was deleted"
    lookup["report"] = rebuild_index(spec_store=lookup["store"], search_index=index)


@then("every lookup and search SHALL return the same results as before")
def _every_answer_is_unchanged(lookup: dict[str, Any]) -> None:
    assert answers(lookup) == lookup["before"]


@when("an index entry disagrees with the specification file it was built from")
def _a_row_disagrees_with_its_file(lookup: dict[str, Any]) -> None:
    index = a_repository(lookup)
    entry = index.get("mech_scout")
    assert entry is not None
    index.upsert(replace(entry, name="Something Else", engine_path="/Game/Wrong"))


@then("the specification file SHALL be treated as correct")
def _the_file_wins(lookup: dict[str, Any]) -> None:
    fresh = current_entry(
        "mech_scout",
        spec_store=lookup["store"],
        search_index=lookup["index"],
        fingerprints=lambda path: None,
    )
    rebuilt = rebuild_index(spec_store=lookup["store"], search_index=lookup["index"])
    entry = lookup["index"].get("mech_scout")

    assert rebuilt.indexed_count == 2
    assert entry is not None
    assert entry.name == SCOUT.name
    assert entry.engine_path == ENGINE
    assert fresh.is_known, "the row is still answerable while the file is re-read"


@given("an index built before a specification file was edited")
def _an_index_built_before_an_edit(lookup: dict[str, Any]) -> None:
    store = a_store()
    index = InMemorySearchIndex()
    lookup["store"], lookup["index"] = store, index
    rebuild_index(
        spec_store=store,
        search_index=index,
        fingerprints=lambda path: _fingerprint(path, 10),
    )
    store.add(SCOUT_PATH, SCOUT.renamed("Recon Mech"))
    lookup["asset_id"] = "mech_scout"


@when("that asset is looked up")
def _that_asset_is_looked_up(lookup: dict[str, Any]) -> None:
    lookup["answer"] = where_is(
        lookup["asset_id"],
        spec_store=lookup["store"],
        search_index=lookup["index"],
        fingerprints=lambda path: _fingerprint(path, 99),
    )


@then("the system SHALL serve the current file content or state that the index is stale")
def _the_answer_is_current_or_says_it_is_stale(lookup: dict[str, Any]) -> None:
    answer = lookup["answer"]

    assert not answer.stale, "this file could be re-read, so it is served current"
    assert answer.name == "Recon Mech", "the edited file, not the row it was indexed from"
    assert answer.notice == ""


@given("a project containing one malformed specification file")
def _a_project_with_a_malformed_file(lookup: dict[str, Any]) -> None:
    store = a_store()
    store.add_unreadable(MALFORMED_PATH, "mapping values are not indented consistently")
    lookup["store"] = store
    lookup["index"] = InMemorySearchIndex()


@when("the index is rebuilt")
def _the_index_is_rebuilt(lookup: dict[str, Any]) -> None:
    lookup["report"] = rebuild_index(spec_store=lookup["store"], search_index=lookup["index"])


@then("the command SHALL report the count of indexed assets and name the malformed file")
def _the_rebuild_reports_both(lookup: dict[str, Any]) -> None:
    report = lookup["report"]

    assert report.indexed_count == 2, "one bad file does not abort the scan"
    assert report.unreadable_paths == (MALFORMED_PATH,)
    assert not report.is_complete


# --------------------------------------------------------------------------
# What changed since a revision (D10)
# --------------------------------------------------------------------------


@given("an asset whose triangle budget was reduced after a given revision")
def _a_budget_reduced_since_a_revision(lookup: dict[str, Any]) -> None:
    constraints = SCOUT.constraints
    assert constraints is not None
    current = replace(SCOUT, constraints=replace(constraints, tri_budget=CURRENT_BUDGET))
    store = a_store((SCOUT_PATH, current))
    store.add_revision(SCOUT_PATH, REVISION, SCOUT)
    lookup["store"] = store


@when("the change since that revision is requested")
def _the_change_since_that_revision(lookup: dict[str, Any]) -> None:
    lookup["difference"] = diff_spec(SCOUT_PATH, REVISION, spec_store=lookup["store"])


@then(
    "the response SHALL state that the triangle budget changed, with its previous and "
    "current values"
)
def _the_budget_change_is_stated(lookup: dict[str, Any]) -> None:
    difference = lookup["difference"]
    change = difference.change("triangle budget")

    assert change is not None
    assert change.previous == str(PREVIOUS_BUDGET)
    assert change.current == str(CURRENT_BUDGET)
    statement = str(change)
    assert str(PREVIOUS_BUDGET) in statement and str(CURRENT_BUDGET) in statement


@when("nothing has changed since the given revision")
def _nothing_changed_since_the_revision(lookup: dict[str, Any]) -> None:
    store = a_store((SCOUT_PATH, SCOUT))
    store.add_revision(SCOUT_PATH, REVISION, SCOUT)
    lookup["difference"] = diff_spec(SCOUT_PATH, REVISION, spec_store=store)


@then("the response SHALL state that the specification is unchanged")
def _the_specification_is_unchanged(lookup: dict[str, Any]) -> None:
    difference = lookup["difference"]

    assert difference.is_unchanged
    assert UNCHANGED in difference.summary


def _fingerprint(path: str, size: int) -> FileFingerprint:
    """What a file looks like on disk, as a caller-supplied fingerprint (D8)."""
    return FileFingerprint(path=path, size=size, mtime_ns=1)
