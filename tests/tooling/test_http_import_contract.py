"""Task 1.2 — the HTTP adapter's layering contract, proved by breaking it.

`just imports` runs `lint-imports` over this repository on every `just check`,
and a contract that has never been seen to fail is indistinguishable from no
contract at all. So this test does the only thing that settles it: it writes a
module into the HTTP adapter that imports an outbound one, runs the real
`lint-imports` against the real configuration, asserts it **fails and names the
contract**, removes the module, and asserts it passes again.

The staged module lives inside the package because that is where the import has
to be for grimp to see it — the contract is over `cybercanon.adapters.inbound.http`,
not over a directory. It is written and removed inside a fixture's `try/finally`
with a name nothing else uses, so an interrupted run leaves a file that is
obviously a probe rather than a mystery.

`lint-imports` takes about two tenths of a second on this repository, so running
it twice costs the build nothing measurable.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

HTTP = Path("libs/cybercanon/adapters/inbound/http")
PROBE = "_layering_probe.py"

CONTRACT = "The HTTP adapter must not import outbound adapters"

VIOLATION = '''\
"""A deliberate layering violation, written by a test and removed by it.

If this file is in your working tree, a run of
`tests/tooling/test_http_import_contract.py` was interrupted. Delete it.
"""

from cybercanon.adapters.outbound.git.spec_store import GitSpecStore

__all__ = ["GitSpecStore"]
'''


def _lint_imports(repo_root: Path) -> subprocess.CompletedProcess[str]:
    """The real contract checker, over the real configuration, as `just` runs it."""
    return subprocess.run(
        ["uv", "run", "--locked", "lint-imports"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": "tools"},
    )


@pytest.fixture
def violating_module(repo_root: Path) -> Iterator[Path]:
    """An outbound import inside the HTTP adapter, removed however the test ends."""
    path = repo_root / HTTP / PROBE
    path.write_text(VIOLATION, encoding="utf-8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def test_the_contract_fails_on_a_violating_import_and_passes_once_it_is_removed(
    repo_root: Path, violating_module: Path
) -> None:
    broken = _lint_imports(repo_root)

    assert broken.returncode != 0, broken.stdout + broken.stderr
    assert CONTRACT in broken.stdout
    assert "BROKEN" in broken.stdout

    violating_module.unlink()
    repaired = _lint_imports(repo_root)

    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    assert f"{CONTRACT} KEPT" in repaired.stdout


def test_the_contract_names_the_import_that_broke_it(
    repo_root: Path, violating_module: Path
) -> None:
    """A contract that failed without saying which import is a contract nobody can fix."""
    broken = _lint_imports(repo_root)

    assert "cybercanon.adapters.outbound.git.spec_store" in broken.stdout
    assert PROBE.removesuffix(".py") in broken.stdout
