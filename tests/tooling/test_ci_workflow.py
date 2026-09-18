"""Task 1.2b — CI runs justfile recipes and nothing else.

`just check` is the contract: a green local run must mean a green pipeline. That
holds only while CI runs no check of its own, so this test reads the workflow and
fails the build the moment a check appears in CI that is not in the justfile.

`just test-e2e` is the one other command CI may run (task 7.3): D6 keeps e2e out
of `check`, and a check that runs nowhere is a check that does not exist. It is
still a recipe, so the rule is unchanged — CI invokes `just`, never a tool.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from canon_lint.justfile import Recipe

WORKFLOW = Path(".github/workflows/ci.yml")

# Anything that verifies the project rather than installing tooling. If one of
# these appears in a CI `run:` step, the justfile has stopped being the single
# way to run an operation.
CHECK_TOOLS = frozenset(
    {
        "ruff",
        "pytest",
        "lint-imports",
        "complexipy",
        "openspec",
        "mypy",
        "pyright",
        "playwright",
        "coverage",
        "eslint",
        "vitest",
        "tsc",
    }
)


ALLOWED_COMMANDS = ("just check", "just test-e2e")
"""The only commands CI may run. Both are recipes; neither is a tool call."""


@pytest.fixture(scope="session")
def workflow(repo_root: Path) -> dict[str, Any]:
    return YAML(typ="safe").load((repo_root / WORKFLOW).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def run_commands(workflow: dict[str, Any]) -> list[str]:
    return [
        step["run"].strip()
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "run" in step
    ]


def test_workflow_exists(repo_root: Path) -> None:
    assert (repo_root / WORKFLOW).is_file(), f"{WORKFLOW} is the single CI entry point"


def test_the_only_commands_ci_runs_are_justfile_recipes(run_commands: list[str]) -> None:
    unexpected = [command for command in run_commands if command not in ALLOWED_COMMANDS]
    assert not unexpected, (
        f"CI must run only {list(ALLOWED_COMMANDS)}; found {unexpected}. Move the "
        "extra command into a justfile recipe and make `check` depend on it."
    )


def test_ci_runs_just_check(run_commands: list[str]) -> None:
    assert "just check" in run_commands, (
        "`just check` is the contract between a developer's machine and CI; "
        f"CI runs {run_commands}."
    )


def test_no_check_is_invoked_outside_the_justfile(run_commands: list[str]) -> None:
    """A check in CI but not in the justfile is a bug in the justfile."""
    for command in run_commands:
        leaked = sorted(CHECK_TOOLS.intersection(_tokens(command)))
        assert not leaked, (
            f"CI step {command!r} invokes {leaked} directly. Every check belongs to a "
            "justfile recipe reached by `just check`, or a green local run stops "
            "meaning a green pipeline."
        )


def test_every_recipe_ci_invokes_exists(
    run_commands: list[str], recipes: dict[str, Recipe]
) -> None:
    invoked = {
        name
        for command in run_commands
        for name in re.findall(r"\bjust\s+(?:--\S+\s+)*([A-Za-z_][A-Za-z0-9_-]*)", command)
    }
    missing = sorted(invoked - set(recipes))
    assert not missing, f"CI invokes recipes that the justfile does not define: {missing}"


def _tokens(command: str) -> set[str]:
    words = shlex.split(command, comments=True)
    return set(words) | {Path(word).name for word in words}
