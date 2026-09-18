"""The `MeshInspector` port — mesh *reading* (D1).

The boundary most implementations get wrong: mesh **rules** are domain, mesh
**reading** is this port. It returns a dumb frozen
:class:`~cybercanon.domain.mesh_facts.MeshFacts` and the domain decides pass or
fail, which is what lets the entire validation suite run over hand-built facts
with zero files on disk and makes the eventual `trimesh` -> `bpy` swap a
one-adapter change.

Two consequences shape the signatures here:

* :meth:`MeshInspector.inspect` returns the facts **and an opaque handle**. The
  handle is the already-loaded mesh, so preview emission piggybacks on the read
  that validation already paid for rather than re-reading a 200 MB export (D7).
  Nothing outside the adapter may look inside it.
* An adapter never invents a value for a fact its format cannot carry: it fills
  `available` from the per-format matrix, and
  :class:`~cybercanon.domain.mesh_facts.FabricatedFact` fires if it tries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.preview import PreviewMesh
from cybercanon.domain.mesh_facts import MeshFacts, MeshFormat


@dataclass(frozen=True)
class InspectedMesh:
    """One export, read once: the facts the rules see and the handle they do not.

    `handle` is adapter-owned and deliberately typed as ``object``: the use case
    carries it from :meth:`MeshInspector.inspect` to
    :meth:`MeshInspector.emit_preview` and never inspects it, which is what
    keeps "the preview comes from the same read" true by construction.
    """

    facts: MeshFacts
    handle: object = None


class MeshUnreadable(OperationFailed):
    """The file is missing, truncated, or not the mesh its extension claims."""

    def __init__(self, export: str, reason: str) -> None:
        super().__init__(f"{export} could not be read as a mesh: {reason}", export)
        self.export = export
        self.reason = reason


class UnsupportedExport(OperationFailed):
    """A format the matrix does not cover: refused by name, never assumed (D13)."""

    def __init__(self, export: str, format_name: str) -> None:
        supported = ", ".join(str(known) for known in MeshFormat)
        super().__init__(
            f"{export} is in an unsupported export format ({format_name}); "
            f"supported formats are {supported}",
            export,
        )
        self.export = export
        self.format_name = format_name


class MeshInspector(Protocol):
    """Reads an export into facts, and emits a preview from that same read."""

    def inspect(self, export: str) -> InspectedMesh:
        """Read the export once.

        Raises :class:`MeshUnreadable` when the file cannot be read and
        :class:`UnsupportedExport` when its format has no row in the matrix.
        """
        ...

    def emit_preview(self, mesh: InspectedMesh) -> PreviewMesh:
        """A decimated, compressed preview of an already-read export.

        Raises :class:`~cybercanon.application.ports.preview.PreviewUnavailable`
        rather than returning a preview that lost clips, bones or named parts.
        """
        ...


__all__ = [
    "InspectedMesh",
    "MeshInspector",
    "MeshUnreadable",
    "UnsupportedExport",
]
