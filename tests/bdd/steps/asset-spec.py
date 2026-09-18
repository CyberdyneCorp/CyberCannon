"""Step definitions for `asset-spec` — the scenarios the domain contract satisfies.

Group 2 of `add-asset-spec-and-validator` builds the spec contract as pure
domain: identity, lifecycle, the three authored blocks, anchors and annotations,
and the structural checks. The scenarios bound here are exactly the ones that
code answers on its own, with no file, no store and no export — which is what
`asset-spec` means by "checkable offline".

Group 3 adds the merge and the gates: project defaults resolved against the
asset's own constraints, `design.states` resolved into required clips through the
naming template, and the two loops the product exists to close — a declared
socket and a declared state becoming export gates, evaluated over hand-built
`MeshFacts` with no file on disk.

Group 5 adds the two this capability cannot answer without a file: a
specification read straight out of a working copy, and an unrecognised field
reported rather than refused (D5). Those run against `GitSpecStore` over a
temporary repository — there is no way to assert "it read the file from the
working copy" without a working copy, and asserting it against a fake would be
asserting that the fake was written as intended.

The rest of this capability's scenarios stay in `tests/bdd/pending.txt` until the
change that earns them: annotation triage (`add-model-sheet-2d`) and anchor
resolution (`add-viewer-3d`).
"""

from __future__ import annotations

import socket
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.adapters.outbound.git.discovery import GIT_DIR
from cybercanon.adapters.outbound.git.schema import RULE_UNKNOWN_FIELD
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig
from cybercanon.domain.design import Design, Socket, State
from cybercanon.domain.effective_spec import EffectiveSpec, merge
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.report import Report
from cybercanon.domain.rules import animation, run, sockets
from cybercanon.domain.spec_checks import (
    SpecDeclaration,
    check_asset,
    check_declared_status,
    check_duplicate_ids,
)
from cybercanon.domain.violations import Severity, errors

ASSET_ID = "mech_scout"
NAME = "Scout Mech"
NEW_NAME = "Recon Walker"
UNREACHABLE = "https://unreachable.invalid/threads/7"

FIRST_FILE = "characters/mech_scout/asset.yaml"
SECOND_FILE = "enemies/mech_scout/asset.yaml"

SPEC_PATH = "characters/mech_scout/asset.yaml"
WORKING_COPY_SPEC = """\
schema_version: 1
id: mech_scout
name: "Scout Mech"
status: modeling
constraints:
  tri_budget: 12000
"""

CONVENTION = "A_{asset}_{state}"
MUZZLE = "SOCKET_muzzle_l"
FIRE_CLIP = "A_mech_scout_fire"


@pytest.fixture
def spec() -> dict[str, Any]:
    """What this scenario has declared, and what the checks answered."""
    return {}


def an_asset(**blocks: Any) -> Asset:
    return Asset(id=AssetId(ASSET_ID), name=NAME, **blocks)


def an_empty_export() -> Any:
    """A well-formed GLB export that carries no sockets and no clips.

    Enough for the two gate scenarios — the point of each is the *absence* the
    specification demanded — and built by hand, with no file on disk.
    """
    return facts_for(
        MeshFormat.GLB,
        triangles=1200,
        objects=("SM_mech_scout_LOD0",),
        transforms_applied=True,
        unit_scale=1.0,
        up_axis="Z",
        uv_sets=1,
        materials=("M_MechScout",),
        empties=(),
        clips=(),
        frame_rate=30.0,
        is_skinned=True,
        bone_count=74,
    )


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "Renaming does not break references",
)
def test_renaming_does_not_break_references() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature", "Concept-only asset is valid"
)
def test_concept_only_asset_is_valid() -> None: ...


@scenario("../features/add-asset-spec-and-validator/asset-spec.feature", "Owners are independent")
def test_owners_are_independent() -> None: ...


