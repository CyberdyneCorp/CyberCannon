"""Task 5.6 — the FBX reader and fixture, cross-checked against a real DCC.

A reader verified only against its own writer is a reader that cannot be wrong,
and an FBX capability row derived from such a pair would be exactly the
over-confident matrix D13 exists to prevent: NOT EVALUATED turning into a silent
pass. So this suite closes the loop with the only independent FBX implementation
available, Blender's, in both directions:

* **Our file, their importer.** Blender imports `canon_fixtures.fbx`'s fixture
  and reports the object, the socket, the material, the polygon count, the bone
  names and every action with its frame range. If the fixture were a private
  dialect rather than FBX, this is where it would show.
* **Their file, our reader.** Blender builds and exports the same rig from a
  script, and `TrimeshInspector` reads it. The values compared are the ones the
  *script authored*, not what either side produced.

**Opt-in, and deliberately not auto-detected.** It runs only when `CANON_BLENDER`
names a Blender executable, so `just check` behaves identically on a machine with
Blender and one without. Auto-detecting it would make the suite pass or fail
depending on which applications a developer happens to have installed, which is
the "passed on my machine" failure the one-core rule exists to stop.

    CANON_BLENDER=/Applications/Blender.app/Contents/MacOS/Blender just test-integration

Last run: Blender 5.2.1 LTS, 2026-09-19, both directions green. What it found,
and what the matrix now records because of it: Blender writes
`UnitScaleFactor: 1.0` into a file whose vertices are in metres, and names every
take `<object>|<clip>`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from canon_fixtures import fbx as fixtures
from canon_fixtures.mesh import ExportFacts
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector

pytestmark = pytest.mark.integration

BLENDER = os.environ.get("CANON_BLENDER", "")

requires_blender = pytest.mark.skipif(
    not BLENDER or not Path(BLENDER).exists(),
    reason="set CANON_BLENDER to a Blender executable to run the DCC cross-check",
)

FRAME_RATE = 30.0
"""What the export script sets, and what a frame range is read back against."""

AUTHORED_CLIPS = {"A_quad_walk": 1.0, "A_quad_idle": 2.0, "A_quad_death": 0.5}
"""Clip name -> seconds, as `_EXPORT_SCRIPT` authors them. The source of truth here."""

AUTHORED_BONES = ("head", "leg_bl", "leg_br", "leg_fl", "leg_fr", "root", "spine_01", "tail")

_IMPORT_SCRIPT = """
import json, sys
import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=sys.argv[-1])
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
print("RESULT " + json.dumps({
    "objects": sorted(o.name for o in meshes),
    "polygons": sum(len(o.data.polygons) for o in meshes),
    "materials": sorted(m.name for m in bpy.data.materials),
    "empties": sorted(o.name for o in bpy.data.objects if o.type == "EMPTY"),
    "bones": sorted(
        b.name for o in bpy.data.objects if o.type == "ARMATURE" for b in o.data.bones
    ),
    "vertex_groups": sorted({g.name for o in meshes for g in o.vertex_groups}),
    "actions": {a.name: list(a.frame_range) for a in bpy.data.actions},
}))
"""

_EXPORT_SCRIPT = """
import sys
import bpy
from mathutils import Vector

BONES = [
    ("root", None, (0, 0, 0), (0, 0.3, 0)),
    ("spine_01", "root", (0, 0.3, 0), (0, 0.8, 0)),
    ("head", "spine_01", (0, 0.8, 0), (0, 1.2, 0)),
    ("leg_fl", "spine_01", (0.3, 0.7, 0.3), (0.3, 0.1, 0.3)),
    ("leg_fr", "spine_01", (-0.3, 0.7, 0.3), (-0.3, 0.1, 0.3)),
    ("leg_bl", "root", (0.3, 0.3, -0.3), (0.3, 0.1, -0.3)),
    ("leg_br", "root", (-0.3, 0.3, -0.3), (-0.3, 0.1, -0.3)),
    ("tail", "root", (0, 0.3, -0.4), (0, 0.4, -0.8)),
]
CLIPS = [("A_quad_walk", 31), ("A_quad_idle", 61), ("A_quad_death", 16)]

