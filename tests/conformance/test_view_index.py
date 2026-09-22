"""Task 3.4 — the `ViewIndex` contract against every implementation.

The in-memory fake and `PostgresViewIndex`, through one contract body. The fake
is what every ingestion test in this repository records into, so a fake that
scoped rows differently from the table would make the mirror's hash mapping a
green build over a lookup that answers somebody else's project.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from contract import implementation_fixture
from view_index_contract import ViewIndexContract

from cybercanon.adapters.outbound.postgres.view_index import PostgresViewIndex
from cybercanon.application.testing.view_index import InMemoryViewIndex


def in_memory(directory: Path) -> InMemoryViewIndex:
    return InMemoryViewIndex()


implementation = implementation_fixture(fake=in_memory)


class TestViewIndex(ViewIndexContract):
    """The contract, against the in-memory fake."""


@pytest.fixture
def implementation_postgres(postgres_dsn: str) -> PostgresViewIndex:
    with PostgresViewIndex(postgres_dsn) as index:
        index.forget_project("cyberdyne-game")
        index.forget_project("cyberdyne-art")
        yield index


class TestPostgresViewIndex(ViewIndexContract):
    """The same contract, against the table the migration set creates."""

    @pytest.fixture
    def implementation(self, implementation_postgres: PostgresViewIndex):
        return implementation_postgres
