"""Tasks 5.8-5.9 — what a real preview keeps, and what it refuses to lose.

`asset-preview` spends one requirement on the preview being small and four on
what it may not drop, which is the right proportion: a preview that loads but
cannot animate, or whose parts are unnamed, sends the 3D viewer back to the
200 MB working export and every annotation anchored to a part goes with it.

So the assertions here are almost all negative-space: the same clip names, the
same durations, the same bone names, the same object and attachment point names,
fewer triangles, fewer bytes. Two of them matter most. An emitter that *cannot*
carry the clips reports a failure rather than writing a clipless preview, and
that decision is `verify_carried`. And a Draco payload that dropped `JOINTS_0`
would produce a file that loads, lists its bones, plays its clips and is not
skinned — so the compressed payload is decoded and checked attribute by
attribute, because nothing in the node graph would have shown it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.mesh import gltf_draco, gltf_preview
from cybercanon.adapters.outbound.mesh.gltf_document import GltfDocument
from cybercanon.adapters.outbound.mesh.gltf_draco import DracoUnsupported
from cybercanon.adapters.outbound.mesh.gltf_preview import Carried, describe, verify_carried
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.ports.preview import GLB_CONTENT_TYPE, PreviewUnavailable

pytestmark = pytest.mark.integration

SKINNED = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
RIGGED = "characters/mech_scout/exports/SM_mech_scout_rig_LOD0.glb"
STATIC = "props/crate/exports/SM_crate_LOD0.glb"
STATIC_OBJ = "props/crate/exports/SM_crate_LOD0.obj"

SHORT = 5122
"""A signed component type: legal glTF, and outside Draco's generic slots."""


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    fixtures.write_skinned_glb(tmp_path / SKINNED)
    fixtures.write_rigged_glb(tmp_path / RIGGED)
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


# --------------------------------------------------------------------------
# 5.8 — Draco compression, and what it is not allowed to cost
# --------------------------------------------------------------------------


@pytest.fixture
def without_an_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    """The machine D7's risk describes: one where Draco would not install."""
    monkeypatch.setattr(gltf_draco, "available", lambda: False)


def test_the_preview_is_draco_compressed(inspector: TrimeshInspector) -> None:
    """D7 asks for Draco, and a browser is told so through `extensionsRequired`."""
    preview = GltfDocument.from_bytes(inspector.emit_preview(inspector.inspect(RIGGED)).content)

    assert gltf_draco.is_compressed(preview)
    assert gltf_draco.DRACO_EXTENSION in (preview.gltf.extensionsRequired or [])
    assert gltf_draco.DRACO_EXTENSION in (preview.gltf.extensionsUsed or [])


def test_every_drawn_primitive_carries_its_geometry_in_draco(
    inspector: TrimeshInspector,
) -> None:
    """One compressed primitive beside an uncompressed one would be neither form."""
    preview = GltfDocument.from_bytes(inspector.emit_preview(inspector.inspect(RIGGED)).content)

    for primitive in preview.primitives():
        assert gltf_draco.DRACO_EXTENSION in (primitive.extensions or {})
        assert preview.gltf.accessors[primitive.indices].bufferView is None


def test_the_compressed_payload_carries_the_skin_attributes(
    inspector: TrimeshInspector,
) -> None:
    """The quiet failure: a file that loads, lists its bones, and is not skinned.

    `JOINTS_0` and `WEIGHTS_0` are ordinary vertex attributes, so an encoder that
    dropped them would leave the node graph, the skins and the clips intact and
    the mesh unbound. Nothing above this line would notice.
    """
    preview = GltfDocument.from_bytes(inspector.emit_preview(inspector.inspect(RIGGED)).content)

    for primitive in preview.primitives():
        mapped = primitive.extensions[gltf_draco.DRACO_EXTENSION]["attributes"]
        assert {"POSITION", "JOINTS_0", "WEIGHTS_0", "TEXCOORD_0"} <= set(mapped)
    gltf_draco.verify(preview)


def test_a_payload_that_lost_the_skin_attributes_is_refused(
    inspector: TrimeshInspector,
) -> None:
    """And the refusal is a *check*, not a hope: verification decodes what was written."""
    preview = GltfDocument.from_bytes(inspector.emit_preview(inspector.inspect(RIGGED)).content)
    for primitive in preview.primitives():
        primitive.extensions[gltf_draco.DRACO_EXTENSION]["attributes"].pop("JOINTS_0")

    with pytest.raises(DracoUnsupported, match="JOINTS_0"):
        gltf_draco.verify(preview)


