"""Tasks 3.2 and 3.3 — the one merge, and the clips design resolves to.

Override, fallback and neither-declared, for every field a rule reads — plus the
two derivations that close the product's loops: declared sockets and, through
the clip naming template, declared states (D12).
"""

from __future__ import annotations

from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig, Texture
from cybercanon.domain.design import Design, Socket, State
from cybercanon.domain.effective_spec import clip_name_for, merge, resolve_required_clips

CONVENTION = "A_{asset}_{state}"
ASSET_ID = "mech_scout"


def an_asset(**blocks: object) -> Asset:
    return Asset(id=AssetId(ASSET_ID), name="Scout Mech", **blocks)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Override, fallback, neither
# --------------------------------------------------------------------------


def test_an_asset_constraint_overrides_the_project_default() -> None:
    effective = merge(
        an_asset(constraints=Constraints(tri_budget=12000)),
        Constraints(tri_budget=8000),
    )

    assert effective.tri_budget == 12000


def test_a_project_default_applies_when_the_asset_is_silent() -> None:
    effective = merge(an_asset(constraints=Constraints()), Constraints(up_axis="Z"))

    assert effective.up_axis == "Z"


def test_a_project_default_applies_when_the_asset_declares_no_constraints_at_all() -> None:
    effective = merge(an_asset(), Constraints(up_axis="Z", naming="SM_{asset}_LOD{n}"))

    assert effective.up_axis == "Z"
    assert effective.naming == "SM_{asset}_LOD{n}"


def test_a_field_neither_declares_is_none_not_a_guess() -> None:
    effective = merge(an_asset())

    assert effective.tri_budget is None
    assert effective.unit_scale is None
    assert effective.naming is None
    assert effective.lods == ()
    assert effective.rig is None
    assert effective.animation is None
    assert effective.texture is None


def test_the_asset_id_travels_with_the_merged_spec() -> None:
    """Every violation message names the asset, so the merge has to carry it."""
    assert merge(an_asset()).asset_id == ASSET_ID


def test_a_declared_lod_list_replaces_the_default_rather_than_extending_it() -> None:
    effective = merge(
        an_asset(constraints=Constraints(lods=(12000, 6000))),
        Constraints(lods=(8000, 4000, 2000)),
    )

    assert effective.lods == (12000, 6000)


def test_an_undeclared_lod_list_falls_back_to_the_project() -> None:
    assert merge(an_asset(), Constraints(lods=(8000, 4000))).lods == (8000, 4000)


def test_the_scalar_engineering_fields_all_merge() -> None:
    effective = merge(
        an_asset(constraints=Constraints(collider=" convex", pivot="feet")),
        Constraints(collider="box", pivot="origin", unit_scale=1.0),
    )

    assert effective.collider == " convex"
    assert effective.pivot == "feet"
    assert effective.unit_scale == 1.0


# --------------------------------------------------------------------------
# rig
# --------------------------------------------------------------------------


def test_the_bone_budget_is_inherited_from_the_project() -> None:
    effective = merge(
        an_asset(constraints=Constraints(rig=Rig(skeleton="SK_Mech"))),
        Constraints(rig=Rig(max_bones=96)),
    )

    assert effective.max_bones == 96
    assert effective.skeleton == "SK_Mech"


def test_an_asset_bone_budget_wins_over_the_project() -> None:
    effective = merge(
        an_asset(constraints=Constraints(rig=Rig(max_bones=128))),
        Constraints(rig=Rig(max_bones=96)),
    )

    assert effective.max_bones == 128


def test_a_project_rig_default_does_not_make_a_static_prop_owe_a_skeleton() -> None:
    """`rig_declared` is the asset's own declaration, never an inherited default."""
    effective = merge(an_asset(constraints=Constraints()), Constraints(rig=Rig(max_bones=96)))

    assert effective.max_bones == 96
    assert not effective.rig_declared
    assert not effective.expects_skinning


def test_a_declared_rig_expects_skinning() -> None:
    effective = merge(an_asset(constraints=Constraints(rig=Rig(skeleton="SK_Mech"))))

    assert effective.rig_declared
    assert effective.expects_skinning


def test_an_explicit_unskinned_rig_is_the_opt_out() -> None:
    effective = merge(an_asset(constraints=Constraints(rig=Rig(skeleton="SK", skinned=False))))

    assert effective.rig_declared
    assert not effective.expects_skinning


def test_an_asset_with_no_rig_expects_no_skinning_and_names_no_skeleton() -> None:
    effective = merge(an_asset())

    assert effective.max_bones is None
    assert effective.skeleton is None
    assert not effective.expects_skinning


def test_texture_merges_field_by_field() -> None:
    effective = merge(
        an_asset(constraints=Constraints(texture=Texture(size=2048))),
        Constraints(texture=Texture(size=1024, sets=1, channels=("ORM",))),
    )

    assert effective.texture == Texture(size=2048, sets=1, channels=("ORM",))


# --------------------------------------------------------------------------
# animation defaults
# --------------------------------------------------------------------------


def test_the_clip_naming_convention_falls_back_to_the_project() -> None:
    effective = merge(an_asset(), Constraints(animation=AnimationDefaults(clip_naming=CONVENTION)))

    assert effective.clip_naming == CONVENTION


