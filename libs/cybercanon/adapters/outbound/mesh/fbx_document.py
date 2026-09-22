"""Reading a binary FBX document: the node tree, and the questions facts ask of it.

FBX has no parser in this project's dependency set — `trimesh` carries no FBX
loader — and the alternatives are a native SDK or a DCC application, neither of
which belongs in `just check`. What FBX *does* have is a stable, mechanical
container: a tree of records, each a name, a property list and a nested list.
That container is what this module reads, and nothing more.

**What it deliberately refuses.** Anything it cannot read literally raises
:class:`FbxUnreadable` rather than returning a plausible number:

* an ASCII FBX (a different grammar entirely, not a variation of this one);
* a version below 7100, whose record layout differs;
* a property code or array encoding it does not know.

The alternative — skipping a record it did not understand — is how a reader
silently reports zero triangles or zero bones for a file that has plenty, and a
zero bone count passes a bone budget. D13 exists to stop exactly that.

**Names.** A binary FBX stores an object's name as ``name\\x00\\x01Class`` (the
ASCII form's ``Class::name``, reversed and with a different separator).
:func:`object_name` splits it, so callers never learn the encoding.

**The graph.** Parent/child, skin bindings and material assignments are all
`Connections` entries of the form ``"OO", child_id, parent_id`` — the child
first. :meth:`FbxDocument.parents_of` is that table, read once. An animation
curve is attached to *one named property* of its target instead
(``"OP", child_id, parent_id, "d|X"``), so :meth:`FbxDocument.connections` keeps
that fourth field and `parents_of` is the same table with it dropped.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BINARY_MAGIC = b"Kaydara FBX Binary  "
"""The 20 bytes that open every binary FBX. Anything else is another format."""

OLDEST_VERSION = 7100
"""Below this the record layout differs; refused rather than guessed at."""

WIDE_VERSION = 7500
"""From 7500 record offsets and counts are 64-bit rather than 32-bit."""

KTIME_PER_SECOND = 46186158000
"""FBX time unit: one second, exactly, as an integer."""

NAME_SEPARATOR = "\x00\x01"

_SCALAR_FORMATS = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
_ARRAY_FORMATS = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "?"}
_RAW_CODES = ("S", "R")

_ENCODING_RAW = 0
_ENCODING_DEFLATE = 1


class FbxUnreadable(ValueError):
    """The file is not a binary FBX this reader can read literally."""


@dataclass(frozen=True)
class FbxNode:
    """One record: a name, its properties, and the records nested inside it."""

    name: str
    properties: tuple[Any, ...]
    children: tuple[FbxNode, ...]

    def child(self, name: str) -> FbxNode | None:
        """The first nested record of that name, or ``None``."""
        return next((node for node in self.children if node.name == name), None)

    def children_named(self, name: str) -> tuple[FbxNode, ...]:
        """Every nested record of that name, in file order."""
        return tuple(node for node in self.children if node.name == name)

    def text(self, index: int) -> str:
        """Property `index` as text, however it was stored."""
        value = self.properties[index] if index < len(self.properties) else b""
        return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)

    @property
    def object_id(self) -> int | None:
        """An object record's id — the key every connection is written in."""
        first = self.properties[0] if self.properties else None
        return first if isinstance(first, int) else None

    @property
    def object_name(self) -> str:
        """The object's own name, with the class suffix removed."""
        return self.text(1).split(NAME_SEPARATOR)[0]

    @property
    def subtype(self) -> str:
        """`Mesh`, `LimbNode`, `Null`, `Skin`, `Cluster` — the record's third property."""
        return self.text(2)


@dataclass(frozen=True)
class FbxConnection:
    """One `Connections` entry: what is attached to what, and to which property.

    `relation` is ``"OO"`` for an object attached to an object and ``"OP"`` for
    an object attached to one named property of an object — which is how an
    animation curve says it drives ``d|X`` of a translation.
    """

    relation: str
    child: int
    parent: int
    property: str | None = None


