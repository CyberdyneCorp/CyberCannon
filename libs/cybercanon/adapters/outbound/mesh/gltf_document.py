"""Reading a glTF document: buffers, accessors, and the questions both readers ask.

`pygltflib` parses the JSON and hands back the binary chunk; it does not
interpret an accessor. Both the fact extractor and the preview emitter need the
same few interpretations — where an accessor's bytes are, how large one element
is, which node is a joint — so they live here once and neither module grows its
own copy.

Everything is deliberately literal: an accessor is `count` elements of
`component_size x components` bytes inside a buffer view, and a view with a
`byteStride` is read at that stride. Nothing guesses, and anything this module
cannot read honestly raises :class:`GltfUnreadable` rather than returning a
plausible number — a fabricated fact is the failure mode D13 exists to prevent.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pygltflib import GLTF2, BufferFormat

COMPONENT_SIZES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
"""glTF component type -> bytes per component."""

COMPONENTS_PER_TYPE = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}
"""glTF element type -> how many components one element has."""

FLOAT = 5126
TRIANGLES_MODE = 4
"""The only primitive mode whose triangle count is its index count over three."""


class GltfUnreadable(ValueError):
    """The document is not readable as glTF, or uses something this reader cannot read."""


@dataclass(frozen=True)
class GltfDocument:
    """A parsed glTF and its binary chunk, with the accessor arithmetic done once."""

    gltf: GLTF2
    blob: bytes
    source: str

    @classmethod
    def read(cls, path: str | Path) -> GltfDocument:
        """Parse a `.glb` or `.gltf`, with external and embedded buffers resolved."""
        location = Path(path)
        try:
            gltf = GLTF2().load(str(location))
        except Exception as error:  # pygltflib raises bare exceptions for bad files
            raise GltfUnreadable(str(error) or type(error).__name__) from error
        if gltf is None:
            raise GltfUnreadable("the file is not a glTF document")
        return cls(gltf=gltf, blob=_binary(gltf, location), source=location.as_posix())

    @classmethod
    def from_bytes(cls, content: bytes, *, source: str = "<memory>") -> GltfDocument:
        """Parse GLB bytes — how an emitter verifies what it just produced."""
        try:
            gltf = GLTF2.load_from_bytes(content)
        except Exception as error:
            raise GltfUnreadable(str(error) or type(error).__name__) from error
        return cls(gltf=gltf, blob=bytes(gltf.binary_blob() or b""), source=source)

    # -- accessors -------------------------------------------------------

    def element_size(self, accessor: Any) -> int:
        """Bytes per element — the one number every read below is built on."""
        component = COMPONENT_SIZES.get(accessor.componentType)
        components = COMPONENTS_PER_TYPE.get(accessor.type)
        if component is None or components is None:
            raise GltfUnreadable(f"accessor type {accessor.type}/{accessor.componentType}")
        return component * components

    def elements(self, index: int) -> tuple[bytes, ...]:
        """The raw bytes of each element of an accessor, in order."""
        accessor = self.gltf.accessors[index]
        if accessor.sparse is not None:
            raise GltfUnreadable("a sparse accessor cannot be read by this reader")
        size = self.element_size(accessor)
        if accessor.bufferView is None:
            return tuple(bytes(size) for _ in range(accessor.count))
        view = self.gltf.bufferViews[accessor.bufferView]
        stride = view.byteStride or size
        start = (view.byteOffset or 0) + (accessor.byteOffset or 0)
        return tuple(
            self.blob[start + index * stride : start + index * stride + size]
            for index in range(accessor.count)
        )

    def floats(self, index: int) -> tuple[tuple[float, ...], ...]:
        """An accessor of floats, element by element. Anything else is refused."""
        accessor = self.gltf.accessors[index]
        if accessor.componentType != FLOAT:
            raise GltfUnreadable("a float accessor was expected")
        width = COMPONENTS_PER_TYPE.get(accessor.type, 1)
        return tuple(struct.unpack(f"<{width}f", data) for data in self.elements(index))

    def scalars(self, index: int) -> tuple[float, ...]:
        """A `SCALAR` float accessor as plain numbers — animation sample times."""
        return tuple(values[0] for values in self.floats(index))

    # -- the graph -------------------------------------------------------

    @property
    def nodes(self) -> list[Any]:
        return list(self.gltf.nodes or [])

    def node_name(self, index: int, fallback: str = "") -> str:
        node = self.gltf.nodes[index]
        return node.name or fallback or f"node_{index}"

    def joint_indices(self) -> frozenset[int]:
        """Every node used as a bone by any skin — never an attachment point."""
        return frozenset(joint for skin in (self.gltf.skins or []) for joint in (skin.joints or []))

    def skeleton_roots(self) -> frozenset[int]:
        """The root bone of each skin: its declared skeleton, else its first joint."""
        roots = set()
        for skin in self.gltf.skins or []:
            if skin.skeleton is not None:
                roots.add(skin.skeleton)
            elif skin.joints:
                roots.add(skin.joints[0])
        return frozenset(roots)

    def primitives(self) -> tuple[Any, ...]:
        return tuple(
            primitive for mesh in (self.gltf.meshes or []) for primitive in (mesh.primitives or [])
        )


def _binary(gltf: GLTF2, path: Path) -> bytes:
    """The binary chunk, whether it arrived as GLB, a `.bin` or a data URI."""
    blob = gltf.binary_blob()
    if blob:
        return bytes(blob)
    try:
        gltf.convert_buffers(BufferFormat.BINARYBLOB)
    except Exception as error:
        raise GltfUnreadable(f"{path.name} has buffers this reader cannot resolve") from error
    return bytes(gltf.binary_blob() or b"")


__all__ = [
    "COMPONENTS_PER_TYPE",
    "COMPONENT_SIZES",
    "TRIANGLES_MODE",
    "GltfDocument",
    "GltfUnreadable",
]
