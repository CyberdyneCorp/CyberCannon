"""An FBX turned into a glTF document in memory, so a preview can be emitted at all.

`fbx_facts` reads an FBX well enough to validate it: object names, the socket,
the skeleton and every clip reach the report. Nothing turned it into a
*previewable* document, and the cost of that gap is not a missing picture — it
is that the 3D viewer loads the preview and an `Anchor3D`'s durable key is a
part name, so an FBX-only asset had nothing for an annotation to resolve
against. That is what this module exists to close, and it is why it lives beside
the reader rather than inside the preview emitter: one decimator serves every
format (D7), and what was missing was a document to hand it.

**What it carries.** Geometry as control points and triangulated polygons, every
`Model`'s own placement, object and socket names, material names, the skeleton
with its hierarchy, the skinning the clusters describe, and every animation
stack as a clip with its curves.

**One name it carries that the report does not offer.** An exporter writes the
armature object itself as a `Null`, and `fbx_facts` deliberately excludes that
holder from the attachment points it reports — it is not something anybody
anchors to. The holder is still a node here, because it carries the placement
the whole rig hangs from, so a preview's part list holds one name the report
does not: the holder's. Nothing can be anchored to it that the report ever
offered, which is why it is a surplus rather than a disagreement.

**What it deliberately does not carry, and why it is not a loss:**

* **UV sets and textures.** Every preview drops its images
  (`gltf_preview._drop_textures`), so coordinates into an image that is gone buy
  nothing and cost a reading of FBX's four UV mapping modes.
* **Unit scale.** The preview keeps the export's own coordinates. `fbx_facts`
  refuses to state an FBX's unit scale — no two exporters agree — and a
  converter that scaled by a factor the reader will not report would be stating
  it anyway, in the one artifact nobody validates.
* **Anything past four influences on a vertex.** The four heaviest are kept and
  renormalised, which is the baseline every engine implements and a far smaller
  approximation than dropping three triangles in four, which decimation does
  next.

**What it refuses by name**, raising :class:`FbxUnconvertible`, because a
preview that is *wrong* is worse than one that is absent (D7 makes the absence
free, and `asset-preview` makes a degraded preview a failure):

* a placement this converter cannot compose — a rotation order other than
  `EulerXYZ`, a pre/post rotation, a rotation or scaling pivot, or a geometric
  transform;
* an animation stack whose curves drive a property that is not one of the three
  transform properties, or that carries no curves at all — a clip in the
  preview that does not move is not the clip that was authored.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

from pygltflib import (
    GLTF2,
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

from cybercanon.adapters.outbound.mesh import affine, fbx_facts
from cybercanon.adapters.outbound.mesh.fbx_document import (
    KTIME_PER_SECOND,
    FbxConnection,
    FbxDocument,
    FbxNode,
    object_property,
    object_vector,
)
from cybercanon.adapters.outbound.mesh.gltf_document import GltfDocument

FLOAT = 5126
UNSIGNED_SHORT = 5123
UNSIGNED_INT = 5125
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
_USHORT_MAX = 65535

INFLUENCES = 4
"""Joints per vertex in one `JOINTS_0` set — glTF's baseline, and this module's."""

TRANSFORM_PROPERTIES = {
    "Lcl Translation": "translation",
    "Lcl Rotation": "rotation",
    "Lcl Scaling": "scale",
}
"""The FBX properties an animation curve may drive, and the glTF path for each."""

CHANNELS = ("d|X", "d|Y", "d|Z")
"""The three per-axis curves an `AnimationCurveNode` is built from."""

UNSUPPORTED_PLACEMENT = (
    "PreRotation",
    "PostRotation",
    "RotationOffset",
    "RotationPivot",
    "ScalingOffset",
    "ScalingPivot",
    "GeometricTranslation",
    "GeometricRotation",
)
"""Placement properties this converter does not compose; a set one is refused."""


class FbxUnconvertible(ValueError):
    """The FBX reads, and no honest previewable document can be made from it."""


def convert(document: FbxDocument) -> GltfDocument:
    """One FBX as a glTF document, or a refusal naming what could not be carried."""
    return _Conversion(document).converted()


# --------------------------------------------------------------------------
# The buffer
# --------------------------------------------------------------------------


class _Blob:
    """The binary chunk under construction, and the views and accessors into it."""

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
        bounds: tuple[list[float], list[float]] | None = None,
    ) -> int:
        while len(self.data) % 4:
            self.data.append(0)
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
                min=bounds[0] if bounds else None,
                max=bounds[1] if bounds else None,
            )
        )
        return len(self.accessors) - 1

    def floats(self, values: tuple[float, ...], *, kind: str, **rest: Any) -> int:
        width = _COMPONENTS[kind]
        return self.accessor(
            struct.pack(f"<{len(values)}f", *values),
            component_type=FLOAT,
            kind=kind,
            count=len(values) // width,
            **rest,
        )


_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _bounds(values: tuple[float, ...], width: int) -> tuple[list[float], list[float]]:
    """The per-component minimum and maximum glTF requires on some accessors."""
    columns = [values[axis::width] for axis in range(width)]
    return [min(column) for column in columns], [max(column) for column in columns]


# --------------------------------------------------------------------------
# The conversion
# --------------------------------------------------------------------------


@dataclass
class _Cluster:
    """One bone's share of a skin: which control points, how much, and the bind."""

    bone: int
    indices: tuple[int, ...]
    weights: tuple[float, ...]
    into_bone: affine.Matrix
    """`inverse(TransformLink)`: world space at bind time into this bone's space."""


