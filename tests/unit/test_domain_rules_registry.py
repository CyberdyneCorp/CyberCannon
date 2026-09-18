"""Tasks 3.13, 3.14 and 3.15 — dispatch, format fitness, and the registry itself.

The registry is the inventory: every rule has a unique, stable identifier, a
default severity and a non-empty declared fact set. The dispatch is what turns
that declaration into the third outcome — a rule whose facts the format cannot
yield is never called, so it can neither pass nor fail by accident.
"""

from __future__ import annotations

import pytest

from cybercanon.domain.constraints import Rig
from cybercanon.domain.effective_spec import EffectiveSpec, RequiredClip
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import ClipFacts, FactKind, MeshFacts, MeshFormat
from cybercanon.domain.report import NotEvaluated, Passed, Violated
from cybercanon.domain.rules import (
    BY_ID,
    REGISTRY,
    RULE_IDS,
    Rule,
    evaluate,
    format_fitness,
    run,
)
from cybercanon.domain.violations import Severity

ASSET = "mech_scout"
WALK = "A_mech_scout_walk"
TEMPLATE = "SM_{asset}_LOD{n}"


def a_spec(**fields: object) -> EffectiveSpec:
    return EffectiveSpec(asset_id=ASSET, **fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# 3.15 — the inventory
# --------------------------------------------------------------------------


def test_every_rule_identifier_is_unique() -> None:
    assert len(set(RULE_IDS)) == len(RULE_IDS) == len(REGISTRY)


@pytest.mark.parametrize("rule", REGISTRY, ids=RULE_IDS)
def test_every_rule_declares_a_non_empty_fact_set(rule: Rule) -> None:
    assert rule.consumes
    assert all(isinstance(kind, FactKind) for kind in rule.consumes)


@pytest.mark.parametrize("rule", REGISTRY, ids=RULE_IDS)
def test_every_rule_identifier_is_a_stable_dotted_name(rule: Rule) -> None:
    """A rule id is what a project configures severity against; it is not prose."""
    assert "." in rule.rule_id
    assert rule.rule_id == rule.rule_id.strip().lower()
    assert BY_ID[rule.rule_id] is rule


@pytest.mark.parametrize("rule", REGISTRY, ids=RULE_IDS)
def test_every_rule_has_a_default_severity(rule: Rule) -> None:
    assert rule.severity in (Severity.ERROR, Severity.WARNING)


def test_a_rule_that_consumes_nothing_is_refused_at_registration() -> None:
    """A rule with no facts could never be NOT EVALUATED, so it would pass in silence."""
    with pytest.raises(ValueError, match="declares no facts"):
        Rule("bad.rule", Severity.ERROR, frozenset(), lambda spec, facts: ())


def test_the_severity_of_a_violation_comes_from_the_registration() -> None:
    """A project lowering a rule to a warning must never have to edit the rule."""
    lowered = Rule(
        "tri_budget.exceeded",
        Severity.WARNING,
        BY_ID["tri_budget.exceeded"].consumes,
        BY_ID["tri_budget.exceeded"].check,
    )
    facts = facts_for(MeshFormat.GLB, triangles=14310)

    (outcome,) = evaluate(lowered, a_spec(tri_budget=12000), facts)

    assert isinstance(outcome, Violated)
    assert outcome.violation.severity is Severity.WARNING


# --------------------------------------------------------------------------
# 3.13 — three-way dispatch
# --------------------------------------------------------------------------


def test_a_rule_whose_fact_is_unavailable_is_neither_passed_nor_violated() -> None:
    narrow = MeshFacts(
        source_format=MeshFormat.GLB,
        available=frozenset({FactKind.TRIANGLES}),
        triangles=11840,
    )

    (outcome,) = evaluate(BY_ID["unit_scale.mismatch"], a_spec(unit_scale=1.0), narrow)

    assert isinstance(outcome, NotEvaluated)
    assert outcome.rule_id == "unit_scale.mismatch"
    assert outcome.missing_fact is FactKind.UNIT_SCALE
    assert outcome.reason == "GLB carries no unit scale"


def test_a_rule_whose_facts_are_available_runs() -> None:
    facts = facts_for(MeshFormat.GLB, unit_scale=1.0)

    (outcome,) = evaluate(BY_ID["unit_scale.mismatch"], a_spec(unit_scale=1.0), facts)

    assert isinstance(outcome, Passed)


def test_a_rule_emits_one_outcome_per_violation() -> None:
    facts = facts_for(MeshFormat.GLB, empties=())
    spec = a_spec(required_sockets=("SOCKET_muzzle_l", "SOCKET_jet_r"))

    outcomes = evaluate(BY_ID["socket.missing"], spec, facts)

    assert len(outcomes) == 2
    assert all(isinstance(outcome, Violated) for outcome in outcomes)


def test_the_unit_scale_rule_is_not_evaluated_for_obj_and_says_why() -> None:
    report = run(a_spec(unit_scale=1.0), facts_for(MeshFormat.OBJ, triangles=4200))

    entry = report.not_evaluated_rule("unit_scale.mismatch")
    assert entry is not None
    assert entry.reason == "OBJ carries no unit scale"
    assert report.passed


def test_identical_facts_in_different_formats_produce_identical_violations() -> None:
    spec = a_spec(tri_budget=12000)
    glb = run(spec, facts_for(MeshFormat.GLB, triangles=14310))
    gltf = run(spec, facts_for(MeshFormat.GLTF, triangles=14310))

    assert glb.violations == gltf.violations
    assert glb.passed == gltf.passed


def test_the_same_rule_violated_twice_carries_the_same_identifier() -> None:
    spec = a_spec(tri_budget=12000)
    first = run(spec, facts_for(MeshFormat.GLB, triangles=14310))
    second = run(spec, facts_for(MeshFormat.FBX, triangles=99999))

    assert [v.rule_id for v in first.violations] == [v.rule_id for v in second.violations]


def test_every_rule_reaches_exactly_one_of_the_three_lists() -> None:
    report = run(a_spec(tri_budget=12000), facts_for(MeshFormat.OBJ, triangles=4200))
    reached = (
        {v.rule_id for v in report.violations}
        | {n.rule_id for n in report.not_evaluated}
        | set(report.passed_rules)
    )

    assert reached == set(RULE_IDS)


# --------------------------------------------------------------------------
# 3.14 — cannot contain, as opposed to cannot record
# --------------------------------------------------------------------------


def test_obj_for_an_animated_asset_is_an_error_naming_the_requirement() -> None:
    spec = a_spec(required_clips=(RequiredClip(state="walk", clip_name=WALK),))
    report = run(spec, facts_for(MeshFormat.OBJ, triangles=4200))

    (violation,) = report.violations_of(format_fitness.UNSUITABLE_FORMAT)
    assert violation.severity is Severity.ERROR
    assert "OBJ" in violation.message
    assert "animation clips" in violation.message
    assert not report.passed


def test_obj_for_a_rigged_or_socketed_asset_is_also_unsuitable() -> None:
    spec = a_spec(
        rig=Rig(skeleton="SK_MechScout"),
        rig_declared=True,
        required_sockets=("SOCKET_muzzle_l",),
    )
    report = run(spec, facts_for(MeshFormat.OBJ, triangles=4200))

    subjects = {v.subject for v in report.violations_of(format_fitness.UNSUITABLE_FORMAT)}
    assert subjects == {"a skeleton", "attachment points"}


def test_obj_for_a_static_asset_yields_only_not_evaluated_rules() -> None:
    spec = a_spec(tri_budget=12000, unit_scale=1.0)
    report = run(spec, facts_for(MeshFormat.OBJ, triangles=4200))

    assert report.violations_of(format_fitness.UNSUITABLE_FORMAT) == ()
    assert report.passed
    assert {n.rule_id for n in report.not_evaluated} >= {
        "unit_scale.mismatch",
        "up_axis.mismatch",
        "socket.missing",
        "animation.clip_missing",
        "rig.not_skinned",
        "rig.bone_budget_exceeded",
    }


def test_a_format_that_can_contain_the_requirement_is_not_unsuitable() -> None:
    spec = a_spec(required_clips=(RequiredClip(state="walk", clip_name=WALK),))
    facts = facts_for(MeshFormat.GLB, clips=(ClipFacts(name=WALK),))
    report = run(spec, facts)

    assert report.violations_of(format_fitness.UNSUITABLE_FORMAT) == ()


def test_format_fitness_is_never_suppressed_by_the_availability_gate() -> None:
    """It consumes only the source format, which every export carries by definition."""
    assert BY_ID[format_fitness.UNSUITABLE_FORMAT].consumes == frozenset({FactKind.SOURCE_FORMAT})
    report = run(
        a_spec(required_clips=(RequiredClip(state="walk", clip_name=WALK),)),
        facts_for(MeshFormat.OBJ, triangles=1),
    )

    assert report.evaluated(format_fitness.UNSUITABLE_FORMAT)


# --------------------------------------------------------------------------
# the whole run
# --------------------------------------------------------------------------


def test_a_clean_glb_export_passes_every_rule() -> None:
    spec = a_spec(
        tri_budget=12000,
        lods=(12000, 6000),
        unit_scale=1.0,
        up_axis="Z",
        naming=TEMPLATE,
        rig=Rig(skeleton="SK_MechScout", max_bones=96),
        rig_declared=True,
        required_sockets=("SOCKET_muzzle_l",),
        required_clips=(
            RequiredClip(
                state="walk",
                clip_name=WALK,
                frame_rate=30.0,
                min_duration_s=1.0,
                root_motion=True,
                loop=True,
            ),
        ),
    )
    facts = facts_for(
        MeshFormat.GLB,
        triangles=11840,
        objects=("SM_mech_scout_LOD0",),
        transforms_applied=True,
        unit_scale=1.0,
        up_axis="Z",
        uv_sets=1,
        materials=("M_MechScout",),
        empties=("SOCKET_muzzle_l",),
        clips=(
            ClipFacts(
                name=WALK,
                frames=45,
                duration_s=1.5,
                frame_rate=30.0,
                has_root_motion=True,
                loop_closed=True,
            ),
        ),
        frame_rate=30.0,
        is_skinned=True,
        bone_count=74,
    )

    report = run(spec, facts, export="exports/SM_mech_scout_LOD0.glb")

    assert report.violations == ()
    assert report.not_evaluated == ()
    assert set(report.passed_rules) == set(RULE_IDS)
    assert report.passed
