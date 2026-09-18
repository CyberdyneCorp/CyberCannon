"""Tasks 1.1-1.3 and 2.2 — the layers, the runners, the coverage threshold, the tags.

The harness has to exist before the first line of domain code, so what it
promises is asserted here rather than discovered by the eleven changes about to
be written against it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from spec_repo import SpecRepo

from canon_bdd import generator
from canon_bdd.plugin import LAYERS

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
LAYER_DIRS = (
    "tests/unit",
    "tests/bdd/features",
    "tests/bdd/steps",
    "tests/conformance",
    "tests/e2e",
)
HARNESS_DEPENDENCIES = ("pytest-bdd", "playwright", "pytest-xdist", "pytest-cov")

STEP_MODULE = """\
from pytest_bdd import given, scenario, then, when


@scenario("../features/{change}/{capability}.feature", "It does the thing")
def test_it_does_the_thing() -> None:
    ...


@given("a thing")
def _a_thing() -> int:
    return 1


@when("it is done")
def _it_is_done() -> None: ...


@then("it SHALL be done")
def _it_shall_be_done() -> None: ...
"""

COVERED_DOMAIN = "def rule(value):\n    return value > 0\n"
UNCOVERED_DOMAIN = "def rule(value):\n    if value > 0:\n        return True\n    return False\n"
COVERAGE_TEST = "from thing.domain import rule\n\n\ndef test_rule():\n    assert rule(1)\n"


@pytest.fixture(scope="module")
def pyproject(repo_root: Path) -> dict:
    return tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1.1 — the layers exist, are collected, and are selectable
# --------------------------------------------------------------------------


@pytest.mark.parametrize("directory", LAYER_DIRS)
def test_every_layer_directory_exists(repo_root: Path, directory: str) -> None:
    assert (repo_root / directory).is_dir()


def test_every_layer_is_a_registered_marker(pyproject: dict) -> None:
    registered = {
        entry.split(":", 1)[0] for entry in pyproject["tool"]["pytest"]["ini_options"]["markers"]
    }
    assert set(LAYERS) <= registered


def test_collection_finds_every_layer(repo_root: Path) -> None:
    collected = _collect(repo_root, [])
    for layer in LAYERS:
        assert any(node.startswith(f"tests/{layer}/") for node in collected), layer


@pytest.mark.parametrize("layer", LAYERS)
def test_a_layer_marker_selects_only_that_layer(repo_root: Path, layer: str) -> None:
    collected = _collect(repo_root, ["-m", layer])
    assert collected, f"no test is marked {layer}"
    assert all(node.startswith(f"tests/{layer}/") for node in collected)


def test_step_modules_are_collected(pyproject: dict) -> None:
    """A step module is named after its capability, not `test_*` (D4)."""
    patterns = pyproject["tool"]["pytest"]["ini_options"]["python_files"]
    assert "steps/*.py" in patterns


# --------------------------------------------------------------------------
# 1.2 — the harness dependencies are declared and locked
# --------------------------------------------------------------------------


@pytest.mark.parametrize("package", HARNESS_DEPENDENCIES)
def test_the_harness_dependencies_are_declared(pyproject: dict, package: str) -> None:
    declared = pyproject["dependency-groups"]["dev"]
    assert any(entry.startswith(package) for entry in declared), declared


@pytest.mark.parametrize("package", HARNESS_DEPENDENCIES)
def test_the_harness_dependencies_are_locked(repo_root: Path, package: str) -> None:
    """uv.lock is authoritative for CI, the image build and a developer's machine."""
    lock = (repo_root / "uv.lock").read_text(encoding="utf-8")
    assert f'name = "{package}"' in lock


def test_the_lock_file_is_current(repo_root: Path) -> None:
    result = subprocess.run(
        ["uv", "lock", "--check"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------
# 1.3 — coverage is enforced on the domain package, and only there (D7)
# --------------------------------------------------------------------------


def test_coverage_measures_the_domain_package_only(pyproject: dict) -> None:
    assert pyproject["tool"]["coverage"]["run"]["source"] == ["cybercanon.domain"]


def test_the_coverage_threshold_is_enforced(pyproject: dict) -> None:
    assert pyproject["tool"]["coverage"]["report"]["fail_under"] > 0


def test_the_test_recipe_measures_coverage(recipes: dict) -> None:
    assert any("--cov" in line for line in recipes["test"].body)


def test_a_gap_in_the_domain_fails_the_run(tmp_path: Path) -> None:
    assert _coverage_run(tmp_path, domain=UNCOVERED_DOMAIN).returncode != 0


def test_a_gap_outside_the_domain_does_not_fail_the_run(tmp_path: Path) -> None:
    result = _coverage_run(tmp_path, domain=COVERED_DOMAIN, adapter=UNCOVERED_DOMAIN)
    assert result.returncode == 0, result.stdout


def _coverage_run(
    tmp_path: Path, domain: str, adapter: str | None = None
) -> subprocess.CompletedProcess[str]:
    """A miniature project configured exactly as this one: domain source only."""
    package = tmp_path / "thing"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "domain.py").write_text(domain, encoding="utf-8")
    if adapter is not None:
        (package / "adapter.py").write_text(adapter, encoding="utf-8")
    (tmp_path / "test_rule.py").write_text(COVERAGE_TEST, encoding="utf-8")
    (tmp_path / ".coveragerc").write_text(
        "[run]\nsource = thing.domain\n\n[report]\nfail_under = 90\n", encoding="utf-8"
    )
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--cov"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------
# 2.2 — `just test-bdd --tag <capability>` selects one capability (D5)
# --------------------------------------------------------------------------


def test_a_tag_selects_only_its_capabilitys_scenarios(spec_repo: SpecRepo, repo_root: Path) -> None:
    _bdd_project(spec_repo, repo_root)

    selected = _collect(spec_repo.root, ["--tag", "thing-capability"])
    assert selected == ["tests/bdd/steps/thing-capability.py::test_it_does_the_thing"]


def test_a_change_tag_selects_every_capability_of_that_change(
    spec_repo: SpecRepo, repo_root: Path
) -> None:
    _bdd_project(spec_repo, repo_root)

    assert len(_collect(spec_repo.root, ["--tag", "add-thing"])) == 2
    assert _collect(spec_repo.root, ["--tag", "capability:other-capability"]) == [
        "tests/bdd/steps/other-capability.py::test_it_does_the_thing"
    ]


def test_an_unknown_tag_selects_nothing(spec_repo: SpecRepo, repo_root: Path) -> None:
    _bdd_project(spec_repo, repo_root)

    assert _collect(spec_repo.root, ["--tag", "no-such-capability"]) == []


def _bdd_project(spec_repo: SpecRepo, repo_root: Path) -> None:
    """A two-capability repository with real features and real step modules."""
    for capability in ("thing-capability", "other-capability"):
        spec_repo.add("add-thing", capability)
    generator.write(spec_repo.root)
    for capability in ("thing-capability", "other-capability"):
        spec_repo.steps(capability, STEP_MODULE.format(change="add-thing", capability=capability))
    (spec_repo.root / "pyproject.toml").write_text(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )


def _collect(root: Path, arguments: list[str]) -> list[str]:
    environment = {**os.environ, "PYTHONPATH": str(TOOLS_DIR)}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *arguments,
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    # 5 is pytest's "nothing was collected", which is a legitimate answer to a
    # tag that selects nothing.
    assert result.returncode in (0, 5), result.stdout + result.stderr
    return [line for line in result.stdout.splitlines() if "::" in line]