@dataclass
class _Skin:
    """A skin as glTF needs it: the joints in order, and the bindings by vertex."""

    joints: tuple[int, ...]
    into_bones: tuple[affine.Matrix, ...]
    influences: dict[int, list[tuple[int, float]]] = field(default_factory=dict)


class _Conversion:
    """One FBX document, read into the pieces a glTF needs, in dependency order."""

    def __init__(self, document: FbxDocument) -> None:
        self.document = document
        self.blob = _Blob()
        self.models = document.objects("Model")
        self.index_of = {
            model.object_id: index
            for index, model in enumerate(self.models)
            if model.object_id is not None
        }
        self.parents = document.parents_of()
        self.attached_to = _by_parent(document)
        self.curves_by_id = {curve.object_id: curve for curve in document.objects("AnimationCurve")}
        self.nodes = [self._node(model) for model in self.models]
        self.meshes: list[Mesh] = []
        self.skins: list[Skin] = []
        self.globals: dict[int, affine.Matrix] = {}
        self.materials = tuple(node.object_name for node in document.objects("Material"))

    def _assembled(self) -> GLTF2:
        """Everything assembled, in the order each piece's inputs become known."""
        self._parent_the_nodes()
        self.globals = self._global_placements()
        for geometry in self.document.objects("Geometry", "Mesh"):
            self._geometry(geometry)
        animations = [self._clip(stack) for stack in self.document.objects("AnimationStack")]
        return GLTF2(
            scene=0,
            scenes=[Scene(nodes=self._roots())],
            nodes=self.nodes,
            meshes=self.meshes,
            skins=self.skins,
            materials=[Material(name=name) for name in self.materials],
            animations=animations,
        )

    def converted(self) -> GltfDocument:
        """The whole document, packed into the one buffer glTF keeps its data in."""
        gltf = self._assembled()
        gltf.bufferViews = self.blob.views
        gltf.accessors = self.blob.accessors
        gltf.buffers = [Buffer(byteLength=len(self.blob.data))]
        gltf.set_binary_blob(bytes(self.blob.data))
        return GltfDocument.from_bytes(b"".join(gltf.save_to_bytes()), source=self.document.source)

    # -- nodes -----------------------------------------------------------

    def _node(self, model: FbxNode) -> Node:
        """One `Model` as a glTF node, with the placement it records."""
        _refuse_unsupported_placement(model)
        return Node(
            name=model.object_name,
            translation=list(object_vector(model, "Lcl Translation", (0.0, 0.0, 0.0))),
            rotation=list(
                affine.euler_to_quaternion(object_vector(model, "Lcl Rotation", (0.0, 0.0, 0.0)))
            ),
            scale=list(object_vector(model, "Lcl Scaling", (1.0, 1.0, 1.0))),
        )

    def _parent_the_nodes(self) -> None:
        for model in self.models:
            parent = self._parent_node(model)
            if parent is not None:
                self.nodes[parent].children.append(self.index_of[model.object_id])

    def _parent_node(self, model: FbxNode) -> int | None:
        """The index of this model's parent model, or ``None`` for a scene root."""
        for parent in self.parents.get(model.object_id or -1, ()):
            if parent in self.index_of:
                return self.index_of[parent]
        return None

    def _global_placements(self) -> dict[int, affine.Matrix]:
        """Every node's place in the world, composed down the hierarchy it is in.

        A skin's inverse bind matrix is written against world space, and so is
        the `TransformLink` it is derived from; reading a mesh's world matrix
        off the hierarchy rather than off a cluster's `Transform` keeps both
        halves in one space, which is the space every exporter agrees on.

        Walked rather than recursed, so a rig deep enough to exhaust the stack
        is slow rather than an exception escaping a preview that may not fail.
        """
        placements: dict[int, affine.Matrix] = {}
        descending = [(root, affine.IDENTITY) for root in self._roots()]
        while descending:
            node, above = descending.pop()
            placements[node] = affine.multiply(above, self._local(self.models[node]))
            descending.extend((child, placements[node]) for child in self.nodes[node].children)
        return placements

    @staticmethod
    def _local(model: FbxNode) -> affine.Matrix:
        return affine.placement(
            object_vector(model, "Lcl Translation", (0.0, 0.0, 0.0)),
            object_vector(model, "Lcl Rotation", (0.0, 0.0, 0.0)),
            object_vector(model, "Lcl Scaling", (1.0, 1.0, 1.0)),
        )

    def _roots(self) -> list[int]:
        return [
            index for index, model in enumerate(self.models) if self._parent_node(model) is None
        ]

    # -- geometry --------------------------------------------------------

    def _geometry(self, geometry: FbxNode) -> None:
        """One `Geometry` as a mesh on the node of the model that draws it."""
        node = self._drawn_by(geometry)
        if node is None:
            return
        positions = _control_points(geometry)
        triangles = tuple(
            corner for polygon in fbx_facts.polygons(geometry) for corner in _fan(polygon)
        )
        if not triangles:
            return
        if max(triangles) >= len(positions) // 3:
            raise FbxUnconvertible(
                f"geometry {geometry.object_name!r} indexes a control point it does not have"
            )
        skin = self._skin_of(geometry)
        self.meshes.append(
            Mesh(
                name=geometry.object_name,
                primitives=[self._primitive(positions, triangles, skin, node)],
            )
        )
        self.nodes[node].mesh = len(self.meshes) - 1
        if skin is not None:
            self.nodes[node].skin = self._skin_index(skin, node)

    def _drawn_by(self, geometry: FbxNode) -> int | None:
        for parent in self.parents.get(geometry.object_id or -1, ()):
            if parent in self.index_of:
                return self.index_of[parent]
        return None

    def _primitive(
        self,
        positions: tuple[float, ...],
        triangles: tuple[int, ...],
        skin: _Skin | None,
        node: int,
    ) -> Primitive:
        count = len(positions) // 3
        attributes = Attributes(
            POSITION=self.blob.floats(
                positions, kind="VEC3", target=ARRAY_BUFFER, bounds=_bounds(positions, 3)
            )
        )
        if skin is not None:
            self._bind(attributes, skin, count)
        return Primitive(
            attributes=attributes,
            indices=self._indices(triangles),
            material=self._material_of(node),
        )

    def _indices(self, triangles: tuple[int, ...]) -> int:
        wide = max(triangles) > _USHORT_MAX
        return self.blob.accessor(
            struct.pack(f"<{len(triangles)}{'I' if wide else 'H'}", *triangles),
            component_type=UNSIGNED_INT if wide else UNSIGNED_SHORT,
            kind="SCALAR",
            count=len(triangles),
            target=ELEMENT_ARRAY_BUFFER,
        )

    def _material_of(self, node: int) -> int | None:
        """The first material attached to this model — a preview keeps names only.

        FBX assigns materials per polygon through a layer element; a preview
        drops every texture and carries no colour, so all a material is here is
        its name, and which of them a triangle points at changes nothing that is
        rendered.
        """
        materials = self.document.objects("Material")
        for index, material in enumerate(materials):
            if node in {self.index_of.get(parent) for parent in self._parents_of(material)}:
                return index
        return None

    def _parents_of(self, node: FbxNode) -> tuple[int, ...]:
        return self.parents.get(node.object_id or -1, ())

    # -- skinning --------------------------------------------------------

    def _skin_of(self, geometry: FbxNode) -> _Skin | None:
        """The skin that deforms this geometry, as joints, binds and influences."""
        clusters = self._clusters(geometry)
        if not clusters:
            return None
        skin = _Skin(
            joints=tuple(cluster.bone for cluster in clusters),
            into_bones=tuple(cluster.into_bone for cluster in clusters),
        )
        for slot, cluster in enumerate(clusters):
            for vertex, weight in zip(cluster.indices, cluster.weights, strict=False):
                skin.influences.setdefault(vertex, []).append((slot, weight))
        return skin

    def _clusters(self, geometry: FbxNode) -> tuple[_Cluster, ...]:
        deformers = {
            skin.object_id
            for skin in self.document.objects("Deformer", "Skin")
            if geometry.object_id in self._parents_of(skin)
        }
        return tuple(
            cluster
            for node in self.document.objects("Deformer", "Cluster")
            if deformers & set(self._parents_of(node))
            if (cluster := self._cluster(node)) is not None
        )

    def _cluster(self, node: FbxNode) -> _Cluster | None:
        """One cluster: the bone it drives, its weights, and its bind matrix."""
        bone = next(
            (
                self.index_of[connection.child]
                for connection in self.attached_to.get(node.object_id or -1, ())
                if connection.child in self.index_of
            ),
            None,
        )
        if bone is None:
            return None
        return _Cluster(
            bone=bone,
            indices=tuple(_numbers(node, "Indexes", int)),
            weights=tuple(_numbers(node, "Weights", float)),
            into_bone=_into_bone(node),
        )

    def _skin_index(self, skin: _Skin, node: int) -> int:
        """Append the skin and its inverse bind matrices; return its index.

        A joint's inverse bind matrix is `inverse(TransformLink) @ world`, where
        `world` is where the mesh sat when it was bound: glTF ignores a skinned
        mesh node's own transform, so the place the vertices were authored in
        has to reach the skin or the preview renders somewhere else.
        """
        world = self.globals.get(node, affine.IDENTITY)
        matrices = tuple(
            value
            for into_bone in skin.into_bones
            for value in affine.to_flat(affine.multiply(into_bone, world))
        )
        self.skins.append(
            Skin(
                joints=list(skin.joints),
                skeleton=skin.joints[self._root_slot(skin.joints)],
                inverseBindMatrices=self.blob.floats(matrices, kind="MAT4"),
            )
        )
        return len(self.skins) - 1

    def _root_slot(self, joints: tuple[int, ...]) -> int:
        """Where in `joints` the one no other joint parents sits — the rig's root."""
        children = {child for joint in joints for child in self.nodes[joint].children}
        return next((slot for slot, joint in enumerate(joints) if joint not in children), 0)

    def _bind(self, attributes: Attributes, skin: _Skin, count: int) -> None:
        """`JOINTS_0` and `WEIGHTS_0`, the four heaviest influences per vertex.

        A vertex no cluster names is bound to the root instead of being left at
        four zero weights: glTF multiplies a vertex by the sum of its weighted
        joint matrices, so all-zero weights collapse it onto the origin, and a
        mesh with a stray unweighted vertex would preview with a spike through
        it. Bound to the root it sits exactly where the export put it, and
        follows the rig rather than the floor.
        """
        root = self._root_slot(skin.joints)
        joints: list[int] = []
        weights: list[float] = []
        for vertex in range(count):
            bound = _four_heaviest(skin.influences.get(vertex, []), root)
            joints.extend(slot for slot, _ in bound)
            weights.extend(weight for _, weight in bound)
        attributes.JOINTS_0 = self.blob.accessor(
            struct.pack(f"<{len(joints)}H", *joints),
            component_type=UNSIGNED_SHORT,
            kind="VEC4",
            count=count,
            target=ARRAY_BUFFER,
        )
        attributes.WEIGHTS_0 = self.blob.floats(tuple(weights), kind="VEC4", target=ARRAY_BUFFER)

    # -- animation -------------------------------------------------------

    def _clip(self, stack: FbxNode) -> Animation:
        """One `AnimationStack` as a glTF animation, refused if it carries no curves."""
        names = frozenset(model.object_name for model in self.models)
        name = fbx_facts.clip_name(stack.object_name, names)
        span = _span(stack)
        channels: list[AnimationChannel] = []
        samplers: list[AnimationSampler] = []
        for curve_node in self._curve_nodes(stack):
            self._channel(curve_node, span, channels, samplers)
        if not channels:
            raise FbxUnconvertible(
                f"animation stack {name!r} carries no curve this reader can convert, and a "
                "clip that does not move is not the clip that was authored"
            )
        return Animation(name=name, channels=channels, samplers=samplers)

    def _curve_nodes(self, stack: FbxNode) -> tuple[FbxNode, ...]:
        layers = {
            layer.object_id
            for layer in self.document.objects("AnimationLayer")
            if stack.object_id in self._parents_of(layer)
        }
        return tuple(
            node
            for node in self.document.objects("AnimationCurveNode")
            if layers & set(self._parents_of(node))
        )

    def _channel(
        self,
        curve_node: FbxNode,
        span: tuple[float, float],
        channels: list[AnimationChannel],
        samplers: list[AnimationSampler],
    ) -> None:
        """One curve node as one sampler and one channel on the node it drives."""
        target, driven = self._target(curve_node)
        path = TRANSFORM_PROPERTIES[driven]
        curves = self._curves(curve_node)
        times = _sample_times(curves, span)
        values = _sampled(curve_node, curves, times, driven, self.models[target])
        samplers.append(
            AnimationSampler(
                input=self.blob.floats(
                    tuple(time - span[0] for time in times),
                    kind="SCALAR",
                    bounds=([0.0], [span[1] - span[0]]),
                ),
                interpolation="LINEAR",
                output=self.blob.floats(values, kind=_PATH_KIND[path]),
            )
        )
        channels.append(
            AnimationChannel(
                sampler=len(samplers) - 1,
                target=AnimationChannelTarget(node=target, path=path),
            )
        )

    def _target(self, curve_node: FbxNode) -> tuple[int, str]:
        """The node this curve node drives, and the FBX property it drives on it."""
        for parent in self.parents.get(curve_node.object_id or -1, ()):
            driven = self._driven(curve_node, parent)
            if driven is not None:
                return self.index_of[parent], driven
        raise FbxUnconvertible("an animation curve node drives nothing this reader found")

    def _driven(self, curve_node: FbxNode, parent: int) -> str | None:
        """The transform property this curve node drives on `parent`, if it is one."""
        if parent not in self.index_of:
            return None
        for connection in self.attached_to.get(parent, ()):
            if connection.child != curve_node.object_id or not connection.property:
                continue
            if connection.property in TRANSFORM_PROPERTIES:
                return connection.property
            raise FbxUnconvertible(
                f"an animation curve drives {connection.property!r}, which this "
                "converter does not carry into a preview"
            )
        return None

    def _curves(self, curve_node: FbxNode) -> dict[str, FbxNode]:
        """This curve node's per-axis curves, by the channel each is attached to."""
        return {
            connection.property: curve
            for connection in self.attached_to.get(curve_node.object_id or -1, ())
            if connection.property in CHANNELS
            if (curve := self.curves_by_id.get(connection.child)) is not None
        }


