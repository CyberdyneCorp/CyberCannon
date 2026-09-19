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

A fourth asset, `characters/quad_scout`, is written only by
:func:`write_quad_scout`, and it is written **four times** — GLB, glTF, FBX and
OBJ — from one `asset.yaml`, carrying the same object name, the same socket, the
same material and the same three clips wherever the container can hold them.
That is what task 7.5 compares: one contract, one asset, every supported format,
so a difference between two reports is a difference between two *formats* rather
than between two assets. It is opt-in because the three assets above are what
every other suite counts, and a format comparison should not silently change
what `canon index` reports to everybody else.

The project configuration exercises every field `.canon/project.yaml` carries,
including the per-rule severity table and the preview settings, so a test can
assert that a default declared once reaches both the validator and the compiled
briefing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from canon_fixtures import fbx as fbx_fixtures
from canon_fixtures import mesh as fixtures
from canon_fixtures.mesh import ClipExpectation
from cybercanon.domain.mesh_facts import MeshFormat

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

QUAD_SCOUT = """\
schema_version: 1
id: quad_scout
name: Scout Quadruped
status: modeling
owner_art: rafa
design:
  role: fast recon quadruped
  sockets:
    - name: SOCKET_muzzle_l
      purpose: muzzle flash and tracer origin
  states:
    - name: walk
      loop: true
      root_motion: true
    - name: idle
      loop: true
    - name: death
      loop: false
constraints:
  tri_budget: 12000
  rig:
    skeleton: SK_QuadScout
"""

MECH_SPEC = "characters/mech_scout/asset.yaml"
MECH_EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
CRATE_SPEC = "props/crate/asset.yaml"
CRATE_EXPORT = "props/crate/exports/SM_crate_LOD0.obj"
BARREL_SPEC = "props/barrel/asset.yaml"
BARREL_EXPORT = "props/barrel/exports/SM_barrel_LOD0.glb"

QUAD_SPEC = "characters/quad_scout/asset.yaml"
QUAD_EXPORT = "characters/quad_scout/exports/SM_quad_scout_LOD0.fbx"

QUAD_EXPORTS: Mapping[MeshFormat, str] = MappingProxyType(
    {
        fmt: f"characters/quad_scout/exports/SM_quad_scout_LOD0.{fmt.value.lower()}"
        for fmt in (MeshFormat.GLB, MeshFormat.GLTF, MeshFormat.FBX, MeshFormat.OBJ)
    }
)
"""One asset, one specification, one export per supported format."""

QUAD_CLIPS: tuple[ClipExpectation, ...] = (
    ClipExpectation(name="A_quad_scout_walk", duration_s=1.0),
    ClipExpectation(name="A_quad_scout_idle", duration_s=2.0),
    ClipExpectation(name="A_quad_scout_death", duration_s=0.5, loop_closed=False),
)
"""The three clips the specification's states resolve to, written into every
container that can hold one. Same names, same durations — so a rule that reads
them either reaches the same verdict in two formats or the difference is the
format's, which is the whole question 7.5 asks."""

QUAD_OBJECT = "SM_quad_scout_LOD0"
QUAD_MATERIAL = "M_quad_scout"

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


def write_quad_scout(root: Path) -> Mapping[MeshFormat, fixtures.ExportFacts]:
    """Add the four-format asset to an existing repository, with its specification.

    Separate from :func:`build_game_repo` on purpose: every other suite counts
    the three assets that builder writes.

    OBJ carries none of the clips, the socket or the skeleton — that is the
    point of including it, since the specification demands all three and the
    honest answer is `format.unsuitable_for_asset`, not a quiet pass.
    """
    _write(root / QUAD_SPEC, QUAD_SCOUT)
    return MappingProxyType(
        {
            MeshFormat.GLB: fixtures.write_skinned_glb(
                root / QUAD_EXPORTS[MeshFormat.GLB], asset="quad_scout", clips=QUAD_CLIPS
            ),
            MeshFormat.GLTF: fixtures.write_skinned_gltf(
                root / QUAD_EXPORTS[MeshFormat.GLTF], asset="quad_scout", clips=QUAD_CLIPS
            ),
            MeshFormat.FBX: fbx_fixtures.write_skinned_fbx(
                root / QUAD_EXPORTS[MeshFormat.FBX], asset="quad_scout", clips=QUAD_CLIPS
            ),
            MeshFormat.OBJ: fixtures.write_static_obj(
                root / QUAD_EXPORTS[MeshFormat.OBJ],
                name=QUAD_OBJECT,
                material=QUAD_MATERIAL,
            ),
        }
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
    "QUAD_CLIPS",
    "QUAD_EXPORT",
    "QUAD_EXPORTS",
    "QUAD_MATERIAL",
    "QUAD_OBJECT",
    "QUAD_SPEC",
    "GameRepo",
    "build_game_repo",
    "write_quad_scout",
]