@dataclass(frozen=True)
class FbxDocument:
    """A parsed binary FBX: its version, its top-level records, and its graph."""

    version: int
    roots: tuple[FbxNode, ...]
    source: str

    @classmethod
    def read(cls, path: str | Path) -> FbxDocument:
        """Parse a `.fbx`, refusing by name anything it cannot read literally."""
        location = Path(path)
        try:
            content = location.read_bytes()
        except OSError as error:
            raise FbxUnreadable(str(error)) from error
        return cls.from_bytes(content, source=location.as_posix())

    @classmethod
    def from_bytes(cls, content: bytes, *, source: str = "<memory>") -> FbxDocument:
        """Parse FBX bytes — how a fixture verifies what it just wrote."""
        version = _preamble(content)
        roots, _ = _read_list(content, 27, version, len(content))
        return cls(version=version, roots=roots, source=source)

    # -- the top level ---------------------------------------------------

    def root(self, name: str) -> FbxNode | None:
        return next((node for node in self.roots if node.name == name), None)

    def objects(self, name: str, subtype: str | None = None) -> tuple[FbxNode, ...]:
        """Every `Objects` record of that name, optionally narrowed by subtype."""
        container = self.root("Objects")
        return tuple(
            node
            for node in (container.children if container else ())
            if node.name == name and (subtype is None or node.subtype == subtype)
        )

    def global_setting(self, name: str) -> Any | None:
        """One `GlobalSettings` property by name, or ``None`` when absent."""
        settings = self.root("GlobalSettings")
        properties = settings.child("Properties70") if settings else None
        for entry in properties.children_named("P") if properties else ():
            if entry.text(0) == name:
                return entry.properties[4] if len(entry.properties) > 4 else None
        return None

    def connections(self) -> tuple[FbxConnection, ...]:
        """The `Connections` table, in file order, with the property field kept."""
        container = self.root("Connections")
        entries = container.children_named("C") if container else ()
        return tuple(
            connection for entry in entries if (connection := _connection(entry)) is not None
        )

    def parents_of(self) -> dict[int, tuple[int, ...]]:
        """child id -> the ids it is connected to, from the `Connections` table."""
        table: dict[int, list[int]] = {}
        for connection in self.connections():
            table.setdefault(connection.child, []).append(connection.parent)
        return {child: tuple(parents) for child, parents in table.items()}


def object_property(node: FbxNode, name: str) -> Any | None:
    """One `Properties70` entry of an object record, by name."""
    values = object_values(node, name)
    return values[0] if values else None


def object_values(node: FbxNode, name: str) -> tuple[Any, ...]:
    """Every value of one `Properties70` entry — ``Lcl Translation`` carries three."""
    properties = node.child("Properties70")
    for entry in properties.children_named("P") if properties else ():
        if entry.text(0) == name:
            return entry.properties[4:]
    return ()


def object_vector(
    node: FbxNode, name: str, default: tuple[float, float, float]
) -> tuple[float, ...]:
    """A three-component `Properties70` entry, or `default` when it is absent.

    An exporter omits a property at its default value, so absence means the
    default and not zero — writing zero for an omitted ``Lcl Scaling`` would
    flatten the object it is read for.
    """
    values = object_values(node, name)
    if len(values) < 3 or not all(isinstance(value, int | float) for value in values[:3]):
        return default
    return tuple(float(value) for value in values[:3])


def _connection(entry: FbxNode) -> FbxConnection | None:
    """One `C` record, or ``None`` for one this reader cannot read as a link."""
    relation = entry.text(0)
    if len(entry.properties) < 3 or not relation.startswith("O"):
        return None
    child, parent = entry.properties[1], entry.properties[2]
    if not isinstance(child, int) or not isinstance(parent, int):
        return None
    named = entry.text(3) if len(entry.properties) > 3 else None
    return FbxConnection(relation=relation, child=child, parent=parent, property=named)


# --------------------------------------------------------------------------
# The container
# --------------------------------------------------------------------------


