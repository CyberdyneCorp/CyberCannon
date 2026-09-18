"""Tasks 4.3, 4.4 and 4.6 — the one validation, as a use case.

Every test here runs over hand-built `MeshFacts` through the in-memory fakes:
no file on disk, no extraction library, no network. That is D1 holding at the
use-case level, not only in the rule suite.

The two properties that are easy to get wrong and are asserted below:

* **the verdict depends only on the facts and the effective spec** — identical
  facts extracted from different formats produce identical violations;
* **preview emission cannot change the verdict** (D7) — the emitter raising, the
  blob store raising, anything raising, leaves a passing run passing.
"""

from __future__ import annotations

import pytest

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.mesh_inspector import MeshUnreadable, UnsupportedExport
from cybercanon.application.ports.preview import PreviewUnavailable
from cybercanon.application.ports.spec_store import ProjectConfig, SpecNotFound
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.design import Design, Socket
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFacts, MeshFormat
from cybercanon.domain.rules import budgets, conventions, sockets
from cybercanon.domain.violations import Severity, SpecViolation

ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
ORPHAN_EXPORT = "sandbox/scratch.glb"
OBJECT = "SM_mech_scout_LOD0"


def an_asset(**blocks: object) -> Asset:
    return Asset(id=AssetId(ASSET_ID), name="Scout Mech", **blocks)  # type: ignore[arg-type]


def a_store(asset: Asset | None = None, project: ProjectConfig | None = None) -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, asset if asset is not None else an_asset())
    if project is not None:
        store.set_project(project)
    return store


def an_inspector(facts: MeshFacts, export: str = EXPORT) -> InMemoryMeshInspector:
    inspector = InMemoryMeshInspector()
    inspector.add(export, facts)
    return inspector


def a_glb(**observed: object) -> MeshFacts:
    return facts_for(MeshFormat.GLB, **observed)


# --------------------------------------------------------------------------
# 4.3 — discovery, merge, extraction, decision
# --------------------------------------------------------------------------


def test_the_governing_spec_is_discovered_from_the_export_path() -> None:
    """D9 — the CLI does no path arithmetic; the store walks upward."""
    outcome = validate_export(
        EXPORT,
        spec_store=a_store(an_asset(constraints=Constraints(tri_budget=12000))),
        mesh_inspector=an_inspector(a_glb(triangles=11840)),
    )

    assert outcome.spec_path == SPEC_PATH
    assert outcome.asset_id == ASSET_ID
    assert outcome.passed


def test_an_export_governed_by_no_spec_is_an_operation_failure() -> None:
    with pytest.raises(SpecNotFound) as raised:
        validate_export(
            ORPHAN_EXPORT,
            spec_store=a_store(),
            mesh_inspector=an_inspector(a_glb(triangles=10), export=ORPHAN_EXPORT),
        )

    assert ORPHAN_EXPORT in raised.value.message


def test_project_defaults_apply_when_the_asset_declares_nothing() -> None:
    """D3 — the merge happens once, before any rule runs."""
    outcome = validate_export(
        EXPORT,
        spec_store=a_store(project=ProjectConfig(defaults=Constraints(up_axis="Z"))),
        mesh_inspector=an_inspector(a_glb(up_axis="Y")),
    )

    (violation,) = outcome.report.violations_of(conventions.UP_AXIS)
    assert violation.expected == "Z"
    assert violation.observed == "Y"


def test_the_asset_overrides_the_project_default() -> None:
    outcome = validate_export(
        EXPORT,
        spec_store=a_store(
            an_asset(constraints=Constraints(tri_budget=8000)),
            project=ProjectConfig(defaults=Constraints(tri_budget=20000)),
        ),
        mesh_inspector=an_inspector(a_glb(triangles=11840)),
    )

    (violation,) = outcome.report.violations_of(budgets.TRI_BUDGET)
    assert violation.expected == "8000"


def test_declared_sockets_reach_the_rules_through_the_use_case() -> None:
    """The closed loop, end to end: design declares it, the export is gated on it."""
    asset = an_asset(design=Design(sockets=(Socket(name="SOCKET_muzzle_l", purpose="vfx"),)))

    outcome = validate_export(
        EXPORT,
        spec_store=a_store(asset),
        mesh_inspector=an_inspector(a_glb(empties=("SOCKET_jet_r",))),
    )

    (violation,) = outcome.report.violations_of(sockets.SOCKET_MISSING)
    assert violation.subject == "SOCKET_muzzle_l"
    assert not outcome.passed


def test_identical_facts_from_different_formats_produce_identical_reports() -> None:
    """The verdict depends on the facts, never on the file they came from."""
    observed = {"triangles": 14310, "objects": (OBJECT,)}
    reports = tuple(
        validate_export(
            EXPORT,
            spec_store=a_store(an_asset(constraints=Constraints(tri_budget=12000))),
            mesh_inspector=an_inspector(facts_for(source_format, **observed)),
        ).report
        for source_format in (MeshFormat.GLB, MeshFormat.GLTF)
    )

    first, second = reports
    assert first.export_format is not second.export_format
    assert first.violations == second.violations
    assert first.passed == second.passed


def test_an_unrecognised_field_is_reported_and_the_mesh_is_still_validated() -> None:
    """D5 — version skew is visible, and never fatal."""
    store = InMemorySpecStore()
    warning = SpecViolation(
        rule_id="spec.unknown_field",
        severity=Severity.WARNING,
        subject="constraints.shinyness",
        message="unrecognised field 'shinyness'",
    )
    store.add(SPEC_PATH, an_asset(constraints=Constraints(tri_budget=12000)), warnings=(warning,))

    outcome = validate_export(
        EXPORT, spec_store=store, mesh_inspector=an_inspector(a_glb(triangles=14310))
    )

    assert outcome.spec_warnings == (warning,)
    assert outcome.report.violations_of(budgets.TRI_BUDGET)


