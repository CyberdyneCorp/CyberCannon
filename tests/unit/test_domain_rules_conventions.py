"""Task 3.6 — the mechanical conventions, each violation naming the offender.

"Something is wrong with the naming in this file" is not actionable; a violation
that names `mesh_final_v2` and the pattern it failed is.
"""

from __future__ import annotations

import pytest

from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.rules import conventions
from cybercanon.domain.violations import Severity

ASSET = "mech_scout"
TEMPLATE = "SM_{asset}_LOD{n}"


def a_spec(**fields: object) -> EffectiveSpec:
    return EffectiveSpec(asset_id=ASSET, **fields)  # type: ignore[arg-type]


def an_export(**observed: object):
    return facts_for(MeshFormat.GLB, **observed)


# --------------------------------------------------------------------------
# unit_scale.mismatch
# --------------------------------------------------------------------------


def test_a_unit_scale_mismatch_names_the_property_and_both_values() -> None:
    (violation,) = conventions.check_unit_scale(a_spec(unit_scale=1.0), an_export(unit_scale=0.01))

    assert violation.rule_id == conventions.UNIT_SCALE
    assert violation.subject == "unit_scale"
    assert violation.observed == "0.01"
    assert violation.expected == "1.0"
    assert ASSET in violation.message


def test_a_matching_unit_scale_is_silence() -> None:
    assert (
        tuple(conventions.check_unit_scale(a_spec(unit_scale=1.0), an_export(unit_scale=1.0))) == ()
    )


def test_floating_point_noise_is_not_a_mismatch() -> None:
    facts = an_export(unit_scale=1.0 + conventions.UNIT_SCALE_TOLERANCE / 2)

    assert tuple(conventions.check_unit_scale(a_spec(unit_scale=1.0), facts)) == ()


def test_an_undeclared_unit_scale_is_nothing_to_check() -> None:
    assert tuple(conventions.check_unit_scale(a_spec(), an_export(unit_scale=0.01))) == ()


# --------------------------------------------------------------------------
# up_axis.mismatch
# --------------------------------------------------------------------------


def test_an_up_axis_mismatch_names_both_axes() -> None:
    (violation,) = conventions.check_up_axis(a_spec(up_axis="Z"), an_export(up_axis="Y"))

    assert violation.rule_id == conventions.UP_AXIS
    assert violation.observed == "Y"
    assert violation.expected == "Z"


def test_an_up_axis_is_compared_case_insensitively() -> None:
    assert tuple(conventions.check_up_axis(a_spec(up_axis="Z"), an_export(up_axis="z"))) == ()


def test_an_undeclared_up_axis_is_nothing_to_check() -> None:
    assert tuple(conventions.check_up_axis(a_spec(), an_export(up_axis="Y"))) == ()


# --------------------------------------------------------------------------
# transforms.unapplied
# --------------------------------------------------------------------------


def test_unapplied_transforms_name_the_object() -> None:
    facts = an_export(transforms_applied=False, objects=("SM_mech_scout_LOD0",))
    (violation,) = conventions.check_transforms_applied(a_spec(), facts)

    assert violation.rule_id == conventions.TRANSFORMS
    assert violation.subject == "SM_mech_scout_LOD0"
    assert "SM_mech_scout_LOD0" in violation.message


def test_unapplied_transforms_name_every_object_in_the_export() -> None:
    """`transforms_applied` is one whole-export fact (D1), so every object is named."""
    facts = an_export(transforms_applied=False, objects=("SM_a", "SM_b"))
    (violation,) = conventions.check_transforms_applied(a_spec(), facts)

    assert "SM_a" in violation.subject
    assert "SM_b" in violation.subject


def test_applied_transforms_are_silence() -> None:
    facts = an_export(transforms_applied=True, objects=("SM_mech_scout_LOD0",))

    assert tuple(conventions.check_transforms_applied(a_spec(), facts)) == ()


def test_an_export_with_no_named_objects_still_reports_the_export() -> None:
    (violation,) = conventions.check_transforms_applied(
        a_spec(), an_export(transforms_applied=False)
    )

    assert "the export" in violation.message


# --------------------------------------------------------------------------
# naming.pattern_mismatch
# --------------------------------------------------------------------------


def test_a_naming_mismatch_names_the_object_and_the_pattern() -> None:
    facts = an_export(objects=("mesh_final_v2",))
    (violation,) = conventions.check_naming(a_spec(naming=TEMPLATE), facts)

    assert violation.rule_id == conventions.NAMING
    assert violation.severity is Severity.WARNING
    assert violation.subject == "mesh_final_v2"
    assert violation.expected == TEMPLATE
    assert "mesh_final_v2" in violation.message
    assert TEMPLATE in violation.message


def test_a_matching_object_name_is_silence() -> None:
    facts = an_export(objects=("SM_mech_scout_LOD0", "SM_mech_scout_LOD1"))

    assert tuple(conventions.check_naming(a_spec(naming=TEMPLATE), facts)) == ()


def test_every_offending_object_gets_its_own_violation() -> None:
    facts = an_export(objects=("mesh_final_v2", "SM_mech_scout_LOD0", "blob"))
    violations = tuple(conventions.check_naming(a_spec(naming=TEMPLATE), facts))

    assert [violation.subject for violation in violations] == ["mesh_final_v2", "blob"]


@pytest.mark.parametrize("spec", [EffectiveSpec(asset_id=ASSET)])
def test_no_declared_pattern_is_nothing_to_check(spec: EffectiveSpec) -> None:
    assert tuple(conventions.check_naming(spec, an_export(objects=("anything",)))) == ()
