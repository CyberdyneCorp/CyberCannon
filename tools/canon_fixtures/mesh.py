"""Exports written from code: what a real file looks like, in readable form.

Every fixture here states its own facts, so a test can assert that the adapter
read *these* names, *these* clip durations and *this* bone count rather than
whatever a binary in git happened to contain. :class:`ExportFacts` travels with
the file for exactly that reason.

The skinned GLB is assembled by hand rather than exported by a library because
no library in this project writes skins or animation clips — which is also why
`TrimeshInspector` reads glTF through `pygltflib` rather than through `trimesh`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import trimesh
from pygltflib import (
    ARRAY_BUFFER,
    ELEMENT_ARRAY_BUFFER,
    FLOAT,
    GLTF2,
    UNSIGNED_BYTE,
    UNSIGNED_SHORT,
    Accessor,
    Animation,
    AnimationChannel,
    AnimationChannelTarget,
    AnimationSampler,
    Attributes,
    Buffer,
    BufferFormat,
    BufferView,
    Material,
    Mesh,
    Node,
    Primitive,
    Scene,
    Skin,
)

FRAME_RATE = 30.0
"""The rate the sample times are laid out at, so a reader can derive it back."""

SHOULDER = "SM_MechScout_Shoulder_L"
"""The part `asset-preview` anchors to by name, spelled as the spec spells it."""

RIG_BONES = 74
"""The skeleton size `asset-preview` names. A joint index still fits in a byte."""


@dataclass(frozen=True)
class ClipExpectation:
    """One clip as authored, so a test compares against the source, not itself."""

    name: str
    duration_s: float
    frame_rate: float = FRAME_RATE
    loop_closed: bool = True
    has_root_motion: bool = True


@dataclass(frozen=True)
class ExportFacts:
    """What the file on disk contains, as its author declared it."""

    objects: tuple[str, ...] = ()
    empties: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    bones: tuple[str, ...] = ()
    triangles: int = 0
    uv_sets: int = 0
    is_skinned: bool = False
    clips: tuple[ClipExpectation, ...] = field(default_factory=tuple)

    @property
    def clip_names(self) -> tuple[str, ...]:
        return tuple(clip.name for clip in self.clips)

    @property
    def bone_count(self) -> int:
        return len(self.bones)


# The geometry every fixture shares: a subdivided icosphere, big enough that
# decimating it produces a measurably smaller file and small enough to build in
# milliseconds. Generated rather than typed out, so the fixture is a shape and
# not a wall of coordinates.
_SPHERE = trimesh.creation.icosphere(subdivisions=3)
CORNERS: tuple[tuple[float, float, float], ...] = tuple(
    tuple(float(value) for value in vertex) for vertex in _SPHERE.vertices
)
FACES: tuple[tuple[int, int, int], ...] = tuple(
    tuple(int(index) for index in face) for face in _SPHERE.faces
)

_IDENTITY = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)  # fmt: skip


class _Blob:
    """A glTF binary chunk under construction, and the views into it."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.views: list[BufferView] = []
        self.accessors: list[Accessor] = []

    def accessor(
        self,
        payload: bytes,
        *,
        component_type: int,
        kind: str,
        count: int,
        target: int | None = None,
        minimum: list[float] | None = None,
        maximum: list[float] | None = None,
    ) -> int:
        """Append the bytes, wrap them in a view, and return the accessor index."""
        self._pad()
        offset = len(self.data)
        self.data.extend(payload)
        self.views.append(
            BufferView(buffer=0, byteOffset=offset, byteLength=len(payload), target=target)
        )
        self.accessors.append(
            Accessor(
                bufferView=len(self.views) - 1,
                componentType=component_type,
                count=count,
                type=kind,
                min=minimum,
                max=maximum,
            )
        )
        return len(self.accessors) - 1

    def _pad(self) -> None:
        while len(self.data) % 4:
            self.data.append(0)


