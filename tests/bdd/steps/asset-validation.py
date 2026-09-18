"""Step definitions for `asset-validation` — the rules, and the use case over them.

Group 3 of `add-asset-spec-and-validator` builds the validation decision as pure
domain: `MeshFacts` and the per-format matrix, the effective-spec merge, every
rule, and the three-way dispatch that makes NOT EVALUATED structural. Group 4
adds `validate_export` above it, and with it the three scenarios no rule can
answer on its own — an export in a format the matrix does not cover, a file that
is not a mesh, and a run with every remote service unreachable.

**Every scenario here runs over hand-built `MeshFacts` with zero files on disk.**
That is not a testing convenience, it is the boundary D1 draws: mesh *reading* is
a port, mesh *rules* are domain. A `.glb` fixture appearing in this module would
mean the boundary had moved — the use-case scenarios below reach the same facts
through the in-memory inspector.

The scenarios that stay in `tests/bdd/pending.txt` are the renderings and the
exit-code seam (group 6), the surfaces that must agree with each other (group 6
and `add-web-backend`), and reporting a result to a destination, which is a
separate use case allowed to fail (D10).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when
from typer.testing import CliRunner

from cybercanon.adapters.inbound.cli import payload, rendering
from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.mesh_inspector import MeshUnreadable, UnsupportedExport
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.validate_export import ValidationOutcome, validate_export
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig
from cybercanon.domain.design import Design, Socket, State
from cybercanon.domain.effective_spec import EffectiveSpec, merge
from cybercanon.domain.format_matrix import available_for, facts_for
from cybercanon.domain.mesh_facts import ClipFacts, FactKind, MeshFacts, MeshFormat
from cybercanon.domain.report import Report
from cybercanon.domain.rules import animation, budgets, conventions, format_fitness, run, sockets
from cybercanon.domain.rules import rig as rig_rules
from cybercanon.domain.violations import Severity

ASSET_ID = "mech_scout"
CONVENTION = "A_{asset}_{state}"
NAMING = "SM_{asset}_LOD{n}"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

WALK = "A_mech_scout_walk"
FIRE = "A_mech_scout_fire"
MUZZLE = "SOCKET_muzzle_l"
JET = "SOCKET_jet_r"
SKELETON = "SK_MechScout"

# The feature path is spelled out in every binding on purpose: the traceability
# gates read these bindings statically from the source, so a computed path reads
# as "this scenario does not execute" and fails the build (canon_bdd.implemented).


@pytest.fixture
def validation() -> dict[str, Any]:
    """What this scenario declared, the facts it built, and the report they produced."""
    return {}


def a_spec(**fields: Any) -> EffectiveSpec:
    return EffectiveSpec(asset_id=ASSET_ID, **fields)


def an_asset(**blocks: Any) -> Asset:
    return Asset(id=AssetId(ASSET_ID), name="Scout Mech", **blocks)


def a_glb(**observed: Any) -> MeshFacts:
    return facts_for(MeshFormat.GLB, **observed)


def animated(asset_spec: EffectiveSpec, *clips: ClipFacts) -> Report:
    return run(asset_spec, a_glb(clips=clips))


def with_states(*states: State, frame_rate: float | None = None) -> EffectiveSpec:
    """An asset whose design states resolve to required clips through the convention."""
    return merge(
        an_asset(
            design=Design(states=states),
            constraints=Constraints(
                animation=AnimationDefaults(clip_naming=CONVENTION, frame_rate=frame_rate)
            ),
        )
    )


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Same facts produce the same verdict",
)
def test_same_facts_produce_the_same_verdict() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "An unavailable fact is not defaulted",
)
def test_an_unavailable_fact_is_not_defaulted() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Over budget",
)
def test_over_budget() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Within budget",
)
def test_within_budget() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Unapplied transforms",
)
def test_unapplied_transforms() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Naming pattern mismatch",
)
def test_naming_pattern_mismatch() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Missing socket blocks the export",
)
def test_missing_socket_blocks_the_export() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Extra attachment points are not violations",
)
def test_extra_attachment_points_are_not_violations() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Missing clip blocks the export",
)
def test_missing_clip_blocks_the_export() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Extra clips are not violations",
)
def test_extra_clips_are_not_violations() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "An asset requiring no clips is unaffected",
)
def test_an_asset_requiring_no_clips_is_unaffected() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Frame rate mismatch",
)
def test_frame_rate_mismatch() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Missing root motion",
)
def test_missing_root_motion() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Clip shorter than the declared minimum",
)
def test_clip_shorter_than_the_declared_minimum() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Over the bone budget",
)
def test_over_the_bone_budget() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Within the bone budget",
)
def test_within_the_bone_budget() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Rig declared but export is not skinned",
)
def test_rig_declared_but_export_is_not_skinned() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Matrix governs OBJ",
)
def test_matrix_governs_obj() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Unit scale cannot be judged from OBJ",
)
def test_unit_scale_cannot_be_judged_from_obj() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Not evaluated is distinguishable from passed",
)
def test_not_evaluated_is_distinguishable_from_passed() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Not evaluated alone does not fail the run",
)
def test_not_evaluated_alone_does_not_fail_the_run() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "OBJ for an animated asset",
)
def test_obj_for_an_animated_asset() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "OBJ for a static asset with no such declarations",
)
def test_obj_for_a_static_asset() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Warnings alone pass",
)
def test_warnings_alone_pass() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Stable rule identifiers",
)
def test_stable_rule_identifiers() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Not-evaluated rules are listed separately",
)
def test_not_evaluated_rules_are_listed_separately() -> None: ...


# --------------------------------------------------------------------------
# GIVEN
# --------------------------------------------------------------------------


@given("two exports in different file formats that yield identical mesh facts")
def _two_exports_yielding_identical_facts(validation: dict[str, Any]) -> None:
    observed = {"triangles": 14310, "objects": ("SM_mech_scout_LOD0",)}
    validation["exports"] = (
        facts_for(MeshFormat.GLB, **observed),
        facts_for(MeshFormat.GLTF, **observed),
    )
    validation["spec"] = a_spec(tri_budget=12000)


@given("an export in a format that records no bone count")
def _an_export_in_a_format_without_bone_counts(validation: dict[str, Any]) -> None:
    validation["format"] = MeshFormat.OBJ


@given("an effective `tri_budget` of 12000")
def _an_effective_tri_budget(validation: dict[str, Any]) -> None:
    validation["spec"] = a_spec(tri_budget=12000)


@given("an effective naming pattern of `SM_{asset}_LOD{n}`")
def _an_effective_naming_pattern(validation: dict[str, Any]) -> None:
    validation["spec"] = a_spec(naming=NAMING)


@given("`design.sockets` declares `SOCKET_muzzle_l` and `SOCKET_jet_r`")
def _two_declared_sockets(validation: dict[str, Any]) -> None:
    validation["spec"] = _sockets(MUZZLE, JET)


@given("`design.sockets` declares `SOCKET_muzzle_l`")
def _one_declared_socket(validation: dict[str, Any]) -> None:
    validation["spec"] = _sockets(MUZZLE)


@given(
    "an asset whose states resolve to required clips `A_mech_scout_walk` and `A_mech_scout_fire`"
)
def _two_required_clips(validation: dict[str, Any]) -> None:
    validation["spec"] = with_states(State(name="walk"), State(name="fire"))


@given("an asset whose only required clip is `A_mech_scout_walk`")
def _one_required_clip(validation: dict[str, Any]) -> None:
    validation["spec"] = with_states(State(name="walk"))


@given("an asset whose states all declare themselves unanimated")
def _no_required_clips(validation: dict[str, Any]) -> None:
    validation["spec"] = with_states(
        State(name="destroyed", animated=False), State(name="idle", animated=False)
    )


@given("a state declaring `frame_rate: 30`")
def _a_state_declaring_a_frame_rate(validation: dict[str, Any]) -> None:
    validation["spec"] = with_states(State(name="walk", frame_rate=30.0))


@given("a state `walk` declaring `root_motion: true`")
def _a_state_declaring_root_motion(validation: dict[str, Any]) -> None:
    validation["spec"] = with_states(State(name="walk", root_motion=True))


@given("a state declaring a minimum duration of 1.0 second")
def _a_state_declaring_a_minimum_duration(validation: dict[str, Any]) -> None:
    validation["spec"] = with_states(State(name="walk", min_duration_s=1.0))


@given("an effective `rig.max_bones` of 96")
def _an_effective_bone_budget(validation: dict[str, Any]) -> None:
    validation["spec"] = a_spec(rig=Rig(max_bones=96))


@given("an asset declaring a rig")
def _an_asset_declaring_a_rig(validation: dict[str, Any]) -> None:
    validation["spec"] = merge(
        an_asset(constraints=Constraints(rig=Rig(skeleton=SKELETON, max_bones=96)))
    )


@given("an asset declaring `unit_scale: 1.0`")
def _an_asset_declaring_a_unit_scale(validation: dict[str, Any]) -> None:
    validation["spec"] = a_spec(unit_scale=1.0)


@given("a validation in which one rule passed and another could not be evaluated")
def _one_passed_one_not_evaluated(validation: dict[str, Any]) -> None:
    validation["report"] = run(
        a_spec(tri_budget=12000, unit_scale=1.0),
        facts_for(MeshFormat.OBJ, triangles=11840),
    )


@given("a validation producing no violations and several not-evaluated rules")
def _no_violations_and_several_suppressed(validation: dict[str, Any]) -> None:
    validation["report"] = run(
        a_spec(tri_budget=12000, unit_scale=1.0, up_axis="Z"),
        facts_for(MeshFormat.OBJ, triangles=11840),
    )


@given("an asset whose states resolve to required animation clips")
def _an_animated_asset(validation: dict[str, Any]) -> None:
    validation["spec"] = with_states(State(name="walk"))


@given("an asset declaring no sockets, no rig and no animated states")
def _a_static_asset(validation: dict[str, Any]) -> None:
    validation["spec"] = merge(an_asset(constraints=Constraints(tri_budget=12000)))


@given("a validation in which two rules could not be evaluated")
def _exactly_two_rules_suppressed(validation: dict[str, Any]) -> None:
    """A deliberately narrow mask: everything is readable except scale and axis."""
    narrow = MeshFacts(
        source_format=MeshFormat.GLB,
        available=available_for(MeshFormat.GLB) - {FactKind.UNIT_SCALE, FactKind.UP_AXIS},
        triangles=11840,
        objects=("SM_mech_scout_LOD0",),
        transforms_applied=True,
    )
    validation["report"] = run(a_spec(unit_scale=1.0, up_axis="Z", tri_budget=12000), narrow)


def _sockets(*names: str) -> EffectiveSpec:
    design = Design(sockets=tuple(Socket(name=name, purpose="attachment") for name in names))
    return merge(an_asset(design=design))


# --------------------------------------------------------------------------
# WHEN
# --------------------------------------------------------------------------


@when("both are validated against the same specification")
def _both_are_validated(validation: dict[str, Any]) -> None:
    validation["reports"] = tuple(run(validation["spec"], facts) for facts in validation["exports"])


@when("facts are extracted from it")
def _facts_are_extracted(validation: dict[str, Any]) -> None:
    validation["facts"] = facts_for(validation["format"], triangles=4200)


@when("an export containing 14310 triangles is validated")
def _an_over_budget_export_is_validated(validation: dict[str, Any]) -> None:
    validation["report"] = run(validation["spec"], a_glb(triangles=14310))


@when("an export containing 11840 triangles is validated")
def _an_under_budget_export_is_validated(validation: dict[str, Any]) -> None:
    validation["report"] = run(validation["spec"], a_glb(triangles=11840))


@when("an export contains an object whose transforms are not applied")
def _an_export_with_unapplied_transforms(validation: dict[str, Any]) -> None:
    validation["object"] = "SM_mech_scout_LOD0"
    validation["report"] = run(
        a_spec(), a_glb(transforms_applied=False, objects=(validation["object"],))
    )


@when("an export contains an object named `mesh_final_v2`")
def _an_export_with_a_misnamed_object(validation: dict[str, Any]) -> None:
    validation["object"] = "mesh_final_v2"
    validation["report"] = run(validation["spec"], a_glb(objects=("mesh_final_v2",)))


@when("an export containing only an attachment point named `SOCKET_jet_r` is validated")
def _an_export_with_one_socket(validation: dict[str, Any]) -> None:
    validation["report"] = run(validation["spec"], a_glb(empties=(JET,)))


@when("an export contains `SOCKET_muzzle_l` and an additional `SOCKET_spare`")
def _an_export_with_an_extra_socket(validation: dict[str, Any]) -> None:
    validation["report"] = run(validation["spec"], a_glb(empties=(MUZZLE, "SOCKET_spare")))


@when("an export containing only a clip named `A_mech_scout_walk` is validated")
def _an_export_with_one_clip(validation: dict[str, Any]) -> None:
    validation["report"] = animated(validation["spec"], ClipFacts(name=WALK))


@when("an export contains `A_mech_scout_walk` and an additional `A_mech_scout_test`")
def _an_export_with_an_extra_clip(validation: dict[str, Any]) -> None:
    validation["report"] = animated(
        validation["spec"], ClipFacts(name=WALK), ClipFacts(name="A_mech_scout_test")
    )


@when("an export containing no animation clips is validated")
def _an_export_with_no_clips(validation: dict[str, Any]) -> None:
    validation["report"] = animated(validation["spec"])


@when("its clip is exported at 24 frames per second")
def _the_clip_is_exported_at_24(validation: dict[str, Any]) -> None:
    validation["report"] = animated(validation["spec"], ClipFacts(name=WALK, frame_rate=24.0))


@when("its clip animates no translation of the root")
def _the_clip_has_no_root_motion(validation: dict[str, Any]) -> None:
    validation["report"] = animated(validation["spec"], ClipFacts(name=WALK, has_root_motion=False))


@when("its clip is 0.4 seconds long")
def _the_clip_is_too_short(validation: dict[str, Any]) -> None:
    validation["report"] = animated(validation["spec"], ClipFacts(name=WALK, duration_s=0.4))


@when("an export whose skeleton has 118 bones is validated")
def _an_export_over_the_bone_budget(validation: dict[str, Any]) -> None:
    validation["report"] = run(validation["spec"], a_glb(bone_count=118, is_skinned=True))


@when("an export whose skeleton has 74 bones is validated")
def _an_export_within_the_bone_budget(validation: dict[str, Any]) -> None:
    validation["report"] = run(validation["spec"], a_glb(bone_count=74, is_skinned=True))


@when("an export containing no skinning is validated")
def _an_unskinned_export(validation: dict[str, Any]) -> None:
    validation["report"] = run(validation["spec"], a_glb(is_skinned=False, bone_count=0))


@when("the fact availability of an `OBJ` export is resolved")
def _obj_availability_is_resolved(validation: dict[str, Any]) -> None:
    validation["available"] = available_for(MeshFormat.OBJ)


@when("an `OBJ` export is validated")
@when("an `OBJ` export is validated for it")
def _an_obj_export_is_validated(validation: dict[str, Any]) -> None:
    validation["report"] = run(
        validation["spec"], facts_for(MeshFormat.OBJ, triangles=4200, objects=("mech_scout",))
    )


@when("the report is read")
@when("the overall outcome is computed")
@when("the report is produced")
def _the_report_is_read(validation: dict[str, Any]) -> None:
    assert isinstance(validation["report"], Report)


@when("a validation produces only `warning` violations")
def _a_validation_producing_only_warnings(validation: dict[str, Any]) -> None:
    validation["report"] = run(a_spec(naming=NAMING), a_glb(objects=("mesh_final_v2",)))


@when("the same rule is violated in two different runs")
def _the_same_rule_violated_twice(validation: dict[str, Any]) -> None:
    spec = a_spec(tri_budget=12000)
    validation["reports"] = (
        run(spec, a_glb(triangles=14310)),
        run(spec, facts_for(MeshFormat.FBX, triangles=99999)),
    )


# --------------------------------------------------------------------------
# THEN
# --------------------------------------------------------------------------


@then("the resulting violations SHALL be identical")
def _the_violations_are_identical(validation: dict[str, Any]) -> None:
    first, second = validation["reports"]
    assert first.export_format is not second.export_format
    assert first.violations == second.violations
    assert first.passed == second.passed


@then("the bone count SHALL be marked unavailable")
def _the_bone_count_is_unavailable(validation: dict[str, Any]) -> None:
    assert not validation["facts"].has(FactKind.BONE_COUNT)


@then("it SHALL NOT be reported as zero or as any other substitute value")
def _the_bone_count_has_no_substitute(validation: dict[str, Any]) -> None:
    facts: MeshFacts = validation["facts"]
    assert facts.bone_count is None
    assert facts.value(FactKind.BONE_COUNT) is None


@then("a violation SHALL be reported stating observed 14310 and allowed 12000")
def _the_budget_violation_states_both_values(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(budgets.TRI_BUDGET)
    assert violation.observed == "14310"
    assert violation.expected == "12000"


@then("no triangle budget violation SHALL be reported")
def _no_triangle_budget_violation(validation: dict[str, Any]) -> None:
    assert validation["report"].violations_of(budgets.TRI_BUDGET) == ()


@then("a violation SHALL be reported naming that object")
def _the_violation_names_the_object(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(conventions.TRANSFORMS)
    assert validation["object"] in violation.subject
    assert validation["object"] in violation.message


@then("a violation SHALL be reported naming that object and the expected pattern")
def _the_violation_names_the_object_and_the_pattern(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(conventions.NAMING)
    assert violation.subject == validation["object"]
    assert violation.expected == NAMING


@then("exactly one violation SHALL be reported, naming `SOCKET_muzzle_l`")
def _exactly_one_socket_violation(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(sockets.SOCKET_MISSING)
    assert violation.subject == MUZZLE


@then("no socket violation SHALL be reported")
def _no_socket_violation(validation: dict[str, Any]) -> None:
    assert validation["report"].violations_of(sockets.SOCKET_MISSING) == ()


@then("exactly one violation SHALL be reported, naming `A_mech_scout_fire`")
def _exactly_one_clip_violation(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(animation.CLIP_MISSING)
    assert violation.subject == FIRE


@then("the violation SHALL name the state that required it")
def _the_clip_violation_names_the_state(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(animation.CLIP_MISSING)
    assert "fire" in violation.message


@then("no animation clip violation SHALL be reported")
def _no_animation_clip_violation(validation: dict[str, Any]) -> None:
    assert validation["report"].violations_of(animation.CLIP_MISSING) == ()


@then("a violation SHALL be reported naming the clip, the expected 30 and the observed 24")
def _the_frame_rate_violation(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(animation.FRAME_RATE)
    assert violation.subject == WALK
    assert violation.expected == "30.0"
    assert violation.observed == "24.0"


@then("a violation SHALL be reported naming the clip and the expectation")
def _the_root_motion_violation(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(animation.ROOT_MOTION)
    assert violation.subject == WALK
    assert violation.expected == "root motion"


@then("a violation SHALL be reported stating observed 0.4 and the declared minimum 1.0")
def _the_duration_violation(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(animation.DURATION)
    assert violation.observed == "0.4"
    assert violation.expected == "1.0"


@then("a violation SHALL be reported stating observed 118 and allowed 96")
def _the_bone_budget_violation(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(rig_rules.BONE_BUDGET)
    assert violation.observed == "118"
    assert violation.expected == "96"


@then("no bone budget violation SHALL be reported")
def _no_bone_budget_violation(validation: dict[str, Any]) -> None:
    assert validation["report"].violations_of(rig_rules.BONE_BUDGET) == ()


@then("a violation SHALL be reported naming the asset and the declared skeleton")
def _the_skinning_violation(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(rig_rules.NOT_SKINNED)
    assert violation.subject == SKELETON
    assert ASSET_ID in violation.message
    assert SKELETON in violation.message


@then(
    "animation clips, frame rate, bone count, skinning, attachment points, unit "
    "scale and up axis SHALL all be marked unavailable"
)
def _obj_yields_none_of_those(validation: dict[str, Any]) -> None:
    absent = (
        FactKind.CLIPS,
        FactKind.FRAME_RATE,
        FactKind.BONE_COUNT,
        FactKind.SKINNING,
        FactKind.EMPTIES,
        FactKind.UNIT_SCALE,
        FactKind.UP_AXIS,
    )
    assert not set(absent) & validation["available"]


@then("triangle count, object names and material names SHALL be marked available")
def _obj_yields_those(validation: dict[str, Any]) -> None:
    present = (FactKind.TRIANGLES, FactKind.OBJECTS, FactKind.MATERIALS)
    assert set(present) <= validation["available"]


@then("the unit scale rule SHALL be reported as not evaluated")
def _the_unit_scale_rule_is_not_evaluated(validation: dict[str, Any]) -> None:
    report: Report = validation["report"]
    assert not report.evaluated(conventions.UNIT_SCALE)
    assert report.violations_of(conventions.UNIT_SCALE) == ()
    assert conventions.UNIT_SCALE not in report.passed_rules


@then("the report SHALL state that the format carries no unit scale")
def _the_report_states_the_reason(validation: dict[str, Any]) -> None:
    entry = validation["report"].not_evaluated_rule(conventions.UNIT_SCALE)
    assert entry is not None
    assert entry.missing_fact is FactKind.UNIT_SCALE
    assert entry.reason == "OBJ carries no unit scale"


@then("the two rules SHALL be distinguishable by outcome")
def _the_two_rules_are_distinguishable(validation: dict[str, Any]) -> None:
    report: Report = validation["report"]
    assert budgets.TRI_BUDGET in report.passed_rules
    assert not report.evaluated(conventions.UNIT_SCALE)


@then("the not-evaluated rule SHALL NOT appear as satisfied")
def _the_not_evaluated_rule_is_not_satisfied(validation: dict[str, Any]) -> None:
    report: Report = validation["report"]
    assert conventions.UNIT_SCALE not in report.passed_rules


@then("it SHALL be passing")
def _the_outcome_is_passing(validation: dict[str, Any]) -> None:
    report: Report = validation["report"]
    assert report.not_evaluated
    assert report.violations == ()
    assert report.passed


@then(
    "an `error`-severity violation SHALL be reported stating that `OBJ` is an "
    "unsuitable export format for this asset"
)
def _an_unsuitable_format_violation(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(format_fitness.UNSUITABLE_FORMAT)
    assert violation.severity is Severity.ERROR
    assert "OBJ" in violation.message
    assert not validation["report"].passed


@then("the violation SHALL name the animation clip requirement")
def _the_violation_names_the_clip_requirement(validation: dict[str, Any]) -> None:
    (violation,) = validation["report"].violations_of(format_fitness.UNSUITABLE_FORMAT)
    assert violation.subject == "animation clips"


@then("no unsuitable-format violation SHALL be reported")
def _no_unsuitable_format_violation(validation: dict[str, Any]) -> None:
    assert validation["report"].violations_of(format_fitness.UNSUITABLE_FORMAT) == ()


@then("the rules whose facts `OBJ` cannot yield SHALL be reported as not evaluated")
def _the_suppressed_rules_are_listed(validation: dict[str, Any]) -> None:
    suppressed = {entry.rule_id for entry in validation["report"].not_evaluated}
    assert {
        conventions.UNIT_SCALE,
        conventions.UP_AXIS,
        sockets.SOCKET_MISSING,
        animation.CLIP_MISSING,
        rig_rules.NOT_SKINNED,
        rig_rules.BONE_BUDGET,
    } <= suppressed


@then("the overall outcome SHALL be passing")
def _the_overall_outcome_is_passing(validation: dict[str, Any]) -> None:
    assert validation["report"].passed


@then("the warnings SHALL still be listed in the report")
def _the_warnings_are_listed(validation: dict[str, Any]) -> None:
    report: Report = validation["report"]
    assert len(report.warnings) == 1
    assert report.errors == ()


@then("both violations SHALL carry the same rule identifier")
def _both_carry_the_same_rule_id(validation: dict[str, Any]) -> None:
    first, second = validation["reports"]
    assert [v.rule_id for v in first.violations] == [v.rule_id for v in second.violations]
    assert first.violations[0].rule_id == budgets.TRI_BUDGET


@then("it SHALL list those two rules with their reasons")
def _the_two_suppressed_rules_are_listed(validation: dict[str, Any]) -> None:
    report: Report = validation["report"]
    assert {entry.rule_id for entry in report.not_evaluated} == {
        conventions.UNIT_SCALE,
        conventions.UP_AXIS,
    }
    assert all(entry.reason for entry in report.not_evaluated)


@then("they SHALL NOT appear in the list of violations")
def _the_suppressed_rules_are_not_violations(validation: dict[str, Any]) -> None:
    reported = {violation.rule_id for violation in validation["report"].violations}
    assert not reported & {conventions.UNIT_SCALE, conventions.UP_AXIS}


# --------------------------------------------------------------------------
# Group 4 — the scenarios only the use case can answer
#
# A rule cannot refuse a file it was never handed: "no identity, no network",
# "this format is not in the matrix" and "this file is not a mesh" are decisions
# `validate_export` makes before any rule runs. They are exercised here through
# the in-memory ports, so they still run with zero files on disk.
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Validation succeeds while services are down",
)
def test_validation_succeeds_while_services_are_down() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Unsupported format is refused, not assumed",
)
def test_unsupported_format_is_refused() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Unparseable export",
)
def test_unparseable_export() -> None: ...


def _a_local_store() -> InMemorySpecStore:
    """One asset, on disk in a working copy — no identity, no service, no token."""
    store = InMemorySpecStore()
    store.add(SPEC_PATH, an_asset(constraints=Constraints(tri_budget=12000)))
    return store


def _validate(validation: dict[str, Any], **ports: Any) -> None:
    """Run the use case, recording the verdict or the operation failure."""
    try:
        validation["outcome"] = validate_export(EXPORT, **ports)
    except OperationFailed as failure:
        validation["failure"] = failure


@given("the identity provider and all remote services are unreachable")
def _every_remote_service_is_down(validation: dict[str, Any]) -> None:
    blobs = InMemoryBlobStore()
    blobs.fail_with(ConnectionError("the network is unreachable"))
    validation["blob_store"] = blobs


@when("an export is validated locally")
def _an_export_is_validated_locally(validation: dict[str, Any]) -> None:
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, a_glb(triangles=14310))
    inspector.fail_preview(EXPORT, ConnectionError("the network is unreachable"))
    _validate(
        validation,
        spec_store=_a_local_store(),
        mesh_inspector=inspector,
        blob_store=validation["blob_store"],
        emit_preview=True,
    )


@then("validation SHALL complete and report its violations normally")
def _validation_completed_normally(validation: dict[str, Any]) -> None:
    outcome = validation["outcome"]
    (violation,) = outcome.report.violations_of(budgets.TRI_BUDGET)
    assert violation.observed == "14310"
    assert violation.expected == "12000"
    assert not outcome.passed


@when("validation is requested for an export in a format the matrix does not cover")
def _an_export_in_an_uncovered_format(validation: dict[str, Any]) -> None:
    inspector = InMemoryMeshInspector()
    inspector.add_unsupported(EXPORT, "3DS")
    _validate(validation, spec_store=_a_local_store(), mesh_inspector=inspector)


@then("the system SHALL report an unsupported export format naming the format")
def _the_unsupported_format_is_named(validation: dict[str, Any]) -> None:
    failure = validation["failure"]
    assert isinstance(failure, UnsupportedExport)
    assert failure.format_name == "3DS"
    assert "3DS" in failure.message


@then("SHALL NOT report the export as passing")
@then("the overall outcome SHALL be failing")
def _no_verdict_was_produced(validation: dict[str, Any]) -> None:
    """An operation that could not run has no verdict — and never a passing one."""
    assert isinstance(validation["failure"], OperationFailed)
    assert "outcome" not in validation


@when("validation is run against a file that is not a readable mesh")
def _a_file_that_is_not_a_mesh(validation: dict[str, Any]) -> None:
    inspector = InMemoryMeshInspector()
    inspector.add_unreadable(EXPORT, "unexpected end of file")
    _validate(validation, spec_store=_a_local_store(), mesh_inspector=inspector)


@then("the system SHALL report a failure naming the file and the reason")
def _the_failure_names_the_file_and_the_reason(validation: dict[str, Any]) -> None:
    failure = validation["failure"]
    assert isinstance(failure, MeshUnreadable)
    assert failure.export == EXPORT
    assert failure.reason == "unexpected end of file"
    assert EXPORT in failure.message


# --------------------------------------------------------------------------
# One verdict across every surface, rendered two ways (group 6)
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Both renderings agree",
)
def test_both_renderings_agree() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-validation.feature",
    "Command line and application agree",
)
def test_command_line_and_application_agree() -> None: ...


def _an_outcome(facts: MeshFacts) -> ValidationOutcome:
    """A verdict with something in all three lists, as a surface would receive it."""
    spec = merge(an_asset(constraints=Constraints(tri_budget=12000, naming=NAMING)))
    return ValidationOutcome(report=run(spec, facts, export=EXPORT), spec_path=SPEC_PATH)


@when("a report is rendered as structured data and as prose")
def _a_report_is_rendered_both_ways(validation: dict[str, Any]) -> None:
    outcome = _an_outcome(facts_for(MeshFormat.OBJ, triangles=14310, objects=("body",)))
    validation["outcome"] = outcome
    document = payload.validation_payload([outcome])
    validation["prose"] = rendering.render_validations([outcome])
    validation["document"] = document
    validation["structured"] = document["results"][0]


@then("both SHALL contain the same violations, severities and overall outcome")
def _both_renderings_state_the_same_verdict(validation: dict[str, Any]) -> None:
    report = validation["outcome"].report
    prose, structured = validation["prose"], validation["structured"]
    assert [entry["rule_id"] for entry in structured["violations"]] == [
        violation.rule_id for violation in report.violations
    ]
    for violation in report.violations:
        assert violation.rule_id in prose
        assert str(violation.severity) in prose
    assert structured["outcome"] == report.outcome
    assert validation["document"]["passed"] is report.passed
    assert ("FAILING" in prose) is not report.passed


@then("both SHALL contain the same not-evaluated rules with their reasons")
def _both_renderings_list_the_same_suppressions(validation: dict[str, Any]) -> None:
    report = validation["outcome"].report
    prose, structured = validation["prose"], validation["structured"]
    assert report.not_evaluated, "this scenario needs a format that suppresses rules"
    assert [entry["rule_id"] for entry in structured["not_evaluated"]] == [
        entry.rule_id for entry in report.not_evaluated
    ]
    for entry in report.not_evaluated:
        assert entry.rule_id in prose
        assert entry.reason in prose


@given("an export that fails its triangle budget")
def _an_over_budget_export(validation: dict[str, Any]) -> None:
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, a_glb(triangles=14310, objects=("SM_mech_scout_LOD0",)))
    validation["spec_store"] = _a_local_store()
    validation["mesh_inspector"] = inspector


@when("it is validated from the command line and again from any other surface")
def _validated_from_two_surfaces(validation: dict[str, Any]) -> None:
    """The CLI and a direct call, over the *same* container — because it is one use case."""
    container = Container(
        spec_store=validation["spec_store"],
        mesh_inspector=validation["mesh_inspector"],
    )
    result = CliRunner().invoke(build_app(container), ["validate", "--json", EXPORT])
    assert result.exit_code == 1, result.output
    validation["from_cli"] = json.loads(result.stdout)["results"][0]["violations"]
    validation["from_use_case"] = container.validate_export(EXPORT).report.violations


@then("both SHALL report the same violations with the same severities")
def _both_surfaces_report_the_same(validation: dict[str, Any]) -> None:
    assert validation["from_use_case"], "the export was supposed to fail its budget"
    assert [
        (entry["rule_id"], entry["severity"], entry["subject"], entry["observed"])
        for entry in validation["from_cli"]
    ] == [
        (violation.rule_id, str(violation.severity), violation.subject, violation.observed)
        for violation in validation["from_use_case"]
    ]
