"""Binary FBX fixtures, written from code — a skinned, animated quadruped rig.

No library in this project writes FBX, and a checked-in binary is a fixture
nobody can review or regenerate. So this module writes the container itself: a
tree of records, each a name, a property list and a nested list, exactly as
`fbx_document` reads it.

**The shape it writes is the shape a DCC writes.** It was derived from a Blender
5.2 export of the same rig, record by record, and the two are cross-checked:
`tests/integration/test_fbx_against_blender.py` — opt-in, skipped when Blender
is absent — imports this file into Blender and exports Blender's own, then reads
both with the same reader. That is what keeps the FBX capability row a
measurement rather than a reader agreeing with its own fixture.

The rig is deliberately not art: eight bones (`root`, a spine, a head, four legs
and a tail), one skinned body, one socket, one material and three named clips of
different lengths.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from canon_fixtures.mesh import CORNERS, FACES, ClipExpectation, ExportFacts

FBX_VERSION = 7400
"""The version Blender 5.2 writes, and the one this writer's record layout matches."""

KTIME_PER_SECOND = 46186158000
"""FBX time unit: one second, exactly, as an integer."""

FRAME_RATE = 30.0
"""What the clips are laid out at. Recorded in the file, never read back — see below."""

BONES: tuple[tuple[str, str | None], ...] = (
    ("root", None),
    ("spine_01", "root"),
    ("head", "spine_01"),
    ("leg_fl", "spine_01"),
    ("leg_fr", "spine_01"),
    ("leg_bl", "root"),
    ("leg_br", "root"),
    ("tail", "root"),
)
"""A quadruped-ish skeleton: enough structure to count, parent and skin."""

ARMATURE = "Armature"
"""The holder every exporter writes as a `Null`; it is not an attachment point."""

_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
"""21 bytes of name, then the 0x1A 0x00 that marks the binary form."""
_FOOTER_MAGIC = b"\xf8\x5a\x8c\x6a\xde\xf5\xd9\x7e\xec\xe9\x0c\xe3\x75\x8f\x29\x0b"
_NULL_RECORD = bytes(13)
_IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


# --------------------------------------------------------------------------
# The container
# --------------------------------------------------------------------------


@dataclass
class Node:
    """One record under construction."""

    name: str
    properties: tuple[object, ...] = ()
    children: list[Node] = field(default_factory=list)

    def add(self, name: str, *properties: object) -> Node:
        child = Node(name, properties)
        self.children.append(child)
        return child


class Str(str):
    """A property that is written as an FBX string rather than inferred."""


class Int64(int):
    """A property that is written as a 64-bit integer — object ids and `KTime`."""


class Doubles(tuple):  # type: ignore[type-arg]
    """A `d` array property."""


class Ints(tuple):  # type: ignore[type-arg]
    """An `i` array property."""


class Longs(tuple):  # type: ignore[type-arg]
    """An `l` array property."""


class Floats(tuple):  # type: ignore[type-arg]
    """An `f` array property."""


def _encode_property(value: object) -> bytes:
    if isinstance(value, Str):
        payload = value.encode("utf-8")
        return b"S" + struct.pack("<I", len(payload)) + payload
    if isinstance(value, Int64):
        return b"L" + struct.pack("<q", int(value))
    if isinstance(value, bool):
        return b"C" + struct.pack("<?", value)
    if isinstance(value, int):
        return b"I" + struct.pack("<i", value)
    if isinstance(value, float):
        return b"D" + struct.pack("<d", value)
    return _encode_array(value)


_ARRAY_CODES: tuple[tuple[type, str, str], ...] = (
    (Doubles, "d", "d"),
    (Floats, "f", "f"),
    (Ints, "i", "i"),
    (Longs, "l", "q"),
)


def _encode_array(value: object) -> bytes:
    for kind, code, layout in _ARRAY_CODES:
        if isinstance(value, kind):
            items = tuple(value)  # type: ignore[call-overload]
            payload = struct.pack(f"<{len(items)}{layout}", *items)
            head = code.encode() + struct.pack("<III", len(items), 0, len(payload))
            return head + payload
    raise TypeError(f"no FBX property encoding for {type(value).__name__}")


def _encode_node(node: Node, offset: int) -> bytes:
    """One record at a known file offset — the offset is part of the record."""
    name = node.name.encode("utf-8")
    properties = b"".join(_encode_property(value) for value in node.properties)
    position = offset + 13 + len(name) + len(properties)
    body = b""
    if node.children:
        for child in node.children:
            encoded = _encode_node(child, position)
            body += encoded
            position += len(encoded)
        body += _NULL_RECORD
        position += len(_NULL_RECORD)
    header = struct.pack("<III", position, len(node.properties), len(properties))
    return header + bytes([len(name)]) + name + properties + body