bpy.ops.wm.read_factory_settings(use_empty=True)
armature = bpy.data.objects.new("Armature", bpy.data.armatures.new("ARM_quad"))
bpy.context.collection.objects.link(armature)
bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode="EDIT")
for name, parent, head, tail in BONES:
    bone = armature.data.edit_bones.new(name)
    bone.head, bone.tail = Vector(head), Vector(tail)
    if parent:
        bone.parent = armature.data.edit_bones[parent]
bpy.ops.object.mode_set(mode="OBJECT")

bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.4, location=(0, 0.6, 0))
body = bpy.context.active_object
body.name = body.data.name = "SM_quad_scout_LOD0"
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.uv.smart_project()
bpy.ops.object.mode_set(mode="OBJECT")
body.data.materials.append(bpy.data.materials.new("M_quad_scout"))
body.select_set(True)
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
bpy.ops.object.parent_set(type="ARMATURE_AUTO")

socket = bpy.data.objects.new("SOCKET_muzzle_l", None)
socket.location = (0.2, 0.9, 0.1)
bpy.context.collection.objects.link(socket)

armature.animation_data_create()
for name, frames in CLIPS:
    action = bpy.data.actions.new(name)
    armature.animation_data.action = action
    slots = getattr(action, "slots", None)
    if slots is not None:
        armature.animation_data.action_slot = slots.new(id_type="OBJECT", name=name)
    bone = armature.pose.bones["root"]
    for frame in range(1, frames + 1):
        bone.location = (0.0, 0.0, 0.5 * (frame - 1) / max(frames - 1, 1))
        bone.keyframe_insert(data_path="location", frame=frame)
    action.use_fake_user = True

