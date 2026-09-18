"""Task 2.2 and 2.4 — the three authored blocks and the state animation contract."""

from __future__ import annotations

import pytest

from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig, Texture
from cybercanon.domain.design import Design, Socket, State

CONVENTION = "A_{asset}_{state}"


def test_a_concept_names_its_views_and_its_durable_rules() -> None:
    concept = Concept(views=("front", "side"), silhouette_rules=("lens glow is emissive",))

    assert concept.has_view("front")
    assert not concept.has_view("back")
    assert concept.silhouette_rules == ("lens glow is emissive",)


def test_an_empty_block_declares_nothing_and_is_still_a_block() -> None:
    assert Concept().views == ()
    assert Design().states == ()
    assert Constraints().lods == ()


def test_declared_sockets_are_readable_as_the_names_an_export_must_carry() -> None:
    design = Design(
        sockets=(
            Socket(name="SOCKET_muzzle_l", purpose="muzzle flash VFX"),
            Socket(name="SOCKET_muzzle_r", purpose="muzzle flash VFX"),
        )
    )

    assert design.socket_names == ("SOCKET_muzzle_l", "SOCKET_muzzle_r")


def test_a_state_is_reachable_by_name() -> None:
    design = Design(states=(State(name="idle"), State(name="fire")))

    assert design.state("fire") == State(name="fire")
    assert design.state("swim") is None


def test_a_state_with_a_convention_resolves_to_a_clip() -> None:
    assert State(name="walk").resolves_to_a_clip(CONVENTION)
    assert not State(name="walk").constrains_nothing(CONVENTION)


def test_an_explicit_clip_resolves_with_no_convention_at_all() -> None:
    state = State(name="walk", clip="Locomotion_Walk_Fwd")

    assert state.resolves_to_a_clip(None)
    assert not state.constrains_nothing(None)


def test_an_unanimated_state_requires_no_clip_and_is_still_checkable() -> None:
    state = State(name="destroyed", animated=False)

    assert state.is_unanimated
    assert not state.resolves_to_a_clip(CONVENTION)
    assert not state.constrains_nothing(None)


def test_a_state_that_resolves_to_nothing_constrains_nothing() -> None:
    """No clip, no convention, no explicit `animated: false` — a wiki page (D12)."""
    state = State(name="fire")

    assert not state.resolves_to_a_clip(None)
    assert state.constrains_nothing(None)
    assert state.constrains_nothing("")


def test_a_state_carries_the_clip_expectations_a_rule_checks() -> None:
    state = State(
        name="walk",
        loop=True,
        frame_rate=30.0,
        root_motion=True,
        min_duration_s=0.8,
    )

    assert (state.loop, state.frame_rate, state.root_motion) == (True, 30.0, True)
    assert state.minimum_duration_seconds() == 0.8


def test_a_minimum_duration_in_frames_uses_the_state_frame_rate() -> None:
    state = State(name="fire", min_duration_frames=30, frame_rate=60.0)

    assert state.minimum_duration_seconds() == 0.5


def test_a_minimum_duration_in_frames_falls_back_to_the_project_frame_rate() -> None:
    state = State(name="fire", min_duration_frames=15)

    assert state.minimum_duration_seconds(30.0) == 0.5


def test_seconds_win_when_both_forms_are_declared() -> None:
    state = State(name="fire", min_duration_s=2.0, min_duration_frames=15, frame_rate=30.0)

    assert state.minimum_duration_seconds() == 2.0


@pytest.mark.parametrize("default_rate", [None, 0.0])
def test_frames_with_no_frame_rate_anywhere_express_no_minimum(default_rate: float | None) -> None:
    """Better no answer than a fabricated one — the same rule the fact matrix follows."""
    assert State(name="fire", min_duration_frames=15).minimum_duration_seconds(default_rate) is None


def test_a_state_declaring_no_minimum_has_none() -> None:
    assert State(name="idle").minimum_duration_seconds(30.0) is None


def test_the_engineering_block_carries_every_specified_field() -> None:
    constraints = Constraints(
        tri_budget=12000,
        lods=(12000, 6000, 2000),
        texture=Texture(size=2048, sets=1, channels=("basecolor", "orm")),
        rig=Rig(skeleton="SK_Mech", max_bones=96, skinned=True),
        animation=AnimationDefaults(frame_rate=30.0, clip_naming=CONVENTION),
        collider="convex",
        pivot="feet_center",
        up_axis="Z",
        unit_scale=1.0,
        naming="SM_{asset}_LOD{n}",
    )

    assert constraints.clip_naming == CONVENTION
    assert constraints.rig == Rig(skeleton="SK_Mech", max_bones=96, skinned=True)
    assert constraints.texture is not None
    assert constraints.texture.channels == ("basecolor", "orm")


def test_a_constraints_block_with_no_animation_declares_no_convention() -> None:
    assert Constraints().clip_naming is None
    assert Constraints(animation=AnimationDefaults(frame_rate=30.0)).clip_naming is None
