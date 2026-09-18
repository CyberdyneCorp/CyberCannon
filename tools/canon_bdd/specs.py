"""Read the OpenSpec spec deltas into the model the BDD harness generates from.

The deltas are written in a structure very close to Gherkin already —
``### Requirement:`` holding ``#### Scenario:`` blocks whose bullets are
``- **GIVEN** / **WHEN** / **THEN** / **AND**``. This module turns that text into
values, keeping every name and every step line verbatim, and **fails loudly**
naming the file and the line when a spec does not parse. A skipped spec is an
untested requirement that looks tested, which is the one outcome worse than a
noisy build.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SPEC_GLOB = "changes/*/specs/*/spec.md"
"""Where the spec deltas live, relative to ``openspec/``."""

KEYWORDS = ("GIVEN", "WHEN", "THEN", "AND")
"""The only step keywords a scenario bullet may carry."""

_REQUIREMENT = re.compile(r"^###\s+Requirement:\s*(?P<name>\S.*?)\s*$")
_SCENARIO = re.compile(r"^####\s+Scenario:\s*(?P<name>\S.*?)\s*$")
_STEP = re.compile(r"^-\s+\*\*(?P<keyword>[A-Za-z]+)\*\*\s+(?P<text>\S.*?)\s*$")
_BULLET = re.compile(r"^[-*+]\s")
_HEADING = re.compile(r"^#{1,6}\s")


class SpecParseError(Exception):
    """A spec delta could not be parsed. Never swallowed, never skipped."""

    def __init__(self, path: Path, line: int, message: str) -> None:
        self.path = path
        self.line = line
        self.message = message
        super().__init__(f"{path}:{line}: {message}")


@dataclass(frozen=True)
class Step:
    """One ``- **GIVEN** ...`` bullet, with its text preserved verbatim."""

    keyword: str
    text: str
    line: int


@dataclass(frozen=True)
class Scenario:
    """One ``#### Scenario:`` block."""

    name: str
    line: int
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Requirement:
    """One ``### Requirement:`` block and the scenarios that verify it."""

    name: str
    line: int
    scenarios: tuple[Scenario, ...]


@dataclass(frozen=True)
class CapabilitySpec:
    """One capability's spec delta: ``changes/<change>/specs/<capability>/spec.md``."""

    change: str
    capability: str
    path: Path
    requirements: tuple[Requirement, ...]

    @property
    def scenarios(self) -> tuple[tuple[Requirement, Scenario], ...]:
        return tuple(
            (requirement, scenario)
            for requirement in self.requirements
            for scenario in requirement.scenarios
        )

    @property
    def feature_path(self) -> Path:
        """Where this capability's generated feature file belongs."""
        return Path("tests/bdd/features") / self.change / f"{self.capability}.feature"


def spec_paths(openspec_dir: Path) -> tuple[Path, ...]:
    """Every spec delta, in a deterministic order."""
    return tuple(sorted(openspec_dir.glob(SPEC_GLOB)))


def load_all(openspec_dir: Path, repo_root: Path | None = None) -> tuple[CapabilitySpec, ...]:
    """Parse every spec delta. Raises :class:`SpecParseError` on the first bad file."""
    root = repo_root if repo_root is not None else openspec_dir.parent
    return tuple(load(path, root) for path in spec_paths(openspec_dir))


def load(path: Path, repo_root: Path) -> CapabilitySpec:
    """Parse one spec delta into a :class:`CapabilitySpec`."""
    capability = path.parent.name
    change = path.parent.parent.parent.name
    requirements = _Reader(path, path.read_text(encoding="utf-8")).parse()
    return CapabilitySpec(
        change=change,
        capability=capability,
        path=_relative(path, repo_root),
        requirements=requirements,
    )


