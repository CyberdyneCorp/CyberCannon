"""Shared BDD fixtures (task 4.2).

The fakes a scenario runs against are the ones `application/testing/` declares,
built through the one constructor the unit suite uses. Nothing here is
capability-specific: a fixture that knows about meshes, annotations or lenses
belongs to that capability's step module (D4), not to every scenario in the
repository.
"""

from __future__ import annotations

from typing import Any

import pytest
from world import World

from cybercanon.application.testing import build_fakes


@pytest.fixture
def fakes() -> dict[str, Any]:
    """A fresh in-memory fake per port, exactly as a unit test builds them."""
    return build_fakes()


@pytest.fixture
def world(fakes: dict[str, Any]) -> World:
    """The scenario's working state: its fakes and whatever the GIVENs named."""
    return World(fakes=fakes)
