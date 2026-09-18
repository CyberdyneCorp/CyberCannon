"""Task 5.7 — what an OBJ export actually reports, end to end.

This is D13 in one file. OBJ is the format the matrix narrows hardest, and the
two outcomes it produces are deliberately different things:

* **cannot contain** — an asset that requires clips, a skeleton or sockets can
  never be satisfied by an OBJ, so `format.unsuitable_for_asset` is an ordinary
  error with an obvious fix (re-export), raised early rather than at integration;
* **cannot observe** — a static prop's OBJ is a perfectly good export, and the
  rules that need a unit scale, an up axis, sockets, a rig or a clip report NOT
  EVALUATED rather than passing. A validator that silently passed those would be
  lying about its coverage, which is worse than refusing the format.

The whole path runs here — `GitSpecStore`, `TrimeshInspector`, the domain rule
registry — because the point is what a person sees, not what one layer returns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.git.discovery import GIT_DIR
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.rules import animation, budgets, conventions, format_fitness, rig, sockets

pytestmark = pytest.mark.integration

CRATE_SPEC = "props/crate/asset.yaml"
CRATE_OBJ = "props/crate/exports/SM_crate_LOD0.obj"
MECH_SPEC = "characters/mech_scout/asset.yaml"
MECH_OBJ = "characters/mech_scout/exports/SM_mech_scout_LOD0.obj"

STATIC_YAML = """\
schema_version: 1
id: crate
name: Supply Crate
status: modeling
constraints:
  tri_budget: 800
  naming: "SM_{asset}_LOD{n}"
"""

ANIMATED_YAML = """\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
design:
  sockets:
    - name: SOCKET_muzzle_l
      purpose: muzzle flash
  states:
    - name: walk
constraints:
  tri_budget: 12000
  naming: "SM_{asset}_LOD{n}"
  rig:
    skeleton: SK_MechScout
    max_bones: 96
    skinned: true
  animation:
    frame_rate: 30
    clip_naming: "A_{asset}_{state}"
"""

SUPPRESSED_ON_OBJ = (
    conventions.UNIT_SCALE,
    conventions.UP_AXIS,
    conventions.TRANSFORMS,
    sockets.SOCKET_MISSING,
    rig.BONE_BUDGET,
    rig.NOT_SKINNED,
    animation.CLIP_MISSING,
    animation.FRAME_RATE,
    animation.DURATION,
    animation.ROOT_MOTION,
    animation.LOOP,
)
"""Every rule an OBJ cannot answer for — listed by name, never as a count."""


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    (tmp_path / GIT_DIR).mkdir(parents=True, exist_ok=True)
    for path, content in ((CRATE_SPEC, STATIC_YAML), (MECH_SPEC, ANIMATED_YAML)):
        written = tmp_path / path
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(content, encoding="utf-8")
    fixtures.write_static_obj(tmp_path / CRATE_OBJ)
    fixtures.write_static_obj(tmp_path / MECH_OBJ, name="SM_mech_scout_LOD0")
    return tmp_path


def _validate(repository: Path, export: str):
    return validate_export(
        export,
        spec_store=GitSpecStore(repository),
        mesh_inspector=TrimeshInspector(root=repository),
    )


# --------------------------------------------------------------------------
# An animated asset exported as OBJ
# --------------------------------------------------------------------------


def test_an_obj_export_of_an_animated_asset_is_reported_as_unsuitable(repository: Path) -> None:
    report = _validate(repository, MECH_OBJ).report

    violations = report.violations_of(format_fitness.UNSUITABLE_FORMAT)
    assert violations, "an OBJ cannot hold clips, a skeleton or sockets"
    assert all(violation.is_error for violation in violations)
    assert not report.passed


def test_the_unsuitable_format_message_names_the_format_and_the_requirement(
    repository: Path,
) -> None:
    """The fix is a re-export, so the message has to say what was required."""
    violation = _validate(repository, MECH_OBJ).report.violations_of(
        format_fitness.UNSUITABLE_FORMAT
    )[0]

    assert "OBJ" in violation.message
    assert violation.observed is not None


# --------------------------------------------------------------------------
# A static asset exported as OBJ
# --------------------------------------------------------------------------


def test_an_obj_export_of_a_static_asset_reports_the_rules_it_can_answer(
    repository: Path,
) -> None:
    report = _validate(repository, CRATE_OBJ).report

    assert report.export_format is MeshFormat.OBJ
    assert report.evaluated(budgets.TRI_BUDGET), "OBJ records a triangle count"
    assert report.evaluated(conventions.NAMING), "OBJ records object names"
    over_budget = report.violations_of(budgets.TRI_BUDGET)
    assert over_budget, "the fixture's triangle count is over the declared budget"
    assert over_budget[0].expected is not None and over_budget[0].observed is not None
    assert report.violations_of(conventions.NAMING) == (), "SM_crate_LOD0 matches the pattern"


def test_the_material_names_in_the_obj_are_read_rather_than_skipped(repository: Path) -> None:
    """No rule consumes materials yet; the fact is still read, so one can."""
    facts = TrimeshInspector(root=repository).inspect(CRATE_OBJ).facts

    assert facts.materials == ("M_Crate",)
    assert facts.uv_sets == 1


def test_every_rule_an_obj_cannot_answer_is_listed_by_name(repository: Path) -> None:
    """Not evaluated is never collapsed into a count: suppression stays visible."""
    report = _validate(repository, CRATE_OBJ).report

    suppressed = {entry.rule_id for entry in report.not_evaluated}
    assert set(SUPPRESSED_ON_OBJ) <= suppressed, sorted(set(SUPPRESSED_ON_OBJ) - suppressed)


def test_a_suppressed_rule_says_which_fact_the_format_lacks(repository: Path) -> None:
    report = _validate(repository, CRATE_OBJ).report

    entry = report.not_evaluated_rule(conventions.UNIT_SCALE)
    assert entry is not None
    assert "OBJ" in entry.reason
    assert entry.missing_fact is not None


def test_no_rule_disappears_from_an_obj_report(repository: Path) -> None:
    """Every registered rule is accounted for: passed, violated or not evaluated."""
    from cybercanon.domain.rules import RULE_IDS

    report = _validate(repository, CRATE_OBJ).report

    accounted = (
        set(report.passed_rules)
        | {violation.rule_id for violation in report.violations}
        | {entry.rule_id for entry in report.not_evaluated}
    )
    assert set(RULE_IDS) <= accounted, sorted(set(RULE_IDS) - accounted)