def _relative(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve()
    root = repo_root.resolve()
    return resolved.relative_to(root) if resolved.is_relative_to(root) else resolved


class _Reader:
    """A line-at-a-time reader; every branch either accumulates or raises."""

    def __init__(self, path: Path, text: str) -> None:
        self._path = path
        self._lines = text.splitlines()
        self._requirements: list[Requirement] = []
        self._scenarios: list[Scenario] = []
        self._steps: list[Step] = []
        self._requirement: tuple[str, int] | None = None
        self._scenario: tuple[str, int] | None = None
        self._seen_scenarios: dict[str, int] = {}
        self._seen_requirements: dict[str, int] = {}

    def parse(self) -> tuple[Requirement, ...]:
        for number, line in enumerate(self._lines, start=1):
            self._read(number, line)
        self._close_requirement()
        if not self._requirements:
            raise self._error(1, "no '### Requirement:' heading found")
        return tuple(self._requirements)

    def _read(self, number: int, line: str) -> None:
        requirement = _REQUIREMENT.match(line)
        if requirement is not None:
            self._open_requirement(requirement.group("name"), number)
        elif (scenario := _SCENARIO.match(line)) is not None:
            self._open_scenario(scenario.group("name"), number)
        elif line.startswith(("### Requirement", "#### Scenario")):
            raise self._error(
                number, f"malformed requirement or scenario heading: {line.strip()!r}"
            )
        elif _HEADING.match(line) is not None:
            self._close_requirement()
        elif self._scenario is not None:
            self._read_scenario_body(number, line)

    def _read_scenario_body(self, number: int, line: str) -> None:
        step = _STEP.match(line)
        if step is not None:
            self._add_step(step.group("keyword"), step.group("text"), number)
        elif _BULLET.match(line) is not None:
            raise self._error(
                number,
                f"bullet is not a **GIVEN**/**WHEN**/**THEN**/**AND** step: {line.strip()!r}",
            )
        elif not line.strip():
            return
        elif line[0].isspace() and self._steps:
            self._continue_step(line.strip())
        else:
            raise self._error(number, f"unexpected content inside a scenario: {line.strip()!r}")

    def _add_step(self, keyword: str, text: str, number: int) -> None:
        if keyword not in KEYWORDS:
            raise self._error(
                number, f"unknown step keyword {keyword!r}; expected one of {KEYWORDS}"
            )
        if keyword == "AND" and not self._steps:
            raise self._error(number, "a scenario may not start with an **AND** step")
        self._steps.append(Step(keyword=keyword, text=text, line=number))

    def _continue_step(self, text: str) -> None:
        previous = self._steps[-1]
        joined = f"{previous.text} {text}"
        self._steps[-1] = Step(keyword=previous.keyword, text=joined, line=previous.line)

    def _open_requirement(self, name: str, number: int) -> None:
        self._close_requirement()
        if (first := self._seen_requirements.get(name)) is not None:
            raise self._error(
                number, f"duplicate requirement name {name!r} (first seen at line {first})"
            )
        self._seen_requirements[name] = number
        self._requirement = (name, number)

    def _open_scenario(self, name: str, number: int) -> None:
        if self._requirement is None:
            raise self._error(
                number, f"scenario {name!r} appears outside a '### Requirement:' block"
            )
        self._close_scenario()
        if (first := self._seen_scenarios.get(name)) is not None:
            raise self._error(
                number, f"duplicate scenario name {name!r} (first seen at line {first})"
            )
        self._seen_scenarios[name] = number
        self._scenario = (name, number)

    def _close_scenario(self) -> None:
        if self._scenario is None:
            return
        name, number = self._scenario
        if not self._steps:
            raise self._error(
                number, f"scenario {name!r} has no **GIVEN**/**WHEN**/**THEN** bullets"
            )
        self._scenarios.append(Scenario(name=name, line=number, steps=tuple(self._steps)))
        self._scenario = None
        self._steps = []

    def _close_requirement(self) -> None:
        self._close_scenario()
        if self._requirement is None:
            return
        name, number = self._requirement
        self._requirements.append(
            Requirement(name=name, line=number, scenarios=tuple(self._scenarios))
        )
        self._requirement = None
        self._scenarios = []

    def _error(self, number: int, message: str) -> SpecParseError:
        return SpecParseError(self._path, number, message)


def iter_scenarios(
    specs: tuple[CapabilitySpec, ...],
) -> Iterator[tuple[CapabilitySpec, Requirement, Scenario]]:
    """Every scenario in the corpus, in spec order."""
    for spec in specs:
        for requirement, scenario in spec.scenarios:
            yield spec, requirement, scenario
