"""The port conformance pattern (task 5.1).

One parametrised suite per port, run against the in-memory fake **and** every
real adapter, in one pass. The value is asymmetric: the suite proves the real
adapter honours the port, and — the part that matters for every other test in
this repository — that the fake the unit suite and the BDD steps run against
does not quietly behave differently. A fake that lies is a green build over
broken software.

A port's suite is three lines:

```python
from contract import implementation_fixture

implementation = implementation_fixture(fake=InMemorySpecStore, real=GitSpecStore)


class TestSpecStore(SpecStoreContract): ...
```

`implementation_fixture` is used at module level, never inside the class: a
fixture defined in a class body is bound to the instance, and this one is shared
by every contract class in the module.

The contract itself is a plain class of test methods living beside the port's
fake, so the same body runs for every implementation and a new adapter costs one
line. `tests/conformance/example_port.py` is the worked example; ports arrive
with the changes that introduce them.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

Factory = Callable[[Path], Any]
"""Builds one implementation of a port, given a directory it may use."""


def implementation_fixture(**factories: Factory) -> Any:
    """A fixture parametrised over every named implementation of one port.

    The parameter id is the name — `fake`, `real`, `postgres` — so a failure
    says which implementation broke the contract before anything else is read.
    """
    if not factories:
        raise ValueError("a conformance suite needs at least one implementation")
    names = sorted(factories)

    @pytest.fixture(params=names, ids=names)
    def implementation(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
        return factories[request.param](tmp_path)

    return implementation
