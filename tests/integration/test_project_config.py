"""Task 7.1 — `.canon/project.yaml`, and the defaults reaching both consumers.

A project default is only worth declaring if the thing that enforces the rule
and the thing a person reads agree about it. Both come from the same
`EffectiveSpec` (D3), so what is asserted here is that one line in the project
file reaches the **validator** and the **compiled briefing** without either
re-deriving it — a bone budget declared once fails an over-budget export *and*
appears in `art-spec.md` as an effective value.

The three fields that are not constraints are checked here too, because each
would otherwise be decoration: the engine content root the project publishes,
the per-rule severity table that lets a project lower a noisy rule without
editing it, and the decimation settings preview emission aims for.

The specification files and the project file are read by the **real**
`GitSpecStore`; the mesh facts are hand-built, because a rule's input is
`MeshFacts` and no file on disk is needed to state one (D1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.wiring.build import preview_settings
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.domain.effective_spec import merge
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import ClipFacts, MeshFormat
from cybercanon.domain.rules import conventions, rig
from cybercanon.domain.violations import Severity

pytestmark = pytest.mark.integration

SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

PROJECT = """\
schema_version: 1
name: Ronin
engine_content_root: Content/Ronin
golden_rules:
  - The silhouette reads at 25 m.
defaults:
  up_axis: Y
  unit_scale: 1.0
  naming: "SM_{asset}_LOD{n}"
  animation:
    frame_rate: 30
    clip_naming: "A_{asset}_{state}"
  rig:
    max_bones: 64
severity:
  naming.pattern_mismatch: warning
preview:
  ratio: 0.5
  ceiling: 5000
"""

ASSET = """\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
design:
  states:
    - name: walk
constraints:
  tri_budget: 12000
  rig:
    skeleton: SK_MechScout
"""


WALK_CLIP = ClipFacts(
    name="A_mech_scout_walk",
    frames=30,
    duration_s=1.0,
    frame_rate=30.0,
    has_root_motion=True,
    loop_closed=True,
)


def _facts(**observed: object) -> object:
    defaults: dict[str, object] = {
        "triangles": 9000,
        "objects": ("SM_mech_scout_LOD0",),
        "transforms_applied": True,
        "unit_scale": 1.0,
        "up_axis": "Y",
        "uv_sets": 1,
        "materials": ("M_mech_scout",),
        "empties": (),
        "clips": (WALK_CLIP,),
        "frame_rate": 30.0,
        "is_skinned": True,
        "bone_count": 12,
    }
    return facts_for(MeshFormat.GLB, **{**defaults, **observed})


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("configured")
    (root / ".git").mkdir()
    (root / ".canon").mkdir()
    (root / ".canon/project.yaml").write_text(PROJECT, encoding="utf-8")
    (root / SPEC_PATH).parent.mkdir(parents=True)
    (root / SPEC_PATH).write_text(ASSET, encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def store(repo: Path) -> GitSpecStore:
    return GitSpecStore(repo)


def _container(store: GitSpecStore, **observed: object) -> Container:
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, _facts(**observed))
    return Container(spec_store=store, mesh_inspector=inspector)


# --------------------------------------------------------------------------
# The file is read
# --------------------------------------------------------------------------


def test_every_declared_default_is_read(store: GitSpecStore) -> None:
    project = store.load_project("")

    assert project.name == "Ronin"
    assert project.engine_content_root == "Content/Ronin"
    assert project.golden_rules == ("The silhouette reads at 25 m.",)
    assert project.defaults is not None
    assert project.defaults.naming == "SM_{asset}_LOD{n}"
    assert project.defaults.rig is not None
    assert project.defaults.rig.max_bones == 64


def test_the_severity_table_is_read_as_the_domains_own_vocabulary(
    store: GitSpecStore,
) -> None:
    project = store.load_project("")

    assert project.severities == {conventions.NAMING: Severity.WARNING}
    assert project.severity_for(conventions.NAMING, Severity.ERROR) is Severity.WARNING
    assert project.severity_for(rig.BONE_BUDGET, Severity.ERROR) is Severity.ERROR


def test_the_preview_settings_reach_the_emitter(store: GitSpecStore) -> None:
    """Decimation is configuration, never a rule — and a preview never moves a verdict."""
    settings = preview_settings(store.load_project("").preview)

    assert settings.ratio == 0.5
    assert settings.ceiling == 5000


# --------------------------------------------------------------------------
# … and flows into the merged contract, the validator and the briefing
# --------------------------------------------------------------------------


def test_defaults_the_asset_never_declared_reach_the_effective_spec(
    store: GitSpecStore,
) -> None:
    project = store.load_project(SPEC_PATH)
    spec = merge(store.load(SPEC_PATH).asset, project.defaults)

    assert spec.tri_budget == 12000  # the asset's own
    assert spec.up_axis == "Y"  # the project's
    assert spec.naming == "SM_{asset}_LOD{n}"
    assert spec.max_bones == 64
    assert spec.clip_naming == "A_{asset}_{state}"
    assert spec.frame_rate == 30
    assert [clip.clip_name for clip in spec.required_clips] == ["A_mech_scout_walk"]


def test_a_project_bone_budget_fails_an_export_the_asset_never_constrained(
    store: GitSpecStore,
) -> None:
    outcome = _container(store, bone_count=120).validate_export(EXPORT)

    (violation,) = outcome.report.violations_of(rig.BONE_BUDGET)
    assert violation.expected == "64"
    assert not outcome.passed


def test_the_project_severity_table_lowers_a_rule_without_editing_it(
    store: GitSpecStore,
) -> None:
    """`naming.pattern_mismatch` is an error by default; this project made it advisory."""
    outcome = _container(store, objects=("mech_scout_body",)).validate_export(EXPORT)

    (violation,) = outcome.report.violations_of(conventions.NAMING)
    assert violation.severity is Severity.WARNING
    assert outcome.passed


def test_the_compiled_briefing_states_the_same_effective_values(
    store: GitSpecStore,
) -> None:
    text = _container(store).compile_spec(SPEC_PATH).text

    assert "**Up axis**: Y" in text
    assert "**Bone budget**: 64" in text
    assert "**Clip naming**: `A_{asset}_{state}`" in text
    assert "`walk` — clip `A_mech_scout_walk`" in text


def test_the_project_briefing_carries_the_shared_constraints(store: GitSpecStore) -> None:
    briefing = _container(store).compile_project_briefing()

    assert briefing.project == "Ronin"
    assert "The silhouette reads at 25 m." in briefing.text
    assert "**Bone budget**: 64" in briefing.text


# --------------------------------------------------------------------------
# A project file that got something wrong says so
# --------------------------------------------------------------------------


def test_an_unusable_severity_level_is_reported_rather_than_silently_ignored(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".canon").mkdir()
    (tmp_path / ".canon/project.yaml").write_text(
        "schema_version: 1\nseverity:\n  tri_budget.exceeded: fatal\n", encoding="utf-8"
    )

    project = GitSpecStore(tmp_path).load_project("")

    assert project.severities == {}
    (note,) = project.warnings
    assert "tri_budget.exceeded" in note.subject
    assert "fatal" in note.message
