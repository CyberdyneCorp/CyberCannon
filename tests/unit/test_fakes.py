"""Task 4.2 — the in-memory fakes are built through one constructor.

The BDD `fakes` fixture and every unit test go through
`cybercanon.application.testing.build_fakes`, so a fake cannot be one thing in
the unit suite and another in the scenarios. This is the unit half; the BDD half
is `tests/bdd/test_shared_fixtures.py`.
"""

from __future__ import annotations

from types import MappingProxyType

from cybercanon.application import testing


class StubFake:
    """Stands in for a port's fake until the first port lands."""

    def __init__(self) -> None:
        self.calls: list[str] = []


REGISTRY = MappingProxyType({"stub": StubFake, "another": StubFake})


def test_an_empty_registry_builds_no_fakes() -> None:
    assert testing.build_fakes(factories={}) == {}


def test_every_registered_fake_is_built() -> None:
    built = testing.build_fakes(factories=REGISTRY)

    assert sorted(built) == ["another", "stub"]
    assert all(isinstance(fake, StubFake) for fake in built.values())


def test_each_call_builds_fresh_instances() -> None:
    """A fake shared between two tests is a test that passes because of the last one."""
    first = testing.build_fakes(factories=REGISTRY)
    second = testing.build_fakes(factories=REGISTRY)

    first["stub"].calls.append("used")

    assert second["stub"].calls == []
    assert first["stub"] is not second["stub"]


def test_fake_names_are_the_registry_in_order() -> None:
    assert testing.fake_names(factories=REGISTRY) == ("another", "stub")


def test_the_declared_registry_is_what_gets_built_by_default() -> None:
    """No argument means the registry every layer shares (empty until a port lands)."""
    assert set(testing.build_fakes()) == set(testing.FAKE_FACTORIES)
    assert testing.fake_names() == tuple(sorted(testing.FAKE_FACTORIES))
