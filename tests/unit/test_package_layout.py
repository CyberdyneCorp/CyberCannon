"""Task 1.1 — the hexagonal package layout exists and imports."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

CORE_PACKAGES = [
    "cybercanon",
    "cybercanon.domain",
    "cybercanon.application",
    "cybercanon.application.ports",
    "cybercanon.application.use_cases",
    "cybercanon.application.testing",
    "cybercanon.adapters",
    "cybercanon.adapters.inbound",
    "cybercanon.adapters.inbound.http",
    "cybercanon.adapters.inbound.mcp",
    "cybercanon.adapters.inbound.cli",
    "cybercanon.adapters.outbound",
    "cybercanon.adapters.outbound.git",
    "cybercanon.adapters.outbound.postgres",
    "cybercanon.adapters.outbound.minio",
    "cybercanon.adapters.outbound.mesh",
    "cybercanon.adapters.outbound.auth",
    "cybercanon.adapters.outbound.arche",
    "cybercanon.adapters.wiring",
    "cybercanon.cli",
    "cybercanon.api",
]


@pytest.mark.parametrize("name", CORE_PACKAGES)
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name) is not None


def test_core_lives_under_libs_and_services_are_separate(repo_root: Path) -> None:
    """The hexagonal core is libs/; a deployable is services/ (openspec/project.md)."""
    domain = importlib.import_module("cybercanon.domain")
    cli_service = importlib.import_module("cybercanon.cli")

    assert Path(domain.__file__).is_relative_to(repo_root / "libs" / "cybercanon")
    assert Path(cli_service.__file__).is_relative_to(repo_root / "services" / "cybercanon")
