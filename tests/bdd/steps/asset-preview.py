"""Step definitions for `asset-preview` — the scenarios the use case satisfies.

Half of this capability is a *decision*: a preview is a by-product of the read
validation already paid for, and a preview failure is a condition of its own that
can never move the verdict (D7). Those scenarios run over the in-memory inspector
and blob store, with no file on disk.

The other half is a property of the real emitter — fewer triangles, a smaller
file, the part names annotations anchor to, the clips and the bones — and it
cannot be asserted against a fake without merely asserting that the fake was
written as intended. Those scenarios run the real `TrimeshInspector` over an
export `canon_fixtures` writes into `tmp_path`, and every assertion is made
against the bytes that reached the blob store, because that is the artifact the
3D viewer will actually load.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.mesh import gltf_preview
from cybercanon.adapters.outbound.mesh.gltf_document import GltfDocument
from cybercanon.adapters.outbound.mesh.gltf_preview import Carried, describe
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.ports.preview import PreviewUnavailable
from cybercanon.application.results import Refusal, succeeded
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.outcomes import ran
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

RIGGED = "characters/mech_scout/exports/SM_mech_scout_rig_LOD0.glb"
CRATE_ID = "crate"
CRATE_SPEC = "props/crate/asset.yaml"
CRATE = "props/crate/exports/SM_crate_LOD0.glb"


@pytest.fixture
def preview_run(tmp_path: Path) -> dict[str, Any]:
    """The fakes this scenario set up, and what validating produced."""
    store = InMemorySpecStore()
    store.add(
        SPEC_PATH,
        Asset(id=AssetId(ASSET_ID), name="Scout Mech", constraints=Constraints(tri_budget=12000)),
    )
    store.add(
        CRATE_SPEC,
        Asset(id=AssetId(CRATE_ID), name="Crate", constraints=Constraints(tri_budget=12000)),
    )
    return {
        "spec_store": store,
        "mesh_inspector": InMemoryMeshInspector(),
        "blob_store": InMemoryBlobStore(),
        "repository": tmp_path,
        "export": EXPORT,
        "asset_id": ASSET_ID,
    }


def _validate(run: dict[str, Any], *, emit: bool = True) -> Any:
    """Validate with preview emission on, recording whichever way it ended (D10)."""
    result = validate_export(
        run["export"],
        spec_store=run["spec_store"],
        mesh_inspector=run["mesh_inspector"],
        blob_store=run["blob_store"],
        emit_preview=emit,
    )
    if succeeded(result):
        run["outcome"] = result.value
    else:
        run["failure"] = result
    return run.get("outcome")


# --------------------------------------------------------------------------
# The real export, read by the real adapter
# --------------------------------------------------------------------------


def _real_export(run: dict[str, Any], write: Any, export: str, asset_id: str = ASSET_ID) -> Any:
    """Write a fixture into the scenario's repository and read it for real.

    The fake inspector is replaced rather than configured: these scenarios are
    about what a decimator actually produces, and a fake cannot answer that.
    """
    run["export"] = export
    run["asset_id"] = asset_id
    run["authored"] = write(run["repository"] / export)
    run["mesh_inspector"] = TrimeshInspector(root=run["repository"])
    run["source"] = describe(GltfDocument.read(run["repository"] / export))
    return run["authored"]


def _emitted(run: dict[str, Any]) -> Carried:
    """What the preview that reached the blob store actually carries."""
    stored = run["outcome"].preview
    assert stored is not None, "no preview was emitted"
    content = run["blob_store"].read(stored.key)
    assert content is not None
    return describe(GltfDocument.from_bytes(content))


def _lose_the_clips(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for a decimator that cannot carry a clip across.

    The substitution is the *production* of the preview; the decision about what
    to do with a clipless one stays the emitter's, which is the thing under test.
    """
    decimate = gltf_preview._decimated_glb

    def clipless(document: GltfDocument, settings: gltf_preview.PreviewSettings) -> bytes:
        emitted = GltfDocument.from_bytes(decimate(document, settings))
        emitted.gltf.animations = []
        return b"".join(emitted.gltf.save_to_bytes())

    monkeypatch.setattr(gltf_preview, "_decimated_glb", clipless)


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
    "Preview is smaller than the source",
)
def test_preview_is_smaller_than_the_source() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "Named parts survive decimation",
)
def test_named_parts_survive_decimation() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "Clips survive decimation",
)
def test_clips_survive_decimation() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "Skinning is preserved",
)
def test_skinning_is_preserved() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "Clips cannot be preserved",
)
def test_clips_cannot_be_preserved() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-preview.feature",
    "A source without clips is not a failure",
)
def test_a_source_without_clips_is_not_a_failure() -> None: ...


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


@given("a working export of substantial size")
def _a_working_export_of_substantial_size(preview_run: dict[str, Any]) -> None:
    _real_export(preview_run, fixtures.write_rigged_glb, RIGGED)


