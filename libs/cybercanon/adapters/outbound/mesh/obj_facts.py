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

**One loader, `split_objects=True`.** `trimesh`'s OBJ loader defaults to
`split_objects=False`, which merges every `o` group into one geometry named
after the first — so a body and a shoulder come back as a body, with the right
triangle total and the wrong part list. An annotation anchored to the lost name
would not orphan; it would resolve against the part that survived and land on
the wrong geometry, which is precisely the silent mis-placement the dual-anchor
design exists to prevent. The load is therefore done once, here, by
:func:`load_scene`, and the preview converter uses that same scene: two call
sites with two sets of options are two readings of one file, and they disagree
exactly when it matters.
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
    return facts_of(load_scene(path))


def facts_of(scene: Any) -> MeshFacts:
    """The same four facts, from a scene already loaded — the preview shares it."""
    geometries = _geometries(scene)
    return facts_for(
        MeshFormat.OBJ,
        triangles=sum(len(mesh.faces) for _, mesh in geometries),
        objects=tuple(name for name, _ in geometries),
        materials=_materials(geometries),
        uv_sets=max((_uv_sets(mesh) for _, mesh in geometries), default=0),
    )


def load_scene(path: str | Path) -> Any:
    """The one OBJ read in this adapter: every `o` group kept, nothing processed.

    `process=False` because merging vertices would change the triangle count the
    budget rule is decided on; `split_objects=True` because the default merges
    named groups and a merged group is an unanchorable part.
    """
    try:
        return trimesh.load(
            str(path), file_type="obj", process=False, force="scene", split_objects=True
        )
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


__all__ = ["ObjUnreadable", "facts_of", "load_scene", "read_facts"]
