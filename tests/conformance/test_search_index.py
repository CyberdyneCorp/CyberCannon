"""Tasks 2.5 and 4.1 — the `SearchIndex` contract against every implementation.

The in-memory fake and `SqliteSearchIndex`, through one contract body. That
equivalence is the whole point of the port: an ordering the FTS5 table produced
differently, a filter that widened instead of combining, a fingerprint that did
not survive a round trip through a column — each fails the build rather than the
product. It is also why the ranking cascade is a pure function in the port
rather than a query the adapter writes for itself.

The SQLite factory takes the directory the fixture hands it as a repository
root, so the file it creates is the `.canon/index.sqlite` a real project gets,
built and thrown away per test — which is the disposability the specification
asks for, exercised on every run.
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from search_index_contract import SearchIndexContract, seed

from cybercanon.adapters.outbound.sqlite.search_index import SqliteSearchIndex
from cybercanon.application.testing.search_index import InMemorySearchIndex


def in_memory(directory: Path) -> InMemorySearchIndex:
    """The fake, holding exactly the corpus the contract asks about."""
    return seed(InMemorySearchIndex())


def sqlite(directory: Path) -> SqliteSearchIndex:
    """The real adapter, over a `.canon/index.sqlite` in a throwaway repository."""
    return seed(SqliteSearchIndex(directory))


implementation = implementation_fixture(fake=in_memory, real=sqlite)


class TestSearchIndex(SearchIndexContract):
    """The `SearchIndex` contract, against the fake and `SqliteSearchIndex`."""
