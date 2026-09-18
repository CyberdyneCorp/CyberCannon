"""In-memory fakes, exercised by the per-port conformance suites and the BDD steps.

One constructor, used by every layer. A unit test, a BDD step and a port
conformance suite all build their fakes through :func:`build_fakes`, so a fake
cannot acquire one shape in the unit suite and another in the scenarios — which
is the same failure the port conformance suites exist to catch one level down
(a fake that lies about its adapter).

The registry is the single place a fake is declared:

```python
from cybercanon.application.testing.spec_store import InMemorySpecStore

FAKE_FACTORIES = MappingProxyType({"spec_store": InMemorySpecStore})
```

It is empty until the first port lands: ports arrive with the change that
introduces them (``SpecStore`` and ``MeshInspector`` with
``add-asset-spec-and-validator``), and the change that adds a port adds its fake
here in the same breath. Everything downstream — the ``fakes`` BDD fixture, the
conformance suites — then picks it up with no further wiring.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

FakeFactory = Callable[[], Any]
"""A zero-argument constructor for one port's in-memory fake."""

FAKE_FACTORIES: Mapping[str, FakeFactory] = MappingProxyType({})
"""Port name -> the fake that stands in for it. One entry per port."""


def fake_names(factories: Mapping[str, FakeFactory] | None = None) -> tuple[str, ...]:
    """The ports that have a fake, in a deterministic order."""
    return tuple(sorted(_registry(factories)))


def build_fakes(factories: Mapping[str, FakeFactory] | None = None) -> dict[str, Any]:
    """A fresh instance of every registered fake, keyed by its port name.

    Fresh on every call: a fake shared between two tests is a test that passes
    because of the one before it.
    """
    return {name: factory() for name, factory in sorted(_registry(factories).items())}


def _registry(factories: Mapping[str, FakeFactory] | None) -> Mapping[str, FakeFactory]:
    return FAKE_FACTORIES if factories is None else factories


__all__ = ["FAKE_FACTORIES", "FakeFactory", "build_fakes", "fake_names"]
