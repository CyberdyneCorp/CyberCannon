"""Task 4.2 — the shared BDD fixtures, and that they mirror the unit suite.

A scenario's fakes come from `application/testing/` through the same
constructor a unit test calls, so the instance a step gets has the shape the
unit tests pinned down. `tests/unit/test_fakes.py` is the other half.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest
from world import World

from cybercanon.application import testing


class StubFake:
    """Stands in for a port's fake until the first port lands."""


def test_the_fakes_fixture_is_the_declared_registry(fakes: dict[str, Any]) -> None:
    assert sorted(fakes) == list(testing.fake_names())


def test_the_fakes_fixture_builds_what_a_unit_test_builds(fakes: dict[str, Any]) -> None:
    """Same constructor, so same shape — the point of task 4.2."""
    built_as_a_unit_test_would = testing.build_fakes()

    assert {name: type(fake) for name, fake in fakes.items()} == {
        name: type(fake) for name, fake in built_as_a_unit_test_would.items()
    }


def test_a_registered_fake_reaches_a_scenario_with_no_further_wiring(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registering a fake is the whole integration: the fixture follows the registry."""
    monkeypatch.setattr(testing, "FAKE_FACTORIES", MappingProxyType({"stub": StubFake}))

    fakes = request.getfixturevalue("fakes")

    assert list(fakes) == ["stub"]
    assert isinstance(fakes["stub"], StubFake)


def test_the_world_carries_the_scenario_fakes(world: World, fakes: dict[str, Any]) -> None:
    assert world.fakes is fakes


def test_the_world_starts_empty(world: World) -> None:
    """The universal GIVENs fill it; nothing is there before a scenario says so."""
    assert (world.actors, world.projects, world.assets) == ({}, {}, {})