_PATH_KIND = {"translation": "VEC3", "scale": "VEC3", "rotation": "VEC4"}


# --------------------------------------------------------------------------
# Reading the records
# --------------------------------------------------------------------------


def _by_parent(document: FbxDocument) -> dict[int, tuple[FbxConnection, ...]]:
    """The connection table indexed by parent, built once.

    A rig with a few hundred bones and a few dozen clips runs to tens of
    thousands of curve nodes, and walking the whole table for each of them is
    the difference between a preview that takes a moment and one nobody waits
    for.
    """
    table: dict[int, list[FbxConnection]] = {}
    for connection in document.connections():
        table.setdefault(connection.parent, []).append(connection)
    return {parent: tuple(entries) for parent, entries in table.items()}


def _refuse_unsupported_placement(model: FbxNode) -> None:
    """A placement this converter cannot compose is named, never approximated."""
    order = object_property(model, "RotationOrder")
    if isinstance(order, int | float) and int(order) != 0:
        raise FbxUnconvertible(
            f"{model.object_name!r} declares rotation order {int(order)}; this converter "
            "reads EulerXYZ only, and another order is a different rotation"
        )
    for name in UNSUPPORTED_PLACEMENT:
        values = object_vector(model, name, (0.0, 0.0, 0.0))
        if any(abs(value) > 1e-9 for value in values):
            raise FbxUnconvertible(
                f"{model.object_name!r} records a {name} this converter does not compose"
            )
    scaling = object_vector(model, "GeometricScaling", (1.0, 1.0, 1.0))
    if any(abs(value - 1.0) > 1e-9 for value in scaling):
        raise FbxUnconvertible(
            f"{model.object_name!r} records a GeometricScaling this converter does not compose"
        )


