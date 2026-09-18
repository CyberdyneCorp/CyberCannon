"""Shared fixtures.

The tooling tests read the justfile and the CI workflow as data, because the
project's central convention — CI runs `just check` and nothing else — is only
worth anything if it is checked mechanically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_lint.justfile import Recipe, parse_justfile

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def justfile_text(repo_root: Path) -> str:
    return (repo_root / "justfile").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def recipes(justfile_text: str) -> dict[str, Recipe]:
    return parse_justfile(justfile_text)
