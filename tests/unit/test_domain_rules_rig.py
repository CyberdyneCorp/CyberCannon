"""Task 3.11 — the bone budget and the skinning gate.

Over, at, under, and the case a static-prop project must not trip over: a
project-wide bone budget does not make every asset owe a skeleton.
"""

from __future__ import annotations

import pytest

from cybercanon.domain.constraints import Rig
from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.rules import rig as rig_rules
from cybercanon.domain.violations import Severity

ASSET = "mech_scout"
SKELETON = "SK_MechScout"


def a_spec(**fields: object) -> EffectiveSpec:
    return EffectiveSpec(asset_id=ASSET, **fields)  # type: ignore[arg-type]


def an_export(**observed: object):
    return facts_for(MeshFormat.GLB, **observed)


def test_over_the_bone_budget_states_both_counts() -> None:
    spec = a_spec(rig=Rig(max_bones=96))
    (violation,) = tuple(rig_rules.check_bone_budget(spec, an_export(bone_count=118)))

    assert violation.rule_id == rig_rules.BONE_BUDGET
    assert violation.severity is Severity.ERROR
    assert violation.observed == "118"
    assert violation.expected == "96"
    assert ASSET in violation.message


@pytest.mark.parametrize("bones", [74, 96])
def test_at_or_under_the_bone_budget_is_silence(bones: int) -> None:
    spec = a_spec(rig=Rig(max_bones=96))

    assert tuple(rig_rules.check_bone_budget(spec, an_export(bone_count=bones))) == ()


def test_no_declared_bone_budget_is_nothing_to_check() -> None:
    assert tuple(rig_rules.check_bone_budget(a_spec(), an_export(bone_count=1000))) == ()


def test_a_declared_rig_with_an_unskinned_export_names_the_skeleton() -> None:
    spec = a_spec(rig=Rig(skeleton=SKELETON), rig_declared=True)
    (violation,) = tuple(rig_rules.check_skinning(spec, an_export(is_skinned=False)))

    assert violation.rule_id == rig_rules.NOT_SKINNED
    assert violation.subject == SKELETON
    assert ASSET in violation.message
    assert SKELETON in violation.message


def test_a_declared_rig_with_a_skinned_export_is_silence() -> None:
    spec = a_spec(rig=Rig(skeleton=SKELETON), rig_declared=True)

    assert tuple(rig_rules.check_skinning(spec, an_export(is_skinned=True))) == ()


def test_an_asset_declaring_no_rig_owes_no_skinning() -> None:
    assert tuple(rig_rules.check_skinning(a_spec(), an_export(is_skinned=False))) == ()


def test_an_explicitly_unskinned_rig_is_the_opt_out() -> None:
    spec = a_spec(rig=Rig(skeleton=SKELETON, skinned=False), rig_declared=True)

    assert tuple(rig_rules.check_skinning(spec, an_export(is_skinned=False))) == ()


def test_a_rig_declared_without_a_name_still_reports() -> None:
    spec = a_spec(rig=Rig(max_bones=96), rig_declared=True)
    (violation,) = tuple(rig_rules.check_skinning(spec, an_export(is_skinned=False)))

    assert violation.subject == rig_rules.UNNAMED_SKELETON
