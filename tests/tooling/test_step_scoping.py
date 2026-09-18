"""Task 4.1 — step definitions are scoped per capability (D4).

Two things are asserted, and they are different things: that this repository's
step modules follow the convention, and that the convention is *enforced by the
runner* — a step defined for one capability does not match another capability's
scenario, even when the two scenarios are phrased identically. The second is
only observable from a failing run, so it is staged in `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_runner import run_pytest
from spec_repo import SpecRepo

from canon_bdd import generator, implemented
from canon_bdd.specs import CapabilitySpec

CHANGE = "add-thing"
DEFINING = "thing-capability"
BORROWING = "other-capability"

SHARED_MODULE = "conftest.py"

BOUND_AND_DEFINED = '''\
"""A capability that binds its scenario and defines the steps it needs."""

from pytest_bdd import given, scenario, then, when


@scenario("../features/{change}/{capability}.feature", "It does the thing")
def test_it_does_the_thing() -> None: ...


@given("a thing")
def _a_thing() -> None: ...


@when("it is done")
def _it_is_done() -> None: ...


@then("it SHALL be done")
def _it_shall_be_done() -> None: ...
'''

BOUND_ONLY = '''\
"""A capability that binds a scenario phrased exactly like its neighbour's, and
defines nothing. If the step namespace were global it would pass on the other
capability's steps, which is the failure D4 exists to prevent."""

from pytest_bdd import scenario


@scenario("../features/{change}/{capability}.feature", "It does the thing")
def test_it_does_the_thing() -> None: ...
'''


@pytest.fixture(scope="module")
def specs(repo_root: Path) -> tuple[CapabilitySpec, ...]:
    return generator.load_specs(repo_root)


@pytest.fixture(scope="module")
def capabilities(specs: tuple[CapabilitySpec, ...]) -> frozenset[str]:
    return frozenset(spec.capability for spec in specs)


def step_modules(repo_root: Path) -> tuple[Path, ...]:
    """Every capability step module: the shared one and dunders are not one."""
    directory = repo_root / implemented.STEPS_DIR
    return tuple(
        path
        for path in sorted(directory.glob("*.py"))
        if path.name != SHARED_MODULE and not path.name.startswith("_")
    )


# --------------------------------------------------------------------------
# The convention, as this repository stands
# --------------------------------------------------------------------------


def test_every_step_module_is_named_after_a_capability(
    repo_root: Path, capabilities: frozenset[str]
) -> None:
    unknown = [path.name for path in step_modules(repo_root) if path.stem not in capabilities]
    assert not unknown, (
        f"{unknown} are not capability names. A step module is "
        "tests/bdd/steps/<capability>.py, named exactly as the capability "
        "directory under openspec/changes/*/specs/ (D4); universal steps go in "
        f"tests/bdd/steps/{SHARED_MODULE}."
    )


def test_a_step_module_binds_only_its_own_capability(repo_root: Path) -> None:
    """A module named for one capability may not bind another's feature."""
    strays = [
        f"{binding.module.name}:{binding.line} binds {binding.feature.name}"
        for binding in implemented.discover(repo_root / implemented.STEPS_DIR)
        if binding.capability != binding.module.stem
    ]
    assert not strays, (
        "a step module binds a feature belonging to another capability: "
        f"{strays}. Scoping keeps a step's meaning attached to the capability "
        "that wrote it."
    )


# --------------------------------------------------------------------------
# The runner enforces it — the proof (task 4.1)
# --------------------------------------------------------------------------


@pytest.fixture
def two_capabilities(spec_repo: SpecRepo, repo_root: Path) -> SpecRepo:
    """Two capabilities whose single scenario is phrased identically."""
    for capability in (DEFINING, BORROWING):
        spec_repo.add(CHANGE, capability)
    generator.write(spec_repo.root)
    spec_repo.steps(DEFINING, BOUND_AND_DEFINED.format(change=CHANGE, capability=DEFINING))
    spec_repo.steps(BORROWING, BOUND_ONLY.format(change=CHANGE, capability=BORROWING))
    (spec_repo.root / "pyproject.toml").write_text(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return spec_repo


def test_the_defining_capability_passes(two_capabilities: SpecRepo) -> None:
    run = run_pytest(two_capabilities.root, ["-q", f"tests/bdd/steps/{DEFINING}.py"])
    assert run.passed, run.output


def test_a_step_defined_for_one_capability_does_not_match_another(
    two_capabilities: SpecRepo,
) -> None:
    run = run_pytest(two_capabilities.root, ["-q", f"tests/bdd/steps/{BORROWING}.py"])
    assert not run.passed, (
        "a step defined in another capability's module satisfied this "
        f"capability's scenario:\n{run.output}"
    )
    assert "a thing" in run.output, run.output
    assert "not found" in run.output.lower(), run.output