def _floats(values: tuple[float, ...]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _flat(vectors: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    return tuple(float(value) for vector in vectors for value in vector)


def write_skinned_glb(
    path: Path, *, asset: str = "mech_scout", clips: tuple[ClipExpectation, ...] | None = None
) -> ExportFacts:
    """A skinned, animated GLB carrying a socket, a material and two clips.

    `clips` overrides the two default ones, which is what lets the same asset be
    written to glTF and to FBX carrying the *same* clips — the only way a
    cross-format coverage comparison compares one contract instead of two.
    """
    gltf, blob, facts = _skinned_document(asset, clips=clips)
    _finish(gltf, blob, path)
    return facts


def write_rigged_glb(path: Path, *, asset: str = "mech_scout") -> ExportFacts:
    """The export the `asset-preview` scenarios name: many parts, many bones.

    Two mesh parts with separate geometry rather than one, because a preview that
    keeps a part and quietly loses its neighbour is exactly the failure a named
    anchor suffers from; and a 74-bone skeleton with every bone actually weighted,
    because a preview that dropped most of a rig would still read as "skinned".
    """
    gltf, blob, facts = _skinned_document(
        asset, parts=(f"SM_{asset}_LOD0", SHOULDER), bones=RIG_BONES
    )
    _finish(gltf, blob, path)
    return facts


def write_skinned_gltf(
    path: Path, *, asset: str = "mech_scout", clips: tuple[ClipExpectation, ...] | None = None
) -> ExportFacts:
    """The same export as `.gltf` — JSON, with its buffer in a data URI.

    GLB and glTF are one row in the matrix, and the adapter reads them through
    one code path, so the fixture that proves it has to be the *same* export in
    both containers. The buffer arrives as a URI rather than a binary chunk,
    which is the branch `GltfDocument` resolves and a `.glb` never exercises.
    """
    gltf, blob, facts = _skinned_document(asset, clips=clips)
    gltf.bufferViews = blob.views
    gltf.accessors = blob.accessors
    gltf.buffers = [Buffer(byteLength=len(blob.data))]
    gltf.set_binary_blob(bytes(blob.data))
    gltf.convert_buffers(BufferFormat.DATAURI)
    path.parent.mkdir(parents=True, exist_ok=True)
    gltf.save_json(str(path))
    return facts


def _skinned_document(
    asset: str,
    *,
    parts: tuple[str, ...] = (),
    bones: int = 2,
    clips: tuple[ClipExpectation, ...] | None = None,
) -> tuple[GLTF2, _Blob, ExportFacts]:
    """The skinned export as a document, before it is committed to a container.

    Node order is fixed and depended on below: the mesh parts, then the bones
    (the first is the skeleton root), then the socket.
    """
    object_names = parts or (f"SM_{asset}_LOD0",)
    socket = "SOCKET_muzzle_l"
    bone_names = _bone_names(bones)
    root = len(object_names)
    clips = clips or (
        ClipExpectation(name=f"A_{asset}_walk", duration_s=4 / FRAME_RATE),
        ClipExpectation(name=f"A_{asset}_fire", duration_s=2 / FRAME_RATE, loop_closed=False),
    )

    blob = _Blob()
    meshes = [_skinned_part(blob, name, bones) for name in object_names]
    gltf = GLTF2(
        scene=0,
        scenes=[Scene(nodes=[*range(len(object_names)), root, root + bones])],
        nodes=[
            *(Node(name=name, mesh=index, skin=0) for index, name in enumerate(object_names)),
            Node(name=bone_names[0], children=list(range(root + 1, root + bones))),
            *(Node(name=name) for name in bone_names[1:]),
            Node(name=socket, translation=[0.4, 0.2, 0.0]),
        ],
        meshes=meshes,
        materials=[Material(name=f"M_{asset}")],
        skins=[
            Skin(
                joints=list(range(root, root + bones)),
                skeleton=root,
                inverseBindMatrices=_bind_matrices(blob, bones),
            )
        ],
        animations=[_animation(blob, clip, root) for clip in clips],
    )
    facts = ExportFacts(
        objects=object_names,
        empties=(socket,),
        materials=(f"M_{asset}",),
        bones=bone_names,
        triangles=len(FACES) * len(object_names),
        uv_sets=1,
        is_skinned=True,
        clips=clips,
    )
    return gltf, blob, facts


def _bone_names(bones: int) -> tuple[str, ...]:
    """`root`, `spine_01`, and however many numbered bones the rig still needs."""
    named = ("root", "spine_01")[:bones]
    return named + tuple(f"bone_{index:02d}" for index in range(len(named), bones))


def _skinned_part(blob: _Blob, name: str, bones: int) -> Mesh:
    """One mesh part with geometry of its own — parts never share an accessor."""
    positions, indices, texcoords = _geometry(blob)
    joints, weights = _skin_attributes(blob, bones)
    return Mesh(
        name=name,
        primitives=[
            Primitive(
                attributes=Attributes(
                    POSITION=positions,
                    TEXCOORD_0=texcoords,
                    JOINTS_0=joints,
                    WEIGHTS_0=weights,
                ),
                indices=indices,
                material=0,
            )
        ],
    )


def write_static_glb(path: Path, *, name: str = "SM_crate_LOD0") -> ExportFacts:
    """A static GLB: geometry, a material, no skin and no clips."""
    blob = _Blob()
    positions, indices, texcoords = _geometry(blob)
    gltf = GLTF2(
        scene=0,
        scenes=[Scene(nodes=[0])],
        nodes=[Node(name=name, mesh=0)],
        meshes=[
            Mesh(
                name=name,
                primitives=[
                    Primitive(
                        attributes=Attributes(POSITION=positions, TEXCOORD_0=texcoords),
                        indices=indices,
                        material=0,
                    )
                ],
            )
        ],
        materials=[Material(name="M_Crate")],
    )
    _finish(gltf, blob, path)
    return ExportFacts(
        objects=(name,),
        materials=("M_Crate",),
        triangles=len(FACES),
        uv_sets=1,
    )


def write_static_obj(
    path: Path, *, name: str = "SM_crate_LOD0", material: str = "M_Crate"
) -> ExportFacts:
    """A static OBJ — the format that records triangles, names, materials, UVs.

    Written with a companion `.mtl` and a UV set, so the four facts OBJ's matrix
    row allows are all actually present in the file and a reader that skipped one
    would be caught rather than merely unexercised.
    """
    mesh = trimesh.Trimesh(vertices=list(CORNERS), faces=list(FACES), process=False)
    surface = trimesh.visual.material.SimpleMaterial()
    surface.name = material
    mesh.visual = trimesh.visual.TextureVisuals(material=surface, uv=[(0.5, 0.5)] * len(CORNERS))
    scene = trimesh.Scene()
    scene.add_geometry(mesh, geom_name=name, node_name=name)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(path))
    return ExportFacts(objects=(name,), materials=(material,), triangles=len(FACES), uv_sets=1)


def write_multipart_obj(
    path: Path, *, parts: tuple[str, ...] = ("SM_mech_scout_LOD0", SHOULDER)
) -> ExportFacts:
    """An OBJ with more than one named object — what an artist exports for real.

    Each part gets geometry of its own, because a part an annotation anchors to
    has to be distinguishable from its neighbour: a reader that merged the two
    would still report the right triangle total and the wrong part list, and a
    pin anchored to the second name would have nowhere to land.
    """
    scene = trimesh.Scene()
    for index, name in enumerate(parts):
        mesh = trimesh.creation.icosphere(subdivisions=2 + index)
        surface = trimesh.visual.material.SimpleMaterial()
        surface.name = f"M_{name}"
        mesh.visual = trimesh.visual.TextureVisuals(
            material=surface, uv=[(0.5, 0.5)] * len(mesh.vertices)
        )
        scene.add_geometry(mesh, geom_name=name, node_name=name)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(path))
    return ExportFacts(
        objects=parts,
        materials=tuple(f"M_{name}" for name in parts),
        triangles=sum(len(mesh.faces) for mesh in scene.geometry.values()),
        uv_sets=1,
    )