def _control_points(geometry: FbxNode) -> tuple[float, ...]:
    values = _numbers(geometry, "Vertices", float)
    if not values or len(values) % 3:
        raise FbxUnconvertible(
            f"geometry {geometry.object_name!r} records no readable control points"
        )
    return tuple(values)


def _numbers(node: FbxNode, name: str, kind: type) -> list[Any]:
    """One array-valued child record, or an empty list when it is absent."""
    child = node.child(name)
    payload = child.properties[0] if child and child.properties else None
    return [kind(value) for value in payload] if isinstance(payload, list) else []


def _fan(polygon: tuple[int, ...]) -> tuple[int, ...]:
    """A polygon as triangles — the same fan `fbx_facts` counts."""
    return tuple(
        corner
        for index in range(1, len(polygon) - 1)
        for corner in (polygon[0], polygon[index], polygon[index + 1])
    )


def _into_bone(cluster: FbxNode) -> affine.Matrix:
    """`inverse(TransformLink)` — world space at bind time, into this bone's space.

    `TransformLink` is where the bone stood in the world when the mesh was bound
    to it, which is the half of an inverse bind matrix a cluster records
    unambiguously. The other half is the mesh's own world matrix, and it is read
    off the node hierarchy rather than off the cluster's `Transform`: exporters
    do not agree on which space `Transform` is written in, and one that is a
    unit conversion out deforms the preview by that factor.
    """
    try:
        return affine.inverse(_matrix(cluster, "TransformLink"))
    except affine.Singular as error:
        raise FbxUnconvertible(
            f"cluster {cluster.object_name!r} records a bind pose that cannot be inverted"
        ) from error


