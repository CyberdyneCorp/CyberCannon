"""`TrimeshInspector` — the real `MeshInspector`, one reader per format.

D1 draws the line this class sits on: reading is here, ruling is domain. So
nothing in this module decides whether an export is acceptable; it turns a file
into facts and refuses, by name, anything it cannot read honestly.

**Per-format normalisation, and what the matrix row means.**

| Format | Read by | Previewed through | Read as |
|---|---|---|---|
| `GLB`, `GLTF` | `pygltflib` | itself | everything: metres, `+Y` up, clips, skins, sockets |
| `FBX` | `fbx_document` | `fbx_gltf` | geometry, sockets, clips, skeleton — no scale or rate |
| `OBJ` | `trimesh` | `trimesh`'s glTF export | triangles, names, materials, UV sets |

**One decimator, so one conversion per format.** `gltf_preview` is the only
thing in this codebase that decimates, and it decimates glTF; a format that is
not glTF is therefore converted into one first. That conversion is part of
reading, not of previewing, which is why it lives beside the reader — and why a
format that cannot be converted loses its preview and nothing else (D7). The
conversion is deferred until a preview is actually asked for on the format
where it is expensive: an `FBX`'s handle is the parsed document, and
`fbx_gltf` runs on it only inside `emit_preview`.

`FBX` is the format the matrix earns its keep on. `trimesh` carries no FBX
loader, so the binary container is read here directly, and the *normalisation* is
mostly a list of refusals: a `Null` that parents a bone is an armature holder
rather than a socket, a take named `Armature|A_scout_walk` is the clip
`A_scout_walk`, and unit scale, applied transforms and frame rate are left to the
matrix to report as NOT EVALUATED because no exporter writes them the same way
twice. An ASCII FBX is refused by name — it is a different grammar, not a
variation of this one.

The adapter never sets a fact its format's row marks unavailable:
`facts_for` fills the mask from the matrix and `MeshFacts` refuses a fabricated
value, so the rule is enforced rather than remembered.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from cybercanon.adapters.outbound.mesh import (
    fbx_facts,
    fbx_gltf,
    gltf_facts,
    gltf_preview,
    obj_facts,
)
from cybercanon.adapters.outbound.mesh.fbx_document import FbxDocument, FbxUnreadable
from cybercanon.adapters.outbound.mesh.gltf_document import GltfDocument, GltfUnreadable
from cybercanon.adapters.outbound.mesh.gltf_preview import PreviewSettings
from cybercanon.application.ports.mesh_inspector import (
    InspectedMesh,
    MeshUnreadable,
    UnsupportedExport,
)
from cybercanon.application.ports.preview import PreviewMesh, PreviewUnavailable
from cybercanon.domain.mesh_facts import MeshFormat

GLTF_FORMATS = (MeshFormat.GLB, MeshFormat.GLTF)


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
        if isinstance(document, FbxDocument):
            document = _converted(document)
        if not isinstance(document, GltfDocument):
            raise PreviewUnavailable("this export was not read into a previewable document")
        return gltf_preview.emit_preview(document, self._settings)

    # -- per-format reading ----------------------------------------------

    def _read(self, export: str, path: Path, source_format: MeshFormat) -> InspectedMesh:
        if source_format in GLTF_FORMATS:
            return self._read_gltf(export, path, source_format)
        if source_format is MeshFormat.FBX:
            return self._read_fbx(export, path)
        return self._read_obj(export, path)

    def _read_gltf(self, export: str, path: Path, source_format: MeshFormat) -> InspectedMesh:
        try:
            document = GltfDocument.read(path)
            facts = gltf_facts.read_facts(document, source_format)
        except (GltfUnreadable, ValueError, KeyError, IndexError) as error:
            raise MeshUnreadable(export, str(error) or type(error).__name__) from error
        return InspectedMesh(facts=facts, handle=document)

    def _read_fbx(self, export: str, path: Path) -> InspectedMesh:
        """The parsed FBX is the handle, and `fbx_gltf` turns it into a preview.

        The conversion is left until a preview is actually asked for, because a
        validation run that wants no preview should pay for no preview — and
        the handle is still the same read the facts came from, which is what
        D7 asks of it.
        """
        try:
            document = FbxDocument.read(path)
            facts = fbx_facts.read_facts(document)
        except (FbxUnreadable, ValueError, KeyError, IndexError, struct.error) as error:
            raise MeshUnreadable(export, str(error) or type(error).__name__) from error
        return InspectedMesh(facts=facts, handle=document)

    def _read_obj(self, export: str, path: Path) -> InspectedMesh:
        """One load answers both questions: the facts, and the preview's source.

        Loading twice would let the report and the viewer disagree about what
        the file contains — which is how a part name survives into one and not
        the other, and how an anchor lands on the wrong geometry.
        """
        try:
            scene = obj_facts.load_scene(path)
            facts = obj_facts.facts_of(scene)
        except (obj_facts.ObjUnreadable, ValueError) as error:
            raise MeshUnreadable(export, str(error) or type(error).__name__) from error
        return InspectedMesh(facts=facts, handle=_as_gltf(scene, path))

    def _absolute(self, export: str) -> Path:
        path = Path(export)
        return path if path.is_absolute() or self._root is None else self._root / path


def _format_of(export: str) -> MeshFormat | None:
    """The format an export's extension declares, or ``None`` for one with no row."""
    return MeshFormat.from_name(Path(export).suffix)


def _converted(document: FbxDocument) -> GltfDocument:
    """An FBX as a previewable glTF, or a refusal naming what could not be carried.

    Every refusal arrives as `PreviewUnavailable`, never as an
    :class:`~cybercanon.application.errors.OperationFailed`: an FBX that cannot
    be converted has already been validated, and a preview never moves a
    verdict (D7).
    """
    try:
        return fbx_gltf.convert(document)
    except (ValueError, KeyError, IndexError, struct.error) as error:
        raise PreviewUnavailable(
            f"this FBX was not read into a previewable document: {error or type(error).__name__}"
        ) from error


def _as_gltf(scene: Any, path: Path) -> GltfDocument | None:
    """The scene the facts were read from, converted to glTF in memory.

    One decimator then serves every format. A conversion that fails costs the
    preview and nothing else, which is why it answers ``None`` rather than
    raising: the facts have already been read and the verdict does not depend
    on this.
    """
    try:
        return GltfDocument.from_bytes(scene.export(file_type="glb"), source=path.as_posix())
    except Exception:  # a preview is optional by construction (D7)
        return None


__all__ = ["GLTF_FORMATS", "TrimeshInspector"]
