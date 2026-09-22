"""Tasks 1.1-1.5 — anchor resolution as a decision about names, with no geometry.

Every test here builds its part and bone names by hand and never opens a file,
which is D6 asserted rather than described: *"an orphan list that requires a GPU
is a list nobody sees"*. The geometric half — the nearest point on a part's
surface — lives in the browser, and nothing in this module can reach it.
"""

from __future__ import annotations

import dataclasses

import pytest

from cybercanon.domain.anchor_resolution import (
    NO_SUCH_BONE,
    AnchorResolution,
    Resolution,
    resolution_of,
    resolve,
)
from cybercanon.domain.annotations import NO_SUCH_PART, Anchor2D, Anchor3D
from cybercanon.domain.mesh_facts import FactKind, MeshFacts, MeshFormat

SHOULDER = "SM_MechScout_Shoulder_L"
PAULDRON = "SM_MechScout_Pauldron_L"
TORSO = "SM_MechScout_Torso"
ARM = "SM_MechScout_Arm_L"
FOREARM_BONE = "bone_forearm_l"

PARTS = (SHOULDER, TORSO, ARM)


def facts(*objects: str) -> MeshFacts:
    """An export as the validator recorded it — names only, no geometry at all."""
    return MeshFacts(
        source_format=MeshFormat.GLB,
        available=frozenset({FactKind.OBJECTS}),
        objects=objects,
    )


# --------------------------------------------------------------------------
# 1.1 — the value object
# --------------------------------------------------------------------------


def test_a_resolution_is_a_frozen_value_object() -> None:
    resolution = resolve(Anchor3D(part=SHOULDER), PARTS)

    assert dataclasses.is_dataclass(resolution)
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolution.outcome = Resolution.ORPHANED  # type: ignore[misc]


def test_the_outcome_set_is_exactly_three() -> None:
    """`resolved | partial | orphaned`, and the absence of a fourth is the point."""
    assert [member.value for member in Resolution] == ["resolved", "partial", "orphaned"]


def test_a_resolution_carries_the_expected_part_the_bone_and_the_reason() -> None:
    resolution = resolve(Anchor3D(part=SHOULDER, bone=FOREARM_BONE), PARTS, bones=())

    assert (resolution.part, resolution.bone) == (SHOULDER, FOREARM_BONE)
    assert resolution.reason == NO_SUCH_BONE


# --------------------------------------------------------------------------
# 1.2 — part present, part renamed, part absent, bone absent, bone present
# --------------------------------------------------------------------------


def test_a_present_part_resolves() -> None:
    resolution = resolve(Anchor3D(part=SHOULDER), facts(*PARTS).objects)

    assert resolution.outcome is Resolution.RESOLVED
    assert resolution.is_resolved and not resolution.is_orphaned


def test_a_renamed_part_orphans_naming_what_the_anchor_expected() -> None:
    """*"THEN the annotation SHALL be reported as orphaned, naming ..."*"""
    resolution = resolve(Anchor3D(part=SHOULDER), facts(PAULDRON, TORSO).objects)

    assert resolution.outcome is Resolution.ORPHANED
    assert resolution.part == SHOULDER
    assert resolution.reason == NO_SUCH_PART


def test_an_absent_part_orphans() -> None:
    assert resolve(Anchor3D(part=SHOULDER), ()).is_orphaned


def test_an_absent_bone_narrows_to_the_part_rather_than_orphaning() -> None:
    resolution = resolve(Anchor3D(part=ARM, bone=FOREARM_BONE), PARTS, bones=("bone_upper_l",))

    assert resolution.outcome is Resolution.PARTIAL
    assert resolution.is_resolved, "a partial anchor is still placed on its part"
    assert resolution.bone == FOREARM_BONE
    assert resolution.reason == NO_SUCH_BONE


def test_a_present_bone_resolves_fully() -> None:
    resolution = resolve(Anchor3D(part=ARM, bone=FOREARM_BONE), PARTS, bones=(FOREARM_BONE,))

    assert resolution.outcome is Resolution.RESOLVED
    assert resolution.reason == ""


def test_an_anchor_with_no_bone_resolves_against_an_export_with_no_bones() -> None:
    """An unrigged export does not make every part anchor partial."""
    assert resolve(Anchor3D(part=ARM), PARTS, bones=()).outcome is Resolution.RESOLVED


def test_a_caller_that_does_not_know_the_bones_does_not_report_partial() -> None:
    """``None`` is *I have not looked*, which is not *the bone is gone*."""
    anchor = Anchor3D(part=ARM, bone=FOREARM_BONE)

    assert resolve(anchor, PARTS, bones=None).outcome is Resolution.RESOLVED
    assert resolve(anchor, PARTS, bones=()).outcome is Resolution.PARTIAL


def test_resolution_reads_the_part_names_the_facts_already_recorded() -> None:
    """D6: the question is answered over `MeshFacts`, with no mesh loaded."""
    recorded = facts(*PARTS)

    assert resolve(Anchor3D(part=TORSO), recorded.objects).is_resolved


