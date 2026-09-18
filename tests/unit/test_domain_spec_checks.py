"""Task 2.5 — the structural checks, each with a failing case naming the field.

Every check is a pure function over value objects: no file, no project, no
network. That is the property `asset-spec` requires ("checkable offline") and it
is why these tests need nothing on disk.
"""

from __future__ import annotations

import pytest

from cybercanon.domain import spec_checks
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints
from cybercanon.domain.design import Design, State
from cybercanon.domain.spec_checks import (
    SpecDeclaration,
    check_asset,
    check_declared_status,
    check_duplicate_ids,
    check_first_lod_within_tri_budget,
    check_lods_descending,
    check_states_are_checkable,
)
from cybercanon.domain.status import Status
from cybercanon.domain.violations import Severity, errors

CONVENTION = "A_{asset}_{state}"


def an_asset(**overrides: object) -> Asset:
    fields: dict[str, object] = {"id": AssetId("mech_scout"), "name": "Scout Mech"}
    fields.update(overrides)
    return Asset(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


def test_an_unknown_status_names_the_field_and_every_allowed_value() -> None:
    (violation,) = check_declared_status("wip")

    assert violation.rule_id == spec_checks.RULE_UNKNOWN_STATUS
    assert violation.subject == "status"
    assert violation.observed == "wip"
    assert violation.severity is Severity.ERROR
    for allowed in Status.values():
        assert allowed in violation.message


@pytest.mark.parametrize("declared", Status.values())
def test_a_declared_status_inside_the_set_passes(declared: str) -> None:
    assert check_declared_status(declared) == ()


# --------------------------------------------------------------------------
# lods
# --------------------------------------------------------------------------


def test_an_ascending_lod_list_names_the_field_and_says_descending() -> None:
    (violation,) = check_lods_descending(Constraints(lods=(2000, 6000, 12000)))

    assert violation.rule_id == spec_checks.RULE_LODS_NOT_DESCENDING
    assert violation.subject == "constraints.lods"
    assert "descending" in violation.message
    assert violation.observed == "2000, 6000, 12000"


def test_two_lods_of_the_same_size_are_not_descending() -> None:
    assert len(check_lods_descending(Constraints(lods=(6000, 6000)))) == 1


@pytest.mark.parametrize(
    "lods", [(), (6000,), (12000, 6000, 2000)], ids=["none", "one", "descending"]
)
def test_a_descending_or_trivial_lod_list_passes(lods: tuple[int, ...]) -> None:
    assert check_lods_descending(Constraints(lods=lods)) == ()


def test_no_constraints_block_declares_no_lods() -> None:
    assert check_lods_descending(None) == ()


def test_lod0_above_the_triangle_budget_names_the_field_and_both_numbers() -> None:
    (violation,) = check_first_lod_within_tri_budget(
        Constraints(tri_budget=8000, lods=(12000, 6000))
    )

    assert violation.rule_id == spec_checks.RULE_LOD0_OVER_TRI_BUDGET
    assert violation.subject == "constraints.lods[0]"
    assert violation.observed == "12000"
    assert violation.expected == "at most 8000"


@pytest.mark.parametrize("first", [8000, 4000], ids=["at budget", "under budget"])
def test_lod0_within_the_triangle_budget_passes(first: int) -> None:
    assert check_first_lod_within_tri_budget(Constraints(tri_budget=8000, lods=(first,))) == ()


@pytest.mark.parametrize(
    "constraints",
    [None, Constraints(lods=(12000,)), Constraints(tri_budget=8000)],
    ids=["no block", "no budget", "no lods"],
)
def test_nothing_to_compare_is_not_a_violation(constraints: Constraints | None) -> None:
    assert check_first_lod_within_tri_budget(constraints) == ()


# --------------------------------------------------------------------------
# states (D12)
# --------------------------------------------------------------------------


def test_a_state_that_constrains_nothing_names_that_state() -> None:
    design = Design(states=(State(name="idle", clip="A_mech_scout_idle"), State(name="fire")))

    (violation,) = check_states_are_checkable(design, clip_naming=None)

    assert violation.rule_id == spec_checks.RULE_STATE_CONSTRAINS_NOTHING
    assert violation.subject == "design.states[fire]"
    assert "'fire'" in violation.message
    assert "animated: false" in violation.expected


def test_a_convention_makes_every_bare_state_checkable() -> None:
    design = Design(states=(State(name="idle"), State(name="fire")))

    assert check_states_are_checkable(design, clip_naming=CONVENTION) == ()


def test_an_explicitly_unanimated_state_is_checkable_without_a_convention() -> None:
    design = Design(states=(State(name="destroyed", animated=False),))

    assert check_states_are_checkable(design, clip_naming=None) == ()


def test_no_design_block_declares_no_states() -> None:
    assert check_states_are_checkable(None) == ()


# --------------------------------------------------------------------------
# duplicate ids — a project-level question
# --------------------------------------------------------------------------


def test_a_duplicate_id_names_every_file_that_declares_it() -> None:
    declarations = (
        SpecDeclaration(path="characters/mech_scout/asset.yaml", asset_id=AssetId("mech_scout")),
        SpecDeclaration(path="props/crate/asset.yaml", asset_id=AssetId("crate")),
        SpecDeclaration(path="enemies/mech_scout/asset.yaml", asset_id=AssetId("mech_scout")),
    )

    (violation,) = check_duplicate_ids(declarations)

    assert violation.rule_id == spec_checks.RULE_DUPLICATE_ID
    assert violation.subject == "id"
    assert "characters/mech_scout/asset.yaml" in violation.message
    assert "enemies/mech_scout/asset.yaml" in violation.message
    assert "props/crate/asset.yaml" not in violation.message


def test_unique_ids_pass() -> None:
    declarations = (
        SpecDeclaration(path="a/asset.yaml", asset_id=AssetId("mech_scout")),
        SpecDeclaration(path="b/asset.yaml", asset_id=AssetId("crate")),
    )

    assert check_duplicate_ids(declarations) == ()
    assert check_duplicate_ids(()) == ()


# --------------------------------------------------------------------------
# the whole file at once
# --------------------------------------------------------------------------


def test_a_concept_only_asset_is_structurally_clean() -> None:
    asset = an_asset(concept=Concept(views=("front", "side")))

    assert check_asset(asset) == ()


def test_an_asset_missing_one_owner_reports_nothing_at_error_severity() -> None:
    asset = an_asset(owner_art="ana", owner_code="rafa")

    assert errors(check_asset(asset)) == ()


def test_every_structural_problem_in_one_file_is_reported_together() -> None:
    asset = an_asset(
        design=Design(states=(State(name="fire"),)),
        constraints=Constraints(tri_budget=8000, lods=(12000, 20000)),
    )

    reported = {violation.rule_id for violation in check_asset(asset)}

    assert reported == {
        spec_checks.RULE_LODS_NOT_DESCENDING,
        spec_checks.RULE_LOD0_OVER_TRI_BUDGET,
        spec_checks.RULE_STATE_CONSTRAINS_NOTHING,
    }


def test_the_asset_convention_wins_over_the_project_one() -> None:
    asset = an_asset(
        design=Design(states=(State(name="fire"),)),
        constraints=Constraints(animation=AnimationDefaults(clip_naming="Anim_{asset}_{state}")),
    )

    assert check_asset(asset, clip_naming=None) == ()


def test_the_project_convention_applies_when_the_asset_declares_none() -> None:
    asset = an_asset(design=Design(states=(State(name="fire"),)))

    assert check_asset(asset, clip_naming=CONVENTION) == ()
    assert len(check_asset(asset, clip_naming=None)) == 1


def test_every_structural_rule_has_a_unique_stable_identifier() -> None:
    assert len(set(spec_checks.RULE_IDS)) == len(spec_checks.RULE_IDS)
    assert all(rule_id.startswith("spec.") for rule_id in spec_checks.RULE_IDS)
