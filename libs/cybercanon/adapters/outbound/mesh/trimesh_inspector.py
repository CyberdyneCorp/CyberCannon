"""`TrimeshInspector` — the real `MeshInspector`, one reader per format.

D1 draws the line this class sits on: reading is here, ruling is domain. So
nothing in this module decides whether an export is acceptable; it turns a file
into facts and refuses, by name, anything it cannot read honestly.

**Per-format normalisation, and what the matrix row means.**

| Format | Read by | Notes |
|---|---|---|
| `GLB`, `GLTF` | `pygltflib` | Everything: metres, `+Y` up, explicit clips, skins and sockets. |
| `OBJ` | `trimesh` | Triangles, object names, materials, UV sets — all the file holds. |
| `FBX` | *(no reader)* | Refused by name, never guessed at. |

`FBX` is the honest gap. The matrix marks it as carrying clips, skinning and
sockets, and no FBX reader ships in this environment — `trimesh` has no FBX
loader and the alternatives are a native SDK or Blender. Returning empty facts
for it would be a validator that lies about its coverage (D13), and marking its
whole row unavailable would silently downgrade a format the design still intends
to support, so an FBX export is an **operation failure** naming the format and
the way out (re-export as GLB). That answer is a one-function change the day a
reader exists.

The adapter never sets a fact its format's row marks unavailable:
`facts_for` fills the mask from the matrix and `MeshFacts` refuses a fabricated
value, so the rule is enforced rather than remembered.
"""

from __future__ import annotations

from pathlib import Path

import trimesh

from cybercanon.adapters.outbound.mesh import gltf_facts, gltf_preview, obj_facts
from cybercanon.adapters.outbound.mesh.gltf_document import GltfDocument, GltfUnreadable
from cybercanon.adapters.outbound.mesh.gltf_preview import PreviewSettings
from cybercanon.application.ports.mesh_inspector import (
    InspectedMesh,
    MeshUnreadable,
    UnsupportedExport,
)
from cybercanon.application.ports.preview import PreviewMesh, PreviewUnavailable
from cybercanon.domain.mesh_facts import MeshFacts, MeshFormat

GLTF_FORMATS = (MeshFormat.GLB, MeshFormat.GLTF)

FBX_REASON = (
    "FBX extraction needs a reader this build does not have (trimesh carries no "
    "FBX loader); re-export as GLB, which records every fact the rules need"
)


class TrimeshInspector:
    """Reads an export into facts, and emits a preview from that same read."""

    def __init__(self, root: str | Path | None = None, settings: PreviewSettings | None = None):
        """`root` is what repository-relative export paths resolve against.

        Without one, paths are taken as given — which is what a CLI invoked in a
        working directory hands over.
        """
        self._root = Path(root) if root is not None else None
        self._settings = settings or PreviewSettings()

    def inspect(self, export: str) -> InspectedMesh:
        """Read the export once: the facts the rules see, and the handle they do not."""
        source_format = _format_of(export)
        if source_format is None:
            raise UnsupportedExport(export, Path(export).suffix.lstrip(".") or "unknown")
        path = self._absolute(export)
        if not path.is_file():
            raise MeshUnreadable(export, "no such file")
        return self._read(export, path, source_format)

    def emit_preview(self, mesh: InspectedMesh) -> PreviewMesh:
        """A decimated preview of an already-read export (D7).

        Raises :class:`~cybercanon.application.ports.preview.PreviewUnavailable`
        rather than returning a preview that lost clips, bones or named parts —
        never an `OperationFailed`, because a preview never moves a verdict.
        """
        document = mesh.handle
        if not isinstance(document, GltfDocument):
            raise PreviewUnavailable("this export was not read into a previewable document")
        return gltf_preview.emit_preview(document, self._settings)

    # -- per-format reading ----------------------------------------------

    def _read(self, export: str, path: Path, source_format: MeshFormat) -> InspectedMesh:
        if source_format in GLTF_FORMATS:
            return self._read_gltf(export, path, source_format)
        if source_format is MeshFormat.OBJ:
            return InspectedMesh(facts=self._read_obj(export, path), handle=_as_gltf(path))
        raise MeshUnreadable(export, FBX_REASON)

    def _read_gltf(self, export: str, path: Path, source_format: MeshFormat) -> InspectedMesh:
        try:
            document = GltfDocument.read(path)
            facts = gltf_facts.read_facts(document, source_format)
        except (GltfUnreadable, ValueError, KeyError, IndexError) as error:
            raise MeshUnreadable(export, str(error) or type(error).__name__) from error
        return InspectedMesh(facts=facts, handle=document)

    def _read_obj(self, export: str, path: Path) -> MeshFacts:
        try:
            return obj_facts.read_facts(path)
        except (obj_facts.ObjUnreadable, ValueError) as error:
            raise MeshUnreadable(export, str(error) or type(error).__name__) from error

    def _absolute(self, export: str) -> Path:
        path = Path(export)
        return path if path.is_absolute() or self._root is None else self._root / path


def _format_of(export: str) -> MeshFormat | None:
    """The format an export's extension declares, or ``None`` for one with no row."""
    return MeshFormat.from_name(Path(export).suffix)


def _as_gltf(path: Path) -> GltfDocument | None:
    """An OBJ converted to glTF in memory, so one decimator serves every format.

    A conversion that fails costs the preview and nothing else, which is why it
    answers ``None`` rather than raising: the facts have already been read and
    the verdict does not depend on this.
    """
    try:
        scene = trimesh.load(str(path), file_type="obj", process=False, force="scene")
        return GltfDocument.from_bytes(scene.export(file_type="glb"), source=path.as_posix())
    except Exception:  # a preview is optional by construction (D7)
        return None


__all__ = ["FBX_REASON", "GLTF_FORMATS", "TrimeshInspector"]
