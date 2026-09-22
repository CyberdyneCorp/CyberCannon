"""Step definitions for `animation-playback` — coverage, and the recorded hint.

**Read the pending list beside this file.** The transport itself — pause, scrub,
speed, loop, and the pose a mixer holds — is a claim about a *screen*, and it is
exercised in `apps/cybercanon/web/tests/viewer-clips.test.ts` and
`viewer-render.test.ts`, which run under `just check` through `web-check`. Those
scenarios are listed in `tests/bdd/pending.txt` as the reviewed exception D3
provides for.

What is bound here is the half that is the system: **which declared design state
each clip satisfies**, derived once in the specification and consumed verbatim
(D8), and **what an annotation placed during playback records** — a clip name
and a proportion of its duration, never a frame index, and never anything that
affects the durable key.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from annotations_world import SCOUT_SPEC
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.viewer import StateCoverage
from cybercanon.domain.anchor_resolution import Resolution, resolve
from cybercanon.domain.annotations import Anchor3D
from viewer_world import (
    FIRE,
    PARTS,
    SHOULDER,
    WALK,
    a_spec_with_states,
    a_viewer,
    an_export,
)

TEST_CLIP = "A_mech_scout_test"


@pytest.fixture
def outcome() -> dict[str, Any]:
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario("../features/add-viewer-3d/animation-playback.feature", "Clip is attributed to its state")
def test_clip_is_attributed_to_its_state() -> None: ...


@scenario(
    "../features/add-viewer-3d/animation-playback.feature",
    "An unclaimed clip is labelled, not rejected",
)
def test_an_unclaimed_clip_is_labelled() -> None: ...


@scenario(
    "../features/add-viewer-3d/animation-playback.feature", "Missing clip is shown, not omitted"
)
def test_missing_clip_is_shown_not_omitted() -> None: ...


@scenario(
    "../features/add-viewer-3d/animation-playback.feature",
    "A deliberately unanimated state is not a gap",
)
def test_a_deliberately_unanimated_state_is_not_a_gap() -> None: ...


@scenario("../features/add-viewer-3d/animation-playback.feature", "Clip and position are recorded")
def test_clip_and_position_are_recorded() -> None: ...


@scenario("../features/add-viewer-3d/animation-playback.feature", "The durable key is unaffected")
def test_the_durable_key_is_unaffected() -> None: ...


# --------------------------------------------------------------------------
# Given
# --------------------------------------------------------------------------


@given("a declared state `fire` whose required clip is `A_mech_scout_fire`")
def _a_declared_fire_state(outcome: dict[str, Any]) -> None:
    outcome["viewer"] = a_viewer(a_spec_with_states("fire"))


@given("a preview carrying a clip of that name")
def _a_preview_carrying_the_fire_clip(outcome: dict[str, Any]) -> None:
    outcome["viewer"].record_export(facts=an_export(clips=(FIRE,)))


@given("a preview carrying a clip `A_mech_scout_test` that no declared state requires")
def _a_preview_with_an_unclaimed_clip(outcome: dict[str, Any]) -> None:
    viewer = a_viewer(a_spec_with_states("walk"))
    viewer.record_export(facts=an_export(clips=(WALK, TEST_CLIP)))
    outcome["viewer"] = viewer


@given(
    "declared states `walk` and `fire` requiring clips, with only `walk`'s clip "
    "present in the preview"
)
def _one_clip_of_two_states(outcome: dict[str, Any]) -> None:
    viewer = a_viewer(a_spec_with_states("walk", "fire"))
    viewer.record_export(facts=an_export(clips=(WALK,)))
    outcome["viewer"] = viewer


@given("a state `destroyed` declared as having no animation")
def _an_unanimated_state(outcome: dict[str, Any]) -> None:
    viewer = a_viewer(a_spec_with_states("walk", unanimated=("destroyed",)))
    viewer.record_export(facts=an_export(clips=(WALK,)))
    outcome["viewer"] = viewer


@given("the clip `A_mech_scout_walk` paused at the middle of its duration")
def _paused_at_the_middle(outcome: dict[str, Any]) -> None:
    outcome["viewer"] = a_viewer()
    outcome["playback"] = (WALK, 0.5)


# --------------------------------------------------------------------------
# When
# --------------------------------------------------------------------------


@when("the clips are listed")
def _the_clips_are_listed(outcome: dict[str, Any]) -> None:
    outcome["coverage"] = ran(outcome["viewer"].descriptor()).coverage


@when("an annotation is placed on a part")
def _an_annotation_is_placed(outcome: dict[str, Any]) -> None:
    clip, position = outcome["playback"]
    placed = Anchor3D(part=SHOULDER, point=(0.2, 0.3, 0.1), clip=clip, t=position)
    recorded = ran(outcome["viewer"].threads.create("an_1", anchor=placed))
    outcome["anchor"] = recorded.annotation.target
    outcome["written"] = outcome["viewer"].threads.spec_text(SCOUT_SPEC)


@when("an annotation is placed during playback")
def _placed_during_playback(outcome: dict[str, Any]) -> None:
    viewer = a_viewer()
    placed = Anchor3D(part=SHOULDER, point=(0.2, 0.3, 0.1), clip=WALK, t=0.75)
    ran(viewer.threads.create("an_1", anchor=placed))
    outcome["viewer"] = viewer
    outcome["anchor"] = placed


# --------------------------------------------------------------------------
# Then
# --------------------------------------------------------------------------


@then("that clip SHALL be shown as satisfying the state `fire`")
def _the_clip_satisfies_fire(outcome: dict[str, Any]) -> None:
    coverage = outcome["coverage"]
    assert coverage.state_for(FIRE) == "fire"
    assert [entry.state for entry in coverage.satisfied] == ["fire"]


@then("it SHALL be listed and labelled as satisfying no declared state")
def _the_unclaimed_clip_is_labelled(outcome: dict[str, Any]) -> None:
    coverage = outcome["coverage"]
    assert TEST_CLIP in coverage.unclaimed
    assert coverage.state_for(TEST_CLIP) == ""


@then("`fire` SHALL be listed as having no clip")
def _fire_has_no_clip(outcome: dict[str, Any]) -> None:
    gap = next(entry for entry in outcome["coverage"].states if entry.state == "fire")
    assert gap.coverage is StateCoverage.NO_CLIP


@then("it SHALL NOT be omitted from the listing")
def _fire_is_not_omitted(outcome: dict[str, Any]) -> None:
    assert [entry.state for entry in outcome["coverage"].states] == ["walk", "fire"]


@then("it SHALL be shown as declared unanimated")
def _shown_as_unanimated(outcome: dict[str, Any]) -> None:
    entry = next(entry for entry in outcome["coverage"].states if entry.state == "destroyed")
    assert entry.coverage is StateCoverage.UNANIMATED


@then("it SHALL NOT be shown as having a missing clip")
def _not_shown_as_a_gap(outcome: dict[str, Any]) -> None:
    assert [entry.state for entry in outcome["coverage"].missing] == []


@then("the anchor SHALL record the clip name and a position of one half")
def _the_clip_and_position_are_recorded(outcome: dict[str, Any]) -> None:
    anchor = outcome["anchor"]
    assert anchor.playback == (WALK, 0.5)
    assert "t: 0.5" in outcome["written"]


@then("it SHALL NOT record a frame index")
def _no_frame_index_is_recorded(outcome: dict[str, Any]) -> None:
    written = outcome["written"].lower()
    for token in ("frame", "frames", "frame_index"):
        assert token not in written, f"{token!r} was written beside the playback hint"
    assert not hasattr(outcome["anchor"], "frame")


@then("the anchor SHALL still resolve by its named part")
def _it_still_resolves_by_its_part(outcome: dict[str, Any]) -> None:
    listing = ran(outcome["viewer"].resolutions(parts=PARTS))
    assert listing.entries[0].resolution.outcome is Resolution.RESOLVED
    assert listing.entries[0].resolution.part == SHOULDER


@then("removing the clip from a later export SHALL NOT orphan it")
def _removing_the_clip_does_not_orphan(outcome: dict[str, Any]) -> None:
    viewer = outcome["viewer"]
    viewer.record_export(facts=an_export(clips=()))
    assert ran(viewer.descriptor()).clips == ()
    assert ran(viewer.resolutions(parts=PARTS)).orphan_count == 0
    # And the same answer from the domain function, over the names alone.
    assert resolve(outcome["anchor"], PARTS).outcome is Resolution.RESOLVED