def _encode_document(roots: list[Node]) -> bytes:
    content = _MAGIC + struct.pack("<I", FBX_VERSION)
    for node in roots:
        content += _encode_node(node, len(content))
    return content + _NULL_RECORD + _footer()


def _footer() -> bytes:
    """A plausible footer. Readers stop at the null record; a real file has one."""
    return bytes(16) + bytes(4) + struct.pack("<I", FBX_VERSION) + bytes(120) + _FOOTER_MAGIC


def _named(name: str, klass: str) -> Str:
    """An object's name as a binary FBX stores it: ``name\\x00\\x01Class``."""
    return Str(f"{name}\x00\x01{klass}")


# --------------------------------------------------------------------------
# The fixtures
# --------------------------------------------------------------------------


def write_skinned_fbx(
    path: Path, *, asset: str = "quad_scout", clips: tuple[ClipExpectation, ...] | None = None
) -> ExportFacts:
    """A skinned, animated FBX carrying a socket, a material and three clips.

    `clips` overrides the three default ones, so the same asset can be written to
    FBX and to glTF carrying the same clip names and durations — what a
    cross-format coverage comparison needs in order to compare one contract.
    """
    clips = clips or (
        ClipExpectation(name=f"A_{asset}_walk", duration_s=1.0, loop_closed=False),
        ClipExpectation(name=f"A_{asset}_idle", duration_s=2.0, loop_closed=False),
        ClipExpectation(name=f"A_{asset}_death", duration_s=0.5, loop_closed=False),
    )
    return _write(path, asset=asset, clips=clips, skinned=True)


def write_static_fbx(path: Path, *, asset: str = "crate") -> ExportFacts:
    """A static FBX: geometry, a material, one socket, no skeleton and no clips."""
    return _write(path, asset=asset, clips=(), skinned=False)


