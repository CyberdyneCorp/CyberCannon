"""Task 6.3 — `canon` end to end, with exit code and standard output asserted apart.

The one thing this layer can check that nothing else can is that the binary a
person installs behaves, on a real directory, the way the use cases behave in
memory — and that it says so through the two channels its callers read.

Every case asserts them separately, which is the whole point of the harness. A
run that printed the right words and exited `0` when it should have exited `1`
is a pre-commit hook letting a broken asset through; a run that exited correctly
while printing progress onto standard output is a broken pipe for everything
downstream of ``| jq``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from canon_process import run_canon

pytestmark = pytest.mark.e2e

EXAMPLE = Path("examples/ronin")

CLEAN_SPEC = """\
schema_version: 1

id: crate_small
name: Small Crate
status: modeling

owner_art: rafa
owner_design: dani
owner_code: leo

constraints:
  tri_budget: 500
"""


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
    """A project whose one specification has nothing wrong with it."""
    asset = tmp_path / "props" / "crate_small"
    asset.mkdir(parents=True)
    (asset / "asset.yaml").write_text(CLEAN_SPEC, encoding="utf-8")
    return tmp_path


def test_the_binary_runs_and_describes_itself(repo_root: Path) -> None:
    run = run_canon("--help", cwd=repo_root)

    run.expect_exit(0).expect_stdout_contains("CyberCanon")


def test_a_clean_specification_exits_zero_and_says_what_it_checked(clean_project: Path) -> None:
    run = run_canon("check", ".", cwd=clean_project)

    run.expect_exit(0).expect_stdout_contains("1 specification file checked")


def test_structured_output_is_the_whole_of_standard_output(clean_project: Path) -> None:
    """``--json`` is for a caller that pipes; the document must be all there is."""
    run = run_canon("check", ".", "--json", cwd=clean_project)

    run.expect_exit(0)
    document = run.stdout_json()

    assert document["command"] == "check"
    assert document["passed"] is True
    assert run.stderr == "", f"progress reached standard output's caller: {run.stderr!r}"


def test_a_finding_changes_the_exit_code_without_changing_the_channel(repo_root: Path) -> None:
    """The two channels move independently: a verdict is an exit code, not a string.

    The worked example currently carries two `spec.state_constrains_nothing`
    findings, so it is the fixture for *a run that happened and did not pass* —
    and the assertion is deliberately about the shape of the answer rather than
    about those two findings, so it stays true when the example is fixed.
    """
    run = run_canon("check", str(EXAMPLE), "--json", cwd=repo_root)
    document = run.stdout_json()

    assert document["ran"] is True
    assert (run.exit_code == 0) is document["passed"], (
        "the exit code and the structured verdict disagree, so one of the two "
        f"callers of this command is being told the wrong thing: exit "
        f"{run.exit_code}, passed={document['passed']}"
    )


def test_a_run_that_could_not_happen_is_not_a_passing_verdict(
    repo_root: Path, tmp_path: Path
) -> None:
    """A validator that lies about its coverage is the failure D13 names."""
    missing = tmp_path / "nothing.glb"

    run = run_canon("validate", str(missing), cwd=repo_root)

    assert run.exit_code != 0, (
        f"validating an export that does not exist reported success: {run.stdout!r}"
    )