def test_compression_makes_the_preview_smaller_still(
    repository: Path, inspector: TrimeshInspector, monkeypatch: pytest.MonkeyPatch
) -> None:
    compressed = inspector.emit_preview(inspector.inspect(RIGGED)).size_bytes

    monkeypatch.setattr(gltf_draco, "available", lambda: False)
    plain = TrimeshInspector(root=repository)

    assert compressed < plain.emit_preview(plain.inspect(RIGGED)).size_bytes


@pytest.mark.usefixtures("without_an_encoder")
def test_a_machine_with_no_encoder_still_gets_a_whole_preview(repository: Path) -> None:
    """D7's recorded risk: a native dependency that will not install somewhere.

    The cost is bytes and nothing else — the preview still carries every part,
    clip and bone, because that is what a preview is judged on.
    """
    authored = fixtures.write_rigged_glb(repository / RIGGED)
    inspector = TrimeshInspector(root=repository)

    preview = inspector.emit_preview(inspector.inspect(RIGGED))

    assert not gltf_draco.is_compressed(GltfDocument.from_bytes(preview.content))
    assert set(authored.objects) <= set(preview.parts)
    assert preview.clips == authored.clip_names
    assert preview.bones == authored.bones
    assert preview.size_bytes < (repository / RIGGED).stat().st_size


def test_a_rigged_export_keeps_every_part_and_every_bone(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """The scenarios' own export: two named parts, a socket, 74 bones, two clips."""
    authored = fixtures.write_rigged_glb(repository / RIGGED)

    preview = inspector.emit_preview(inspector.inspect(RIGGED))

    assert fixtures.SHOULDER in preview.parts
    assert set(authored.objects) <= set(preview.parts)
    assert set(authored.empties) <= set(preview.parts)
    assert preview.bones == authored.bones
    assert len(preview.bones) == fixtures.RIG_BONES
    assert preview.clips == authored.clip_names
    assert preview.triangles < authored.triangles


def test_an_attribute_draco_has_no_slot_for_is_refused(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """Draco takes unsigned integers and floats; a signed one is refused, not bent.

    The preview is still emitted — uncompressed, whole — which is the whole point
    of keeping compression a choice rather than a requirement.
    """
    document = GltfDocument.read(repository / STATIC)
    primitive = document.primitives()[0]
    document.gltf.accessors[primitive.attributes.POSITION].componentType = SHORT

    with pytest.raises(DracoUnsupported, match="not encodable"):
        gltf_draco.compress(document, primitive, ((0, 1, 2),))

    assert inspector.emit_preview(inspector.inspect(STATIC)).triangles > 0


@pytest.mark.parametrize("export", [RIGGED, STATIC, STATIC_OBJ])
def test_no_accessor_declares_an_offset_into_nothing(
    inspector: TrimeshInspector, export: str
) -> None:
    """glTF forbids `byteOffset` on an accessor that has no `bufferView`.

    Regression: the first compressed emission left the index accessor's default
    offset of zero in place beside a cleared buffer view, and the Khronos
    validator rejects that as `UNSATISFIED_DEPENDENCY` — an error, not a warning,
    so a strict loader would refuse the preview outright. Nothing in this suite
    saw it, because `pygltflib` reads such a file back perfectly happily.
    """
    content = inspector.emit_preview(inspector.inspect(export)).content

    orphaned = [
        index
        for index, accessor in enumerate(_glb_json(content)["accessors"])
        if "bufferView" not in accessor and "byteOffset" in accessor
    ]
    assert orphaned == []


def _glb_json(content: bytes) -> dict[str, Any]:
    """The GLB's JSON chunk as it was written.

    Read from the bytes rather than from a parsed document on purpose: a reader
    fills a defaulted field back in, so a document round-tripped through
    `pygltflib` cannot answer what the file actually declares — which is exactly
    why the bug above survived a suite that only ever read its own output back.
    """
    length = int.from_bytes(content[12:16], "little")
    return json.loads(content[20 : 20 + length])