def write_ascii_fbx(path: Path) -> None:
    """The grammar this reader does not read, so the refusal is exercised."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('; FBX 7.4.0 project file\nObjects:  {\n\tGeometry: "Geometry::x" {\n\t}\n}\n')


def write_unterminated_fbx(path: Path) -> None:
    """A geometry whose polygon list never negates a polygon's last index.

    Malformed rather than exotic: the negation is how FBX marks where a polygon
    ends, so without it every index would read as its own triangle.
    """
    geometry = Node("Geometry", (Int64(1007), _named("SM_broken_LOD0", "Geometry"), Str("Mesh")))
    geometry.add("PolygonVertexIndex", Ints((0, 1, 2)))
    settings = Node("GlobalSettings")
    settings.add("Properties70").children.append(_integer_property("UpAxis", 1))
    document = [settings, Node("Objects", (), [geometry]), Node("Connections")]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encode_document(document))


def write_axisless_fbx(path: Path) -> ExportFacts:
    """A well-formed FBX whose `GlobalSettings` records no up axis."""
    return _write(path, asset="axisless", clips=(), skinned=False, up_axis=None)


def _write(
    path: Path,
    *,
    asset: str,
    clips: tuple[ClipExpectation, ...],
    skinned: bool,
    up_axis: int | None = 1,
) -> ExportFacts:
    builder = _Builder(asset=asset, clips=clips, skinned=skinned, up_axis=up_axis)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encode_document(builder.document()))
    return builder.facts()


class _Builder:
    """Assembles one FBX document, handing out object ids as it goes."""

    def __init__(
        self,
        *,
        asset: str,
        clips: tuple[ClipExpectation, ...],
        skinned: bool,
        up_axis: int | None,
    ) -> None:
        self.asset = asset
        self.clips = clips
        self.skinned = skinned
        self.up_axis = up_axis
        self.object_name = f"SM_{asset}_LOD0"
        self.material = f"M_{asset}"
        self.socket = "SOCKET_muzzle_l"
        self._next_id = 1000
        self._root_bone = Int64(0)
        self._objects = Node("Objects")
        self._connections = Node("Connections")

    # -- assembly --------------------------------------------------------

    def document(self) -> list[Node]:
        mesh_model, geometry = self._mesh()
        self._material_object(mesh_model)
        self._null(self.socket)
        if self.skinned:
            self._skeleton(geometry)
        for clip in self.clips:
            self._clip(clip)
        return [self._header(), self._settings(), self._objects, self._connections]

    def facts(self) -> ExportFacts:
        return ExportFacts(
            objects=(self.object_name,),
            empties=(self.socket,),
            materials=(self.material,),
            bones=tuple(name for name, _ in BONES) if self.skinned else (),
            triangles=len(FACES),
            uv_sets=1,
            is_skinned=self.skinned,
            clips=self.clips,
        )

    # -- pieces ----------------------------------------------------------

    def _identifier(self) -> Int64:
        self._next_id += 7
        return Int64(self._next_id)

    def _connect(self, child: Int64, parent: Int64 | int, relation: str | None = None) -> None:
        properties: tuple[object, ...] = (Str("OO"), child, Int64(parent))
        if relation is not None:
            properties = (Str("OP"), child, Int64(parent), Str(relation))
        self._connections.children.append(Node("C", properties))

    def _header(self) -> Node:
        header = Node("FBXHeaderExtension")
        header.add("FBXHeaderVersion", 1003)
        header.add("FBXVersion", FBX_VERSION)
        header.add("Creator", Str("CyberCanon fixture writer"))
        return header

    def _settings(self) -> Node:
        settings = Node("GlobalSettings")
        settings.add("Version", 1000)
        properties = settings.add("Properties70")
        for name, value in self._axis_properties():
            properties.children.append(_integer_property(name, value))
        properties.children.append(_double_property("UnitScaleFactor", 1.0))
        properties.children.append(_enum_property("TimeMode", 6))
        properties.children.append(_double_property("CustomFrameRate", FRAME_RATE))
        return settings

    def _axis_properties(self) -> tuple[tuple[str, int], ...]:
        if self.up_axis is None:
            return ()
        return (
            ("UpAxis", self.up_axis),
            ("UpAxisSign", 1),
            ("FrontAxis", 2),
            ("FrontAxisSign", 1),
            ("CoordAxis", 0),
            ("CoordAxisSign", 1),
        )

    def _mesh(self) -> tuple[Int64, Int64]:
        geometry_id = self._identifier()
        name = _named(self.object_name, "Geometry")
        geometry = Node("Geometry", (geometry_id, name, Str("Mesh")))
        geometry.add("GeometryVersion", 124)
        geometry.add("Vertices", Doubles(value for corner in CORNERS for value in corner))
        geometry.add("PolygonVertexIndex", Ints(_polygon_indices()))
        geometry.children.append(_uv_layer())
        self._objects.children.append(geometry)

        model_id = self._identifier()
        self._objects.children.append(_model(model_id, self.object_name, "Mesh"))
        self._connect(geometry_id, model_id)
        self._connect(model_id, 0)
        return model_id, geometry_id

    def _material_object(self, mesh_model: Int64) -> None:
        material_id = self._identifier()
        material = Node("Material", (material_id, _named(self.material, "Material"), Str("")))
        material.add("Version", 102)
        material.add("ShadingModel", Str("phong"))
        self._objects.children.append(material)
        self._connect(material_id, mesh_model)

    def _null(self, name: str, parent: Int64 | int = 0) -> Int64:
        null_id = self._identifier()
        self._objects.children.append(_model(null_id, name, "Null"))
        self._connect(null_id, parent)
        return null_id

    def _skeleton(self, geometry: Int64) -> None:
        holder = self._null(ARMATURE)
        bones: dict[str, Int64] = {}
        for name, parent in BONES:
            bone_id = self._identifier()
            self._objects.children.append(_model(bone_id, name, "LimbNode"))
            self._connect(bone_id, bones[parent] if parent else holder)
            bones[name] = bone_id
        self._skin(geometry, bones)
        self._root_bone = bones["root"]

    def _skin(self, geometry: Int64, bones: dict[str, Int64]) -> None:
        """A skin deforms the *geometry*, not the model that draws it."""
        skin_id = self._identifier()
        skin = Node("Deformer", (skin_id, _named(ARMATURE, "Deformer"), Str("Skin")))
        skin.add("Version", 101)
        self._objects.children.append(skin)
        self._connect(skin_id, geometry)
        for name, bone_id in bones.items():
            cluster_id = self._identifier()
            self._objects.children.append(_cluster(cluster_id, name))
            self._connect(cluster_id, skin_id)
            self._connect(bone_id, cluster_id)

    def _clip(self, clip: ClipExpectation) -> None:
        stack_id = self._identifier()
        stack = Node("AnimationStack", (stack_id, _named(clip.name, "AnimStack"), Str("")))
        properties = stack.add("Properties70")
        properties.children.append(_time_property("LocalStart", 0))
        properties.children.append(_time_property("LocalStop", _ktime(clip.duration_s)))
        self._objects.children.append(stack)

        layer_id = self._identifier()
        layer = Node("AnimationLayer", (layer_id, _named(clip.name, "AnimLayer"), Str("")))
        self._objects.children.append(layer)
        self._connect(layer_id, stack_id)
        if self.skinned:
            self._curve(clip, layer_id)

    def _curve(self, clip: ClipExpectation, layer_id: Int64) -> None:
        """A translation curve on the root bone, so the clip animates something."""
        node_id = self._identifier()
        curve_node = Node("AnimationCurveNode", (node_id, _named("T", "AnimCurveNode"), Str("")))
        properties = curve_node.add("Properties70")
        for axis in ("d|X", "d|Y", "d|Z"):
            properties.children.append(_number_property(axis, 0.0))
        self._objects.children.append(curve_node)
        self._connect(node_id, layer_id)
        self._connect(node_id, self._root_bone, "Lcl Translation")

        curve_id = self._identifier()
        curve = Node("AnimationCurve", (curve_id, _named("", "AnimCurve"), Str("")))
        times, values = _samples(clip)
        curve.add("Default", 0.0)
        curve.add("KeyTime", Longs(times))
        curve.add("KeyValueFloat", Floats(values))
        self._objects.children.append(curve)
        self._connect(curve_id, node_id, "d|X")


# --------------------------------------------------------------------------
# Record helpers
# --------------------------------------------------------------------------


def _property(name: str, kind: str, label: str, value: object) -> Node:
    return Node("P", (Str(name), Str(kind), Str(label), Str(""), value))


def _integer_property(name: str, value: int) -> Node:
    return _property(name, "int", "Integer", value)


def _double_property(name: str, value: float) -> Node:
    return _property(name, "double", "Number", value)


def _number_property(name: str, value: float) -> Node:
    return _property(name, "Number", "", value)


def _enum_property(name: str, value: int) -> Node:
    return _property(name, "enum", "", value)


def _time_property(name: str, value: int) -> Node:
    return _property(name, "KTime", "Time", Int64(value))


def _model(identifier: Int64, name: str, subtype: str) -> Node:
    model = Node("Model", (identifier, _named(name, "Model"), Str(subtype)))
    model.add("Version", 232)
    model.add("Properties70")
    model.add("Shading", True)
    model.add("Culling", Str("CullingOff"))
    return model


def _cluster(identifier: Int64, name: str) -> Node:
    """Every vertex bound to every bone, which keeps the weights legible."""
    cluster = Node("Deformer", (identifier, _named(name, "SubDeformer"), Str("Cluster")))
    cluster.add("Version", 100)
    cluster.add("UserData", Str(""), Str(""))
    cluster.add("Indexes", Ints(range(len(CORNERS))))
    cluster.add("Weights", Doubles(1.0 for _ in CORNERS))
    cluster.add("Transform", Doubles(_IDENTITY))
    cluster.add("TransformLink", Doubles(_IDENTITY))
    return cluster


def _uv_layer() -> Node:
    layer = Node("LayerElementUV", (0,))
    layer.add("Version", 101)
    layer.add("Name", Str("UVMap"))
    layer.add("MappingInformationType", Str("ByVertice"))
    layer.add("ReferenceInformationType", Str("Direct"))
    layer.add("UV", Doubles(value for _ in CORNERS for value in (0.5, 0.5)))
    return layer


def _polygon_indices() -> tuple[int, ...]:
    """A polygon's last index is stored negated — how FBX marks a polygon's end."""
    return tuple(
        index if position < 2 else ~index for face in FACES for position, index in enumerate(face)
    )


def _ktime(seconds: float) -> int:
    return round(seconds * KTIME_PER_SECOND)


def _samples(clip: ClipExpectation) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """A there-and-back translation, one key per frame at the fixture's rate."""
    count = round(clip.duration_s * FRAME_RATE) + 1
    times = tuple(_ktime(index / FRAME_RATE) for index in range(count))
    values = tuple(index / max(count - 1, 1) for index in range(count))
    return times, values


__all__ = [
    "ARMATURE",
    "BONES",
    "FBX_VERSION",
    "FRAME_RATE",
    "KTIME_PER_SECOND",
    "write_ascii_fbx",
    "write_axisless_fbx",
    "write_skinned_fbx",
    "write_static_fbx",
    "write_unterminated_fbx",
]
