"""Step definitions for `anchor-resolution` — the half that is not geometry (D6).

**Read the pending list beside this file.** Resolution is split in two by
design: *"is this anchor's part present in this export"* is a question about
names and is answered here with no renderer; *"where on that part does the pin
go"* needs a mesh and a camera, and is exercised in
`apps/cybercanon/web/tests/viewer-geometry.test.ts`,
`viewer-scene.test.ts` and `viewer-anchor.test.ts`, which run under `just check`
through `web-check`. The geometric scenarios are listed in
`tests/bdd/pending.txt` as the reviewed exception `add-test-strategy`'s D3
provides for, exactly as `add-model-sheet-2d` listed its own screen scenarios.

What is bound here is every scenario whose THEN is satisfiable by the **system**:
the part as the durable key, the orphan that names what it expected, the bone
that narrows rather than orphans, the re-anchoring that is attributed and never
automatic, and the prohibition that gives the whole change its shape — *no
topology identifier is ever written*.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from annotations_world import AUTOMATION_ACTOR, SCOUT_SPEC, a_part_anchor
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.domain.anchor_resolution import Resolution, resolve
from cybercanon.domain.annotations import Anchor3D, Camera
from viewer_world import ARM, PARTS, PAULDRON, SHOULDER, TORSO, Viewer, a_viewer

FOREARM = "bone_forearm_l"
WALK = "A_mech_scout_walk"

CAMERA = Camera(position=(3.0, 2.0, 4.0), target=(0.0, 1.0, 0.0), fov_deg=45.0)


@pytest.fixture
def viewer() -> Viewer:
    """An asset with a validated export, its preview, and nothing else."""
    return a_viewer()


@pytest.fixture
def outcome() -> dict[str, Any]:
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario("../features/add-viewer-3d/anchor-resolution.feature", "Retopology preserves the anchor")
def test_retopology_preserves_the_anchor() -> None: ...


@scenario(
    "../features/add-viewer-3d/anchor-resolution.feature", "Topology identifiers are not stored"
)
def test_topology_identifiers_are_not_stored() -> None: ...


@scenario(
    "../features/add-viewer-3d/anchor-resolution.feature", "A moved hint does not break resolution"
)
def test_a_moved_hint_does_not_break_resolution() -> None: ...


@scenario(
    "../features/add-viewer-3d/anchor-resolution.feature",
    "Renamed part orphans rather than relocates",
)
def test_renamed_part_orphans_rather_than_relocates() -> None: ...


@scenario("../features/add-viewer-3d/anchor-resolution.feature", "Orphans are listed")
def test_orphans_are_listed() -> None: ...


@scenario(
    "../features/add-viewer-3d/anchor-resolution.feature",
    "Orphan status is determinable without rendering",
)
def test_orphan_status_is_determinable_without_rendering() -> None: ...


@scenario("../features/add-viewer-3d/anchor-resolution.feature", "Bone absent, part present")
def test_bone_absent_part_present() -> None: ...


@scenario("../features/add-viewer-3d/anchor-resolution.feature", "Part and bone both present")
def test_part_and_bone_both_present() -> None: ...


@scenario("../features/add-viewer-3d/anchor-resolution.feature", "Placement records the named part")
def test_placement_records_the_named_part() -> None: ...


@scenario(
    "../features/add-viewer-3d/anchor-resolution.feature", "Re-anchoring clears the orphan state"
)
def test_re_anchoring_clears_the_orphan_state() -> None: ...


@scenario(
    "../features/add-viewer-3d/anchor-resolution.feature", "Re-anchoring preserves the conversation"
)
def test_re_anchoring_preserves_the_conversation() -> None: ...


@scenario("../features/add-viewer-3d/anchor-resolution.feature", "Re-anchoring is attributed")
def test_re_anchoring_is_attributed() -> None: ...


@scenario("../features/add-viewer-3d/anchor-resolution.feature", "Nothing re-anchors on its own")
def test_nothing_re_anchors_on_its_own() -> None: ...


# --------------------------------------------------------------------------
# Given
# --------------------------------------------------------------------------


@given("an annotation anchored to part `SM_MechScout_Shoulder_L`")
def _anchored_to_the_shoulder(viewer: Viewer) -> None:
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))


@given(
    "an annotation whose recorded point now lies well away from the mesh surface, "
    "with its named part still present"
)
def _a_hint_far_from_the_surface(viewer: Viewer) -> None:
    far = Anchor3D(part=SHOULDER, point=(900.0, -900.0, 900.0), normal=(0.0, 1.0, 0.0))
    ran(viewer.threads.create("an_1", anchor=far))


@given("a loaded mesh for which three annotations are orphaned")
def _three_orphans(viewer: Viewer) -> None:
    for index, part in enumerate(("SM_Gone_A", "SM_Gone_B", "SM_Gone_C"), start=1):
        ran(viewer.threads.create(f"an_{index}", anchor=a_part_anchor(part)))
    ran(viewer.threads.create("an_4", anchor=a_part_anchor(SHOULDER)))


@given("the set of part names recorded for an export")
def _the_recorded_part_names(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["parts"] = ran(viewer.descriptor()).parts
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    ran(viewer.threads.create("an_2", anchor=a_part_anchor("SM_Gone")))


@given("an anchor naming part `SM_MechScout_Arm_L` and bone `bone_forearm_l`")
def _an_anchor_naming_a_bone(viewer: Viewer) -> None:
    ran(viewer.threads.create("an_1", anchor=Anchor3D(part=ARM, bone=FOREARM)))


@given("an anchor naming a part and a bone both present in the loaded mesh")
def _an_anchor_whose_bone_is_present(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["bones"] = (FOREARM,)
    ran(viewer.threads.create("an_1", anchor=Anchor3D(part=ARM, bone=FOREARM)))


@given("a loaded mesh with a part named `SM_MechScout_Shoulder_L`")
def _a_mesh_with_the_shoulder(viewer: Viewer) -> None:
    assert SHOULDER in ran(viewer.descriptor()).parts


@given("an annotation orphaned because `SM_MechScout_Shoulder_L` is absent")
def _an_orphaned_annotation(viewer: Viewer) -> None:
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    viewer.threads.parts = (PAULDRON,)
    assert ran(viewer.resolutions(parts=(PAULDRON,))).orphan_count == 1


@given("an orphaned annotation with an identifier, text and replies")
def _an_orphan_with_replies(viewer: Viewer) -> None:
    ran(
        viewer.threads.create(
            "an_1", anchor=a_part_anchor(SHOULDER), text="the pauldron reads flat"
        )
    )
    ran(viewer.threads.reply("an_1"))
    viewer.threads.parts = (PAULDRON,)


@given("an orphaned annotation and a loaded mesh containing a plausible replacement part")
def _an_orphan_beside_a_plausible_replacement(viewer: Viewer) -> None:
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    viewer.record_export(facts=_export_named(PAULDRON))


# --------------------------------------------------------------------------
# When
# --------------------------------------------------------------------------


@when(
    "the mesh is retopologised with an entirely different triangle layout and "
    "that part still present"
)
def _retopologised(viewer: Viewer, outcome: dict[str, Any]) -> None:
    # A different layout is a different triangle count over the same names, and
    # resolution reads the names — which is the property being checked.
    viewer.record_export(facts=_export_named(*PARTS, triangles=98_000))
    outcome["resolutions"] = ran(viewer.resolutions())


@when("a 3D anchor is created and written")
def _a_3d_anchor_is_written(viewer: Viewer, outcome: dict[str, Any]) -> None:
    placed = Anchor3D(
        part=SHOULDER,
        point=(0.2, 0.3, 0.1),
        normal=(0.0, 0.0, 1.0),
        camera=CAMERA,
        clip=WALK,
        t=0.5,
    )
    ran(viewer.threads.create("an_1", anchor=placed))
    outcome["written"] = viewer.threads.spec_text(SCOUT_SPEC)


@when("the anchor is resolved")
def _the_anchor_is_resolved(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["resolutions"] = ran(viewer.resolutions(bones=outcome.get("bones")))


@when("an export is loaded in which that part is named `SM_MechScout_Pauldron_L`")
def _the_part_is_renamed(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["resolutions"] = ran(viewer.resolutions(parts=(PAULDRON, TORSO)))


@when("the asset's annotations are presented")
def _the_annotations_are_presented(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["resolutions"] = ran(viewer.resolutions())


@when("an asset's annotations are evaluated against that set")
def _evaluated_against_the_names(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["resolutions"] = ran(viewer.resolutions(parts=outcome["parts"]))


@when("a mesh containing that part but no such bone is loaded")
def _a_mesh_without_that_bone(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["resolutions"] = ran(viewer.resolutions(bones=("bone_upper_l",)))


@when("an annotation is placed by pointing at that part")
def _an_annotation_is_placed(viewer: Viewer, outcome: dict[str, Any]) -> None:
    placed = Anchor3D(part=SHOULDER, point=(0.2, 0.3, 0.1), normal=(0.0, 0.0, 1.0), camera=CAMERA)
    outcome["recorded"] = ran(viewer.threads.create("an_1", anchor=placed)).annotation


@when("a person re-anchors it to `SM_MechScout_Pauldron_L`")
def _a_person_re_anchors_it(viewer: Viewer) -> None:
    ran(viewer.threads.reanchor("an_1", a_part_anchor(PAULDRON)))


@when("it is re-anchored")
def _it_is_re_anchored(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["before"] = viewer.threads.annotation("an_1")
    ran(viewer.threads.reanchor("an_1", a_part_anchor(PAULDRON)))


@when("a person re-anchors an annotation through an automated caller acting on their behalf")
def _re_anchored_through_an_agent(viewer: Viewer, outcome: dict[str, Any]) -> None:
    ran(viewer.threads.create("an_1", anchor=a_part_anchor(SHOULDER)))
    viewer.threads.parts = (PAULDRON,)
    ran(viewer.threads.reanchor("an_1", a_part_anchor(PAULDRON), via=_agent()))
    outcome["message"] = viewer.threads.messages()[-1]


@when("the mesh is loaded and resolved")
def _the_mesh_is_loaded_and_resolved(viewer: Viewer, outcome: dict[str, Any]) -> None:
    outcome["resolutions"] = ran(viewer.resolutions(parts=(PAULDRON,)))
    outcome["automated"] = viewer.threads.reanchor(
        "an_1", a_part_anchor(PAULDRON), actor=AUTOMATION_ACTOR
    )


# --------------------------------------------------------------------------
# Then
# --------------------------------------------------------------------------


@then("the annotation SHALL resolve to that part")
def _it_resolves_to_that_part(outcome: dict[str, Any]) -> None:
    entry = _one(outcome)
    assert entry.resolution.outcome is Resolution.RESOLVED
    assert entry.resolution.part == SHOULDER


@then("the written anchor SHALL contain no triangle index, barycentric coordinate or vertex index")
def _no_topology_is_written(outcome: dict[str, Any]) -> None:
    written = outcome["written"].lower()
    for token in ("triangle", "barycentric", "bary", "face_index", "vertex_index", "uvw"):
        assert token not in written, f"{token!r} was written into the specification"
    # The hint, the camera and the playback proportion are what a 3D anchor does
    # carry, so the assertion above is checking an absence rather than an empty file.
    assert "part:" in written and "camera:" in written and "t: 0.5" in written


@then("it SHALL resolve to that part rather than being reported as orphaned")
def _it_is_not_orphaned(outcome: dict[str, Any]) -> None:
    assert _one(outcome).resolution.outcome is Resolution.RESOLVED


@then("the annotation SHALL be reported as orphaned, naming `SM_MechScout_Shoulder_L`")
def _orphaned_naming_the_shoulder(outcome: dict[str, Any]) -> None:
    entry = _one(outcome)
    assert entry.resolution.is_orphaned
    assert entry.resolution.part == SHOULDER


@then("it SHALL NOT be placed on `SM_MechScout_Pauldron_L`")
def _not_placed_on_the_pauldron(outcome: dict[str, Any]) -> None:
    assert _one(outcome).resolution.part != PAULDRON


@then("the three SHALL be presented as orphaned and SHALL be countable as such")
def _three_are_orphaned(outcome: dict[str, Any]) -> None:
    listing = outcome["resolutions"]
    assert listing.orphan_count == 3
    assert {entry.id for entry in listing.orphaned} == {"an_1", "an_2", "an_3"}


@then(
    "each annotation's orphan status SHALL be determinable from the part names "
    "alone, with no mesh geometry loaded"
)
def _determinable_from_names_alone(outcome: dict[str, Any]) -> None:
    listing = outcome["resolutions"]
    assert listing.orphan_count == 1
    # The same answer, from the domain function over the names and nothing else.
    assert resolve(Anchor3D(part="SM_Gone"), outcome["parts"]).is_orphaned
    assert resolve(Anchor3D(part=SHOULDER), outcome["parts"]).is_resolved


@then("the anchor SHALL resolve to the part")
def _it_resolves_to_the_part(outcome: dict[str, Any]) -> None:
    assert _one(outcome).resolution.part == ARM


@then("it SHALL be reported as partially resolved, naming the missing bone")
def _partially_resolved(outcome: dict[str, Any]) -> None:
    resolution = _one(outcome).resolution
    assert resolution.outcome is Resolution.PARTIAL
    assert resolution.bone == FOREARM


@then("it SHALL be reported as fully resolved")
def _fully_resolved(outcome: dict[str, Any]) -> None:
    assert _one(outcome).resolution.outcome is Resolution.RESOLVED


@then("the anchor SHALL record `SM_MechScout_Shoulder_L` as its part")
def _the_anchor_records_the_part(outcome: dict[str, Any]) -> None:
    assert outcome["recorded"].target.part == SHOULDER
    assert outcome["recorded"].durable_key == SHOULDER


@then("it SHALL record the surface point, the normal and the current camera")
def _the_anchor_records_the_hints(outcome: dict[str, Any]) -> None:
    anchor = outcome["recorded"].target
    assert anchor.point == (0.2, 0.3, 0.1)
    assert anchor.normal == (0.0, 0.0, 1.0)
    assert anchor.camera == CAMERA


@then("the annotation SHALL resolve to `SM_MechScout_Pauldron_L`")
def _it_resolves_to_the_pauldron(viewer: Viewer) -> None:
    entry = ran(viewer.resolutions(parts=(PAULDRON,))).entries[0]
    assert entry.resolution.part == PAULDRON
    assert entry.resolution.outcome is Resolution.RESOLVED


@then("it SHALL no longer be reported as orphaned")
def _no_longer_orphaned(viewer: Viewer) -> None:
    assert ran(viewer.resolutions(parts=(PAULDRON,))).orphan_count == 0


@then("its identifier, text, replies and open state SHALL be unchanged")
def _the_conversation_is_preserved(viewer: Viewer, outcome: dict[str, Any]) -> None:
    before, after = outcome["before"], viewer.threads.annotation("an_1")
    assert after is not None and before is not None
    assert (after.id, after.text, after.state) == (before.id, before.text, before.state)
    assert [reply.id for reply in after.replies] == [reply.id for reply in before.replies]


@then("the recorded change SHALL name both that person and the caller")
def _the_change_names_both(viewer: Viewer, outcome: dict[str, Any]) -> None:
    annotation = viewer.threads.annotation("an_1")
    assert annotation is not None
    assert annotation.reanchored_by == "auth|rafa"
    assert "blender-agent" in outcome["message"]


@then("the annotation SHALL remain orphaned until a person re-anchors it")
def _it_remains_orphaned(viewer: Viewer, outcome: dict[str, Any]) -> None:
    assert outcome["resolutions"].orphan_count == 1
    assert refused(outcome["automated"]).kind.value == "forbidden"
    annotation = viewer.threads.annotation("an_1")
    assert annotation is not None and annotation.durable_key == SHOULDER


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _one(outcome: dict[str, Any]):
    """The single resolution this scenario is about."""
    entries = outcome["resolutions"].entries
    assert len(entries) == 1, f"expected one resolution, got {entries}"
    return entries[0]


def _export_named(*parts: str, triangles: int = 14310):
    from viewer_world import an_export

    return an_export(triangles=triangles, parts=parts)


def _agent():
    from cybercanon.domain.identity import AgentId

    return AgentId("blender-agent")
