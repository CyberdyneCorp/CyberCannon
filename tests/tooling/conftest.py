"""Fixtures for the harness tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from spec_repo import SpecRepo


@pytest.fixture
def spec_repo(tmp_path: Path) -> SpecRepo:
    return SpecRepo(root=tmp_path)
