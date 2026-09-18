"""Tasks 3.1-3.4 — the two gates, the pending list, and the report.

D3's gates fail in opposite directions and only both together pin the spec and
the code to each other: coverage alone lets someone write a scenario that
asserts nothing, step-completeness alone lets a requirement carry no scenario.
These tests drive both against hand-built spec fixtures, where the shape under
test can be stated exactly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from spec_repo import ONE_REQUIREMENT, SpecRepo

from canon_bdd import generator, implemented, pending, traceability

SCENARIOLESS_REQUIREMENT = """\
### Requirement: The system SHALL do the unverified thing

Nobody wrote a scenario for this one.

### Requirement: The system SHALL do the thing

#### Scenario: It does the thing
- **GIVEN** a thing
- **WHEN** it is done
- **THEN** it SHALL be done
"""

STEP_MODULE = '''\
"""Steps for thing-capability."""

from pytest_bdd import given, scenario, then, when


@scenario("../features/add-thing/thing-capability.feature", "It does the thing")
def test_it_does_the_thing() -> None:
    """Binds the generated scenario."""


@given("a thing")
def _a_thing() -> int:
    return 1


@when("it is done")
def _it_is_done() -> None: ...


@then("it SHALL be done")
def _it_shall_be_done() -> None: ...
'''


def statuses_for(
    repo: SpecRepo, entries: tuple[pending.PendingEntry, ...] = ()
) -> tuple[traceability.ScenarioStatus, ...]:
    specs = generator.load_specs(repo.root)
    bindings = implemented.discover(repo.root / implemented.STEPS_DIR)
    return traceability.classify(specs, bindings, entries)


def pending_for(*keys: tuple[str, str]) -> tuple[pending.PendingEntry, ...]:
    return tuple(
        pending.PendingEntry(capability=capability, scenario=scenario, line=number)
        for number, (capability, scenario) in enumerate(keys, start=1)
    )


# --------------------------------------------------------------------------
# 3.1 — a requirement with no scenario that executes
# --------------------------------------------------------------------------


def test_a_scenarioless_requirement_fails_gate_one(spec_repo: SpecRepo) -> None:
    path = spec_repo.add("add-thing", "thing-capability", SCENARIOLESS_REQUIREMENT)
    specs = generator.load_specs(spec_repo.root)
    failures = traceability.unverified_requirements(specs, statuses_for(spec_repo))

    unverified = [failure for failure in failures if "unverified thing" in failure]
    assert unverified, failures
    assert str(path.relative_to(spec_repo.root)) in unverified[0]
    assert "carries no scenario at all" in unverified[0]


def test_a_requirement_whose_scenarios_all_execute_passes_gate_one(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    spec_repo.steps("thing-capability", STEP_MODULE)

    specs = generator.load_specs(spec_repo.root)
    statuses = statuses_for(spec_repo)
    assert [status.state for status in statuses] == [traceability.EXECUTING]
    assert traceability.unverified_requirements(specs, statuses) == ()


def test_a_requirement_whose_scenarios_are_all_pending_is_excused(spec_repo: SpecRepo) -> None:
    """Migration: the first run has 657 pending scenarios and a green build."""
    spec_repo.add("add-thing", "thing-capability")
    entries = pending_for(("thing-capability", "It does the thing"))
    specs = generator.load_specs(spec_repo.root)
    statuses = statuses_for(spec_repo, entries)

    assert [status.state for status in statuses] == [traceability.PENDING]
    assert traceability.unverified_requirements(specs, statuses) == ()


# --------------------------------------------------------------------------
# 3.2 — a generated scenario with no step definition, named at its spec line
# --------------------------------------------------------------------------


def test_a_scenario_with_no_step_definition_fails_gate_two(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)

    failures = traceability.missing_step_definitions(statuses_for(spec_repo))
    assert len(failures) == 1
    assert "It does the thing" in failures[0]


def test_the_failure_points_at_the_spec_and_not_at_the_generated_feature(
    spec_repo: SpecRepo,
) -> None:
    path = spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)

    failure = traceability.missing_step_definitions(statuses_for(spec_repo))[0]
    location, _, _ = failure.partition(": ")
    spec_path, _, line = location.rpartition(":")

    assert spec_path == path.relative_to(spec_repo.root).as_posix()
    assert ".feature" not in location
    assert path.read_text(encoding="utf-8").splitlines()[int(line) - 1].startswith("#### Scenario:")


def test_a_bound_scenario_is_not_reported_as_missing(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    spec_repo.steps("thing-capability", STEP_MODULE)

    assert traceability.missing_step_definitions(statuses_for(spec_repo)) == ()


def test_binding_a_whole_feature_covers_every_scenario_in_it(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability", ONE_REQUIREMENT)
    generator.write(spec_repo.root)
    spec_repo.steps(
        "thing-capability",
        "from pytest_bdd import scenarios\n\n"
        'scenarios("../features/add-thing/thing-capability.feature")\n',
    )

    assert [status.state for status in statuses_for(spec_repo)] == [traceability.EXECUTING]


def test_a_binding_in_another_capabilitys_module_still_counts_for_its_own_capability(
    spec_repo: SpecRepo,
) -> None:
    """The capability is the feature the binding names, never the module's name."""
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    spec_repo.steps("shared", STEP_MODULE)

    assert [status.capability for status in statuses_for(spec_repo)] == ["thing-capability"]
    assert [status.state for status in statuses_for(spec_repo)] == [traceability.EXECUTING]


