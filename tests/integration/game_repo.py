"""A game repository, written from code — what `canon` is pointed at.

Nothing binary lives in git, so the exports here are produced by
`tools/canon_fixtures` at test time and the specification files are written
beside them. Three assets, each carrying a different question:

* `characters/mech_scout` — skinned and animated, GLB, and **clean**: the worked
  case where every rule the format can evaluate passes.
* `props/crate` — static, **OBJ**: the format that records triangles, names,
  materials and UV sets and nothing else, so a run over it must list every
  suppressed rule by name (D13).
* `props/barrel` — static, GLB, **over its triangle budget**: the failing
  verdict a pre-commit hook blocks a commit over.

The project configuration exercises every field `.canon/project.yaml` carries,
including the per-rule severity table and the preview settings, so a test can
assert that a default declared once reaches both the validator and the compiled
briefing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from canon_fixtures import mesh as fixtures

PROJECT_CONFIG = """\
schema_version: 1
name: Ronin
engine_content_root: Content/Ronin
golden_rules:
  - The silhouette reads at 25 m before any detail does.
defaults:
  up_axis: Y
  unit_scale: 1.0
  naming: "SM_{asset}_LOD{n}"
  pivot: feet centre
  animation:
    frame_rate: 30
    clip_naming: "A_{asset}_{state}"
  rig:
    max_bones: 64
severity:
  naming.pattern_mismatch: warning
preview:
  ratio: 0.25
  ceiling: 20000
"""

MECH_SCOUT = """\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
owner_art: rafa
owner_design: dani
owner_code: leo
concept:
  silhouette_rules:
    - One asymmetric shoulder reads as the scout's front.
design:
  role: fast recon walker
  read_distance_m: 25
  sockets:
    - name: SOCKET_muzzle_l
      purpose: muzzle flash and tracer origin
  states:
    - name: walk
      loop: true
      root_motion: true
    - name: fire
      loop: false
constraints:
  tri_budget: 12000
  rig:
    skeleton: SK_MechScout
"""

CRATE = """\
schema_version: 1
id: crate
name: Supply Crate
status: modeling
constraints:
  tri_budget: 12000
"""

BARREL = """\
schema_version: 1
id: barrel
name: Fuel Barrel
status: modeling
constraints:
  tri_budget: 100
"""

MECH_SPEC = "characters/mech_scout/asset.yaml"
MECH_EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
CRATE_SPEC = "props/crate/asset.yaml"
CRATE_EXPORT = "props/crate/exports/SM_crate_LOD0.obj"
BARREL_SPEC = "props/barrel/asset.yaml"
BARREL_EXPORT = "props/barrel/exports/SM_barrel_LOD0.glb"

BARREL_BUDGET = 100


@dataclass(frozen=True)
class GameRepo:
    """A working copy `canon` can be run inside, and the facts its exports carry."""

    root: Path
    mech: fixtures.ExportFacts
    crate: fixtures.ExportFacts
    barrel: fixtures.ExportFacts

    def path(self, relative: str) -> Path:
        return self.root / relative


def build_game_repo(root: Path, *, with_project_config: bool = True) -> GameRepo:
    """Write the repository, its specifications and its exports under `root`."""
    (root / ".git").mkdir(parents=True, exist_ok=True)
    if with_project_config:
        _write(root / ".canon/project.yaml", PROJECT_CONFIG)
    _write(root / MECH_SPEC, MECH_SCOUT)
    _write(root / CRATE_SPEC, CRATE)
    _write(root / BARREL_SPEC, BARREL)
    return GameRepo(
        root=root,
        mech=fixtures.write_skinned_glb(root / MECH_EXPORT),
        crate=fixtures.write_static_obj(root / CRATE_EXPORT, name="SM_crate_LOD0"),
        barrel=fixtures.write_static_glb(root / BARREL_EXPORT, name="SM_barrel_LOD0"),
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


__all__ = [
    "BARREL_BUDGET",
    "BARREL_EXPORT",
    "BARREL_SPEC",
    "CRATE_EXPORT",
    "CRATE_SPEC",
    "MECH_EXPORT",
    "MECH_SPEC",
    "PROJECT_CONFIG",
    "GameRepo",
    "build_game_repo",
]
