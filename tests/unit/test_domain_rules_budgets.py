"""Task 3.5 — the budget rules, over hand-built facts and nothing else.

Over, at and under budget. "At budget" is the case a naive `<` gets wrong and
nobody notices until an artist is told to remove one triangle.
"""

from __future__ import annotations

import pytest

from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.rules import budgets
from cybercanon.domain.violations import Severity

ASSET = "mech_scout"
TEMPLATE = "SM_{asset}_LOD{n}"


def a_spec(**fields: object) -> EffectiveSpec:
    return EffectiveSpec(asset_id=ASSET, **fields)  # type: ignore[arg-type]


def an_export(triangles: int, *objects: str):
    return facts_for(MeshFormat.GLB, triangles=triangles, objects=objects)


# --------------------------------------------------------------------------
# tri_budget.exceeded
# --------------------------------------------------------------------------


def test_over_budget_states_the_observed_and_the_allowed_value() -> None:
    (violation,) = budgets.check_tri_budget(a_spec(tri_budget=12000), an_export(14310))

    assert violation.rule_id == budgets.TRI_BUDGET
    assert violation.severity is Severity.ERROR
    assert violation.observed == "14310"
    assert violation.expected == "12000"
    assert violation.subject == "triangles"
    for fragment in (ASSET, "14310", "12000"):
        assert fragment in violation.message


@pytest.mark.parametrize("triangles", [11840, 12000])
def test_at_or_under_budget_is_silence(triangles: int) -> None:
    assert tuple(budgets.check_tri_budget(a_spec(tri_budget=12000), an_export(triangles))) == ()


def test_no_declared_budget_is_nothing_to_check() -> None:
    assert tuple(budgets.check_tri_budget(a_spec(), an_export(999_999))) == ()


# --------------------------------------------------------------------------
# lod.exceeded
# --------------------------------------------------------------------------


def test_a_lod_over_its_level_budget_names_the_level() -> None:
    spec = a_spec(lods=(12000, 6000, 2000), naming=TEMPLATE)
    (violation,) = budgets.check_lod_budget(spec, an_export(9000, "SM_mech_scout_LOD1"))

    assert violation.rule_id == budgets.LOD_BUDGET
    assert violation.subject == "LOD1"
    assert violation.observed == "9000"
    assert violation.expected == "6000"


@pytest.mark.parametrize("triangles", [6000, 5000])
def test_a_lod_at_or_under_its_level_budget_is_silence(triangles: int) -> None:
    spec = a_spec(lods=(12000, 6000), naming=TEMPLATE)

    assert tuple(budgets.check_lod_budget(spec, an_export(triangles, "SM_mech_scout_LOD1"))) == ()


def test_a_level_the_list_does_not_declare_is_not_judged() -> None:
    spec = a_spec(lods=(12000,), naming=TEMPLATE)

    assert tuple(budgets.check_lod_budget(spec, an_export(99999, "SM_mech_scout_LOD3"))) == ()


def test_an_export_holding_two_levels_is_not_attributed_to_either() -> None:
    """The triangle count is for the whole export; guessing a level would be a lie."""
    spec = a_spec(lods=(12000, 6000), naming=TEMPLATE)
    facts = an_export(18000, "SM_mech_scout_LOD0", "SM_mech_scout_LOD1")

    assert budgets.claimed_lod_levels(spec, facts) == frozenset({0, 1})
    assert tuple(budgets.check_lod_budget(spec, facts)) == ()


def test_without_a_naming_template_no_level_can_be_claimed() -> None:
    spec = a_spec(lods=(12000, 6000))

    assert budgets.claimed_lod_levels(spec, an_export(9000, "SM_mech_scout_LOD1")) == frozenset()
    assert tuple(budgets.check_lod_budget(spec, an_export(9000, "SM_mech_scout_LOD1"))) == ()


def test_without_a_declared_lod_list_there_is_nothing_to_check() -> None:
    spec = a_spec(naming=TEMPLATE)

    assert tuple(budgets.check_lod_budget(spec, an_export(9000, "SM_mech_scout_LOD1"))) == ()
