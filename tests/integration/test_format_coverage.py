"""Task 7.5 (partial) — one asset through each readable format, rule by rule.

A wrong capability row is quieter than a wrong violation: a fact marked
unavailable that the format does carry means a rule that should have failed is
reported as *not evaluated* instead. The defence is arithmetic — **every**
registered rule must appear in exactly one of a report's three lists, in every
format — so a rule cannot vanish from a report without this failing.

Scope, stated honestly: `GLB` and `OBJ` are exercised against real files written
from code. `GLTF` and `FBX` are not, because no fixture writer and no reader
exist for them yet (tasks 5.5 and 5.6). What *is* asserted for the unreadable
format is the only thing that keeps the coverage claim honest: it is refused by
name, as an operation that could not run, never as a report whose rules quietly
went missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from game_repo import CRATE_EXPORT, CRATE_SPEC, MECH_EXPORT, GameRepo, build_game_repo

from cybercanon.adapters.wiring.build import build_container
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.errors import OperationFailed
from cybercanon.domain.report import Report
from cybercanon.domain.rules import RULE_IDS

pytestmark = pytest.mark.integration

READABLE_FORMATS = (MECH_EXPORT, CRATE_EXPORT)
FBX_EXPORT = "props/crate/exports/SM_crate_LOD0.fbx"


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> GameRepo:
    return build_game_repo(tmp_path_factory.mktemp("formats"))


@pytest.fixture(scope="module")
def container(repo: GameRepo) -> Container:
    return build_container(repo.root)


def _report(container: Container, export: str) -> Report:
    return container.validate_export(export).report


def _accounted_for(report: Report) -> set[str]:
    return (
        set(report.passed_rules)
        | {violation.rule_id for violation in report.violations}
        | {entry.rule_id for entry in report.not_evaluated}
    )


@pytest.mark.parametrize("export", READABLE_FORMATS)
def test_every_rule_is_accounted_for_in_every_readable_format(
    container: Container, export: str
) -> None:
    """Passed, violated or not evaluated — a rule is never simply absent."""
    report = _report(container, export)

    missing = set(RULE_IDS) - _accounted_for(report)
    assert not missing, f"{export}: {sorted(missing)} disappeared from the report"


@pytest.mark.parametrize("export", READABLE_FORMATS)
def test_a_rule_is_never_in_two_lists_at_once(container: Container, export: str) -> None:
    report = _report(container, export)
    suppressed = {entry.rule_id for entry in report.not_evaluated}

    assert not suppressed & set(report.passed_rules)
    assert not suppressed & {violation.rule_id for violation in report.violations}


def test_coverage_differs_by_format_and_the_difference_is_stated(
    container: Container,
) -> None:
    """GLB answers everything; OBJ answers four facts and says so about the rest."""
    glb = _report(container, MECH_EXPORT)
    obj = _report(container, CRATE_EXPORT)

    assert glb.not_evaluated == ()
    suppressed = {entry.rule_id for entry in obj.not_evaluated}
    assert suppressed
    assert all(entry.reason for entry in obj.not_evaluated)
    assert suppressed <= set(RULE_IDS)


def test_an_unreadable_format_is_refused_rather_than_partly_reported(
    container: Container, repo: GameRepo
) -> None:
    """No reader for FBX yet (tasks 5.5, 5.6) — and no report pretending otherwise."""
    (repo.root / FBX_EXPORT).write_bytes(b"Kaydara FBX Binary\x00")

    with pytest.raises(OperationFailed) as refused:
        container.validate_export(FBX_EXPORT)

    assert "FBX" in refused.value.message
    assert FBX_EXPORT in str(refused.value.subject)


def test_the_same_specification_governs_every_format(container: Container) -> None:
    """Coverage is compared across formats of the *same* contract, not two contracts."""
    assert container.discover(CRATE_EXPORT) == CRATE_SPEC
    assert Path(CRATE_EXPORT).suffix == ".obj"