bpy.context.scene.render.fps = 30
bpy.ops.export_scene.fbx(
    filepath=sys.argv[-1],
    bake_anim=True,
    bake_anim_use_all_actions=True,
    bake_anim_use_nla_strips=False,
    add_leaf_bones=False,
)
"""


def _run_blender(script: str, tmp_path: Path, argument: Path) -> str:
    """Blender, headless, with a factory startup so no user preference leaks in."""
    module = tmp_path / "blender_script.py"
    module.write_text(script, encoding="utf-8")
    command = [BLENDER, "--background", "--factory-startup", "--python", str(module)]
    completed = subprocess.run(
        [*command, "--", str(argument)],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout[-4000:] + completed.stderr[-2000:]
    return completed.stdout


def _imported(tmp_path: Path, export: Path) -> dict:
    output = _run_blender(_IMPORT_SCRIPT, tmp_path, export)
    line = next((line for line in output.splitlines() if line.startswith("RESULT ")), None)
    assert line, output[-4000:]
    return json.loads(line.removeprefix("RESULT "))


def _seconds(frame_range: list[float]) -> float:
    """Blender reports a clip as a first and last frame; FBX records seconds."""
    return (frame_range[1] - frame_range[0]) / FRAME_RATE


# --------------------------------------------------------------------------
# Our file, their importer
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_export(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ExportFacts]:
    """The committed fixture, and the facts its writer declared for it."""
    path = tmp_path_factory.mktemp("fbx-fixture") / "SM_quad_scout_LOD0.fbx"
    return path, fixtures.write_skinned_fbx(path, asset="quad_scout")


@pytest.fixture(scope="module")
def blender_read(
    tmp_path_factory: pytest.TempPathFactory, fixture_export: tuple[Path, ExportFacts]
) -> dict:
    return _imported(tmp_path_factory.mktemp("fbx-import"), fixture_export[0])


@requires_blender
def test_blender_imports_the_fixture_as_the_geometry_it_authored(blender_read: dict) -> None:
    """If this writer emitted a private dialect, an industry importer would say so."""
    assert blender_read["objects"] == ["SM_quad_scout_LOD0"]
    assert blender_read["polygons"] == 1280
    assert blender_read["materials"] == ["M_quad_scout"]


@requires_blender
def test_blender_sees_the_socket_and_not_the_armature_holder(blender_read: dict) -> None:
    """The same distinction `fbx_facts._empties` makes, made independently."""
    assert blender_read["empties"] == ["SOCKET_muzzle_l"]


@requires_blender
def test_blender_sees_the_skeleton_and_the_skinning(blender_read: dict) -> None:
    assert tuple(blender_read["bones"]) == AUTHORED_BONES
    assert tuple(blender_read["vertex_groups"]) == AUTHORED_BONES


@requires_blender
def test_blender_sees_every_clip_at_the_authored_length(
    blender_read: dict, fixture_export: tuple[Path, ExportFacts]
) -> None:
    authored = {clip.name: clip.duration_s for clip in fixture_export[1].clips}
    observed = {
        name.rpartition("|")[2]: _seconds(frames)
        for name, frames in blender_read["actions"].items()
    }

    assert observed == pytest.approx(authored)


# --------------------------------------------------------------------------
# Their file, our reader
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def blender_export(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("fbx-export")
    path = directory / "blender_quad.fbx"
    _run_blender(_EXPORT_SCRIPT, directory, path)
    return path


@requires_blender
def test_the_reader_reads_a_blender_export_as_the_script_authored_it(
    blender_export: Path,
) -> None:
    facts = TrimeshInspector().inspect(str(blender_export)).facts

    assert facts.objects == ("SM_quad_scout_LOD0",)
    assert facts.materials == ("M_quad_scout",)
    assert facts.empties == ("SOCKET_muzzle_l",), "the armature holder is not a socket"
    assert facts.up_axis == "Y"
    assert facts.uv_sets == 1


@requires_blender
def test_the_reader_reads_a_blender_skeleton_as_the_script_authored_it(
    blender_export: Path,
) -> None:
    facts = TrimeshInspector().inspect(str(blender_export)).facts

    assert facts.is_skinned is True
    assert facts.bone_count == len(AUTHORED_BONES)


@requires_blender
def test_the_reader_reads_blender_clip_names_and_durations(blender_export: Path) -> None:
    """Blender names every take `<object>|<clip>`; the clip is what the spec declares."""
    facts = TrimeshInspector().inspect(str(blender_export)).facts

    observed = {clip.name: clip.duration_s for clip in facts.clips}

    assert observed == pytest.approx(AUTHORED_CLIPS)


@requires_blender
def test_a_blender_export_states_no_unit_scale_however_tempting(blender_export: Path) -> None:
    """The measurement behind the matrix row, kept executable rather than remembered.

    Blender writes `UnitScaleFactor: 1.0` into this file while its vertices are
    in metres — reading that factor as the FBX convention defines it would report
    a hundredth of the truth, and a unit scale is the one fact this product must
    never state wrongly.
    """
    from cybercanon.adapters.outbound.mesh.fbx_document import FbxDocument

    document = FbxDocument.read(blender_export)
    facts = TrimeshInspector().inspect(str(blender_export)).facts

    assert document.global_setting("UnitScaleFactor") == 1.0
    assert facts.unit_scale is None
    assert facts.transforms_applied is None
    assert facts.frame_rate is None


# --------------------------------------------------------------------------
# Their file, our preview
# --------------------------------------------------------------------------

_MEASURE_SCRIPT = """
import json, sys
import bpy

path = sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)
if path.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=path)
else:
    bpy.ops.import_scene.gltf(filepath=path)

# The glTF importer leaves a stray unparented mesh behind; the export under test
# is the one named as the script authored it.
meshes = [
    o for o in bpy.data.objects
    if o.type == "MESH" and o.name.split("|")[-1].startswith("SM_")
]
armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]


def box():
    evaluated = meshes[0].evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    points = [meshes[0].matrix_world @ vertex.co for vertex in mesh.vertices]
    evaluated.to_mesh_clear()
    return [
        [min(p[axis] for p in points) for axis in range(3)],
        [max(p[axis] for p in points) for axis in range(3)],
    ]


clips = {}
if armatures:
    rig = armatures[0]
    if rig.animation_data is None:
        rig.animation_data_create()
    for action in bpy.data.actions:
        rig.animation_data.action = action
        slots = getattr(action, "slots", None)
        if slots is not None and len(slots):
            rig.animation_data.action_slot = slots[0]
        first, last = action.frame_range
        sampled = []
        for frame in (first, last):
            bpy.context.scene.frame_set(int(round(frame)))
            bpy.context.view_layer.update()
            sampled.append(box())
        clips[action.name.split("|")[-1]] = sampled

