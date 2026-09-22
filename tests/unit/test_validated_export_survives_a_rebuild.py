"""Tasks 12.6 and 12.7 — `where_is` answers, and keeps answering after a rebuild.

G2 is what these two assert, from the far end. The gate decision says a
validation outcome is repository content *because* `asset-lookup` requires
`where_is` to report which export was validated and when, and because dropping
the index must lose nothing. Until the worker existed the product shipped a
reader for those two fields and nothing that wrote them, so both requirements
were satisfied only by a test that upserted the row by hand.

**The reader is untouched.** Nothing below imports anything the worker added
into `lookup_assets`: `where_is` is called exactly as `add-mcp-read-server`
shipped it, with the labels it defined, and the fields it reads are the ones it
has always read. That is task 12.6's acceptance — if the reader had needed a
change, the reader and the writer would disagree about the shape and that would
be the finding.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.hosted_repository import rebuild_project_index
from cybercanon.application.use_cases.index_assets import entry_for
from cybercanon.application.use_cases.lookup_assets import (
    VALIDATED_AT,
    VALIDATED_EXPORT,
    LocationAnswer,
    where_is,
)
from cybercanon.application.use_cases.validation_worker import validate_changed_exports
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat

PROJECT = "cyberdyne-game"
ASSET = "mech_scout"
SPEC = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

SPEC_BYTES = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\n"
MESH = b"glTF-ish bytes nothing here parses"

NOON = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC: SPEC_BYTES, EXPORT: MESH})
    built.clone(PROJECT)
    return built


@pytest.fixture
def store(host: InMemoryRepositoryHost) -> InMemorySpecStore:
    built = InMemorySpecStore()
    built.add(
        SPEC,
        Asset(id=AssetId(ASSET), name="Scout Mech", constraints=Constraints(tri_budget=12000)),
    )
    built.snapshot(host.head(PROJECT).value)
    return built


def an_inspector() -> InMemoryMeshInspector:
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, facts_for(MeshFormat.GLB, triangles=11840))
    return inspector


def a_worked_project(host: InMemoryRepositoryHost, store: InMemorySpecStore) -> InMemorySearchIndex:
    """One project whose export the worker has processed, with an index over it."""
    index = InMemorySearchIndex()
    index.upsert(entry_for(store.load(SPEC)))
    ran(
        validate_changed_exports(
            PROJECT,
            repository_host=host,
            spec_store=store,
            mesh_inspector=an_inspector(),
            search_index=index,
            clock=fixed_clock(NOON),
        )
    )
    return index


def located(index: InMemorySearchIndex, store: InMemorySpecStore) -> LocationAnswer:
    return ran(where_is(ASSET, spec_store=store, search_index=index))


# --------------------------------------------------------------------------
# 12.6 — `where_is` reports which export was validated and when
# --------------------------------------------------------------------------


def test_where_is_reports_which_export_was_validated_and_when(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    index = a_worked_project(host, store)

    answer = located(index, store)

    assert answer.location(VALIDATED_EXPORT).value == EXPORT
    assert answer.location(VALIDATED_AT).value == NOON.isoformat()


def test_an_asset_nobody_validated_still_says_so_rather_than_omitting_it(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """The reader's other half, unchanged: unrecorded is stated, never dropped."""
    index = InMemorySearchIndex()
    index.upsert(entry_for(store.load(SPEC)))

    answer = located(index, store)

    assert not answer.location(VALIDATED_EXPORT).is_recorded
    assert VALIDATED_EXPORT in {entry.label for entry in answer.unrecorded}


# --------------------------------------------------------------------------
# 12.7 — the outcome survives an index rebuild
# --------------------------------------------------------------------------


def test_dropping_the_index_and_rebuilding_leaves_the_answer_unchanged(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """It is repository content, so a rebuild reads it back rather than losing it."""
    before = located(a_worked_project(host, store), store)
    store.snapshot(host.head(PROJECT).value)

    dropped = InMemorySearchIndex()
    ran(
        rebuild_project_index(PROJECT, repository_host=host, spec_store=store, search_index=dropped)
    )
    after = located(dropped, store)

    assert dropped.get(ASSET) is not None
    assert after.location(VALIDATED_EXPORT).value == before.location(VALIDATED_EXPORT).value
    assert after.location(VALIDATED_AT).value == before.location(VALIDATED_AT).value
    assert after.locations == before.locations


def test_a_rebuild_over_a_project_nobody_validated_records_no_export(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """The file is absent, so the rebuild says so rather than inventing a date."""
    dropped = InMemorySearchIndex()
    ran(
        rebuild_project_index(PROJECT, repository_host=host, spec_store=store, search_index=dropped)
    )

    entry = dropped.get(ASSET)
    assert entry is not None
    assert entry.validated_export is None
    assert entry.validated_at is None
