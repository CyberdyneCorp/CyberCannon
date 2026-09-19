"""Tasks 2.5, 4.1 and 6.1 — the `SearchIndex` contract, every implementation.

The in-memory fake, `SqliteSearchIndex` and `PostgresSearchIndex`, through one
contract body. That equivalence is the whole point of the port: an ordering the
FTS5 table or the `tsvector` produced differently, a filter that widened instead
of combining, a fingerprint that did not survive a round trip through a column —
each fails the build rather than the product. It is also why the ranking cascade
is a pure function in the port rather than a query each adapter writes for
itself, and why task 6.1 can ask for *byte-identical* results from the hosted
index and the local one: there is one cascade, and all three sort with it.

The SQLite factory takes the directory the fixture hands it as a repository
root, so the file it creates is the `.canon/index.sqlite` a real project gets,
built and thrown away per test — which is the disposability the specification
asks for, exercised on every run. The PostgreSQL factory takes a database whose
schema came from the migration set and whose rows were truncated, which is the
same disposability against a server.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from contract import implementation_fixture
from search_index_contract import SearchIndexContract, seed

from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.outbound.sqlite.search_index import SqliteSearchIndex
from cybercanon.application.testing.search_index import InMemorySearchIndex


def in_memory(directory: Path) -> InMemorySearchIndex:
    """The fake, holding exactly the corpus the contract asks about."""
    return seed(InMemorySearchIndex())


def sqlite(directory: Path) -> SqliteSearchIndex:
    """The real adapter, over a `.canon/index.sqlite` in a throwaway repository."""
    return seed(SqliteSearchIndex(directory))


implementation = implementation_fixture(fake=in_memory, sqlite=sqlite)


class TestSearchIndex(SearchIndexContract):
    """The `SearchIndex` contract, against the fake and `SqliteSearchIndex`."""


@pytest.fixture
def implementation_postgres(postgres_dsn: str) -> PostgresSearchIndex:
    """The hosted adapter, over a migrated database emptied for this test."""
    with PostgresSearchIndex(postgres_dsn) as index:
        yield seed(index)


class TestPostgresSearchIndex(SearchIndexContract):
    """The same contract, against `PostgresSearchIndex` (task 6.1).

    A separate class rather than a fourth entry in `implementation_fixture`
    because this implementation needs a fixture the other two do not — a server.
    The body is the one above it, unchanged, which is the property that matters:
    nothing here is a PostgreSQL-shaped copy of the contract.
    """

    @pytest.fixture
    def implementation(self, implementation_postgres: PostgresSearchIndex):
        return implementation_postgres
