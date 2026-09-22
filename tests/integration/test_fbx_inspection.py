"""Tasks 5.5-5.6 — FBX read into facts, and the facts it refuses to state.

FBX is the format that justifies the capability matrix, so this suite is written
in two halves and the second half matters more:

1. what the reader **does** answer for, compared against what
   `canon_fixtures.fbx` authored — never against the reader's own output;
2. what it **does not**, and the two shapes of "does not":
   * a fact the matrix marks unavailable carries no value at all, so its rule
     reports NOT EVALUATED rather than looking satisfied;
   * a file that does not record a fact the matrix marks *available* is refused
     by name, because a mask is per format and a `None` in an available slot is
     a silent pass.

The fixture is written from code and cross-checked against Blender's own
importer and exporter in `test_fbx_against_blender.py`, which is what keeps the
FBX row a measurement rather than this reader agreeing with its own writer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures import fbx as fixtures
from cybercanon.adapters.outbound.mesh.fbx_facts import clip_name
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.ports.mesh_inspector import MeshUnreadable
from cybercanon.application.ports.preview import PreviewUnavailable
from cybercanon.domain.format_matrix import FBX_UNTRUSTED, available_for, unavailable_for
from cybercanon.domain.mesh_facts import MESH_FIELD_BY_FACT, FactKind, MeshFormat

pytestmark = pytest.mark.integration

SKINNED = "characters/quad_scout/exports/SM_quad_scout_LOD0.fbx"
STATIC = "props/crate/exports/SM_crate_LOD0.fbx"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    fixtures.write_skinned_fbx(tmp_path / SKINNED)
    fixtures.write_static_fbx(tmp_path / STATIC)
    return tmp_path


@pytest.fixture
def inspector(repository: Path) -> TrimeshInspector:
    return TrimeshInspector(root=repository)


# --------------------------------------------------------------------------
# 5.5 — normalisation and the available mask
# --------------------------------------------------------------------------


def test_an_fbx_yields_exactly_its_matrix_row(inspector: TrimeshInspector) -> None:
    facts = inspector.inspect(SKINNED).facts

    assert facts.source_format is MeshFormat.FBX
    assert facts.available == available_for(MeshFormat.FBX)


def test_geometry_names_materials_and_uv_sets_match_the_authored_source(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_fbx(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    assert facts.objects == authored.objects
    assert facts.materials == authored.materials
    assert facts.triangles == authored.triangles
    assert facts.uv_sets == authored.uv_sets


def test_the_armature_holder_is_not_reported_as_an_attachment_point(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """An exporter writes the armature as a `Null` too; a socket it is not."""
    authored = fixtures.write_skinned_fbx(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    assert facts.empties == authored.empties
    assert fixtures.ARMATURE not in facts.empties


def test_the_up_axis_is_read_from_global_settings(inspector: TrimeshInspector) -> None:
    facts = inspector.inspect(SKINNED).facts

    assert facts.up_axis == "Y"


@pytest.mark.parametrize("kind", sorted(FBX_UNTRUSTED, key=lambda kind: kind.order))
def test_a_fact_fbx_cannot_be_trusted_for_carries_no_value(
    inspector: TrimeshInspector, kind: FactKind
) -> None:
    """Unit scale, applied transforms and frame rate are absent, never substituted.

    Blender writes `UnitScaleFactor: 1.0` into a file whose vertices are metres,
    which is why reading it would be worse than not reading it: the rule would
    compare a number nobody wrote against a number somebody did.
    """
    facts = inspector.inspect(SKINNED).facts

    assert kind in unavailable_for(MeshFormat.FBX)
    field = MESH_FIELD_BY_FACT.get(kind)
    if field is not None:
        assert getattr(facts, field) in (None, ())


def test_no_clip_carries_a_rate_a_loop_or_root_motion(inspector: TrimeshInspector) -> None:
    facts = inspector.inspect(SKINNED).facts

    assert facts.clips
    assert all(clip.frame_rate is None for clip in facts.clips)
    assert all(clip.loop_closed is None for clip in facts.clips)
    assert all(clip.has_root_motion is None for clip in facts.clips)


def test_reading_the_same_export_twice_is_the_same_answer(inspector: TrimeshInspector) -> None:
    assert inspector.inspect(SKINNED).facts == inspector.inspect(SKINNED).facts


# --------------------------------------------------------------------------
# 5.6 — animation facts against the authored source
# --------------------------------------------------------------------------


def test_clip_names_match_the_authored_source(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_fbx(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    assert facts.clip_names == authored.clip_names


def test_clip_durations_match_the_authored_source(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_fbx(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    for expected in authored.clips:
        clip = facts.clip(expected.name)
        assert clip is not None, expected.name
        assert clip.duration_s == pytest.approx(expected.duration_s, abs=1e-6)


def test_a_take_named_after_its_object_reports_the_clip_alone() -> None:
    """`Armature|A_scout_walk` is the clip `A_scout_walk` — Blender writes both halves.

    The prefix is stripped only when it names an object in this very file, so a
    clip an artist genuinely named with a `|` keeps its name.
    """
    names = frozenset({"Armature", "SM_scout_LOD0"})

    assert clip_name("Armature|A_scout_walk", names) == "A_scout_walk"
    assert clip_name("Left|Right", names) == "Left|Right"
    assert clip_name("A_scout_walk", names) == "A_scout_walk"


def test_skinning_and_bone_count_match_the_authored_skeleton(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_fbx(repository / SKINNED)

    facts = inspector.inspect(SKINNED).facts

    assert facts.is_skinned is True
    assert facts.bone_count == authored.bone_count == len(fixtures.BONES)


def test_a_static_fbx_reports_no_clips_and_no_skinning(inspector: TrimeshInspector) -> None:
    facts = inspector.inspect(STATIC).facts

    assert facts.clips == ()
    assert facts.is_skinned is False
    assert facts.bone_count == 0


# --------------------------------------------------------------------------
# What is refused, and how loudly
# --------------------------------------------------------------------------


def test_an_ascii_fbx_is_refused_by_name(repository: Path, inspector: TrimeshInspector) -> None:
    """A different grammar, not a variation of this one."""
    fixtures.write_ascii_fbx(repository / "props/crate/exports/ascii.fbx")

    with pytest.raises(MeshUnreadable) as raised:
        inspector.inspect("props/crate/exports/ascii.fbx")

    assert "binary FBX" in raised.value.reason


def test_an_fbx_that_records_no_up_axis_is_refused_rather_than_assumed(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """`up_axis` is in FBX's row, so every FBX must answer for it or be refused."""
    fixtures.write_axisless_fbx(repository / "props/crate/exports/axisless.fbx")

    with pytest.raises(MeshUnreadable) as raised:
        inspector.inspect("props/crate/exports/axisless.fbx")

    assert "up axis" in raised.value.reason


