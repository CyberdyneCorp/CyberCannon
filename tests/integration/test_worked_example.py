"""Task 7.3 — the worked example validates and compiles through the CLI, in CI.

`examples/ronin/` is the answer to "what does adopting this actually look like",
and an example that has drifted from the tool is worse than none: it is the
first thing a new team copies. So CI runs it rather than reading it — the same
binary, the same two commands, from a real working copy.

The export is written from code by `tools/canon_fixtures` into a temporary copy,
because nothing binary lives in git. Everything else is the committed example,
untouched, including `art-spec.md`, which is compared **byte for byte** against
what `canon compile` produces now. That comparison is what keeps the derived
file honest: a committed briefing that no longer matches its specification is
exactly the drift the compiler exists to prevent.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from canon_fixtures import mesh as fixtures

pytestmark = pytest.mark.integration

EXAMPLE = Path("examples/ronin")
SPEC = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
COMPILED = "characters/mech_scout/art-spec.md"
PROJECT_CONFIG = ".canon/project.yaml"

CLEAN = 0


def canon(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def example(repo_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The committed example as a working copy, with its export written from code."""
    working = tmp_path_factory.mktemp("ronin") / "ronin"
    shutil.copytree(repo_root / EXAMPLE, working)
    (working / ".git").mkdir()
    fixtures.write_skinned_glb(working / EXPORT, asset="mech_scout")
    return working


def test_the_example_is_a_complete_repository(repo_root: Path) -> None:
    """Three committed files, and the export deliberately not among them."""
    committed = repo_root / EXAMPLE
    assert (committed / PROJECT_CONFIG).is_file()
    assert (committed / SPEC).is_file()
    assert (committed / COMPILED).is_file()
    assert not (committed / EXPORT).exists()


def test_the_example_specification_is_structurally_valid(example: Path) -> None:
    result = canon(example, "check")

    assert result.returncode == CLEAN, result.stderr
    assert "0 error" in result.stdout


def test_the_example_export_validates_clean(example: Path) -> None:
    """Every rule GLB can answer passes: sockets, clips, rig budget, naming, scale."""
    result = canon(example, "validate", EXPORT)

    assert result.returncode == CLEAN, result.stdout + result.stderr
    assert "no violations" in result.stdout
    assert "not evaluated" not in result.stdout


def test_the_committed_briefing_is_what_the_compiler_produces(
    repo_root: Path, example: Path
) -> None:
    result = canon(example, "compile", "--stdout", SPEC)

    assert result.returncode == CLEAN, result.stderr
    assert result.stdout == (repo_root / EXAMPLE / COMPILED).read_text(encoding="utf-8")


def test_compiling_twice_is_byte_identical(example: Path) -> None:
    """Determinism is what makes the derived file reviewable in a diff."""
    first = canon(example, "compile", "--stdout", SPEC)
    second = canon(example, "compile", "--stdout", SPEC)

    assert first.stdout == second.stdout


def test_the_briefing_carries_rules_and_open_issues_only(repo_root: Path) -> None:
    """A resolved thread is not context; it is history."""
    briefing = (repo_root / EXAMPLE / COMPILED).read_text(encoding="utf-8")

    assert "SOCKET_muzzle_l" in briefing
    assert "A_mech_scout_walk" in briefing
    assert "pauldron still reads as a backpack" in briefing
    assert "rotated 90 degrees" not in briefing


def test_the_briefing_states_the_project_defaults_as_effective_values(
    repo_root: Path,
) -> None:
    """The asset declares neither; the briefing states what the validator enforces."""
    briefing = (repo_root / EXAMPLE / COMPILED).read_text(encoding="utf-8")

    assert "**Up axis**: Y" in briefing
    assert "**Bone budget**: 64" in briefing