print("RESULT " + json.dumps({
    "objects": sorted(o.name.split("|")[-1] for o in meshes),
    "empties": sorted(o.name.split("|")[-1] for o in bpy.data.objects if o.type == "EMPTY"),
    "bones": sorted(b.name for o in armatures for b in o.data.bones),
    "clips": clips,
}))
"""


def _measured(tmp_path: Path, export: Path) -> dict:
    output = _run_blender(_MEASURE_SCRIPT, tmp_path, export)
    line = next((line for line in output.splitlines() if line.startswith("RESULT ")), None)
    assert line, output[-4000:]
    return json.loads(line.removeprefix("RESULT "))


def _shape(box: list[list[float]]) -> tuple[float, ...]:
    """A box as proportions of its own longest side — the same shape at any scale.

    The preview keeps the export's own coordinates and this converter states no
    unit scale, deliberately (`fbx_gltf`), so the two files are compared on
    shape and on motion-relative-to-size rather than on absolute millimetres.
    """
    extents = [box[1][axis] - box[0][axis] for axis in range(3)]
    longest = max(extents) or 1.0
    return tuple(round(extent / longest, 3) for extent in extents)


def _travel(sampled: list[list[list[float]]]) -> tuple[float, ...]:
    """How far the mesh moved over the clip, as a fraction of its own size."""
    first, last = sampled
    size = max(first[1][axis] - first[0][axis] for axis in range(3)) or 1.0
    return tuple(round((last[0][axis] - first[0][axis]) / size, 3) for axis in range(3))


@pytest.fixture(scope="module")
def blender_preview(tmp_path_factory: pytest.TempPathFactory, blender_export: Path) -> Path:
    """Blender's own export, converted by `fbx_gltf` and written out as a GLB.

    The *converted* document rather than the decimated preview, because what is
    compared below is the conversion — decimation is asserted against its own
    source in `test_preview_emission.py`, and a decimated mesh has a slightly
    smaller bounding box by construction.
    """
    from cybercanon.adapters.outbound.mesh import fbx_gltf
    from cybercanon.adapters.outbound.mesh.fbx_document import FbxDocument

    converted = fbx_gltf.convert(FbxDocument.read(blender_export))
    path = tmp_path_factory.mktemp("fbx-preview") / "converted.glb"
    path.write_bytes(b"".join(converted.gltf.save_to_bytes()))
    return path


@requires_blender
def test_blender_reads_our_conversion_as_the_parts_the_script_authored(
    tmp_path_factory: pytest.TempPathFactory, blender_preview: Path
) -> None:
    """An anchor's durable key is a part name, so the names are the first question."""
    read = _measured(tmp_path_factory.mktemp("preview-read"), blender_preview)

    assert read["objects"] == ["SM_quad_scout_LOD0"]
    assert read["empties"] == ["SOCKET_muzzle_l"]
    assert tuple(read["bones"]) == AUTHORED_BONES


@requires_blender
def test_our_conversion_deforms_the_way_the_source_fbx_does(
    tmp_path_factory: pytest.TempPathFactory, blender_export: Path, blender_preview: Path
) -> None:
    """The assertion a part list cannot make: the geometry ends up in one place.

    A bind matrix composed in the wrong order, a rotation read in the wrong
    Euler order or a curve sampled in the wrong units all leave every name
    intact and move the mesh somewhere else — which is visible to a person
    looking at the viewer and to nothing else. So Blender evaluates both files
    with their skeletons and their clips, and the two are compared on shape and
    on how far each clip travels relative to that shape.
    """
    directory = tmp_path_factory.mktemp("deformation")
    source = _measured(directory, blender_export)
    preview = _measured(directory, blender_preview)

    assert source["clips"] and set(source["clips"]) == set(preview["clips"])
    for name, sampled in source["clips"].items():
        assert _shape(preview["clips"][name][0]) == pytest.approx(_shape(sampled[0]), abs=0.02)
        assert _travel(preview["clips"][name]) == pytest.approx(_travel(sampled), abs=0.02)
