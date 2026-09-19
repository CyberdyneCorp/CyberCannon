"""Tasks 3.1-3.3 — the rebuild, per-file staleness, and a disposable index.

Everything here runs over the in-memory store and the in-memory index: the
scanning rule, the staleness rule and the "deleting the index loses nothing"
guarantee are all decidable without a file, and the SQLite adapter is held to
the same behaviour by the port conformance suite.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cybercanon.application.ports.search_index import FileFingerprint
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.index_assets import (
    ROOT_DIRECTORY,
    current_entry,
    directory_of,
    rebuild_index,
)
from cybercanon.application.use_cases.lookup_assets import search_assets, where_is
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.status import Status

PROJECT = "cyberdyne-game"
SCOUT_PATH = "characters/mech_scout/asset.yaml"
CRATE_PATH = "props/crate/asset.yaml"
BROKEN_PATH = "props/broken/asset.yaml"

SCOUT = Asset(
    id=AssetId("mech_scout"),
    name="Scout Mech",
    status=Status.MODELING,
    aliases=("drone",),
    owner_art="rafa@cyberdyne.com",
    links=Links(source="art/mech_scout.blend", engine="/Game/Chars/MechScout"),
)
CRATE = Asset(id=AssetId("crate"), name="Supply Crate", status=Status.VALIDATED)


def a_store(broken: bool = False) -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SCOUT_PATH, SCOUT)
    store.add(CRATE_PATH, CRATE)
    if broken:
        store.add_unreadable(BROKEN_PATH, "mapping values are not indented consistently")
    return store


def a_fingerprint(path: str, size: int = 10) -> FileFingerprint:
    return FileFingerprint(path=path, size=size, mtime_ns=1)


# --------------------------------------------------------------------------
# 3.1 — the scan
# --------------------------------------------------------------------------


def test_a_rebuild_indexes_every_specification_under_the_root() -> None:
    store, index = a_store(), InMemorySearchIndex()

    report = rebuild_index(spec_store=store, search_index=index)

    assert report.indexed_count == 2
    assert report.indexed == ("mech_scout", "crate")
    assert report.project == PROJECT
    assert report.is_complete


def test_an_unreadable_specification_is_named_and_does_not_abort_the_scan() -> None:
    store, index = a_store(broken=True), InMemorySearchIndex()

    report = rebuild_index(spec_store=store, search_index=index)

    assert report.indexed_count == 2, "the readable files were still indexed"
    assert report.unreadable_paths == (BROKEN_PATH,)
    assert "indented" in report.unreadable[0].reason
    assert not report.is_complete


def test_a_rebuild_forgets_a_specification_that_has_disappeared() -> None:
    store, index = a_store(), InMemorySearchIndex()
    rebuild_index(spec_store=store, search_index=index)

    report = rebuild_index(spec_store=a_pruned_store(), search_index=index)

    assert report.forgotten == ("crate",)
    assert index.get("crate") is None


def a_pruned_store() -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SCOUT_PATH, SCOUT)
    return store


def test_an_indexed_row_carries_the_locations_the_file_records() -> None:
    store, index = a_store(), InMemorySearchIndex()

    rebuild_index(spec_store=store, search_index=index)
    entry = index.get("mech_scout")

    assert entry is not None
    assert entry.directory == "characters/mech_scout"
    assert entry.source_file == "art/mech_scout.blend"
    assert entry.engine_path == "/Game/Chars/MechScout"
    assert entry.aliases == ("drone",)
    assert entry.status == "modeling"


def test_a_specification_at_the_repository_root_has_a_directory() -> None:
    assert directory_of("asset.yaml") == ROOT_DIRECTORY
    assert directory_of("props/crate/asset.yaml") == "props/crate"


def test_a_rebuild_keeps_a_recorded_validation_that_no_scan_could_restore() -> None:
    """A validation result is recorded by a validation run, not by reading a file."""
    store, index = a_store(), InMemorySearchIndex()
    rebuild_index(spec_store=store, search_index=index)
    validated = index.get("mech_scout")
    assert validated is not None
    index.upsert(
        replace(
            validated,
            validated_export="exports/SM_MechScout_LOD0.glb",
            validated_at="2026-09-17",
        )
    )

    rebuild_index(spec_store=store, search_index=index)

    refreshed = index.get("mech_scout")
    assert refreshed is not None
    assert refreshed.validated_export == "exports/SM_MechScout_LOD0.glb"
    assert refreshed.validated_at == "2026-09-17"


# --------------------------------------------------------------------------
# 3.2 — per-file staleness, and the self-healing read path (D8)
# --------------------------------------------------------------------------


def test_an_unchanged_file_is_served_from_the_row() -> None:
    store, index = a_store(), InMemorySearchIndex()
    rebuild_index(spec_store=store, search_index=index, fingerprints=a_fingerprint)

    fresh = current_entry(
        "mech_scout",
        spec_store=store,
        search_index=index,
        fingerprints=a_fingerprint,
    )

    assert fresh.is_known
    assert not fresh.refreshed
    assert not fresh.stale


def test_an_edited_specification_is_re_read_without_a_full_rebuild() -> None:
    store, index = a_store(), InMemorySearchIndex()
    rebuild_index(spec_store=store, search_index=index, fingerprints=a_fingerprint)
    store.add(SCOUT_PATH, SCOUT.renamed("Recon Mech"))
    edited = index.get("crate")

    fresh = current_entry(
        "mech_scout",
        spec_store=store,
        search_index=index,
        fingerprints=lambda path: a_fingerprint(path, size=99),
    )

    assert fresh.refreshed, "the one edited file was re-read on the read path"
    assert fresh.entry is not None
    assert fresh.entry.name == "Recon Mech"
    assert index.get("crate") == edited, "no other row was touched"


def test_a_file_that_changed_and_cannot_be_read_is_marked_stale_not_served_as_current() -> None:
    store, index = a_store(), InMemorySearchIndex()
    rebuild_index(spec_store=store, search_index=index, fingerprints=a_fingerprint)
    store.add_unreadable(SCOUT_PATH, "the file no longer parses")

    fresh = current_entry(
        "mech_scout",
        spec_store=store,
        search_index=index,
        fingerprints=lambda path: a_fingerprint(path, size=99),
    )

    assert fresh.stale
    assert not fresh.refreshed
    assert fresh.entry is not None, "the answer is still offered, marked stale"
    assert "no longer parses" in fresh.detail


def test_an_unindexed_asset_is_unknown_rather_than_empty() -> None:
    store, index = a_store(), InMemorySearchIndex()

    fresh = current_entry("nobody", spec_store=store, search_index=index)

    assert not fresh.is_known


def test_the_specification_file_wins_over_the_row_that_disagrees_with_it() -> None:
    """`asset-lookup`: an index entry that disagrees with its file is the wrong one."""
    store, index = a_store(), InMemorySearchIndex()
    rebuild_index(spec_store=store, search_index=index, fingerprints=a_fingerprint)
    indexed = index.get("mech_scout")
    assert indexed is not None
    index.upsert(replace(indexed, name="Something Else"))

    fresh = current_entry(
        "mech_scout",
        spec_store=store,
        search_index=index,
        fingerprints=lambda path: a_fingerprint(path, size=99),
    )

    assert fresh.entry is not None
    assert fresh.entry.name == "Scout Mech", "the file is the source of truth"


# --------------------------------------------------------------------------
# 3.3 — the index is disposable
# --------------------------------------------------------------------------


@pytest.mark.parametrize("term", ["mech_scout", "drone", "crate", "Scout"])
def test_deleting_and_rebuilding_the_index_changes_no_answer(term: str) -> None:
    store, index = a_store(), InMemorySearchIndex()
    rebuild_index(spec_store=store, search_index=index)
    before_lookup = where_is("mech_scout", spec_store=store, search_index=index)
    before_search = search_assets(term, search_index=index)

    index.clear()
    rebuild_index(spec_store=store, search_index=index)

    assert where_is("mech_scout", spec_store=store, search_index=index) == before_lookup
    assert search_assets(term, search_index=index) == before_search


def test_a_deleted_index_is_restored_in_full_by_one_scan() -> None:
    store, index = a_store(), InMemorySearchIndex()
    rebuild_index(spec_store=store, search_index=index)
    before = index.list_assets()

    index.clear()
    assert index.list_assets() == ()
    rebuild_index(spec_store=store, search_index=index)

    assert index.list_assets() == before
