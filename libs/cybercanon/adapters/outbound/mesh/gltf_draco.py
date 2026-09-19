"""Draco compression for a preview's geometry — the `KHR_draco_mesh_compression` seam.

D7 asks for a Draco-compressed preview. The encoder is `DracoPy`, a binding over
Google's `draco` that `uv` resolves from a wheel on macOS (x86_64 and arm64) and
on manylinux (x86_64 and aarch64) with no compiler involved — which is why it is
a declared dependency rather than an optional extra. The import is still guarded:
D7's recorded risk is precisely a native dependency failing to install, and a
platform outside that set (musl, say) must still get a preview rather than none.

**What compression may not cost.** `asset-preview` makes a preview that lost a
named part, a clip or its skinning a *failure*, and the way a compressed preview
loses skinning is quiet: `JOINTS_0` and `WEIGHTS_0` are ordinary vertex
attributes, so an encoder that simply does not carry them writes a file that
still loads, still lists its bones and still plays its clips — against an
unskinned mesh. Nothing in the node graph shows it. So every attribute the
primitive declares is encoded as a Draco attribute with an explicit unique id,
and :func:`verify` decodes what was written and refuses a preview whose
compressed payload does not carry every one of them.

**What this asks of a consumer.** A compressed preview lists the extension in
`extensionsRequired`, which is the honest declaration and also a hard one: a
glTF reader with no Draco decoder wired in SHALL refuse the file rather than
open it half-read. `three.js` needs `GLTFLoader.setDRACOLoader(...)`, so the 3D
viewer has to ship a decoder — that is the cost of D7, paid where it is visible
instead of where it would surprise somebody.

**Why the vertex order is preserved.** `preserve_order=True` costs about 8% of
the compressed size on the fixtures here and buys the property the rest of the
emitter is built on: the decoded vertex count and order are the source's, so
every attribute accessor keeps its `count`, its `min`/`max` and its meaning, and
decimation stays a question about the index list alone. Deduplicating vertices
would make each accessor a separate rewrite and each rewrite a chance to silently
mis-bind a joint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from cybercanon.adapters.outbound.mesh.gltf_document import COMPONENTS_PER_TYPE, GltfDocument

DRACO_EXTENSION = "KHR_draco_mesh_compression"
"""The glTF extension a compressed primitive declares, and browsers decode."""

QUANTIZATION_BITS = 14
"""Position precision. Preview-grade: a viewer shows shape, not measurements."""

COMPRESSION_LEVEL = 7
"""Draco's own effort dial, 0-10. Previews are written once and fetched often."""

POSITION = "POSITION"

_DRACO_POSITION = 0
"""Draco's `GeometryAttribute::POSITION`, the one attribute it names itself."""

_DTYPES = {5121: "uint8", 5123: "uint16", 5125: "uint32", 5126: "float32"}
"""glTF component type -> the numpy dtype Draco accepts for it.

Signed byte and short are absent on purpose: Draco takes unsigned integers and
floats, and a signed attribute silently reinterpreted would be a fabricated
vertex. A primitive carrying one is refused compression, not bent into shape.
"""


class DracoUnsupported(ValueError):
    """This geometry cannot be Draco-encoded without losing or inventing something.

    Never fatal: the caller falls back to an uncompressed preview, which is
    larger but carries everything (D7 — a preview never moves a verdict).
    """


@dataclass(frozen=True)
class Compressed:
    """One primitive's geometry as a Draco buffer, and how to read it back.

    `attributes` maps each glTF semantic to the Draco attribute unique id that
    holds it — the map that goes into the extension and the map `verify` checks.
    """

    buffer: bytes
    attributes: dict[str, int]
    vertices: int
    triangles: int


def encoder() -> Any:
    """The Draco binding, or a refusal naming its absence."""
    try:
        import DracoPy
    except ImportError as error:  # pragma: no cover - a synced environment has it
        raise DracoUnsupported("no Draco encoder is installed") from error
    return DracoPy


def available() -> bool:
    """Whether this machine can compress at all (D7's native-dependency risk)."""
    try:
        encoder()
    except DracoUnsupported:  # pragma: no cover - a synced environment has it
        return False
    return True


def is_compressed(document: GltfDocument) -> bool:
    """Whether any primitive of this document carries its geometry in Draco."""
    return any(_extension_of(primitive) is not None for primitive in document.primitives())


# --------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------


def compress(
    document: GltfDocument, primitive: Any, triangles: tuple[tuple[int, ...], ...]
) -> Compressed:
    """Encode one primitive's vertices and the triangles decimation kept.

    Every attribute other than `POSITION` is encoded as a Draco *generic*
    attribute under an id chosen here, because the glTF extension addresses
    attributes by unique id and never by Draco's own notion of what a normal or
    a texture coordinate is. `POSITION`'s id is whichever one Draco assigned,
    read back from the buffer rather than assumed.
    """
    draco = encoder()
    semantics = _semantics(primitive)
    others = tuple(name for name in semantics if name != POSITION)
    ids = {name: index for index, name in enumerate(others, start=1)}
    buffer = draco.encode(
        _attribute(document, semantics[POSITION]).astype("float64"),
        np.asarray(triangles, dtype="uint32"),
        generic_attributes={ids[name]: _attribute(document, semantics[name]) for name in others},
        preserve_order=True,
        quantization_bits=QUANTIZATION_BITS,
        compression_level=COMPRESSION_LEVEL,
    )
    ids[POSITION] = _position_id(draco, buffer)
    return Compressed(
        buffer=bytes(buffer),
        attributes=ids,
        vertices=document.gltf.accessors[semantics[POSITION]].count,
        triangles=len(triangles),
    )