@scenario("../features/add-asset-spec-and-validator/asset-spec.feature", "Unknown status rejected")
def test_unknown_status_rejected() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature", "Ascending LOD list rejected"
)
def test_ascending_lod_list_rejected() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature", "Duplicate id within a project"
)
def test_duplicate_id_within_a_project() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "A state with no animation is declared explicitly",
)
def test_a_state_with_no_animation_is_declared_explicitly() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "A state that constrains nothing is rejected",
)
def test_a_state_that_constrains_nothing_is_rejected() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "Unreachable link does not invalidate the spec",
)
def test_unreachable_link_does_not_invalidate_the_spec() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "Asset constraint overrides project default",
)
def test_asset_constraint_overrides_project_default() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "Project default applies when asset is silent",
)
def test_project_default_applies_when_asset_is_silent() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "Bone budget inherited from the project",
)
def test_bone_budget_inherited_from_the_project() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "Template expands to the required clip name",
)
def test_template_expands_to_the_required_clip_name() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "An explicit clip name wins over the convention",
)
def test_an_explicit_clip_name_wins_over_the_convention() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "Declared socket becomes an export gate",
)
def test_declared_socket_becomes_an_export_gate() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "A named state becomes an export gate",
)
def test_a_named_state_becomes_an_export_gate() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/asset-spec.feature",
    "Spec read directly from a working copy",
)
def test_spec_read_directly_from_a_working_copy() -> None: ...


@scenario("../features/add-asset-spec-and-validator/asset-spec.feature", "Unknown field reported")
def test_unknown_field_reported() -> None: ...


# --------------------------------------------------------------------------
# GIVEN
# --------------------------------------------------------------------------


@given('an asset with `id: mech_scout` and `name: "Scout Mech"`')
def _an_asset_with_an_id_and_a_name(spec: dict[str, Any]) -> None:
    spec["asset"] = an_asset(aliases=("scout",))


@given("a specification declaring identity and a `concept` block only")
def _a_concept_only_specification(spec: dict[str, Any]) -> None:
    spec["asset"] = an_asset(concept=Concept(views=("front", "side")))


