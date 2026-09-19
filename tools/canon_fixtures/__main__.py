"""Write every export fixture to a directory, so a person can open them.

The fixtures are built from code at test time and nothing binary lives in git,
which is the right trade for review — but it leaves nobody able to *look* at
one. This is that escape hatch: `just fixtures <dir>` writes the same files the
suites use, and the facts each one declares, so a fixture can be opened in
Blender or diffed against a real export when its reader is in doubt.
"""

from __future__ import annotations

import sys
from pathlib import Path

from canon_fixtures import fbx, mesh

WRITERS = (
    ("SM_mech_scout_LOD0.glb", mesh.write_skinned_glb),
    ("SM_mech_scout_LOD0.gltf", mesh.write_skinned_gltf),
    ("SM_mech_scout_rig_LOD0.glb", mesh.write_rigged_glb),
    ("SM_crate_LOD0.glb", mesh.write_static_glb),
    ("SM_crate_LOD0.obj", mesh.write_static_obj),
    ("SM_mech_scout_parts_LOD0.obj", mesh.write_multipart_obj),
    ("SM_quad_scout_LOD0.fbx", fbx.write_skinned_fbx),
    ("SM_crate_LOD0.fbx", fbx.write_static_fbx),
)


def main(arguments: list[str]) -> int:
    if not arguments:
        print("usage: python -m canon_fixtures <directory>", file=sys.stderr)
        return 2
    directory = Path(arguments[0])
    for name, write in WRITERS:
        path = directory / name
        facts = write(path)
        print(f"{path}  {path.stat().st_size:>8} bytes  {_describe(facts)}")
    return 0


def _describe(facts: mesh.ExportFacts) -> str:
    clips = ", ".join(f"{clip.name}={clip.duration_s}s" for clip in facts.clips) or "no clips"
    return f"{facts.triangles} triangles, {facts.bone_count} bones, {clips}"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
