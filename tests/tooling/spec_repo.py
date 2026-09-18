"""A throwaway repository holding spec deltas, for the harness tests.

The generator and the gates are pure functions over a repository root, so they
can be exercised against a two-scenario repository in `tmp_path` instead of the
real 657. The real corpus is verified separately, and in one direction only:
nothing is lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SPEC_TEMPLATE = """# Spec Delta

## Purpose

A throwaway capability used by the harness tests.

## ADDED Requirements

{body}
"""

ONE_REQUIREMENT = """\
### Requirement: The system SHALL do the thing

#### Scenario: It does the thing
- **GIVEN** a thing
- **WHEN** it is done
- **THEN** it SHALL be done
"""


@dataclass(frozen=True)
class SpecRepo:
    """A repository root holding spec deltas and nothing else."""

    root: Path

    def add(self, change: str, capability: str, body: str = ONE_REQUIREMENT) -> Path:
        path = self.root / "openspec" / "changes" / change / "specs" / capability / "spec.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SPEC_TEMPLATE.format(body=body.rstrip() + "\n"), encoding="utf-8")
        return path

    def feature(self, change: str, capability: str) -> Path:
        return self.root / "tests" / "bdd" / "features" / change / f"{capability}.feature"

    def steps(self, capability: str, source: str) -> Path:
        path = self.root / "tests" / "bdd" / "steps" / f"{capability}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path