def _matrix(cluster: FbxNode, name: str) -> affine.Matrix:
    values = _numbers(cluster, name, float)
    return affine.from_flat(values) if len(values) == 16 else affine.IDENTITY


def _four_heaviest(influences: list[tuple[int, float]], root: int) -> tuple[tuple[int, float], ...]:
    """The four strongest bindings on one vertex, renormalised, padded to four.

    A vertex with no binding at all — or with weights that sum to nothing — is
    bound to `root` rather than to nothing; see :meth:`_Conversion._bind`.
    """
    strongest = sorted(influences, key=lambda binding: -binding[1])[:INFLUENCES]
    total = sum(weight for _, weight in strongest)
    scaled = [(slot, weight / total) for slot, weight in strongest] if total else [(root, 1.0)]
    return tuple(scaled) + ((0, 0.0),) * (INFLUENCES - len(scaled))


# --------------------------------------------------------------------------
# Sampling a curve
# --------------------------------------------------------------------------


def _span(stack: FbxNode) -> tuple[float, float]:
    """The stack's own start and stop in seconds — the clip's authored length."""
    start = object_property(stack, "LocalStart")
    stop = object_property(stack, "LocalStop")
    if not isinstance(stop, int):
        raise FbxUnconvertible(
            f"animation stack {stack.object_name!r} records no length, and a preview clip "
            "of an invented duration would not be the clip that was authored"
        )
    begins = start if isinstance(start, int) else 0
    return begins / KTIME_PER_SECOND, stop / KTIME_PER_SECOND