@given("an export containing a part named `SM_MechScout_Shoulder_L`")
def _an_export_containing_the_shoulder(preview_run: dict[str, Any]) -> None:
    authored = _real_export(preview_run, fixtures.write_rigged_glb, RIGGED)
    assert fixtures.SHOULDER in authored.objects


@given("an export containing clips `A_mech_scout_walk` and `A_mech_scout_fire`")
def _an_export_containing_two_clips(preview_run: dict[str, Any]) -> None:
    authored = _real_export(preview_run, fixtures.write_rigged_glb, RIGGED)
    assert authored.clip_names == ("A_mech_scout_walk", "A_mech_scout_fire")


@given("a skinned export whose skeleton has 74 bones")
def _a_skinned_export_with_74_bones(preview_run: dict[str, Any]) -> None:
    authored = _real_export(preview_run, fixtures.write_rigged_glb, RIGGED)
    assert authored.is_skinned
    assert authored.bone_count == 74


@given("an export whose clips cannot be carried into the preview")
def _an_export_whose_clips_cannot_be_carried(
    preview_run: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _real_export(preview_run, fixtures.write_rigged_glb, RIGGED)
    preview_run["baseline"] = ran(
        validate_export(
            preview_run["export"],
            spec_store=preview_run["spec_store"],
            mesh_inspector=preview_run["mesh_inspector"],
        )
    )
    _lose_the_clips(monkeypatch)


@given("an export containing no animation clips")
def _an_export_containing_no_clips(preview_run: dict[str, Any]) -> None:
    authored = _real_export(preview_run, fixtures.write_static_glb, CRATE, asset_id=CRATE_ID)
    assert authored.clips == ()


# --------------------------------------------------------------------------
# WHEN
# --------------------------------------------------------------------------


@when("preview emission is requested for that run")
def _preview_emission_is_requested(preview_run: dict[str, Any]) -> None:
    _validate(preview_run)


@when("validation runs")
def _validation_runs(preview_run: dict[str, Any]) -> None:
    _validate(preview_run)


@when("a preview is emitted for it")
@when("a preview is emitted")
@when("preview emission runs")
def _a_preview_is_emitted(preview_run: dict[str, Any]) -> None:
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
    assert isinstance(failure, Refusal)
    assert EXPORT in failure.message
    assert "outcome" not in preview_run


@then("the preview SHALL contain fewer triangles than the source")
def _the_preview_has_fewer_triangles(preview_run: dict[str, Any]) -> None:
    assert _emitted(preview_run).triangles < preview_run["source"].triangles


@then("the preview file SHALL be smaller than the source file")
def _the_preview_is_a_smaller_file(preview_run: dict[str, Any]) -> None:
    source = preview_run["repository"] / preview_run["export"]
    assert preview_run["outcome"].preview.size_bytes < source.stat().st_size


@then("the preview SHALL contain a part with the same name")
def _the_preview_contains_the_named_part(preview_run: dict[str, Any]) -> None:
    assert fixtures.SHOULDER in _emitted(preview_run).parts


@then("the preview SHALL contain clips with the same two names")
def _the_preview_contains_the_same_clips(preview_run: dict[str, Any]) -> None:
    assert _emitted(preview_run).clip_names == preview_run["source"].clip_names


@then("each clip SHALL have the same duration as in the source")
def _each_clip_has_the_same_duration(preview_run: dict[str, Any]) -> None:
    assert _emitted(preview_run).durations == preview_run["source"].durations


@then("the preview SHALL be skinned to a skeleton with the same bone names")
def _the_preview_is_skinned_to_the_same_skeleton(preview_run: dict[str, Any]) -> None:
    assert _emitted(preview_run).bones == preview_run["authored"].bones


@then("the preview SHALL be reported as failed rather than emitted without its clips")
def _the_preview_is_reported_as_failed(preview_run: dict[str, Any]) -> None:
    outcome = preview_run["outcome"]
    assert outcome.preview is None, "a clipless preview was written anyway"
    assert preview_run["blob_store"].preview_for(preview_run["asset_id"]) is None
    assert outcome.preview_failure is not None
    assert "animation clips" in outcome.preview_failure.reason


@then("the validation outcome SHALL be unchanged")
def _the_validation_outcome_is_unchanged(preview_run: dict[str, Any]) -> None:
    assert preview_run["outcome"].report == preview_run["baseline"].report


@then("the preview SHALL contain no clips")
def _the_preview_contains_no_clips(preview_run: dict[str, Any]) -> None:
    assert _emitted(preview_run).clip_names == ()


@then("no preview failure SHALL be reported")
def _no_preview_failure_is_reported(preview_run: dict[str, Any]) -> None:
    assert preview_run["outcome"].preview_failure is None


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