def test_a_polygon_list_with_no_polygon_ends_is_refused(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """Counting it anyway would report every index as its own triangle."""
    fixtures.write_unterminated_fbx(repository / "props/crate/exports/unterminated.fbx")

    with pytest.raises(MeshUnreadable) as raised:
        inspector.inspect("props/crate/exports/unterminated.fbx")

    assert "polygon ends" in raised.value.reason


def test_a_truncated_fbx_is_named_not_assumed(
    repository: Path, inspector: TrimeshInspector
) -> None:
    whole = (repository / SKINNED).read_bytes()
    truncated = repository / "props/crate/exports/truncated.fbx"
    truncated.write_bytes(whole[: len(whole) // 3])

    with pytest.raises(MeshUnreadable) as raised:
        inspector.inspect("props/crate/exports/truncated.fbx")

    assert "truncated.fbx" in raised.value.message


def test_an_fbx_yields_a_preview_carrying_what_the_report_named(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """`fbx_gltf` converts the parsed FBX, so this format has a preview at all.

    It did not: the facts reached the report and nothing turned the same read
    into a previewable document, which cost the 3D viewer a whole format and
    left an FBX-only asset with nothing for an annotation to anchor against.
    What the preview must carry is what the report offered — the object, the
    socket, every bone and every clip — and `test_preview_anchoring.py` asks the
    anchoring question the same way for FBX as for glTF.
    """
    authored = fixtures.write_skinned_fbx(repository / SKINNED)

    preview = inspector.emit_preview(inspector.inspect(SKINNED))

    assert set(authored.objects) | set(authored.empties) <= set(preview.parts)
    assert set(authored.bones) <= set(preview.bones)
    assert preview.clips == authored.clip_names
    assert 0 < preview.triangles < authored.triangles


def test_a_static_fbx_is_previewable_too(repository: Path, inspector: TrimeshInspector) -> None:
    """No skeleton and no clips is not a degraded preview, it is a smaller one."""
    authored = fixtures.write_static_fbx(repository / STATIC)

    preview = inspector.emit_preview(inspector.inspect(STATIC))

    assert set(authored.objects) | set(authored.empties) <= set(preview.parts)
    assert preview.clips == ()


def test_a_vertex_no_cluster_names_is_not_dragged_onto_the_origin(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """Weight painting misses vertices, and glTF punishes that differently.

    A vertex left at four zero weights is multiplied by a zero matrix and ends
    up at the origin — a spike through the middle of the preview rather than a
    vertex that stayed where the export put it. Every vertex therefore leaves
    this converter weighted to something, and the sum is what says so.
    """
    from cybercanon.adapters.outbound.mesh import fbx_gltf
    from cybercanon.adapters.outbound.mesh.fbx_document import FbxDocument

    export = "characters/half_scout/exports/SM_half_scout_LOD0.fbx"
    fixtures.write_partly_skinned_fbx(repository / export)

    converted = fbx_gltf.convert(FbxDocument.read(repository / export))

    primitive = converted.gltf.meshes[0].primitives[0]
    weights = converted.floats(primitive.attributes.WEIGHTS_0)
    assert weights
    assert all(sum(vertex) == pytest.approx(1.0) for vertex in weights)


def test_an_fbx_this_converter_cannot_carry_is_refused_and_not_a_verdict(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """A clip with no curves is refused by name, and the facts are untouched (D7).

    The refusal is a `PreviewUnavailable` rather than an `OperationFailed`, so
    an export whose preview cannot be made still validates on everything the
    rules were able to read.
    """
    export = "props/curveless/exports/SM_curveless_LOD0.fbx"
    authored = fixtures.write_curveless_fbx(repository / export)

    inspected = inspector.inspect(export)

    assert inspected.facts.clip_names == authored.clip_names
    with pytest.raises(PreviewUnavailable, match="carries no curve"):
        inspector.emit_preview(inspected)