# --------------------------------------------------------------------------
# 4.6 — an input the run cannot be made over is never a passing report
# --------------------------------------------------------------------------


def test_an_unreadable_export_fails_the_operation_naming_the_file() -> None:
    inspector = InMemoryMeshInspector()
    inspector.add_unreadable(EXPORT, "unexpected end of file")

    with pytest.raises(MeshUnreadable) as raised:
        validate_export(EXPORT, spec_store=a_store(), mesh_inspector=inspector)

    assert EXPORT in raised.value.message
    assert "unexpected end of file" in raised.value.message


def test_an_unsupported_format_is_refused_by_name_not_validated() -> None:
    inspector = InMemoryMeshInspector()
    inspector.add_unsupported(EXPORT, "3DS")

    with pytest.raises(UnsupportedExport) as raised:
        validate_export(EXPORT, spec_store=a_store(), mesh_inspector=inspector)

    assert "3DS" in raised.value.message
    assert isinstance(raised.value, OperationFailed)


def test_every_operation_failure_is_one_kind_of_exception() -> None:
    """The CLI's exit-code seam (D11) can only be one seam if this holds."""
    assert issubclass(SpecNotFound, OperationFailed)
    assert issubclass(MeshUnreadable, OperationFailed)
    assert issubclass(UnsupportedExport, OperationFailed)
    assert not issubclass(PreviewUnavailable, OperationFailed)


# --------------------------------------------------------------------------
# 4.4 — preview emission, guarded (D7)
# --------------------------------------------------------------------------


def test_no_preview_is_emitted_unless_it_is_asked_for() -> None:
    inspector = an_inspector(a_glb(triangles=11840, objects=(OBJECT,)))

    outcome = validate_export(
        EXPORT, spec_store=a_store(), mesh_inspector=inspector, blob_store=InMemoryBlobStore()
    )

    assert outcome.preview is None
    assert inspector.previewed == []


def test_a_preview_is_emitted_from_the_read_validation_already_paid_for() -> None:
    inspector = an_inspector(a_glb(triangles=11840, objects=(OBJECT,)))
    blobs = InMemoryBlobStore()

    outcome = validate_export(
        EXPORT,
        spec_store=a_store(),
        mesh_inspector=inspector,
        blob_store=blobs,
        emit_preview=True,
    )

    assert inspector.inspected == [EXPORT]
    assert inspector.previewed == [EXPORT]
    assert outcome.preview is not None
    assert outcome.preview.asset_id == ASSET_ID
    assert outcome.preview.source_export == EXPORT
    assert blobs.preview_for(ASSET_ID) == outcome.preview


def test_a_failing_emitter_leaves_a_passing_run_passing() -> None:
    """The test D7 exists for: preview emission raises, the verdict does not move."""
    inspector = an_inspector(a_glb(triangles=11840))
    inspector.fail_preview(EXPORT, PreviewUnavailable("decimation would drop the clips"))

    outcome = validate_export(
        EXPORT,
        spec_store=a_store(an_asset(constraints=Constraints(tri_budget=12000))),
        mesh_inspector=inspector,
        blob_store=InMemoryBlobStore(),
        emit_preview=True,
    )

    assert outcome.passed
    assert outcome.report.violations == ()
    assert outcome.preview is None
    assert outcome.preview_failure is not None
    assert outcome.preview_failure.reason == "decimation would drop the clips"


def test_a_preview_failure_is_a_distinct_condition_not_a_violation() -> None:
    inspector = an_inspector(a_glb(triangles=11840))
    inspector.fail_preview(EXPORT)

    outcome = validate_export(
        EXPORT,
        spec_store=a_store(),
        mesh_inspector=inspector,
        blob_store=InMemoryBlobStore(),
        emit_preview=True,
    )

    assert outcome.report.violations == ()
    assert outcome.preview_failure is not None
    assert outcome.preview_failure.export == EXPORT


def test_an_unreachable_blob_store_cannot_fail_a_validation() -> None:
    blobs = InMemoryBlobStore()
    blobs.fail_with(ConnectionError("minio is unreachable"))

    outcome = validate_export(
        EXPORT,
        spec_store=a_store(an_asset(constraints=Constraints(tri_budget=12000))),
        mesh_inspector=an_inspector(a_glb(triangles=11840)),
        blob_store=blobs,
        emit_preview=True,
    )

    assert outcome.passed
    assert outcome.preview is None
    assert outcome.preview_failure is not None
    assert "minio is unreachable" in outcome.preview_failure.reason


def test_a_preview_never_rescues_a_failing_run_either() -> None:
    outcome = validate_export(
        EXPORT,
        spec_store=a_store(an_asset(constraints=Constraints(tri_budget=12000))),
        mesh_inspector=an_inspector(a_glb(triangles=14310)),
        blob_store=InMemoryBlobStore(),
        emit_preview=True,
    )

    assert outcome.preview is not None
    assert not outcome.passed


def test_an_unreadable_export_emits_no_preview_at_all() -> None:
    inspector = InMemoryMeshInspector()
    inspector.add_unreadable(EXPORT, "not a glTF container")
    blobs = InMemoryBlobStore()

    with pytest.raises(MeshUnreadable):
        validate_export(
            EXPORT,
            spec_store=a_store(),
            mesh_inspector=inspector,
            blob_store=blobs,
            emit_preview=True,
        )

    assert inspector.previewed == []
    assert blobs.preview_for(ASSET_ID) is None
