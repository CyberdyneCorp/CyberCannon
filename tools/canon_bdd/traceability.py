"""The two gates, and the per-capability report they produce.

D3 — the gates fail in opposite directions, and only both together pin the spec
and the code to each other:

1. a requirement with no scenario that executes → fail, naming the requirement
   and its spec path;
2. a generated scenario with no step definition → fail, naming the **spec file
   and line**, not the generated feature, because the spec is where the fix goes.

Everything here is a pure function over parsed values, so the gates are unit
testable against hand-built specs with nothing on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from canon_bdd.implemented import Binding, executing_keys
from canon_bdd.pending import PendingEntry
from canon_bdd.specs import CapabilitySpec, Requirement, iter_scenarios

EXECUTING = "executing"
PENDING = "pending"
ABSENT = "absent"
STATES = (EXECUTING, PENDING, ABSENT)

REPORT_PATH = Path("reports/bdd-traceability.md")


@dataclass(frozen=True)
class ScenarioStatus:
    """One generated scenario and whether anything executes it."""

    change: str
    capability: str
    requirement: str
    scenario: str
    spec_path: Path
    spec_line: int
    state: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.capability, self.scenario)

    @property
    def location(self) -> str:
        return f"{self.spec_path.as_posix()}:{self.spec_line}"


@dataclass(frozen=True)
class CapabilityCounts:
    """Executing, pending and absent scenarios for one capability."""

    change: str
    capability: str
    executing: int
    pending: int
    absent: int

    @property
    def total(self) -> int:
        return self.executing + self.pending + self.absent


def scenarios_by_capability(specs: tuple[CapabilitySpec, ...]) -> dict[str, tuple[str, ...]]:
    """Every scenario name the specs declare, per capability."""
    return {
        spec.capability: tuple(scenario.name for _, scenario in spec.scenarios) for spec in specs
    }


def classify(
    specs: tuple[CapabilitySpec, ...],
    bindings: tuple[Binding, ...],
    pending: tuple[PendingEntry, ...],
) -> tuple[ScenarioStatus, ...]:
    """Label every generated scenario executing, pending or absent."""
    executing = executing_keys(bindings, scenarios_by_capability(specs))
    excused = {item.key for item in pending}
    return tuple(
        ScenarioStatus(
            change=spec.change,
            capability=spec.capability,
            requirement=requirement.name,
            scenario=scenario.name,
            spec_path=spec.path,
            spec_line=scenario.line,
            state=_state((spec.capability, scenario.name), executing, excused),
        )
        for spec, requirement, scenario in iter_scenarios(specs)
    )


def _state(
    key: tuple[str, str], executing: set[tuple[str, str]], excused: set[tuple[str, str]]
) -> str:
    if key in executing:
        return EXECUTING
    return PENDING if key in excused else ABSENT


def missing_step_definitions(statuses: tuple[ScenarioStatus, ...]) -> tuple[str, ...]:
    """Gate two: a generated scenario nothing executes and nobody excused."""
    return tuple(
        f"{status.location}: scenario {status.scenario!r} of requirement "
        f"{status.requirement!r} has no step definition. Implement it in "
        f"tests/bdd/steps/{status.capability}.py, or add "
        f"'{status.capability} :: {status.scenario}' to tests/bdd/pending.txt."
        for status in statuses
        if status.state == ABSENT
    )


def unverified_requirements(
    specs: tuple[CapabilitySpec, ...], statuses: tuple[ScenarioStatus, ...]
) -> tuple[str, ...]:
    """Gate one: a requirement with no scenario that executes, and none excused."""
    by_requirement = _states_by_requirement(statuses)
    return tuple(
        _unverified_message(
            spec, requirement, by_requirement.get((spec.capability, requirement.name), ())
        )
        for spec in specs
        for requirement in spec.requirements
        if _is_unverified(by_requirement.get((spec.capability, requirement.name), ()))
    )


def _states_by_requirement(
    statuses: tuple[ScenarioStatus, ...],
) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for status in statuses:
        grouped.setdefault((status.capability, status.requirement), []).append(status.state)
    return {key: tuple(states) for key, states in grouped.items()}


def _is_unverified(states: tuple[str, ...]) -> bool:
    if EXECUTING in states:
        return False
    return not states or ABSENT in states or PENDING not in states


def _unverified_message(
    spec: CapabilitySpec, requirement: Requirement, states: tuple[str, ...]
) -> str:
    reason = (
        "carries no scenario at all"
        if not states
        else f"has {len(states)} scenario(s), none of which executes"
    )
    return (
        f"{spec.path.as_posix()}:{requirement.line}: requirement "
        f"{requirement.name!r} {reason}. A requirement nobody verified is a "
        "requirement nobody implemented."
    )


def pending_list_problems(
    statuses: tuple[ScenarioStatus, ...], pending: tuple[PendingEntry, ...]
) -> tuple[str, ...]:
    """The pending list must stay honest: no stale lines, no redundant ones."""
    known = {status.key for status in statuses}
    executing = {status.key for status in statuses if status.state == EXECUTING}
    problems = [
        f"tests/bdd/pending.txt:{entry.line}: '{entry.capability} :: {entry.scenario}' "
        "names no generated scenario; the spec moved, so the line must go."
        for entry in pending
        if entry.key not in known
    ]
    problems.extend(
        f"tests/bdd/pending.txt:{entry.line}: '{entry.capability} :: {entry.scenario}' "
        "now executes; delete the line so the pending count stays truthful."
        for entry in pending
        if entry.key in executing
    )
    return tuple(problems)


def counts(statuses: tuple[ScenarioStatus, ...]) -> tuple[CapabilityCounts, ...]:
    """Per-capability executing/pending/absent counts, in a stable order."""
    grouped: dict[tuple[str, str], list[ScenarioStatus]] = {}
    for status in statuses:
        grouped.setdefault((status.change, status.capability), []).append(status)
    return tuple(
        CapabilityCounts(
            change=change,
            capability=capability,
            executing=sum(1 for s in group if s.state == EXECUTING),
            pending=sum(1 for s in group if s.state == PENDING),
            absent=sum(1 for s in group if s.state == ABSENT),
        )
        for (change, capability), group in sorted(grouped.items())
    )


def render_report(statuses: tuple[ScenarioStatus, ...]) -> str:
    """The per-capability report written on every `just check` (task 3.4)."""
    rows = counts(statuses)
    lines = [
        "# BDD traceability",
        "",
        "Generated by `just check` from the spec deltas. Every scenario in",
        "`openspec/changes/*/specs/*/spec.md` is executing, pending (a reviewed",
        "exception in `tests/bdd/pending.txt`) or absent (a failing build).",
        "",
        "| change | capability | scenarios | executing | pending | absent |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {row.change} | {row.capability} | {row.total} | "
        f"{row.executing} | {row.pending} | {row.absent} |"
        for row in rows
    )
    lines.extend(["", summary_line(statuses), ""])
    return "\n".join(lines)


def summary_line(statuses: tuple[ScenarioStatus, ...]) -> str:
    """One line fit for a terminal summary."""
    totals = {state: sum(1 for s in statuses if s.state == state) for state in STATES}
    return (
        f"**{len(statuses)} scenarios across {len({s.capability for s in statuses})} "
        f"capabilities: {totals[EXECUTING]} executing, {totals[PENDING]} pending, "
        f"{totals[ABSENT]} absent.**"
    )