def shares_accessors(document: GltfDocument) -> bool:
    """Whether two primitives read the same accessor — which compression cannot split.

    A compressed primitive owns its geometry outright: its accessors lose their
    buffer views and point at its Draco buffer. Two primitives sharing one
    accessor cannot both do that, so such a document is left uncompressed rather
    than rewritten into something that decodes differently per primitive.
    """
    seen: set[int] = set()
    for primitive in document.primitives():
        for accessor in _accessors_of(primitive):
            if accessor in seen:
                return True
            seen.add(accessor)
    return False


def _semantics(primitive: Any) -> dict[str, int]:
    """The primitive's attribute accessors by semantic, or a refusal."""
    if getattr(primitive, "targets", None):
        raise DracoUnsupported("morph targets cannot be carried through this encoder")
    attributes = {
        name: accessor
        for name, accessor in vars(primitive.attributes).items()
        if accessor is not None
    }
    if POSITION not in attributes:
        raise DracoUnsupported("a primitive with no POSITION cannot be compressed")
    return attributes


def _attribute(document: GltfDocument, accessor_index: int) -> np.ndarray:
    """One attribute accessor as a `(count, components)` array Draco accepts."""
    accessor = document.gltf.accessors[accessor_index]
    dtype = _DTYPES.get(accessor.componentType)
    components = COMPONENTS_PER_TYPE.get(accessor.type)
    if dtype is None or components is None:
        raise DracoUnsupported(
            f"an attribute of type {accessor.type}/{accessor.componentType} is not encodable"
        )
    raw = b"".join(document.elements(accessor_index))
    return np.frombuffer(raw, dtype=dtype).reshape(accessor.count, components).copy()


def _position_id(draco: Any, buffer: bytes) -> int:
    """Draco's unique id for the position attribute, read back from the buffer."""
    for attribute in draco.decode(buffer).attributes:
        if attribute["attribute_type"] == _DRACO_POSITION:
            return int(attribute["unique_id"])
    raise DracoUnsupported("the encoder produced a buffer with no position attribute")


# --------------------------------------------------------------------------
# Verification — the guard against a quietly unskinned preview
# --------------------------------------------------------------------------


def verify(document: GltfDocument) -> None:
    """Decode what was written and refuse a payload missing any declared attribute.

    Raises :class:`DracoUnsupported` rather than returning a verdict, because the
    only caller's answer to either is the same: do not ship this preview.
    """
    draco = encoder()
    for primitive in document.primitives():
        extension = _extension_of(primitive)
        if extension is not None:
            _verify_primitive(draco, document, primitive, extension)


def _verify_primitive(
    draco: Any, document: GltfDocument, primitive: Any, extension: dict[str, Any]
) -> None:
    mesh = draco.decode(_view_bytes(document, extension["bufferView"]))
    carried = {int(attribute["unique_id"]) for attribute in mesh.attributes}
    mapped = extension.get("attributes") or {}
    for name, accessor_index in _semantics(primitive).items():
        if mapped.get(name) not in carried:
            raise DracoUnsupported(f"the compressed preview does not carry {name}")
        _refuse_count(document, accessor_index, len(mesh.points), name)
    if primitive.indices is not None:
        _refuse_count(document, primitive.indices, 3 * len(mesh.faces), "the index list")


def _refuse_count(document: GltfDocument, accessor_index: int, decoded: int, what: str) -> None:
    declared = document.gltf.accessors[accessor_index].count
    if declared != decoded:
        raise DracoUnsupported(f"{what} declares {declared} elements but decodes to {decoded}")


def _view_bytes(document: GltfDocument, index: int) -> bytes:
    view = document.gltf.bufferViews[index]
    start = view.byteOffset or 0
    return document.blob[start : start + view.byteLength]


def _extension_of(primitive: Any) -> dict[str, Any] | None:
    return (getattr(primitive, "extensions", None) or {}).get(DRACO_EXTENSION)


def _accessors_of(primitive: Any) -> tuple[int, ...]:
    attributes = tuple(
        accessor for accessor in vars(primitive.attributes).values() if accessor is not None
    )
    return attributes if primitive.indices is None else (*attributes, primitive.indices)


__all__ = [
    "COMPRESSION_LEVEL",
    "DRACO_EXTENSION",
    "POSITION",
    "QUANTIZATION_BITS",
    "Compressed",
    "DracoUnsupported",
    "available",
    "compress",
    "encoder",
    "is_compressed",
    "shares_accessors",
    "verify",
]
