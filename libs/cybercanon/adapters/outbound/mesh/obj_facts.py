"""OBJ, read into `MeshFacts` — four facts, and deliberately no more.

OBJ is the format the matrix narrows hardest (D13), and the narrowing is the
honest part: an OBJ file records triangles, object names, material names and UV
sets, and records *nothing* about unit scale, up axis, applied transforms,
sockets, skinning or animation. An OBJ export may well be correctly scaled, so
claiming otherwise in either direction would be a lie; the rules that need those
facts report NOT EVALUATED instead.

That is why this module sets exactly the four fields OBJ's matrix row allows:
`MeshFacts` refuses a value for an unavailable fact, so a reader that drifted
here would fail loudly rather than quietly widen the format's coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import trimesh

from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFacts, MeshFormat


class ObjUnreadable(ValueError):
    """The file is not a readable OBJ."""


def read_facts(path: str | Path) -> MeshFacts:
    """The four facts an OBJ can answer for, and nothing invented around them."""
    scene = _load(path)
    geometries = _geometries(scene)
    return facts_for(
        MeshFormat.OBJ,
        triangles=sum(len(mesh.faces) for _, mesh in geometries),
        objects=tuple(name for name, _ in geometries),
        materials=_materials(geometries),
        uv_sets=max((_uv_sets(mesh) for _, mesh in geometries), default=0),
    )


def _load(path: str | Path) -> Any:
    """Load without processing: merging vertices would change the triangle count."""
    try:
        return trimesh.load(str(path), file_type="obj", process=False, force="scene")
    except Exception as error:  # trimesh raises whatever its parsers raise
        raise ObjUnreadable(str(error) or type(error).__name__) from error


def _geometries(scene: Any) -> tuple[tuple[str, Any], ...]:
    """Named meshes, in a deterministic order, skipping anything without faces."""
    geometries = getattr(scene, "geometry", None) or {}
    return tuple(
        (name, mesh) for name, mesh in sorted(geometries.items()) if hasattr(mesh, "faces")
    )


def _materials(geometries: tuple[tuple[str, Any], ...]) -> tuple[str, ...]:
    """Material names from the companion `.mtl`, deduplicated in first-seen order."""
    names: list[str] = []
    for _, mesh in geometries:
        name = getattr(getattr(mesh, "visual", None), "material", None)
        label = getattr(name, "name", None)
        if label and label not in names:
            names.append(str(label))
    return tuple(names)


def _uv_sets(mesh: Any) -> int:
    """OBJ carries at most one UV set, and only when the file actually has one."""
    uv = getattr(getattr(mesh, "visual", None), "uv", None)
    return 1 if uv is not None and len(uv) else 0


__all__ = ["ObjUnreadable", "read_facts"]
