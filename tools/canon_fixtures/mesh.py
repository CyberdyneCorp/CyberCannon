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
_CORNERS: tuple[tuple[float, float, float], ...] = tuple(
    tuple(float(value) for value in vertex) for vertex in _SPHERE.vertices
)
_FACES: tuple[tuple[int, int, int], ...] = tuple(
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


def write_skinned_glb(path: Path, *, asset: str = "mech_scout") -> ExportFacts:
    """A skinned, animated GLB carrying a socket, a material and two clips."""
    object_name = f"SM_{asset}_LOD0"
    socket = "SOCKET_muzzle_l"
    bones = ("root", "spine_01")
    clips = (
        ClipExpectation(name=f"A_{asset}_walk", duration_s=4 / FRAME_RATE),
        ClipExpectation(name=f"A_{asset}_fire", duration_s=2 / FRAME_RATE, loop_closed=False),
    )

    blob = _Blob()
    positions, indices, texcoords = _geometry(blob)
    joints, weights = _skin_attributes(blob)
    gltf = GLTF2(
        scene=0,
        scenes=[Scene(nodes=[0, 1, 3])],
        nodes=[
            Node(name=object_name, mesh=0, skin=0),
            Node(name=bones[0], children=[2]),
            Node(name=bones[1]),
            Node(name=socket, translation=[0.4, 0.2, 0.0]),
        ],
        meshes=[
            Mesh(
                name=object_name,
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
        ],
        materials=[Material(name=f"M_{asset}")],
        skins=[Skin(joints=[1, 2], skeleton=1, inverseBindMatrices=_bind_matrices(blob))],
        animations=[_animation(blob, clip) for clip in clips],
    )
    _finish(gltf, blob, path)
    return ExportFacts(
        objects=(object_name,),
        empties=(socket,),
        materials=(f"M_{asset}",),
        bones=bones,
        triangles=len(_FACES),
        uv_sets=1,
        is_skinned=True,
        clips=clips,
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
        triangles=len(_FACES),
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
    mesh = trimesh.Trimesh(vertices=list(_CORNERS), faces=list(_FACES), process=False)
    surface = trimesh.visual.material.SimpleMaterial()
    surface.name = material
    mesh.visual = trimesh.visual.TextureVisuals(material=surface, uv=[(0.5, 0.5)] * len(_CORNERS))
    scene = trimesh.Scene()
    scene.add_geometry(mesh, geom_name=name, node_name=name)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(path))
    return ExportFacts(objects=(name,), materials=(material,), triangles=len(_FACES), uv_sets=1)


def write_unreadable_glb(path: Path) -> None:
    """A file that exists and is not the mesh its extension claims."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"glTF\x02\x00\x00\x00truncated")


def _geometry(blob: _Blob) -> tuple[int, int, int]:
    """Positions, indices and one UV set — the three every fixture shares."""
    flat = _flat(_CORNERS)
    positions = blob.accessor(
        _floats(flat),
        component_type=FLOAT,
        kind="VEC3",
        count=len(_CORNERS),
        target=ARRAY_BUFFER,
        minimum=[min(flat[axis::3]) for axis in range(3)],
        maximum=[max(flat[axis::3]) for axis in range(3)],
    )
    corner_indices = tuple(index for face in _FACES for index in face)
    indices = blob.accessor(
        struct.pack(f"<{len(corner_indices)}H", *corner_indices),
        component_type=UNSIGNED_SHORT,
        kind="SCALAR",
        count=len(corner_indices),
        target=ELEMENT_ARRAY_BUFFER,
    )
    texcoords = blob.accessor(
        _floats(tuple(value for _ in _CORNERS for value in (0.5, 0.5))),
        component_type=FLOAT,
        kind="VEC2",
        count=len(_CORNERS),
        target=ARRAY_BUFFER,
    )
    return positions, indices, texcoords


def _skin_attributes(blob: _Blob) -> tuple[int, int]:
    """Every vertex fully weighted to the first joint: skinning, kept legible."""
    joints = blob.accessor(
        bytes(bytearray(byte for _ in _CORNERS for byte in (0, 0, 0, 0))),
        component_type=UNSIGNED_BYTE,
        kind="VEC4",
        count=len(_CORNERS),
        target=ARRAY_BUFFER,
    )
    weights = blob.accessor(
        _floats(tuple(value for _ in _CORNERS for value in (1.0, 0.0, 0.0, 0.0))),
        component_type=FLOAT,
        kind="VEC4",
        count=len(_CORNERS),
        target=ARRAY_BUFFER,
    )
    return joints, weights


def _bind_matrices(blob: _Blob) -> int:
    return blob.accessor(
        _floats(_IDENTITY + _IDENTITY),
        component_type=FLOAT,
        kind="MAT4",
        count=2,
    )


def _animation(blob: _Blob, clip: ClipExpectation) -> Animation:
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
            AnimationChannel(sampler=0, target=AnimationChannelTarget(node=1, path="translation"))
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
    "FRAME_RATE",
    "ClipExpectation",
    "ExportFacts",
    "write_skinned_glb",
    "write_static_glb",
    "write_static_obj",
    "write_unreadable_glb",
]
