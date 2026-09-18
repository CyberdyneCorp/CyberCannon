"""Tasks 7.1-7.3 — the recipes, what `just check` covers, and the CI wiring.

There is exactly one way to run any operation and it is a `just` recipe, so a
layer that cannot be run on its own is a layer nobody runs. Each recipe is
executed here — through `just`, from the repository root — rather than read, so
"it runs standalone" is a fact and not a claim about a text file.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from canon_lint.justfile import Recipe

LAYER_RECIPES = {
    "test-unit": "unit",
    "test-bdd": "bdd",
    "test-conformance": "conformance",
    "test-e2e": "e2e",
}
REQUIRED_RECIPES = ("test-unit", "test-bdd", "test-e2e", "gen-features")

CHECK_LAYERS = ("unit", "bdd", "conformance")
GATES = "tests/bdd/test_traceability.py"
EXCLUDED_FROM_CHECK = "tests/e2e/"

RUNTIME_RECORD = re.compile(r"Measured runtime: ~\s*\d+\s*s")
SUMMARY = re.compile(
    r"\*\*(?P<total>\d+) scenarios across \d+ capabilities: "
    r"(?P<executing>\d+) executing, (?P<pending>\d+) pending, (?P<absent>\d+) absent\.\*\*"
)
SPEC_COUNT = re.compile(r"(?P<count>\d+) GIVEN/WHEN/THEN scenarios")

REPORT = Path("reports/bdd-traceability.md")
WORKFLOW = Path(".github/workflows/ci.yml")


def _just(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    assert shutil.which("just") is not None, (
        "`just` is the only way to run an operation in this project; install it "
        "(https://github.com/casey/just) before running the tooling suite."
    )
    return subprocess.run(
        ["just", *arguments],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _collected_layers(output: str) -> set[str]:
    return {line.split("/")[1] for line in output.splitlines() if line.startswith("tests/")}


# --------------------------------------------------------------------------
# 7.1 — every layer has a recipe, and each runs standalone
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", REQUIRED_RECIPES)
def test_the_recipe_exists(recipes: dict[str, Recipe], name: str) -> None:
    assert name in recipes, f"justfile is missing `just {name}`"


@pytest.mark.parametrize("name", sorted(LAYER_RECIPES))
def test_a_layer_recipe_needs_nothing_but_the_environment(
    recipes: dict[str, Recipe], name: str
) -> None:
    """Standalone from a clean checkout means: `just setup`, then this recipe."""
    assert recipes[name].dependencies == (), recipes[name].dependencies
    assert all(line.startswith("uv run --locked") for line in recipes[name].body), recipes[
        name
    ].body


@pytest.mark.parametrize(("name", "layer"), sorted(LAYER_RECIPES.items()))
def test_a_layer_recipe_runs_and_selects_only_its_layer(
    repo_root: Path, name: str, layer: str
) -> None:
    result = _just(repo_root, name, "--collect-only", "-q", "--no-cov")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _collected_layers(result.stdout) == {layer}, result.stdout


def test_gen_features_regenerates_from_the_spec_deltas(recipes: dict[str, Recipe]) -> None:
    """Task 2.5's recipe is part of the set a developer is promised (7.1)."""
    assert any("gen_features.py" in line for line in recipes["gen-features"].body)
    assert "features" in recipes["check"].dependencies, (
        "`just check` must verify the committed features against the specs (D1)"
    )


# --------------------------------------------------------------------------
# 7.2 — `just check` is unit + BDD + conformance + both gates, and no e2e
# --------------------------------------------------------------------------


def test_check_runs_the_test_recipe_and_not_the_e2e_one(recipes: dict[str, Recipe]) -> None:
    assert "test" in recipes["check"].dependencies
    assert "test-e2e" not in recipes["check"].dependencies, (
        "D6 keeps e2e out of `check`: it needs browsers and a compose stack, and "
        "`check` has to stay fast enough to run constantly."
    )


def test_check_covers_every_layer_but_e2e(repo_root: Path) -> None:
    result = _just(repo_root, "test", "--collect-only", "-q", "--no-cov")

    assert result.returncode == 0, result.stdout + result.stderr
    collected = _collected_layers(result.stdout)
    assert set(CHECK_LAYERS) <= collected, collected
    assert "e2e" not in collected, collected
    assert EXCLUDED_FROM_CHECK not in result.stdout


def test_check_runs_both_traceability_gates(repo_root: Path) -> None:
    result = _just(repo_root, "test", "--collect-only", "-q", "--no-cov")

    assert f"{GATES}::test_every_requirement_has_an_executing_scenario" in result.stdout
    assert f"{GATES}::test_every_generated_scenario_has_a_step_definition" in result.stdout


def test_the_measured_runtime_of_check_is_recorded(justfile_text: str) -> None:
    """7.2 asks for the runtime; a number nobody wrote down is a number nobody has."""
    assert RUNTIME_RECORD.search(justfile_text), (
        "the justfile no longer records how long `just check` takes. Re-measure "
        "and restore the 'Measured runtime: ~N s' line above the recipe."
    )


# --------------------------------------------------------------------------
# 7.3 — CI runs `just check` on every push and `just test-e2e` on the branch
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow(repo_root: Path) -> dict[str, Any]:
    return YAML(typ="safe").load((repo_root / WORKFLOW).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    return workflow["on"]


def test_ci_runs_on_every_push_and_on_pull_requests(triggers: dict[str, Any]) -> None:
    assert set(triggers) == {"push", "pull_request"}, triggers
    assert not (triggers["push"] or {}).get("branches"), (
        "`just check` runs on every push, not only on the default branch: a "
        f"branch filter hides failures until merge ({triggers['push']})."
    )


def test_e2e_runs_in_its_own_job(workflow: dict[str, Any]) -> None:
    jobs = {
        name: [step["run"].strip() for step in job["steps"] if "run" in step]
        for name, job in workflow["jobs"].items()
    }
    assert ["just check"] in jobs.values(), jobs
    assert ["just test-e2e"] in jobs.values(), (
        "D6 runs e2e on the branch rather than in `check`; a suite CI never runs "
        f"is a suite that does not exist. Jobs: {jobs}"
    )


def test_the_run_reports_the_whole_corpus_pending_and_nothing_absent(repo_root: Path) -> None:
    """The initial state: every scenario accounted for, none silently missing."""
    summary = SUMMARY.search((repo_root / REPORT).read_text(encoding="utf-8"))
    assert summary is not None, f"{REPORT} carries no summary line"
    declared = SPEC_COUNT.search((repo_root / "openspec" / "project.md").read_text("utf-8"))
    assert declared is not None, "openspec/project.md no longer states the scenario count"

    total = int(summary.group("total"))
    assert total == int(declared.group("count")), "the corpus and project.md disagree"
    assert int(summary.group("absent")) == 0, "a generated scenario has no step definition"
    assert int(summary.group("executing")) + int(summary.group("pending")) == total