def _preamble(content: bytes) -> int:
    """The version this file declares, or a refusal naming why it cannot be read."""
    if not content.startswith(BINARY_MAGIC):
        raise FbxUnreadable(
            "not a binary FBX; an ASCII FBX or another format cannot be read by this "
            "reader — re-export as binary FBX"
        )
    if len(content) < 27:
        raise FbxUnreadable("the file ends inside its own header")
    (version,) = struct.unpack("<I", content[23:27])
    if version < OLDEST_VERSION:
        raise FbxUnreadable(f"FBX version {version} predates the record layout this reader reads")
    return version


def _null_record_size(version: int) -> int:
    return 25 if version >= WIDE_VERSION else 13


def _read_list(
    content: bytes, position: int, version: int, limit: int
) -> tuple[tuple[FbxNode, ...], int]:
    """Records until the list's null terminator, and where reading stopped."""
    nodes: list[FbxNode] = []
    stop = limit - _null_record_size(version) + 1
    while position < stop:
        node, position = _read_node(content, position, version)
        if node is None:
            break
        nodes.append(node)
    return tuple(nodes), position


def _read_node(content: bytes, position: int, version: int) -> tuple[FbxNode | None, int]:
    """One record, or ``None`` for the null record that ends a list."""
    wide = version >= WIDE_VERSION
    layout, size = ("<QQQ", 24) if wide else ("<III", 12)
    if position + size + 1 > len(content):
        raise FbxUnreadable("the file ends inside a record header")
    end, count, _ = struct.unpack(layout, content[position : position + size])
    position += size
    name_length = content[position]
    position += 1
    if end == 0 and count == 0 and name_length == 0:
        return None, position
    name = content[position : position + name_length].decode("utf-8", "replace")
    position += name_length
    properties, position = _read_properties(content, position, count)
    children: tuple[FbxNode, ...] = ()
    if position < end:
        children, _ = _read_list(content, position, version, end)
    return FbxNode(name=name, properties=properties, children=children), max(position, end)


def _read_properties(content: bytes, position: int, count: int) -> tuple[tuple[Any, ...], int]:
    values: list[Any] = []
    for _ in range(count):
        value, position = _read_property(content, position)
        values.append(value)
    return tuple(values), position


def _read_property(content: bytes, position: int) -> tuple[Any, int]:
    code = chr(content[position])
    position += 1
    if code in _SCALAR_FORMATS:
        layout = _SCALAR_FORMATS[code]
        size = struct.calcsize(layout)
        return struct.unpack(layout, content[position : position + size])[0], position + size
    if code in _ARRAY_FORMATS:
        return _read_array(content, position, code)
    if code in _RAW_CODES:
        (length,) = struct.unpack("<I", content[position : position + 4])
        position += 4
        return content[position : position + length], position + length
    raise FbxUnreadable(f"property type {code!r} is not one this reader knows")


def _read_array(content: bytes, position: int, code: str) -> tuple[list[Any], int]:
    length, encoding, packed = struct.unpack("<III", content[position : position + 12])
    position += 12
    payload = content[position : position + packed]
    position += packed
    if encoding == _ENCODING_DEFLATE:
        payload = _inflate(payload)
    elif encoding != _ENCODING_RAW:
        raise FbxUnreadable(f"array encoding {encoding} is not one this reader knows")
    return list(struct.unpack(f"<{length}{_ARRAY_FORMATS[code]}", payload)), position


def _inflate(payload: bytes) -> bytes:
    try:
        return zlib.decompress(payload)
    except zlib.error as error:
        raise FbxUnreadable(f"a compressed array could not be decompressed: {error}") from error


__all__ = [
    "BINARY_MAGIC",
    "KTIME_PER_SECOND",
    "NAME_SEPARATOR",
    "OLDEST_VERSION",
    "WIDE_VERSION",
    "FbxConnection",
    "FbxDocument",
    "FbxNode",
    "FbxUnreadable",
    "object_property",
    "object_values",
    "object_vector",
]