# --------------------------------------------------------------------------
# 1.3 — nothing resolves an orphan automatically
# --------------------------------------------------------------------------


def test_a_near_identical_part_name_still_yields_an_orphan() -> None:
    """The substitution has nowhere to happen, which is why it never happens."""
    present = (f"{SHOULDER} ", SHOULDER.lower(), SHOULDER.replace("_L", "_R"), PAULDRON)

    resolution = resolve(Anchor3D(part=SHOULDER), present)

    assert resolution.outcome is Resolution.ORPHANED
    assert resolution.part == SHOULDER


def test_resolution_never_reports_a_part_the_anchor_did_not_name() -> None:
    resolution = resolve(Anchor3D(part=SHOULDER), (PAULDRON,))

    assert PAULDRON not in (resolution.part, resolution.bone, resolution.reason)


def test_resolving_the_same_anchor_twice_answers_the_same_thing() -> None:
    anchor = Anchor3D(part=SHOULDER, point=(1.0, 2.0, 3.0))

    assert resolve(anchor, PARTS) == resolve(anchor, PARTS)


def test_the_hints_do_not_participate_in_the_decision() -> None:
    """*"The recorded point and normal SHALL be treated as positioning hints only."*"""
    far_away = Anchor3D(part=SHOULDER, point=(900.0, -900.0, 900.0), normal=(0.0, 1.0, 0.0))

    assert resolve(far_away, PARTS) == resolve(Anchor3D(part=SHOULDER), PARTS)


def test_a_two_dimensional_anchor_is_not_a_mesh_anchor() -> None:
    """A concept view resolves against slots, which is `view-versioning`'s question."""
    assert resolution_of(Anchor2D(view="front", u=0.5, v=0.5), PARTS) is None


def test_resolution_of_answers_for_a_mesh_anchor() -> None:
    assert resolution_of(Anchor3D(part=SHOULDER), PARTS) == AnchorResolution(
        outcome=Resolution.RESOLVED, part=SHOULDER
    )


# --------------------------------------------------------------------------
# 1.4 — the playback hint is a proportion, never a frame
# --------------------------------------------------------------------------


@pytest.mark.parametrize("position", [0.0, 0.5, 1.0])
def test_a_playback_position_inside_the_range_is_accepted(position: float) -> None:
    anchor = Anchor3D(part=SHOULDER, clip="A_mech_scout_walk", t=position)

    assert anchor.playback == ("A_mech_scout_walk", position)


@pytest.mark.parametrize("position", [-0.01, 1.01, 24.0, float("nan"), float("inf")])
def test_a_playback_position_outside_the_range_is_refused(position: float) -> None:
    with pytest.raises(ValueError, match="proportion"):
        Anchor3D(part=SHOULDER, clip="A_mech_scout_walk", t=position)


def test_a_position_with_no_clip_is_not_a_playback_hint() -> None:
    assert Anchor3D(part=SHOULDER, t=0.5).playback is None


def test_a_clip_with_no_position_is_not_a_playback_hint() -> None:
    assert Anchor3D(part=SHOULDER, clip="A_mech_scout_walk").playback is None


def test_an_anchor_with_no_playback_hint_says_so() -> None:
    assert Anchor3D(part=SHOULDER).playback is None


def test_the_playback_hint_does_not_enter_the_durable_key() -> None:
    """*"SHALL NOT form part of the anchor's durable key."*"""
    posed = Anchor3D(part=SHOULDER, clip="A_mech_scout_walk", t=0.75)

    assert posed.durable_key == Anchor3D(part=SHOULDER).durable_key
    assert resolve(posed, PARTS) == resolve(Anchor3D(part=SHOULDER), PARTS)


def test_removing_the_clip_from_a_later_export_does_not_orphan_the_anchor() -> None:
    """*"removing the clip from a later export SHALL NOT orphan it."*"""
    posed = Anchor3D(part=SHOULDER, clip="A_mech_scout_walk", t=0.5)

    assert resolve(posed, PARTS).outcome is Resolution.RESOLVED


# --------------------------------------------------------------------------
# 1.5 — the topology prohibition, structurally
# --------------------------------------------------------------------------


FORBIDDEN = ("triangle", "index", "barycentric", "bary", "uvw", "face", "vertex", "frame")


def test_the_anchor_type_has_no_field_for_topology_or_a_frame() -> None:
    offenders = [
        field.name
        for field in dataclasses.fields(Anchor3D)
        if any(token in field.name.lower() for token in FORBIDDEN)
    ]

    assert not offenders, (
        f"{offenders} would let an anchor be stored by something that does not "
        "survive a re-export. The durable key is the named part (asset-spec), and "
        "the playback hint is a proportion (add-viewer-3d D9)."
    )


def test_the_anchor_constructor_refuses_a_field_it_does_not_declare() -> None:
    """A face index has nowhere to go, which is D3 made structural."""
    with pytest.raises(TypeError):
        Anchor3D(part=SHOULDER, face_index=17)  # type: ignore[call-arg]