def _sample_times(curves: dict[str, FbxNode], span: tuple[float, float]) -> tuple[float, ...]:
    """Every key time in the clip's window, with its own ends included.

    The ends matter: a glTF clip is as long as its last sample, so a curve that
    stops keying before the stack's end would shorten the clip and the preview
    would no longer carry the duration the source recorded.
    """
    keys = {
        time / KTIME_PER_SECOND
        for curve in curves.values()
        for time in _numbers(curve, "KeyTime", int)
    }
    inside = {time for time in keys if span[0] <= time <= span[1]}
    return tuple(sorted(inside | {span[0], span[1]}))


def _sampled(
    curve_node: FbxNode,
    curves: dict[str, FbxNode],
    times: tuple[float, ...],
    driven: str,
    model: FbxNode,
) -> tuple[float, ...]:
    """The curve node evaluated at every sample time, in glTF's units for `driven`."""
    rest = _rest_value(curve_node, driven, model)
    axes = [
        _axis(curves.get(channel), times, rest[index]) for index, channel in enumerate(CHANNELS)
    ]
    values = [tuple(axis[index] for axis in axes) for index in range(len(times))]
    if driven != "Lcl Rotation":
        return tuple(value for triple in values for value in triple)
    return _rotations(values)


def _rest_value(curve_node: FbxNode, driven: str, model: FbxNode) -> tuple[float, ...]:
    """What an unkeyed axis holds: the curve node's own default, else the rest pose.

    An exporter writes only the axes it keyed, and reading a missing one as zero
    would drop a bone to the origin for the length of the clip.
    """
    resting = object_vector(model, driven, _RESTS[driven])
    declared = tuple(object_property(curve_node, channel) for channel in CHANNELS)
    return tuple(
        float(value) if isinstance(value, int | float) else resting[axis]
        for axis, value in enumerate(declared)
    )


