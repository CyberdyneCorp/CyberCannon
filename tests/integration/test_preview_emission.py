"""Tasks 5.8-5.9 — what a real preview keeps, and what it refuses to lose.

`asset-preview` spends one requirement on the preview being small and four on
what it may not drop, which is the right proportion: a preview that loads but
cannot animate, or whose parts are unnamed, sends the 3D viewer back to the
200 MB working export and every annotation anchored to a part goes with it.

So the assertions here are almost all negative-space: the same clip names, the
same durations, the same bone names, the same object and attachment point names,
fewer triangles, fewer bytes. The last test is the one that matters most — an
emitter that *cannot* carry the clips reports a failure rather than writing a
clipless preview, and that decision is `verify_carried`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.mesh import gltf_preview
from cybercanon.adapters.outbound.mesh.gltf_document import GltfDocument
from cybercanon.adapters.outbound.mesh.gltf_preview import Carried, describe, verify_carried
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.ports.preview import GLB_CONTENT_TYPE, PreviewUnavailable

pytestmark = pytest.mark.integration

SKINNED = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
STATIC = "props/crate/exports/SM_crate_LOD0.glb"
STATIC_OBJ = "props/crate/exports/SM_crate_LOD0.obj"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    fixtures.write_skinned_glb(tmp_path / SKINNED)
    fixtures.write_static_glb(tmp_path / STATIC)
    fixtures.write_static_obj(tmp_path / STATIC_OBJ)
    return tmp_path


@pytest.fixture
def inspector(repository: Path) -> TrimeshInspector:
    return TrimeshInspector(root=repository)


# --------------------------------------------------------------------------
# 5.8 — decimated, smaller, and still anchorable
# --------------------------------------------------------------------------


def test_a_preview_has_fewer_triangles_than_its_source(inspector: TrimeshInspector) -> None:
    inspected = inspector.inspect(SKINNED)

    preview = inspector.emit_preview(inspected)

    assert inspected.facts.triangles is not None
    assert preview.triangles < inspected.facts.triangles


def test_a_preview_is_a_smaller_file_than_its_source(
    repository: Path, inspector: TrimeshInspector
) -> None:
    preview = inspector.emit_preview(inspector.inspect(SKINNED))

    assert preview.size_bytes < (repository / SKINNED).stat().st_size
    assert preview.content_type == GLB_CONTENT_TYPE


def test_a_preview_is_still_a_readable_gltf(inspector: TrimeshInspector) -> None:
    """A preview nothing can open is not a preview."""
    preview = inspector.emit_preview(inspector.inspect(SKINNED))

    assert describe(GltfDocument.from_bytes(preview.content)).triangles == preview.triangles


def test_object_and_attachment_point_names_survive_decimation(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """The durable key of a 3D anchor is the part name; losing it orphans feedback."""
    authored = fixtures.write_skinned_glb(repository / SKINNED)

    preview = inspector.emit_preview(inspector.inspect(SKINNED))

    assert set(authored.objects) <= set(preview.parts)
    assert set(authored.empties) <= set(preview.parts)


def test_a_preview_of_an_obj_keeps_its_object_names(inspector: TrimeshInspector) -> None:
    preview = inspector.emit_preview(inspector.inspect(STATIC_OBJ))

    assert "SM_crate_LOD0" in preview.parts


# --------------------------------------------------------------------------
# 5.9 — clips and skinning survive, or the preview fails
# --------------------------------------------------------------------------


def test_clip_names_and_durations_survive_decimation(
    repository: Path, inspector: TrimeshInspector
) -> None:
    authored = fixtures.write_skinned_glb(repository / SKINNED)
    source = describe(GltfDocument.read(repository / SKINNED))

    preview = inspector.emit_preview(inspector.inspect(SKINNED))
    carried = describe(GltfDocument.from_bytes(preview.content))

    assert preview.clips == authored.clip_names
    assert carried.durations == source.durations


def test_bone_names_survive_decimation(repository: Path, inspector: TrimeshInspector) -> None:
    authored = fixtures.write_skinned_glb(repository / SKINNED)

    preview = inspector.emit_preview(inspector.inspect(SKINNED))

    assert preview.bones == authored.bones
    assert describe(GltfDocument.from_bytes(preview.content)).bones == authored.bones


def test_a_source_without_clips_yields_a_preview_without_clips(
    inspector: TrimeshInspector,
) -> None:
    """And that is not a failure: absence is only a failure when it was a loss."""
    preview = inspector.emit_preview(inspector.inspect(STATIC))

    assert preview.clips == ()
    assert preview.bones == ()
    assert preview.triangles > 0


def test_an_emitter_that_would_drop_the_clips_reports_a_failure(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """The decision `asset-preview` asks for: fail rather than write a clipless preview."""
    source = describe(GltfDocument.read(repository / SKINNED))
    clipless = Carried(
        triangles=source.triangles // 4,
        parts=source.parts,
        clip_names=(),
        durations=(),
        bones=source.bones,
    )

    with pytest.raises(PreviewUnavailable) as raised:
        verify_carried(source, clipless)

    assert "animation clips" in str(raised.value)
    assert source.clip_names[0] in str(raised.value)


def test_a_preview_that_dropped_a_bone_is_refused(repository: Path) -> None:
    source = describe(GltfDocument.read(repository / SKINNED))
    boneless = Carried(
        triangles=source.triangles // 4,
        parts=source.parts,
        clip_names=source.clip_names,
        durations=source.durations,
        bones=(),
    )

    with pytest.raises(PreviewUnavailable, match="bones"):
        verify_carried(source, boneless)


def test_a_preview_that_dropped_a_named_part_is_refused(repository: Path) -> None:
    source = describe(GltfDocument.read(repository / SKINNED))
    partless = Carried(
        triangles=source.triangles // 4,
        parts=(),
        clip_names=source.clip_names,
        durations=source.durations,
        bones=source.bones,
    )

    with pytest.raises(PreviewUnavailable, match="named parts"):
        verify_carried(source, partless)


def test_a_preview_whose_clip_durations_changed_is_refused(repository: Path) -> None:
    """A clip that plays at a different length is not the clip that was authored."""
    source = describe(GltfDocument.read(repository / SKINNED))
    stretched = Carried(
        triangles=source.triangles // 4,
        parts=source.parts,
        clip_names=source.clip_names,
        durations=tuple(duration * 2 for duration in source.durations),
        bones=source.bones,
    )

    with pytest.raises(PreviewUnavailable, match="durations"):
        verify_carried(source, stretched)


def test_an_export_that_was_not_read_into_a_document_yields_no_preview(
    inspector: TrimeshInspector,
) -> None:
    """A preview failure is never an operation failure: the verdict stands (D7)."""
    from cybercanon.application.ports.mesh_inspector import InspectedMesh

    with pytest.raises(PreviewUnavailable):
        inspector.emit_preview(InspectedMesh(facts=inspector.inspect(STATIC).facts, handle=None))


def test_decimation_settings_control_the_target(repository: Path) -> None:
    gentle = TrimeshInspector(root=repository, settings=gltf_preview.PreviewSettings(ratio=0.5))
    aggressive = TrimeshInspector(root=repository, settings=gltf_preview.PreviewSettings(ratio=0.1))

    assert (
        aggressive.emit_preview(aggressive.inspect(SKINNED)).triangles
        < gentle.emit_preview(gentle.inspect(SKINNED)).triangles
    )
