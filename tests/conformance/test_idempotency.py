"""Task 6.5 — the `IdempotencyStore` contract against every implementation.

The in-memory fake and `PostgresIdempotencyStore`, through one contract body.
The fake is what the unit suite composes `once` against, so a fake that expired
records on a different comparison than the table does would make every one of
those tests a green build over broken software.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from contract import implementation_fixture
from idempotency_contract import IdempotencyStoreContract

from cybercanon.adapters.outbound.postgres.idempotency import PostgresIdempotencyStore
from cybercanon.application.testing.idempotency import InMemoryIdempotencyStore


def in_memory(directory: Path) -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


implementation = implementation_fixture(fake=in_memory)


class TestIdempotencyStore(IdempotencyStoreContract):
    """The contract, against the in-memory fake."""


@pytest.fixture
def implementation_postgres(postgres_dsn: str) -> PostgresIdempotencyStore:
    with PostgresIdempotencyStore(postgres_dsn) as store:
        yield store


class TestPostgresIdempotencyStore(IdempotencyStoreContract):
    """The same contract, against the table the migration set creates."""

    @pytest.fixture
    def implementation(self, implementation_postgres: PostgresIdempotencyStore):
        return implementation_postgres
