"""Task 7.5 — one asset, every supported format, rule by rule.

A wrong capability row is quieter than a wrong violation: a fact marked
unavailable that the format does carry means a rule that should have failed is
reported as *not evaluated* instead, and a rule that fell out of the report
altogether reads to a human as "fine". So the property asserted here is
arithmetic — **every** registered rule appears in exactly one of a report's
three lists, in every format — and it is asserted over one asset.

*One* asset is the point. `characters/quad_scout` is a single `asset.yaml`
declaring a socket, three animated states and a rig budget, exported four times
by `game_repo.write_quad_scout`: GLB, glTF, FBX and OBJ, with the same object
name, the same socket, the same material and the same three clips wherever the
container can hold one. A difference between two of these reports is therefore a
difference between two *formats*, never between two assets — which is what makes
the comparison worth running at all.

What the four runs say, and what each assertion below would catch:

| | glTF / GLB | FBX | OBJ |
|---|---|---|---|
| rules evaluated | 15 of 15 | 10 of 15 | 4 of 15 |
| suppressed | none | scale, transforms, clip rate, root motion, loop | all but four |
| verdict | passing | passing | **failing** — `format.unsuitable_for_asset` |

The split is not spelled out by hand: it is recomputed from the capability
matrix and the facts each rule declares it consumes, so widening a row without
teaching a reader to read that fact moves a rule from the suppressed list into
`passed` and fails here. And where two formats both evaluate a rule they must
reach the same verdict, because they are looking at the same asset.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from game_repo import (
    CRATE_EXPORT,
    CRATE_SPEC,
    QUAD_EXPORTS,
    QUAD_SPEC,
    GameRepo,
    build_game_repo,
    write_quad_scout,
)

from cybercanon.adapters.wiring.build import build_container
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.errors import OperationFailed
from cybercanon.domain.format_matrix import ContentKind, available_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.report import Report
from cybercanon.domain.rules import REGISTRY, RULE_IDS, animation, conventions, format_fitness
from cybercanon.domain.violations import Severity

pytestmark = pytest.mark.integration

SUPPORTED = tuple(QUAD_EXPORTS)
UNSUPPORTED_EXPORT = "characters/quad_scout/exports/SM_quad_scout_LOD0.blend"


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> GameRepo:
    built = build_game_repo(tmp_path_factory.mktemp("formats"))
    write_quad_scout(built.root)
    return built


@pytest.fixture(scope="module")
def container(repo: GameRepo) -> Container:
    return build_container(repo.root)


@pytest.fixture(scope="module")
def reports(container: Container) -> dict[MeshFormat, Report]:
    """The same asset, validated once per supported format."""
    return {fmt: container.validate_export(export).report for fmt, export in QUAD_EXPORTS.items()}


def _accounted_for(report: Report) -> set[str]:
    return (
        set(report.passed_rules)
        | {violation.rule_id for violation in report.violations}
        | {entry.rule_id for entry in report.not_evaluated}
    )


def _evaluated(report: Report) -> set[str]:
    """The rules that actually ran — passed or violated, never suppressed."""
    return set(report.passed_rules) | {violation.rule_id for violation in report.violations}


def _verdicts(report: Report) -> dict[str, bool]:
    """Rule id to "it passed", for the rules this format could evaluate."""
    violated = {violation.rule_id for violation in report.violations}
    return {rule_id: rule_id not in violated for rule_id in _evaluated(report)}


def _predicted_evaluable(source_format: MeshFormat) -> set[str]:
    """Which rules the matrix says this format can answer, from the table alone."""
    readable = available_for(source_format)
    return {rule.rule_id for rule in REGISTRY if rule.consumes <= readable}


# --------------------------------------------------------------------------
# No rule silently disappears from a report
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source_format", SUPPORTED)
def test_every_rule_is_accounted_for_in_every_format(
    reports: dict[MeshFormat, Report], source_format: MeshFormat
) -> None:
    """Passed, violated or not evaluated — a rule is never simply absent.

    This is the whole exercise: a rule missing from a report reads as "fine".
    """
    missing = set(RULE_IDS) - _accounted_for(reports[source_format])

    assert not missing, f"{source_format}: {sorted(missing)} disappeared from the report"


@pytest.mark.parametrize("source_format", SUPPORTED)
def test_a_rule_is_never_in_two_lists_at_once(
    reports: dict[MeshFormat, Report], source_format: MeshFormat
) -> None:
    """Exactly one of the three, so "accounted for" cannot be bought twice."""
    report = reports[source_format]
    suppressed = {entry.rule_id for entry in report.not_evaluated}

    assert not suppressed & _evaluated(report)
    assert len(report.passed_rules) == len(set(report.passed_rules))


@pytest.mark.parametrize("source_format", SUPPORTED)
def test_coverage_is_exactly_what_the_capability_matrix_predicts(
    reports: dict[MeshFormat, Report], source_format: MeshFormat
) -> None:
    """The report and the table are pinned to each other, in both directions.

    Widening a row without teaching a reader to read that fact moves a rule out
    of the suppressed list and into `passed` — a rule that now reports "fine"
    about a fact nobody read — and that shows up here rather than in a viewer.
    """
    report = reports[source_format]
    predicted = _predicted_evaluable(source_format)

    assert _evaluated(report) == predicted
    assert {entry.rule_id for entry in report.not_evaluated} == set(RULE_IDS) - predicted


@pytest.mark.parametrize("source_format", SUPPORTED)
def test_every_suppressed_rule_says_why(
    reports: dict[MeshFormat, Report], source_format: MeshFormat
) -> None:
    """A suppressed rule with no reason is a count, and a count hides a row."""
    for entry in reports[source_format].not_evaluated:
        assert entry.reason
        assert str(source_format) in entry.reason


# --------------------------------------------------------------------------
# Comparing coverage: one contract, four containers
# --------------------------------------------------------------------------


def test_every_export_is_governed_by_the_same_specification(container: Container) -> None:
    """Otherwise this compares two assets and calls the difference a format."""
    assert {container.discover(export) for export in QUAD_EXPORTS.values()} == {QUAD_SPEC}


def test_the_two_gltf_containers_report_identically(reports: dict[MeshFormat, Report]) -> None:
    """GLB and glTF are one matrix row and one code path; the same export, twice."""
    glb, gltf = reports[MeshFormat.GLB], reports[MeshFormat.GLTF]

    assert _verdicts(glb) == _verdicts(gltf)
    assert glb.not_evaluated == () == gltf.not_evaluated
    assert glb.outcome == gltf.outcome


@pytest.mark.parametrize("source_format", [MeshFormat.FBX, MeshFormat.OBJ])
def test_a_narrower_format_never_contradicts_a_wider_one(
    reports: dict[MeshFormat, Report], source_format: MeshFormat
) -> None:
    """Where both formats could evaluate a rule, they must agree about the asset.

    glTF answers every fact, so it is the reference. A narrower format may say
    less; it may not say something *else*, and a per-format normalisation bug —
    a bone count read from the wrong record, a socket taken for an armature
    holder — would show up here as a disagreement about one shared rule.
    """
    reference = _verdicts(reports[MeshFormat.GLB])
    narrower = _verdicts(reports[source_format])

    shared = set(narrower) & set(reference) - {format_fitness.UNSUITABLE_FORMAT}
    assert shared
    assert {rule: narrower[rule] for rule in shared} == {rule: reference[rule] for rule in shared}


def test_coverage_narrows_monotonically_from_gltf_to_fbx_to_obj(
    reports: dict[MeshFormat, Report],
) -> None:
    """The comparison stated as one chain, so a widened row is visible as a shape."""
    evaluated = {fmt: _evaluated(reports[fmt]) for fmt in SUPPORTED}

    assert evaluated[MeshFormat.OBJ] < evaluated[MeshFormat.FBX] < evaluated[MeshFormat.GLB]
    assert evaluated[MeshFormat.GLB] == set(RULE_IDS)


# --------------------------------------------------------------------------
# What each narrower format says, and why
# --------------------------------------------------------------------------


def test_fbx_suppresses_exactly_the_facts_it_cannot_be_trusted_for(
    reports: dict[MeshFormat, Report],
) -> None:
    """The matrix row, asserted through a whole validation run rather than read.

    A row someone widened would show up here as a rule that moved out of the
    not-evaluated list and into `passed` without anyone looking at the file.
    """
    report = reports[MeshFormat.FBX]
    suppressed = {entry.rule_id for entry in report.not_evaluated}

    assert suppressed == {
        conventions.UNIT_SCALE,
        conventions.TRANSFORMS,
        animation.FRAME_RATE,
        animation.ROOT_MOTION,
        animation.LOOP,
    }
    assert all("this reader can trust" in entry.reason for entry in report.not_evaluated), (
        "an FBX records these facts; what it cannot do is record them dependably"
    )
    assert report.passed


def test_obj_refuses_the_asset_rather_than_passing_it_quietly(
    reports: dict[MeshFormat, Report],
) -> None:
    """Cannot *observe* is not evaluated; cannot *contain* is an error (D13).

    The same specification that GLB satisfies can never be satisfied by an OBJ,
    and saying so here is strictly kinder than saying it at integration.
    """
    report = reports[MeshFormat.OBJ]
    unsuitable = [v for v in report.violations if v.rule_id == format_fitness.UNSUITABLE_FORMAT]

    assert not report.passed
    assert {violation.subject for violation in unsuitable} == {str(kind) for kind in ContentKind}
    assert {violation.severity for violation in unsuitable} == {Severity.ERROR}


def test_obj_evaluates_the_four_facts_it_can_and_names_the_rest(
    reports: dict[MeshFormat, Report],
) -> None:
    """A static prop's whole contract is triangles, names and materials — and OBJ
    answers those. Everything else is listed by name, never collapsed."""
    report = reports[MeshFormat.OBJ]

    assert len(report.not_evaluated) == len(RULE_IDS) - len(_evaluated(report))
    assert all("this reader can trust" not in entry.reason for entry in report.not_evaluated), (
        "OBJ does not record these at all; that is a different sentence"
    )


def test_a_format_with_no_row_is_refused_rather_than_partly_reported(
    container: Container, repo: GameRepo
) -> None:
    """A format the matrix does not cover produces no report at all, by design.

    The alternative is the failure this whole file exists to catch, at its
    worst: a report in which *every* rule silently went missing.
    """
    (repo.root / UNSUPPORTED_EXPORT).write_bytes(b"BLENDER-v500")

    with pytest.raises(OperationFailed) as refused:
        container.validate_export(UNSUPPORTED_EXPORT)

    assert "blend" in refused.value.message
    assert UNSUPPORTED_EXPORT in str(refused.value.subject)


def test_the_comparison_is_not_an_artifact_of_one_asset(container: Container) -> None:
    """A second OBJ asset, with a static contract, reaches the opposite verdict.

    Same format, same rules, different specification: OBJ is not "the format
    that fails", it is the format that answers four facts.
    """
    report = container.validate_export(CRATE_EXPORT).report

    assert container.discover(CRATE_EXPORT) == CRATE_SPEC
    assert Path(CRATE_EXPORT).suffix == ".obj"
    assert report.passed
    suppressed = {entry.rule_id for entry in report.not_evaluated}
    assert suppressed == set(RULE_IDS) - _predicted_evaluable(MeshFormat.OBJ)
