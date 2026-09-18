"""Run pytest against a throwaway project, so the harness is tested by using it.

Several harness promises — a step scoped to one capability, a conformance suite
that catches a lying fake — are only observable from a *failing* run. A failing
run cannot live in this repository's own suite, so it is staged in `tmp_path`
and executed in a subprocess, and what is asserted is the exit code and the
message the developer would read.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"

NOTHING_COLLECTED = 5


@dataclass(frozen=True)
class Run:
    """One subprocess pytest run: what it returned and what it printed."""

    returncode: int
    output: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(line for line in self.output.splitlines() if "::" in line)


def run_pytest(root: Path, arguments: Sequence[str] = (), path: Sequence[Path] = ()) -> Run:
    """Run pytest in ``root`` with ``path`` prepended to PYTHONPATH."""
    entries = [str(TOOLS_DIR), *(str(entry) for entry in path)]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(entries)}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return Run(returncode=result.returncode, output=result.stdout + result.stderr)


def collect(
    root: Path, arguments: Sequence[str] = (), path: Sequence[Path] = ()
) -> tuple[str, ...]:
    """The node ids pytest collects in ``root``. Collecting nothing is an answer."""
    run = run_pytest(root, ["--collect-only", "-q", *arguments], path)
    assert run.returncode in (0, NOTHING_COLLECTED), run.output
    return run.node_ids