_RESTS = {
    "Lcl Translation": (0.0, 0.0, 0.0),
    "Lcl Rotation": (0.0, 0.0, 0.0),
    "Lcl Scaling": (1.0, 1.0, 1.0),
}


def _axis(curve: FbxNode | None, times: tuple[float, ...], default: float) -> tuple[float, ...]:
    """One axis sampled at every time: its keys, held at the ends, linear between."""
    if curve is None:
        return tuple(default for _ in times)
    keys = tuple(time / KTIME_PER_SECOND for time in _numbers(curve, "KeyTime", int))
    values = tuple(_numbers(curve, "KeyValueFloat", float))
    if not keys or len(keys) != len(values):
        return tuple(default for _ in times)
    return tuple(_at(keys, values, time) for time in times)


def _at(keys: tuple[float, ...], values: tuple[float, ...], time: float) -> float:
    """A piecewise-linear read of one curve, holding its first and last values."""
    if time <= keys[0]:
        return values[0]
    if time >= keys[-1]:
        return values[-1]
    following = next(index for index, key in enumerate(keys) if key >= time)
    before, after = keys[following - 1], keys[following]
    share = (time - before) / (after - before) if after > before else 0.0
    return values[following - 1] + (values[following] - values[following - 1]) * share


def _rotations(degrees: list[tuple[float, float, float]]) -> tuple[float, ...]:
    """Euler keys as quaternions, each signed to interpolate the short way round."""
    previous = affine.IDENTITY_ROTATION
    flat: list[float] = []
    for angles in degrees:
        previous = affine.shortest_way_round(affine.euler_to_quaternion(angles), previous)
        flat.extend(previous)
    return tuple(flat)


__all__ = ["FbxUnconvertible", "convert"]
