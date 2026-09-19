"""Task 10.5 — the `Dismissals` contract against every implementation.

The in-memory fake and `PostgresDismissals`, through one contract body. The fake
is what the unit suite and the BDD steps compose the unread-items query against,
so a fake that scoped dismissals differently from the table would make every one
of those tests a green build over a notification list that is wrong for exactly
one person — the second one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from contract import implementation_fixture
from dismissals_contract import DismissalsContract

from cybercanon.adapters.outbound.postgres.dismissals import PostgresDismissals
from cybercanon.application.testing.dismissals import InMemoryDismissals


def in_memory(directory: Path) -> InMemoryDismissals:
    return InMemoryDismissals()


implementation = implementation_fixture(fake=in_memory)


class TestDismissals(DismissalsContract):
    """The contract, against the in-memory fake."""


@pytest.fixture
def implementation_postgres(postgres_dsn: str) -> PostgresDismissals:
    with PostgresDismissals(postgres_dsn) as store:
        yield store


class TestPostgresDismissals(DismissalsContract):
    """The same contract, against the table the migration set creates."""

    @pytest.fixture
    def implementation(self, implementation_postgres: PostgresDismissals):
        return implementation_postgres
