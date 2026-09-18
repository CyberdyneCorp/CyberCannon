"""Task 3.1 — `MeshFacts`, `ClipFacts`, and the mask that makes NOT EVALUATED real.

Zero files on disk, by construction: if a test in this suite ever needs a `.glb`
fixture, the boundary between mesh *reading* and mesh *rules* has moved and D1
has been broken.
"""

from __future__ import annotations

import pytest

from cybercanon.domain.format_matrix import available_for, facts_for
from cybercanon.domain.mesh_facts import (
    ALWAYS_AVAILABLE,
    ClipFacts,
    FabricatedFact,
    FactKind,
    MeshFacts,
    MeshFormat,
)

# --------------------------------------------------------------------------
# The format itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("glb", MeshFormat.GLB),
        ("GLB", MeshFormat.GLB),
        (".fbx", MeshFormat.FBX),
        (" obj ", MeshFormat.OBJ),
        ("gltf", MeshFormat.GLTF),
    ],
)
def test_a_format_is_recognised_however_it_was_spelled(text: str, expected: MeshFormat) -> None:
    assert MeshFormat.from_name(text) is expected


def test_an_unknown_format_is_none_rather_than_an_exception() -> None:
    """The caller reports it as unsupported; it never becomes assumed facts."""
    assert MeshFormat.from_name("usd") is None


def test_a_format_renders_as_its_own_name() -> None:
    assert str(MeshFormat.OBJ) == "OBJ"


# --------------------------------------------------------------------------
# The mask
# --------------------------------------------------------------------------


def test_the_source_format_is_always_available() -> None:
    facts = MeshFacts(source_format=MeshFormat.OBJ, available=frozenset())

    assert facts.available == ALWAYS_AVAILABLE
    assert facts.has(FactKind.SOURCE_FORMAT)


def test_an_unavailable_fact_is_not_defaulted() -> None:
    """`asset-validation`: OBJ records no bone count, so there is no bone count."""
    facts = facts_for(MeshFormat.OBJ, triangles=4200, objects=("SM_crate_LOD0",))

    assert not facts.has(FactKind.BONE_COUNT)
    assert facts.bone_count is None
    assert facts.value(FactKind.BONE_COUNT) is None


def test_a_value_for_an_unavailable_fact_is_refused_not_dropped() -> None:
    with pytest.raises(FabricatedFact) as raised:
        facts_for(MeshFormat.OBJ, triangles=10, bone_count=0)

    assert "BONE_COUNT" in str(raised.value)


def test_a_false_observation_still_counts_as_a_value() -> None:
    """`transforms_applied=False` is an observation, not an absence."""
    with pytest.raises(FabricatedFact):
        facts_for(MeshFormat.OBJ, transforms_applied=False)


def test_a_clip_level_value_is_refused_when_its_fact_is_unavailable() -> None:
    with pytest.raises(FabricatedFact) as raised:
        facts_for(
            MeshFormat.FBX,
            clips=(ClipFacts(name="A_mech_scout_walk", loop_closed=True),),
        )

    assert "CLIP_LOOP" in str(raised.value)


def test_missing_reports_the_first_unavailable_fact_in_declaration_order() -> None:
    facts = facts_for(MeshFormat.OBJ, triangles=10)

    assert facts.missing(frozenset({FactKind.BONE_COUNT, FactKind.UNIT_SCALE})) is (
        FactKind.UNIT_SCALE
    )
    assert facts.missing(frozenset({FactKind.TRIANGLES})) is None


def test_the_value_of_an_available_fact_is_the_observation() -> None:
    facts = facts_for(MeshFormat.GLB, triangles=11840, up_axis="Z")

    assert facts.value(FactKind.TRIANGLES) == 11840
    assert facts.value(FactKind.UP_AXIS) == "Z"


def test_a_fact_kind_carries_the_phrase_a_report_prints() -> None:
    assert FactKind.UNIT_SCALE.label == "unit scale"
    assert str(FactKind.BONE_COUNT) == "bone count"


def test_facts_for_fills_the_mask_from_the_matrix() -> None:
    assert facts_for(MeshFormat.GLB, triangles=1).available == available_for(MeshFormat.GLB)


# --------------------------------------------------------------------------
# Clips
# --------------------------------------------------------------------------


def test_a_clip_reports_its_own_duration_when_the_export_recorded_one() -> None:
    assert ClipFacts(name="walk", duration_s=1.5).seconds == 1.5


def test_a_clip_derives_its_duration_from_frames_and_rate() -> None:
    assert ClipFacts(name="walk", frames=30, frame_rate=30.0).seconds == 1.0


def test_a_clip_with_neither_has_no_duration_rather_than_zero() -> None:
    assert ClipFacts(name="walk").seconds is None
    assert ClipFacts(name="walk", frames=30).seconds is None


def test_clips_are_addressable_by_name() -> None:
    walk = ClipFacts(name="A_mech_scout_walk")
    facts = facts_for(MeshFormat.GLB, clips=(walk,))

    assert facts.clip_names == ("A_mech_scout_walk",)
    assert facts.clip("A_mech_scout_walk") is walk
    assert facts.clip("A_mech_scout_fire") is None
