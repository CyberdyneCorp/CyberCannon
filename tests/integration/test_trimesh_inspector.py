"""Tasks 5.5-5.6 — `TrimeshInspector` against real exports written to disk.

The domain suite proves the rules; this proves the *reading*. Every assertion
below compares what the adapter extracted against what
`canon_fixtures.mesh` authored, never against the adapter's own output, because
a reader compared to itself is a reader that cannot be wrong.

Three properties are the reason this suite exists at all:

* the `available` mask is exactly the format's matrix row, so NOT EVALUATED has a
  basis the adapter did not invent (D13);
* a fact the format cannot carry has **no** substitute value — not ``0``, not
  ``1.0``, not ``"Y"``;
* clip names and durations match the authored source, which is the fact the
  risks section says `trimesh` is weakest at and the reason glTF is read through
  `pygltflib` here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.mesh.gltf_facts import GLTF_UNIT_SCALE, GLTF_UP_AXIS
from cybercanon.adapters.outbound.mesh.trimesh_inspector import FBX_REASON, TrimeshInspector
from cybercanon.application.ports.mesh_inspector import MeshUnreadable, UnsupportedExport
from cybercanon.domain.format_matrix import available_for, unavailable_for
from cybercanon.domain.mesh_facts import MESH_FIELD_BY_FACT, MeshFormat

pytestmark = pytest.mark.integration

SKINNED = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
STATIC_GLB = "props/crate/exports/SM_crate_LOD0.glb"
STATIC_OBJ = "props/crate/exports/SM_crate_LOD0.obj"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A working copy holding one export of each shape the adapter can read."""
    fixtures.write_skinned_glb(tmp_path / SKINNED)
    fixtures.write_static_glb(tmp_path / STATIC_GLB)
    fixtures.write_static_obj(tmp_path / STATIC_OBJ)
    return tmp_path


@pytest.fixture
def inspector(repository: Path) -> TrimeshInspector:
    return TrimeshInspector(root=repository)


# --------------------------------------------------------------------------
# 5.5 — per-format normalisation and the available mask
# --------------------------------------------------------------------------


def test_a_glb_yields_every_fact_its_matrix_row_promises(inspector: TrimeshInspector) -> None:
    facts = inspector.inspect(SKINNED).facts

    assert facts.source_format is MeshFormat.GLB
    assert facts.available == available_for(MeshFormat.GLB)


def test_glb_geometry_names_materials_and_sockets_are_read(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_glb(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    assert facts.objects == authored.objects
    assert facts.empties == authored.empties, "a socket is an attachment point, not a bone"
    assert facts.materials == authored.materials
    assert facts.triangles == authored.triangles
    assert facts.uv_sets == authored.uv_sets


def test_glb_scale_and_axis_are_normalised_to_what_gltf_defines(
    inspector: TrimeshInspector,
) -> None:
    """glTF is metres and `+Y` up by definition; normalisation is stating that."""
    facts = inspector.inspect(SKINNED).facts

    assert facts.unit_scale == GLTF_UNIT_SCALE
    assert facts.up_axis == GLTF_UP_AXIS
    assert facts.transforms_applied is True


def test_an_obj_yields_four_facts_and_substitutes_nothing(inspector: TrimeshInspector) -> None:
    """D13 — OBJ records no unit scale, so the report must not claim one."""
    facts = inspector.inspect(STATIC_OBJ).facts

    assert facts.available == available_for(MeshFormat.OBJ)
    absent = [
        MESH_FIELD_BY_FACT[kind]
        for kind in unavailable_for(MeshFormat.OBJ)
        if kind in MESH_FIELD_BY_FACT
    ]
    assert all(getattr(facts, field) in (None, ()) for field in absent), absent


def test_obj_triangles_objects_and_materials_match_the_authored_source(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_static_obj(repository / STATIC_OBJ)

    facts = inspector.inspect(STATIC_OBJ).facts

    assert facts.triangles == authored.triangles
    assert facts.objects == authored.objects
    assert facts.materials == authored.materials
    assert facts.uv_sets == authored.uv_sets


def test_reading_the_same_export_twice_is_the_same_answer(inspector: TrimeshInspector) -> None:
    assert inspector.inspect(SKINNED).facts == inspector.inspect(SKINNED).facts


def test_an_fbx_export_is_refused_by_name_rather_than_guessed_at(repository: Path) -> None:
    """The honest gap: no FBX reader ships here, and empty facts would be a lie."""
    (repository / "characters/mech_scout/exports/SM_mech_scout_LOD0.fbx").write_bytes(b"Kaydara")

    with pytest.raises(MeshUnreadable) as raised:
        TrimeshInspector(root=repository).inspect(
            "characters/mech_scout/exports/SM_mech_scout_LOD0.fbx"
        )

    assert FBX_REASON in raised.value.message


def test_a_format_with_no_matrix_row_is_refused_by_name(repository: Path) -> None:
    (repository / "props/crate/exports/crate.blend").write_bytes(b"BLENDER")

    with pytest.raises(UnsupportedExport) as raised:
        TrimeshInspector(root=repository).inspect("props/crate/exports/crate.blend")

    assert "blend" in raised.value.message


def test_a_truncated_export_is_named_not_assumed(repository: Path) -> None:
    fixtures.write_unreadable_glb(repository / "props/crate/exports/truncated.glb")

    with pytest.raises(MeshUnreadable) as raised:
        TrimeshInspector(root=repository).inspect("props/crate/exports/truncated.glb")

    assert "truncated.glb" in raised.value.message


# --------------------------------------------------------------------------
# 5.6 — animation facts against the authored source
# --------------------------------------------------------------------------


def test_clip_names_match_the_authored_source(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_glb(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    assert facts.clip_names == authored.clip_names


def test_clip_durations_frames_and_frame_rates_match_the_authored_source(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_glb(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    for expected in authored.clips:
        clip = facts.clip(expected.name)
        assert clip is not None
        assert clip.duration_s == pytest.approx(expected.duration_s, abs=1e-5)
        assert clip.frame_rate == pytest.approx(expected.frame_rate)
        assert clip.frames == round(expected.duration_s * expected.frame_rate)


def test_loop_closure_is_read_per_clip_not_assumed(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """The fixture closes one clip and leaves the other open; both must be seen."""
    authored = fixtures.write_skinned_glb(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    observed = {clip.name: clip.loop_closed for clip in facts.clips}
    assert observed == {clip.name: clip.loop_closed for clip in authored.clips}


def test_root_motion_is_read_from_the_skeleton_root(inspector: TrimeshInspector) -> None:
    facts = inspector.inspect(SKINNED).facts

    assert all(clip.has_root_motion for clip in facts.clips)


def test_skinning_and_bone_count_match_the_authored_skeleton(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_glb(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    assert facts.is_skinned is authored.is_skinned
    assert facts.bone_count == authored.bone_count


def test_a_static_glb_reports_no_clips_and_no_skinning(inspector: TrimeshInspector) -> None:
    facts = inspector.inspect(STATIC_GLB).facts

    assert facts.clips == ()
    assert facts.is_skinned is False
    assert facts.bone_count == 0