def test_an_asset_clip_naming_convention_wins() -> None:
    effective = merge(
        an_asset(
            constraints=Constraints(animation=AnimationDefaults(clip_naming="{asset}@{state}"))
        ),
        Constraints(animation=AnimationDefaults(clip_naming=CONVENTION, frame_rate=30.0)),
    )

    assert effective.clip_naming == "{asset}@{state}"
    assert effective.frame_rate == 30.0


def test_neither_declaring_animation_leaves_both_unset() -> None:
    effective = merge(an_asset())

    assert effective.clip_naming is None
    assert effective.frame_rate is None


# --------------------------------------------------------------------------
# sockets and states — the two derivations (D12)
# --------------------------------------------------------------------------


def test_declared_sockets_become_required_sockets() -> None:
    design = Design(
        sockets=(
            Socket(name="SOCKET_muzzle_l", purpose="muzzle flash"),
            Socket(name="SOCKET_jet_r", purpose="thruster"),
        )
    )

    assert merge(an_asset(design=design)).required_sockets == ("SOCKET_muzzle_l", "SOCKET_jet_r")


def test_a_bare_state_list_resolves_through_the_template() -> None:
    effective = merge(
        an_asset(design=Design(states=(State(name="walk"), State(name="fire")))),
        Constraints(animation=AnimationDefaults(clip_naming=CONVENTION)),
    )

    assert [clip.clip_name for clip in effective.required_clips] == [
        "A_mech_scout_walk",
        "A_mech_scout_fire",
    ]
    assert [clip.state for clip in effective.required_clips] == ["walk", "fire"]


def test_an_explicit_clip_name_wins_over_the_convention() -> None:
    effective = merge(
        an_asset(design=Design(states=(State(name="walk", clip="Locomotion_Walk_Fwd"),))),
        Constraints(animation=AnimationDefaults(clip_naming=CONVENTION)),
    )

    names = [clip.clip_name for clip in effective.required_clips]
    assert names == ["Locomotion_Walk_Fwd"]
    assert "A_mech_scout_walk" not in names


def test_an_unanimated_state_contributes_nothing() -> None:
    effective = merge(
        an_asset(
            design=Design(states=(State(name="destroyed", animated=False), State(name="walk")))
        ),
        Constraints(animation=AnimationDefaults(clip_naming=CONVENTION)),
    )

    assert [clip.state for clip in effective.required_clips] == ["walk"]


def test_a_state_that_resolves_to_nothing_contributes_nothing_here() -> None:
    """It is a *spec-file* violation (`lint_spec`), never a silent mesh requirement."""
    effective = merge(an_asset(design=Design(states=(State(name="walk"),))))

    assert effective.required_clips == ()


def test_a_state_expectation_travels_into_the_requirement() -> None:
    state = State(
        name="walk",
        frame_rate=24.0,
        root_motion=True,
        loop=True,
        min_duration_s=1.0,
    )
    effective = merge(
        an_asset(design=Design(states=(state,))),
        Constraints(animation=AnimationDefaults(clip_naming=CONVENTION, frame_rate=30.0)),
    )

    (required,) = effective.required_clips
    assert required.frame_rate == 24.0
    assert required.min_duration_s == 1.0
    assert required.root_motion is True
    assert required.loop is True


def test_a_state_without_its_own_frame_rate_inherits_the_effective_one() -> None:
    effective = merge(
        an_asset(design=Design(states=(State(name="walk"),))),
        Constraints(animation=AnimationDefaults(clip_naming=CONVENTION, frame_rate=30.0)),
    )

    (required,) = effective.required_clips
    assert required.frame_rate == 30.0


def test_a_minimum_in_frames_becomes_seconds_at_the_effective_rate() -> None:
    effective = merge(
        an_asset(design=Design(states=(State(name="walk", min_duration_frames=30),))),
        Constraints(animation=AnimationDefaults(clip_naming=CONVENTION, frame_rate=30.0)),
    )

    (required,) = effective.required_clips
    assert required.min_duration_s == 1.0


def test_a_required_clip_is_addressable_by_name() -> None:
    effective = merge(
        an_asset(design=Design(states=(State(name="walk"),))),
        Constraints(animation=AnimationDefaults(clip_naming=CONVENTION)),
    )

    assert effective.required_clip("A_mech_scout_walk") is not None
    assert effective.required_clip("A_mech_scout_test") is None


# --------------------------------------------------------------------------
# resolution on its own
# --------------------------------------------------------------------------


def test_clip_name_for_prefers_the_explicit_name() -> None:
    state = State(name="walk", clip="Locomotion_Walk_Fwd")

    assert clip_name_for(ASSET_ID, state, CONVENTION) == "Locomotion_Walk_Fwd"


def test_clip_name_for_expands_the_template() -> None:
    assert clip_name_for(ASSET_ID, State(name="fire"), CONVENTION) == "A_mech_scout_fire"


def test_clip_name_for_answers_none_when_nothing_resolves() -> None:
    assert clip_name_for(ASSET_ID, State(name="fire"), None) is None
    assert clip_name_for(ASSET_ID, State(name="destroyed", animated=False), CONVENTION) is None


def test_resolving_a_design_that_does_not_exist_yields_nothing() -> None:
    assert resolve_required_clips(ASSET_ID, None, CONVENTION) == ()
