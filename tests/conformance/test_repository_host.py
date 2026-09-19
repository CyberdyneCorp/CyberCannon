"""Task 4.3 — the `RepositoryHost` contract against every implementation.

One factory today, because `GitRepositoryHost` is group 5 of this change and
this sprint stops at group 4. The suite is written now rather than with the
adapter on purpose: the use cases built on top of this port in group 4 are
tested against the fake, and a fake nobody held to a contract is a green build
over software nobody has checked. When the real host arrives it joins with one
more factory and the body below does not move.
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from repository_host_contract import RepositoryHostContract

from cybercanon.application.testing.repository_host import InMemoryRepositoryHost


def in_memory(directory: Path) -> InMemoryRepositoryHost:
    return InMemoryRepositoryHost()


implementation = implementation_fixture(fake=in_memory)


class TestRepositoryHost(RepositoryHostContract):
    """The `RepositoryHost` contract, against the in-memory fake."""
