"""Tasks 4.3 and 5.1 — the `RepositoryHost` contract against every implementation.

Two factories now. Group 4 wrote the contract against the fake alone and said
what would happen next: *"when the real host arrives it joins with one more
factory and the body below does not move."* It did, and it did not — the only
change in this file is the line below.

`real` is `GitRepositoryHost` over throwaway repositories on disk, wrapped in the
staging seams a contract needs to make the *remote* misbehave (see
`staged_git_host.py`). The value of running both is the asymmetry the pattern was
built for: the fake is what every unit test and BDD step in this repository runs
against, and this is the suite that stops it quietly disagreeing with git.
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from repository_host_contract import RepositoryHostContract
from staged_git_host import StagedGitRepositoryHost

from cybercanon.application.testing.repository_host import InMemoryRepositoryHost


def in_memory(directory: Path) -> InMemoryRepositoryHost:
    return InMemoryRepositoryHost()


def on_disk(directory: Path) -> StagedGitRepositoryHost:
    return StagedGitRepositoryHost(directory)


implementation = implementation_fixture(fake=in_memory, real=on_disk)


class TestRepositoryHost(RepositoryHostContract):
    """The `RepositoryHost` contract, against the fake and against real git."""
