"""Tasks 5.1-5.2 — the conformance pattern, and that it catches a lying fake.

5.1 is observable from this repository: the example port's suite is collected
once per implementation, fake and real. 5.2 is only observable from a failing
run, so the contract is re-run in a throwaway project against a deliberately
divergent fake, and what is asserted is that the suite fails and says which
implementation broke it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_runner import collect, run_pytest

CONFORMANCE_DIR = Path("tests/conformance")
SUITE = CONFORMANCE_DIR / "test_example_port.py"
CONTRACT_TESTS = 4
IMPLEMENTATIONS = ("fake", "real")

DIVERGENT_SUITE = """\
from contract import implementation_fixture
from example_port import DivergentNoteStore, FileNoteStore, NoteStoreContract

implementation = implementation_fixture(divergent=DivergentNoteStore, real=FileNoteStore)


class TestNoteStore(NoteStoreContract): ...
"""


@pytest.fixture(scope="module")
def suite_node_ids(repo_root: Path) -> tuple[str, ...]:
    return collect(repo_root, [str(SUITE)])


# --------------------------------------------------------------------------
# 5.1 — collected for the fake and for the real adapter
# --------------------------------------------------------------------------


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_the_suite_is_collected_for_every_implementation(
    suite_node_ids: tuple[str, ...], implementation: str
) -> None:
    selected = [node for node in suite_node_ids if node.endswith(f"[{implementation}]")]
    assert len(selected) == CONTRACT_TESTS, (
        f"the contract has {CONTRACT_TESTS} tests but {len(selected)} run against "
        f"{implementation!r}: {selected}"
    )


def test_the_suite_runs_one_contract_over_every_implementation(
    suite_node_ids: tuple[str, ...],
) -> None:
    """One body, parametrised — not a copy of the contract per adapter."""
    assert len(suite_node_ids) == CONTRACT_TESTS * len(IMPLEMENTATIONS)


# --------------------------------------------------------------------------
# 5.2 — a fake that diverges from its real adapter fails the suite
# --------------------------------------------------------------------------


@pytest.fixture
def divergent_project(tmp_path: Path) -> Path:
    (tmp_path / "test_divergent_fake.py").write_text(DIVERGENT_SUITE, encoding="utf-8")
    return tmp_path


def test_a_divergent_fake_fails_the_suite(divergent_project: Path, repo_root: Path) -> None:
    run = run_pytest(divergent_project, ["-q", "-rf"], path=[repo_root / CONFORMANCE_DIR])

    assert not run.passed, (
        "the conformance suite passed a fake that answers an unknown key with an "
        f"empty note while the real adapter reports it missing:\n{run.output}"
    )
    assert "divergent" in run.output, run.output


def test_only_the_divergent_implementation_fails(divergent_project: Path, repo_root: Path) -> None:
    """The real adapter still passes, so the failure names the liar, not the port."""
    run = run_pytest(divergent_project, ["-q", "-rf"], path=[repo_root / CONFORMANCE_DIR])

    failures = [line for line in run.output.splitlines() if line.startswith("FAILED")]
    assert failures, run.output
    assert all("[divergent]" in line for line in failures), failures