# --------------------------------------------------------------------------
# 3.3 — the single pending list is the only escape hatch
# --------------------------------------------------------------------------


def test_an_unlisted_missing_step_still_fails(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    spec_repo.add("add-thing", "other-capability")
    generator.write(spec_repo.root)
    entries = pending_for(("thing-capability", "It does the thing"))

    statuses = statuses_for(spec_repo, entries)
    failures = traceability.missing_step_definitions(statuses)

    assert {status.capability: status.state for status in statuses} == {
        "thing-capability": traceability.PENDING,
        "other-capability": traceability.ABSENT,
    }
    assert len(failures) == 1
    assert "other-capability" in failures[0]


def test_a_pending_entry_that_now_executes_fails(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    spec_repo.steps("thing-capability", STEP_MODULE)
    entries = pending_for(("thing-capability", "It does the thing"))

    problems = traceability.pending_list_problems(statuses_for(spec_repo, entries), entries)
    assert len(problems) == 1
    assert "now executes" in problems[0]


def test_a_stale_pending_entry_fails(spec_repo: SpecRepo) -> None:
    spec_repo.add("add-thing", "thing-capability")
    generator.write(spec_repo.root)
    entries = pending_for(("thing-capability", "A scenario the spec no longer has"))

    problems = traceability.pending_list_problems(statuses_for(spec_repo, entries), entries)
    assert len(problems) == 1
    assert "names no generated scenario" in problems[0]


def test_the_pending_file_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "pending.txt"
    keys = [("b-capability", "Second"), ("a-capability", "First")]
    path.write_text(pending.render(keys), encoding="utf-8")

    assert [entry.key for entry in pending.load(path)] == sorted(keys)


def test_a_malformed_pending_line_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "pending.txt"
    path.write_text("a-capability - First\n", encoding="utf-8")

    with pytest.raises(pending.PendingListError, match=re.escape("pending.txt:1")):
        pending.load(path)


def test_a_duplicate_pending_line_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "pending.txt"
    path.write_text("a :: First\na :: First\n", encoding="utf-8")

    with pytest.raises(pending.PendingListError, match="duplicate"):
        pending.load(path)


def test_the_committed_pending_list_covers_exactly_the_unimplemented_scenarios(
    repo_root: Path,
) -> None:
    """The repository's own list: every pending scenario, nothing else."""
    entries = pending.load(repo_root / pending.PENDING_PATH)
    specs = generator.load_specs(repo_root)
    bindings = implemented.discover(repo_root / implemented.STEPS_DIR)
    statuses = traceability.classify(specs, bindings, entries)

    assert traceability.pending_list_problems(statuses, entries) == ()
    assert traceability.missing_step_definitions(statuses) == ()


# --------------------------------------------------------------------------
# 3.4 — the per-capability report
# --------------------------------------------------------------------------


def test_the_report_counts_executing_pending_and_absent_per_capability(
    spec_repo: SpecRepo,
) -> None:
    spec_repo.add("add-thing", "thing-capability")
    spec_repo.add("add-thing", "other-capability")
    spec_repo.add("add-other", "third-capability")
    generator.write(spec_repo.root)
    spec_repo.steps("thing-capability", STEP_MODULE)
    entries = pending_for(("other-capability", "It does the thing"))

    statuses = statuses_for(spec_repo, entries)
    counts = {row.capability: row for row in traceability.counts(statuses)}
    report = traceability.render_report(statuses)

    assert (counts["thing-capability"].executing, counts["thing-capability"].pending) == (1, 0)
    assert (counts["other-capability"].pending, counts["other-capability"].absent) == (1, 0)
    assert counts["third-capability"].absent == 1
    assert "| add-other | third-capability | 1 | 0 | 0 | 1 |" in report
    assert "1 executing, 1 pending, 1 absent" in report


def test_the_repository_report_is_current(repo_root: Path) -> None:
    """Task 3.4 — `just check` writes it, so it must be on disk and up to date."""
    report = repo_root / traceability.REPORT_PATH
    entries = pending.load(repo_root / pending.PENDING_PATH)
    specs = generator.load_specs(repo_root)
    bindings = implemented.discover(repo_root / implemented.STEPS_DIR)
    statuses = traceability.classify(specs, bindings, entries)

    assert report.is_file(), "`just check` writes it; run `just test`"
    assert report.read_text(encoding="utf-8") == traceability.render_report(statuses)
