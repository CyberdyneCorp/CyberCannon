"""Tasks 3.1-3.4 — the two traceability gates, the pending list, the report.

These run on every `just check`, over the real spec deltas, the real generated
features and the real step modules. The gate *logic* is unit tested against
hand-built specs in `tests/tooling/test_traceability_gates.py`; what this module
adds is the verdict on this repository as it stands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_bdd import generator, implemented, pending, traceability
from canon_bdd.specs import CapabilitySpec
from canon_bdd.traceability import ScenarioStatus


@pytest.fixture(scope="session")
def specs(repo_root: Path) -> tuple[CapabilitySpec, ...]:
    return generator.load_specs(repo_root)


@pytest.fixture(scope="session")
def pending_entries(repo_root: Path) -> tuple[pending.PendingEntry, ...]:
    return pending.load(repo_root / pending.PENDING_PATH)


@pytest.fixture(scope="session")
def statuses(
    repo_root: Path,
    specs: tuple[CapabilitySpec, ...],
    pending_entries: tuple[pending.PendingEntry, ...],
) -> tuple[ScenarioStatus, ...]:
    bindings = implemented.discover(repo_root / implemented.STEPS_DIR)
    return traceability.classify(specs, bindings, pending_entries)


@pytest.fixture(scope="session")
def report(repo_root: Path) -> Path:
    """Task 3.4 — written by canon_bdd.plugin once collection is complete."""
    return repo_root / traceability.REPORT_PATH


def test_every_requirement_has_an_executing_scenario(
    specs: tuple[CapabilitySpec, ...], statuses: tuple[ScenarioStatus, ...]
) -> None:
    """Gate one (D3): a requirement nobody verified fails the build."""
    failures = traceability.unverified_requirements(specs, statuses)
    assert not failures, _message(
        "requirement(s) with no scenario that executes and none excused", failures
    )


def test_every_generated_scenario_has_a_step_definition(
    statuses: tuple[ScenarioStatus, ...],
) -> None:
    """Gate two (D3): a spec that moved ahead of the code fails the build."""
    failures = traceability.missing_step_definitions(statuses)
    assert not failures, _message(
        "generated scenario(s) with no step definition and no pending entry", failures
    )


def test_the_pending_list_stays_honest(
    statuses: tuple[ScenarioStatus, ...], pending_entries: tuple[pending.PendingEntry, ...]
) -> None:
    """The escape hatch only ever shrinks: no stale lines, no redundant ones."""
    problems = traceability.pending_list_problems(statuses, pending_entries)
    assert not problems, _message("problem(s) in the pending list", problems)


def test_the_report_is_written(report: Path, statuses: tuple[ScenarioStatus, ...]) -> None:
    """Task 3.4 — the pending count is a live progress measure, not a rumour."""
    assert report.is_file(), f"{traceability.REPORT_PATH} is written on every `just check`"
    text = report.read_text(encoding="utf-8")
    assert text.startswith("# BDD traceability")
    assert traceability.summary_line(statuses) in text
    for row in traceability.counts(statuses):
        assert f"| {row.change} | {row.capability} |" in text


def test_every_spec_scenario_reaches_the_report(
    specs: tuple[CapabilitySpec, ...], statuses: tuple[ScenarioStatus, ...]
) -> None:
    """No scenario is dropped between the spec, the feature and the report."""
    expected = sum(len(spec.scenarios) for spec in specs)
    counted = sum(row.total for row in traceability.counts(statuses))
    assert counted == expected == len(statuses)


def _message(headline: str, failures: tuple[str, ...]) -> str:
    listed = "\n".join(f"  - {failure}" for failure in failures)
    return f"{len(failures)} {headline}:\n{listed}"