def write_unreadable_glb(path: Path) -> None:
    """A file that exists and is not the mesh its extension claims."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"glTF\x02\x00\x00\x00truncated")


def _geometry(blob: _Blob) -> tuple[int, int, int]:
    """Positions, indices and one UV set — the three every fixture shares."""
    flat = _flat(CORNERS)
    positions = blob.accessor(
        _floats(flat),
        component_type=FLOAT,
        kind="VEC3",
        count=len(CORNERS),
        target=ARRAY_BUFFER,
        minimum=[min(flat[axis::3]) for axis in range(3)],
        maximum=[max(flat[axis::3]) for axis in range(3)],
    )
    corner_indices = tuple(index for face in FACES for index in face)
    indices = blob.accessor(
        struct.pack(f"<{len(corner_indices)}H", *corner_indices),
        component_type=UNSIGNED_SHORT,
        kind="SCALAR",
        count=len(corner_indices),
        target=ELEMENT_ARRAY_BUFFER,
    )
    texcoords = blob.accessor(
        _floats(tuple(value for _ in CORNERS for value in (0.5, 0.5))),
        component_type=FLOAT,
        kind="VEC2",
        count=len(CORNERS),
        target=ARRAY_BUFFER,
    )
    return positions, indices, texcoords


def _skin_attributes(blob: _Blob, bones: int = 1) -> tuple[int, int]:
    """Every vertex fully weighted to one joint, spread over the whole skeleton.

    Spread rather than all-to-the-root so that every bone a rig declares is a
    bone the mesh actually uses, and a preview that dropped one would show it.
    """
    bound = tuple(index % bones for index in range(len(CORNERS)))
    joints = blob.accessor(
        bytes(bytearray(byte for joint in bound for byte in (joint, 0, 0, 0))),
        component_type=UNSIGNED_BYTE,
        kind="VEC4",
        count=len(CORNERS),
        target=ARRAY_BUFFER,
    )
    weights = blob.accessor(
        _floats(tuple(value for _ in CORNERS for value in (1.0, 0.0, 0.0, 0.0))),
        component_type=FLOAT,
        kind="VEC4",
        count=len(CORNERS),
        target=ARRAY_BUFFER,
    )
    return joints, weights


def _bind_matrices(blob: _Blob, bones: int = 2) -> int:
    return blob.accessor(
        _floats(_IDENTITY * bones),
        component_type=FLOAT,
        kind="MAT4",
        count=bones,
    )


def _animation(blob: _Blob, clip: ClipExpectation, root: int = 1) -> Animation:
    """One clip translating the skeleton root — root motion, and a closable loop."""
    samples = round(clip.duration_s * clip.frame_rate) + 1
    times = tuple(index / clip.frame_rate for index in range(samples))
    offsets = _translations(samples, closed=clip.loop_closed)
    input_accessor = blob.accessor(
        _floats(times),
        component_type=FLOAT,
        kind="SCALAR",
        count=samples,
        minimum=[times[0]],
        maximum=[times[-1]],
    )
    output_accessor = blob.accessor(
        _floats(offsets),
        component_type=FLOAT,
        kind="VEC3",
        count=samples,
    )
    return Animation(
        name=clip.name,
        samplers=[AnimationSampler(input=input_accessor, output=output_accessor)],
        channels=[
            AnimationChannel(
                sampler=0, target=AnimationChannelTarget(node=root, path="translation")
            )
        ],
    )


def _translations(samples: int, *, closed: bool) -> tuple[float, ...]:
    """A there-and-back translation; an unclosed clip ends somewhere else."""
    values: list[float] = []
    for index in range(samples):
        forward = index / max(samples - 1, 1)
        position = forward if index < samples - 1 or not closed else 0.0
        values.extend((position, 0.0, 0.0))
    return tuple(values)


def _finish(gltf: GLTF2, blob: _Blob, path: Path) -> None:
    gltf.bufferViews = blob.views
    gltf.accessors = blob.accessors
    gltf.buffers = [Buffer(byteLength=len(blob.data))]
    gltf.set_binary_blob(bytes(blob.data))
    path.parent.mkdir(parents=True, exist_ok=True)
    gltf.save_binary(str(path))


__all__ = [
    "CORNERS",
    "FACES",
    "FRAME_RATE",
    "RIG_BONES",
    "SHOULDER",
    "ClipExpectation",
    "ExportFacts",
    "write_multipart_obj",
    "write_rigged_glb",
    "write_skinned_glb",
    "write_skinned_gltf",
    "write_static_glb",
    "write_static_obj",
    "write_unreadable_glb",
]
