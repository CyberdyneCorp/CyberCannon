"""Step definitions for `asset-preview` — the scenarios the use case satisfies.

Group 4 owns the half of this capability that is a *decision*: a preview is a
by-product of the read validation already paid for, and a preview failure is a
condition of its own that can never move the verdict (D7). Those scenarios run
here, over the in-memory inspector and blob store, with no file on disk.

The other half — that a real decimator produces fewer triangles, keeps the part
names annotations anchor to, and carries clips and bones across — is a property
of the emitter, not of the use case. Asserting it against a fake would be
asserting that the fake was written as intended. Those scenarios stay in
`tests/bdd/pending.txt` until group 5 emits a real preview from a real export
(tasks 5.8-5.9).
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.preview import PreviewUnavailable
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat

ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"


@pytest.fixture
def preview_run() -> dict[str, Any]:
    """The fakes this scenario set up, and what validating produced."""
    store = InMemorySpecStore()
    store.add(
        SPEC_PATH,
        Asset(id=AssetId(ASSET_ID), name="Scout Mech", constraints=Constraints(tri_budget=12000)),
    )
    return {
        "spec_store": store,
        "mesh_inspector": InMemoryMeshInspector(),
        "blob_store": InMemoryBlobStore(),
    }


def _validate(run: dict[str, Any]) -> None:
    """Validate with preview emission on, recording whichever way it ended."""
    try:
        run["outcome"] = validate_export(
            EXPORT,
            spec_store=run["spec_store"],
            mesh_inspector=run["mesh_inspector"],
            blob_store=run["blob_store"],
            emit_preview=True,
        )
    except OperationFailed as failure:
        run["failure"] = failure


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "Preview emitted during validation",
)
def test_preview_emitted_during_validation() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "Unreadable export produces no preview",
)
def test_unreadable_export_produces_no_preview() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "Preview emission fails",
)
def test_preview_emission_fails() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "Preview traceable to its export",
)
def test_preview_traceable_to_its_export() -> None: ...


# --------------------------------------------------------------------------
# GIVEN
# --------------------------------------------------------------------------


@given("an export that was successfully read for validation")
def _an_export_that_was_read(preview_run: dict[str, Any]) -> None:
    preview_run["mesh_inspector"].add(
        EXPORT, facts_for(MeshFormat.GLB, triangles=11840, objects=(OBJECT,))
    )


@given("an export that could not be read")
def _an_export_that_could_not_be_read(preview_run: dict[str, Any]) -> None:
    preview_run["mesh_inspector"].add_unreadable(EXPORT, "unexpected end of file")


@given("a validation that produced no errors")
def _a_clean_validation(preview_run: dict[str, Any]) -> None:
    preview_run["mesh_inspector"].add(
        EXPORT, facts_for(MeshFormat.GLB, triangles=11840, objects=(OBJECT,))
    )


# --------------------------------------------------------------------------
# WHEN
# --------------------------------------------------------------------------


@when("preview emission is requested for that run")
def _preview_emission_is_requested(preview_run: dict[str, Any]) -> None:
    _validate(preview_run)


@when("validation runs")
def _validation_runs(preview_run: dict[str, Any]) -> None:
    _validate(preview_run)


@when("preview emission fails")
def _preview_emission_fails(preview_run: dict[str, Any]) -> None:
    preview_run["mesh_inspector"].fail_preview(
        EXPORT, PreviewUnavailable("decimation would drop the clips")
    )
    _validate(preview_run)


@when("a preview is emitted for an export of `mech_scout`")
def _a_preview_is_emitted_for_mech_scout(preview_run: dict[str, Any]) -> None:
    preview_run["mesh_inspector"].add(
        EXPORT, facts_for(MeshFormat.GLB, triangles=11840, objects=(OBJECT,))
    )
    _validate(preview_run)


# --------------------------------------------------------------------------
# THEN
# --------------------------------------------------------------------------


@then("a preview mesh SHALL be produced from the already-loaded data")
def _the_preview_came_from_the_same_read(preview_run: dict[str, Any]) -> None:
    inspector: InMemoryMeshInspector = preview_run["mesh_inspector"]
    assert inspector.inspected == [EXPORT], "the export was read more than once"
    assert inspector.previewed == [EXPORT], "the preview came from a different read"
    assert preview_run["outcome"].preview is not None


@then("no preview SHALL be emitted")
def _no_preview_was_emitted(preview_run: dict[str, Any]) -> None:
    assert preview_run["mesh_inspector"].previewed == []
    assert preview_run["blob_store"].preview_for(ASSET_ID) is None


@then("the validation failure SHALL still be reported")
def _the_validation_failure_is_reported(preview_run: dict[str, Any]) -> None:
    failure = preview_run.get("failure")
    assert isinstance(failure, OperationFailed)
    assert EXPORT in failure.message
    assert "outcome" not in preview_run


@then("the validation outcome SHALL remain passing")
def _the_outcome_remains_passing(preview_run: dict[str, Any]) -> None:
    assert preview_run["outcome"].passed


@then("the preview failure SHALL be reported as a distinct condition")
def _the_preview_failure_is_distinct(preview_run: dict[str, Any]) -> None:
    outcome = preview_run["outcome"]
    assert outcome.preview_failure is not None
    assert outcome.preview_failure.reason == "decimation would drop the clips"
    assert outcome.report.violations == (), "a preview failure became a violation"


@then("the recorded preview SHALL identify `mech_scout` and the source export")
def _the_preview_identifies_its_source(preview_run: dict[str, Any]) -> None:
    stored = preview_run["blob_store"].preview_for(ASSET_ID)
    assert stored is not None
    assert stored.asset_id == ASSET_ID
    assert stored.source_export == EXPORT
