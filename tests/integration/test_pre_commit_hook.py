"""Task 7.2 — the published pre-commit hook blocks what it promises to block.

`.pre-commit-hooks.yaml` is the only part of this product most artists will ever
configure, and a hook that is declared but does not run is worse than no hook:
the team believes exports are being checked. So the entry point is read out of
the manifest and executed exactly as `pre-commit` would execute it — the
installed `canon` binary, staged filenames appended — rather than approximated
by calling a function.

Three behaviours, each straight from `canon-cli`:

* an over-budget export **blocks** the commit (`1`);
* a clean export **allows** it (`0`);
* a file belonging to no asset exits `0` with no work, so a repository that has
  not adopted `asset.yaml` is unaffected.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from game_repo import BARREL_EXPORT, MECH_EXPORT, MECH_SPEC, GameRepo, build_game_repo
from ruamel.yaml import YAML

pytestmark = pytest.mark.integration

MANIFEST = ".pre-commit-hooks.yaml"
HOOK_ID = "canon"
CHECK_HOOK_ID = "canon-check"
BINARY = "canon"

CLEAN = 0
VIOLATIONS = 1


@pytest.fixture(scope="module")
def hooks(repo_root: Path) -> dict[str, dict[str, Any]]:
    """The published manifest, read as the data `pre-commit` reads."""
    declared = YAML(typ="safe").load((repo_root / MANIFEST).read_text(encoding="utf-8"))
    return {hook["id"]: hook for hook in declared}


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> GameRepo:
    return build_game_repo(tmp_path_factory.mktemp("hooked"))


def run_hook(hook: dict[str, Any], repo: Path, *files: str) -> subprocess.CompletedProcess[str]:
    """Run a hook's `entry`, with the staged filenames appended as pre-commit does."""
    entry = shlex.split(hook["entry"])
    binary = Path(sys.executable).parent / entry[0]
    assert binary.is_file(), f"the {entry[0]!r} console script is not installed"
    arguments = [str(binary), *entry[1:]]
    if hook.get("pass_filenames", True):
        arguments.extend(files)
    return subprocess.run(arguments, cwd=repo, capture_output=True, text=True, check=False)


# --------------------------------------------------------------------------
# The manifest itself
# --------------------------------------------------------------------------


def test_the_manifest_declares_the_hook_a_game_repository_installs(
    hooks: dict[str, dict[str, Any]],
) -> None:
    hook = hooks[HOOK_ID]

    assert hook["entry"].split() == ["canon", "changed"]
    assert hook["language"] == "python"
    assert hook.get("pass_filenames", True) is True


def test_the_specification_check_hook_needs_no_filenames(
    hooks: dict[str, dict[str, Any]],
) -> None:
    """`canon check` walks the repository itself; handing it filenames would narrow it."""
    hook = hooks[CHECK_HOOK_ID]

    assert hook["entry"].split() == ["canon", "check"]
    assert hook["pass_filenames"] is False


# --------------------------------------------------------------------------
# What it blocks, and what it lets through
# --------------------------------------------------------------------------


def test_the_hook_blocks_a_commit_containing_an_over_budget_export(
    hooks: dict[str, dict[str, Any]], repo: GameRepo
) -> None:
    result = run_hook(hooks[HOOK_ID], repo.root, BARREL_EXPORT)

    assert result.returncode == VIOLATIONS, result.stdout + result.stderr
    assert "tri_budget.exceeded" in result.stdout


def test_the_hook_allows_a_commit_whose_exports_are_clean(
    hooks: dict[str, dict[str, Any]], repo: GameRepo
) -> None:
    result = run_hook(hooks[HOOK_ID], repo.root, MECH_EXPORT, MECH_SPEC)

    assert result.returncode == CLEAN, result.stdout + result.stderr


def test_the_hook_exits_zero_when_nothing_staged_belongs_to_an_asset(
    hooks: dict[str, dict[str, Any]], repo: GameRepo
) -> None:
    (repo.root / "docs/pipeline.md").parent.mkdir(parents=True, exist_ok=True)
    (repo.root / "docs/pipeline.md").write_text("# Pipeline\n", encoding="utf-8")

    result = run_hook(hooks[HOOK_ID], repo.root, "docs/pipeline.md")

    assert result.returncode == CLEAN
    assert "no changed file belongs to an asset" in result.stdout


def test_the_check_hook_runs_over_the_repository(
    hooks: dict[str, dict[str, Any]], repo: GameRepo
) -> None:
    result = run_hook(hooks[CHECK_HOOK_ID], repo.root)

    assert result.returncode == CLEAN, result.stdout + result.stderr
    assert "3 specification files checked" in result.stdout