@given("a game repository containing `characters/mech_scout/asset.yaml`")
def _a_game_repository(
    spec: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A working copy, and the network taken away for the duration.

    Blocking the socket is half the scenario: "it SHALL NOT require any
    database, service or network connection" is only proven if a connection
    would have failed the test.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("reading a specification opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    (tmp_path / GIT_DIR).mkdir(parents=True, exist_ok=True)
    written = tmp_path / SPEC_PATH
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(WORKING_COPY_SPEC, encoding="utf-8")
    spec["network_blocked"] = True
    spec["repository"] = tmp_path
    spec["store"] = GitSpecStore(tmp_path)


@given("a specification declaring `owner_art` and `owner_code` but no `owner_design`")
def _a_specification_missing_one_owner(spec: dict[str, Any]) -> None:
    spec["asset"] = an_asset(owner_art="ana", owner_code="rafa")


@given("a specification whose `links.discussion` points to an unreachable URL")
def _a_specification_with_an_unreachable_link(
    spec: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The link is recorded verbatim, and the socket module is taken away.

    Blocking the socket is the assertion: if reading the specification tried to
    resolve the link, validation would raise here instead of reporting.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("reading a specification opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    spec["network_blocked"] = True
    spec["asset"] = an_asset(links=Links(discussion=UNREACHABLE))


@given("a state `destroyed` declaring that it has no animation")
def _an_unanimated_state(spec: dict[str, Any]) -> None:
    spec["asset"] = an_asset(design=Design(states=(State(name="destroyed", animated=False),)))
    spec["state"] = "destroyed"


@given(
    "a state that names no clip, resolves to no clip through any convention, "
    "and does not declare itself unanimated"
)
def _a_state_that_constrains_nothing(spec: dict[str, Any]) -> None:
    spec["asset"] = an_asset(design=Design(states=(State(name="fire"),)))
    spec["state"] = "fire"
    spec["clip_naming"] = None


@given("two specification files in the same project declare `id: mech_scout`")
def _two_files_declaring_one_id(spec: dict[str, Any]) -> None:
    spec["declarations"] = (
        SpecDeclaration(path=FIRST_FILE, asset_id=AssetId(ASSET_ID)),
        SpecDeclaration(path="props/crate/asset.yaml", asset_id=AssetId("crate")),
        SpecDeclaration(path=SECOND_FILE, asset_id=AssetId(ASSET_ID)),
    )


@given("a specification whose `design.sockets` declares `SOCKET_muzzle_l`")
def _a_specification_declaring_a_socket(spec: dict[str, Any]) -> None:
    spec["design"] = Design(sockets=(Socket(name=MUZZLE, purpose="muzzle flash"),))


@given("a specification whose `design.states` lists `fire`")
def _a_specification_listing_a_state(spec: dict[str, Any]) -> None:
    spec["design"] = Design(states=(State(name="fire"),))


@given("a clip naming convention resolving that state to `A_mech_scout_fire`")
def _a_convention_resolving_that_state(spec: dict[str, Any]) -> None:
    spec["clip_naming"] = CONVENTION


@given("a clip naming convention of `A_{asset}_{state}`")
def _a_clip_naming_convention(spec: dict[str, Any]) -> None:
    spec["clip_naming"] = CONVENTION


@given("an asset `mech_scout` with a state `walk`")
def _an_asset_with_a_state(spec: dict[str, Any]) -> None:
    spec["design"] = Design(states=(State(name="walk"),))


@given("a state `walk` declaring `clip: Locomotion_Walk_Fwd`")
def _a_state_declaring_its_clip(spec: dict[str, Any]) -> None:
    spec["design"] = Design(states=(State(name="walk", clip="Locomotion_Walk_Fwd"),))


@given("a project default of `tri_budget: 8000`")
def _a_project_tri_budget(spec: dict[str, Any]) -> None:
    spec["project"] = Constraints(tri_budget=8000)


@given("a project default of `up_axis: Z`")
def _a_project_up_axis(spec: dict[str, Any]) -> None:
    spec["project"] = Constraints(up_axis="Z")


@given("a project default of `rig.max_bones: 96`")
def _a_project_bone_budget(spec: dict[str, Any]) -> None:
    spec["project"] = Constraints(rig=Rig(max_bones=96))


@given("an asset declaring `tri_budget: 12000`")
def _an_asset_declaring_a_tri_budget(spec: dict[str, Any]) -> None:
    spec["constraints"] = Constraints(tri_budget=12000)


@given("an asset declaring no `up_axis`")
def _an_asset_declaring_no_up_axis(spec: dict[str, Any]) -> None:
    spec["constraints"] = Constraints(tri_budget=12000)


@given("an asset declaring a `rig` without `max_bones`")
def _an_asset_declaring_a_rig_without_a_budget(spec: dict[str, Any]) -> None:
    spec["constraints"] = Constraints(rig=Rig(skeleton="SK_MechScout"))


# --------------------------------------------------------------------------
# WHEN
# --------------------------------------------------------------------------


@when("the specification file is validated")
def _the_specification_file_is_validated(spec: dict[str, Any]) -> None:
    spec["violations"] = check_asset(spec["asset"], clip_naming=spec.get("clip_naming"))


@when("the project is validated")
def _the_project_is_validated(spec: dict[str, Any]) -> None:
    spec["violations"] = check_duplicate_ids(spec["declarations"])


@when("a specification declares `status: wip`")
def _a_specification_declares_an_unknown_status(spec: dict[str, Any]) -> None:
    spec["violations"] = check_declared_status("wip")


@when("a specification declares `lods: [2000, 6000, 12000]`")
def _a_specification_declares_ascending_lods(spec: dict[str, Any]) -> None:
    spec["asset"] = an_asset(constraints=Constraints(lods=(2000, 6000, 12000)))
    spec["violations"] = check_asset(spec["asset"])


@when('`name` is changed to `"Recon Walker"`')
def _the_name_is_changed(spec: dict[str, Any]) -> None:
    spec["asset"] = spec["asset"].renamed(NEW_NAME)


def _merged(spec: dict[str, Any]) -> EffectiveSpec:
    """The effective specification these GIVENs describe (D3)."""
    constraints = spec.get("constraints") or Constraints()
    if spec.get("clip_naming"):
        constraints = replace(
            constraints, animation=AnimationDefaults(clip_naming=spec["clip_naming"])
        )
    asset = an_asset(design=spec.get("design"), constraints=constraints)
    spec["effective"] = merge(asset, spec.get("project"))
    return spec["effective"]


@when("an export for that asset is validated")
def _an_export_is_validated(spec: dict[str, Any]) -> None:
    spec["report"] = run(_merged(spec), an_empty_export())


@when("the required clips are resolved")
def _the_required_clips_are_resolved(spec: dict[str, Any]) -> None:
    spec["required_clips"] = _merged(spec).required_clips


@when("the system is asked for the specification of `mech_scout`")
def _the_specification_is_asked_for(spec: dict[str, Any]) -> None:
    spec["loaded"] = spec["store"].load(spec["store"].discover(SPEC_PATH))


@when("a specification declares a field not defined by the schema")
def _a_specification_declares_an_unknown_field(spec: dict[str, Any], tmp_path: Path) -> None:
    (tmp_path / GIT_DIR).mkdir(parents=True, exist_ok=True)
    written = tmp_path / SPEC_PATH
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(WORKING_COPY_SPEC + "  shinyness: 3\n", encoding="utf-8")
    spec["loaded"] = GitSpecStore(tmp_path).load(SPEC_PATH)


# --------------------------------------------------------------------------
# THEN
# --------------------------------------------------------------------------


@then("it SHALL be reported as a valid specification")
@then("it SHALL be reported as valid")
def _it_is_valid(spec: dict[str, Any]) -> None:
    assert errors(spec["violations"]) == ()


@then("the absence of `design` and `constraints` SHALL NOT be a violation")
def _the_missing_blocks_are_not_a_violation(spec: dict[str, Any]) -> None:
    asset: Asset = spec["asset"]
    assert (asset.design, asset.constraints) == (None, None)
    assert spec["violations"] == ()


@then("the missing `owner_design` SHALL be reported at most as a warning")
def _the_missing_owner_is_at_most_a_warning(spec: dict[str, Any]) -> None:
    assert spec["asset"].owner_design is None
    about_the_owner = [
        violation for violation in spec["violations"] if "owner_design" in violation.subject
    ]
    assert all(violation.severity is Severity.WARNING for violation in about_the_owner)


@then("no network request SHALL be made")
def _no_network_request_was_made(spec: dict[str, Any]) -> None:
    assert spec["network_blocked"], "the guard was never installed, so this proves nothing"
    assert spec["asset"].links is not None
    assert spec["asset"].links.discussion == UNREACHABLE, "the link is stored verbatim"


@then("the system SHALL report a violation naming the allowed values")
def _the_violation_names_the_allowed_values(spec: dict[str, Any]) -> None:
    (violation,) = spec["violations"]
    assert violation.subject == "status"
    for allowed in ("concept", "approved", "modeling", "validated", "in-engine"):
        assert allowed in violation.message


@then("the system SHALL report a violation stating LOD triangle counts must be descending")
def _the_violation_states_lods_must_descend(spec: dict[str, Any]) -> None:
    (violation,) = spec["violations"]
    assert violation.subject == "constraints.lods"
    assert "descending" in violation.message


@then("the system SHALL report a violation naming both file paths")
def _the_violation_names_both_files(spec: dict[str, Any]) -> None:
    (violation,) = spec["violations"]
    assert FIRST_FILE in violation.message
    assert SECOND_FILE in violation.message


@then("a violation SHALL be reported naming that state")
def _the_violation_names_the_state(spec: dict[str, Any]) -> None:
    (violation,) = spec["violations"]
    assert violation.subject == f"design.states[{spec['state']}]"
    assert spec["state"] in violation.message


@then("no animation clip SHALL be required for that state")
def _no_clip_is_required(spec: dict[str, Any]) -> None:
    state = spec["asset"].design.state(spec["state"])
    assert state.is_unanimated
    assert not state.resolves_to_a_clip("A_{asset}_{state}")


@then("the `id` SHALL remain `mech_scout`")
def _the_id_is_unchanged(spec: dict[str, Any]) -> None:
    assert spec["asset"].id == AssetId(ASSET_ID)
    assert spec["asset"].name == NEW_NAME


@then("existing references to `mech_scout` SHALL continue to resolve")
def _references_still_resolve(spec: dict[str, Any]) -> None:
    assert spec["asset"].refers_to(ASSET_ID)


@then("the effective budget SHALL be 12000")
def _the_effective_budget_is_twelve_thousand(spec: dict[str, Any]) -> None:
    assert spec["effective"].tri_budget == 12000


@then("the effective up axis SHALL be `Z`")
def _the_effective_up_axis_is_z(spec: dict[str, Any]) -> None:
    assert spec["effective"].up_axis == "Z"


@then("the effective bone budget SHALL be 96")
def _the_effective_bone_budget_is_ninety_six(spec: dict[str, Any]) -> None:
    assert spec["effective"].max_bones == 96


@then("the required clip name SHALL be `A_mech_scout_walk`")
def _the_required_clip_name_is_expanded(spec: dict[str, Any]) -> None:
    assert [clip.clip_name for clip in spec["required_clips"]] == ["A_mech_scout_walk"]


@then("the required clip name SHALL be `Locomotion_Walk_Fwd`")
def _the_required_clip_name_is_the_explicit_one(spec: dict[str, Any]) -> None:
    assert [clip.clip_name for clip in spec["required_clips"]] == ["Locomotion_Walk_Fwd"]


@then("`A_mech_scout_walk` SHALL NOT be required")
def _the_expanded_name_is_not_required(spec: dict[str, Any]) -> None:
    assert spec["effective"].required_clip("A_mech_scout_walk") is None


@then("the absence of an attachment point named `SOCKET_muzzle_l` SHALL be reported as a violation")
def _the_missing_socket_is_a_violation(spec: dict[str, Any]) -> None:
    report: Report = spec["report"]
    (violation,) = report.violations_of(sockets.SOCKET_MISSING)
    assert violation.subject == MUZZLE
    assert not report.passed


@then("the absence of an animation clip named `A_mech_scout_fire` SHALL be reported as a violation")
def _the_missing_clip_is_a_violation(spec: dict[str, Any]) -> None:
    report: Report = spec["report"]
    (violation,) = report.violations_of(animation.CLIP_MISSING)
    assert violation.subject == FIRE_CLIP
    assert "fire" in violation.message
    assert not report.passed


@then("it SHALL read the file from the working copy")
def _it_read_the_file_from_the_working_copy(spec: dict[str, Any]) -> None:
    loaded = spec["loaded"]
    assert loaded.path == SPEC_PATH
    assert loaded.asset.id.value == ASSET_ID
    assert (spec["repository"] / SPEC_PATH).is_file(), "the file is the source of truth"


@then("it SHALL NOT require any database, service or network connection")
def _it_required_nothing_external(spec: dict[str, Any]) -> None:
    assert spec["network_blocked"], "the guard was never installed, so this proves nothing"
    assert spec["loaded"].asset.constraints is not None


@then("the system SHALL report it, naming the field and its location in the file")
def _the_unknown_field_is_reported(spec: dict[str, Any]) -> None:
    (warning,) = spec["loaded"].warnings
    assert warning.rule_id == RULE_UNKNOWN_FIELD
    assert warning.severity is Severity.WARNING, "version skew must never be fatal (D5)"
    assert warning.subject == "constraints.shinyness"
    assert "shinyness" in warning.message
    assert spec["loaded"].asset.id.value == ASSET_ID, "the specification still loaded"
