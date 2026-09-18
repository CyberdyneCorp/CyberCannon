"""Tasks 3.9 and 3.10 — the animation gates, over hand-built `ClipFacts`.

`animation.clip_missing` is the socket loop applied to `design.states` (D12):
one derived requirement list against one export fact list, so a declared state
becomes an export gate without engineering restating it. The four expectation
rules judge a clip that is present, and each names the clip, the expectation and
the observed value.
"""

from __future__ import annotations

from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import AnimationDefaults, Constraints
from cybercanon.domain.design import Design, State
from cybercanon.domain.effective_spec import EffectiveSpec, RequiredClip, merge
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import ClipFacts, MeshFormat
from cybercanon.domain.rules import animation
from cybercanon.domain.violations import Severity

ASSET = "mech_scout"
WALK = "A_mech_scout_walk"
FIRE = "A_mech_scout_fire"
CONVENTION = "A_{asset}_{state}"


def a_spec(*required: RequiredClip) -> EffectiveSpec:
    return EffectiveSpec(asset_id=ASSET, required_clips=required)


def an_export(*clips: ClipFacts):
    return facts_for(MeshFormat.GLB, clips=clips)


# --------------------------------------------------------------------------
# animation.clip_missing
# --------------------------------------------------------------------------


def test_exactly_one_violation_names_the_missing_clip_and_its_state() -> None:
    spec = a_spec(
        RequiredClip(state="walk", clip_name=WALK), RequiredClip(state="fire", clip_name=FIRE)
    )

    (violation,) = tuple(animation.check_clips_present(spec, an_export(ClipFacts(name=WALK))))

    assert violation.rule_id == animation.CLIP_MISSING
    assert violation.severity is Severity.ERROR
    assert violation.subject == FIRE
    assert FIRE in violation.message
    assert "fire" in violation.message


def test_an_extra_clip_is_not_a_violation() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK))
    facts = an_export(ClipFacts(name=WALK), ClipFacts(name="A_mech_scout_test"))

    assert tuple(animation.check_clips_present(spec, facts)) == ()


def test_an_asset_requiring_no_clips_is_unaffected() -> None:
    assert tuple(animation.check_clips_present(a_spec(), an_export())) == ()


def test_the_rule_reads_the_design_states_not_a_separate_engineering_list() -> None:
    asset = Asset(
        id=AssetId(ASSET),
        name="Scout Mech",
        design=Design(states=(State(name="walk"), State(name="fire"))),
        constraints=Constraints(animation=AnimationDefaults(clip_naming=CONVENTION)),
    )

    (violation,) = tuple(
        animation.check_clips_present(merge(asset), an_export(ClipFacts(name=WALK)))
    )

    assert violation.subject == FIRE


# --------------------------------------------------------------------------
# animation.frame_rate_mismatch
# --------------------------------------------------------------------------


def test_a_frame_rate_mismatch_names_the_clip_and_both_rates() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, frame_rate=30.0))
    facts = an_export(ClipFacts(name=WALK, frame_rate=24.0))

    (violation,) = tuple(animation.check_clip_frame_rate(spec, facts))

    assert violation.rule_id == animation.FRAME_RATE
    assert violation.severity is Severity.WARNING
    assert violation.subject == WALK
    assert violation.observed == "24.0"
    assert violation.expected == "30.0"
    assert "30" in violation.message


def test_a_matching_frame_rate_is_silence() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, frame_rate=30.0))

    assert (
        tuple(
            animation.check_clip_frame_rate(spec, an_export(ClipFacts(name=WALK, frame_rate=30.0)))
        )
        == ()
    )


def test_an_undeclared_frame_rate_is_nothing_to_check() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK))

    assert (
        tuple(
            animation.check_clip_frame_rate(spec, an_export(ClipFacts(name=WALK, frame_rate=24.0)))
        )
        == ()
    )


def test_a_missing_clip_is_not_also_a_frame_rate_violation() -> None:
    """One defect, one violation: the clip is absent, and that is what is reported."""
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, frame_rate=30.0))

    assert tuple(animation.check_clip_frame_rate(spec, an_export())) == ()


# --------------------------------------------------------------------------
# animation.duration_too_short
# --------------------------------------------------------------------------


def test_a_clip_shorter_than_the_minimum_states_both_lengths() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, min_duration_s=1.0))
    facts = an_export(ClipFacts(name=WALK, duration_s=0.4))

    (violation,) = tuple(animation.check_clip_duration(spec, facts))

    assert violation.rule_id == animation.DURATION
    assert violation.observed == "0.4"
    assert violation.expected == "1.0"
    assert WALK in violation.message


def test_a_long_enough_clip_is_silence() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, min_duration_s=1.0))

    assert (
        tuple(animation.check_clip_duration(spec, an_export(ClipFacts(name=WALK, duration_s=1.0))))
        == ()
    )


def test_a_duration_expressed_in_frames_is_judged_too() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, min_duration_s=1.0))
    facts = an_export(ClipFacts(name=WALK, frames=12, frame_rate=30.0))

    (violation,) = tuple(animation.check_clip_duration(spec, facts))

    assert violation.observed == "0.4"


# --------------------------------------------------------------------------
# animation.root_motion_missing and animation.loop_not_closed
# --------------------------------------------------------------------------


def test_a_clip_without_the_declared_root_motion_names_the_expectation() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, root_motion=True))
    facts = an_export(ClipFacts(name=WALK, has_root_motion=False))

    (violation,) = tuple(animation.check_clip_root_motion(spec, facts))

    assert violation.rule_id == animation.ROOT_MOTION
    assert violation.subject == WALK
    assert "root" in violation.message
    assert violation.expected == "root motion"


def test_a_clip_with_root_motion_is_silence() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, root_motion=True))
    facts = an_export(ClipFacts(name=WALK, has_root_motion=True))

    assert tuple(animation.check_clip_root_motion(spec, facts)) == ()


def test_a_state_not_declaring_root_motion_judges_nothing() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK))
    facts = an_export(ClipFacts(name=WALK, has_root_motion=False))

    assert tuple(animation.check_clip_root_motion(spec, facts)) == ()


def test_an_unclosed_loop_names_the_clip() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, loop=True))
    facts = an_export(ClipFacts(name=WALK, loop_closed=False))

    (violation,) = tuple(animation.check_clip_loop(spec, facts))

    assert violation.rule_id == animation.LOOP
    assert violation.severity is Severity.WARNING
    assert violation.subject == WALK


def test_a_closed_loop_is_silence() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK, loop=True))
    facts = an_export(ClipFacts(name=WALK, loop_closed=True))

    assert tuple(animation.check_clip_loop(spec, facts)) == ()


def test_a_state_not_declaring_a_loop_judges_nothing() -> None:
    spec = a_spec(RequiredClip(state="walk", clip_name=WALK))
    facts = an_export(ClipFacts(name=WALK, loop_closed=False))

    assert tuple(animation.check_clip_loop(spec, facts)) == ()
