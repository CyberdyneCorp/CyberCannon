"""Tasks 6.1-6.3 — PostgreSQL as the rebuildable index, against a real server.

The port conformance suite already runs `PostgresSearchIndex` through the same
contract body as the in-memory fake and `SqliteSearchIndex`. What only a real
project and two real stores can show is asserted here:

* **6.1** the hosted index and the local one return **byte-identical** results
  for the same fixture project — same rows, same order, same match kind. That is
  not a property of either adapter: it is a property of there being one ranking
  cascade (D9), and this is the test that would fail the day somebody added a
  `ts_rank` to make PostgreSQL "better";
* **6.2** the migration set applied to an empty database yields a schema the
  rebuild populates with no manual step, and re-running it applies nothing;
* **6.3** the drop-and-rebuild guarantee, stated the way `hosted-repository`
  states it: *"every previously answerable lookup, listing, search and read
  SHALL return the same result as before"*. So every answer is recorded first,
  the schema is really dropped, the migration set is really re-applied, and the
  rebuild really reads the working copy.

The index is never given a fact of its own. Every row here is a projection of an
`asset.yaml` in a git working copy, which is why dropping the schema is a
recovery rather than an incident.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from staged_project import MULE_SPEC, PROJECT, SCOUT_SPEC, Staged, ready

from cybercanon.adapters.outbound.postgres.migrations import (
    apply_migrations,
    migrations_in,
)
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.outbound.sqlite.search_index import SqliteSearchIndex
from cybercanon.application.ports.search_index import FileFingerprint, SearchIndex
from cybercanon.application.results import Ok
from cybercanon.application.use_cases.hosted_repository import (
    read_at_revision,
    rebuild_project_index,
)

pytestmark = pytest.mark.integration

TERMS = (
    "mech_scout",
    "mech",
    "scout",
    "drone",
    "mule",
    "hauler",
    "nothing-matches-this",
    "MECH_SCOUT",
)
"""Terms chosen so that every pass of the cascade fires at least once.

`mech_scout` is an exact identifier, `scout` a name prefix and an alias at once,
`mule` an identifier and a name prefix, `MECH_SCOUT` the same query in the wrong
case, and one term matches nothing — which is an answer the two stores must also
agree about.
"""

MIGRATIONS = Path("db/migrations")

TABLES = ("assets", "search_misses", "idempotency_keys", "dismissals", "schema_migrations")
"""Everything the migration set creates — dropped in full by the 6.3 drill."""


# --------------------------------------------------------------------------
# Recording every answer a project can give
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Answers:
    """Every lookup, listing and search a project answers, as comparable values."""

    listing: tuple
    filtered: Mapping[str, tuple]
    lookups: Mapping[str, object]
    searches: Mapping[str, tuple]

    @staticmethod
    def of(index: SearchIndex) -> Answers:
        listing = index.list_assets(project=PROJECT)
        return Answers(
            listing=listing,
            filtered={
                "status=modeling": index.list_assets(project=PROJECT, status="modeling"),
                "owner=rafa": index.list_assets(project=PROJECT, owner="rafa@cyberdyne.com"),
                "owner=nobody": index.list_assets(project=PROJECT, owner="nobody@example.com"),
            },
            lookups={entry.asset_id: index.get(entry.asset_id, PROJECT) for entry in listing},
            searches={term: index.search(term, PROJECT) for term in TERMS},
        )


def fingerprints_under(root: Path) -> Callable[[str], FileFingerprint | None]:
    """A fingerprinter over a real working copy — one stat call per lookup (D8)."""

    def fingerprint(path: str) -> FileFingerprint | None:
        target = root / path
        if not target.is_file():
            return None
        stat = os.stat(target)
        return FileFingerprint(path=path, size=stat.st_size, mtime_ns=stat.st_mtime_ns)

    return fingerprint


def rebuild(staged: Staged, index: SearchIndex) -> None:
    """Rebuild this index from the working copy, as the operation does it."""
    outcome = rebuild_project_index(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        search_index=index,
        fingerprints=fingerprints_under(staged.working_copy),
    )
    assert isinstance(outcome, Ok), outcome
    assert outcome.value.is_complete, outcome.value.unreadable


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    return ready(tmp_path)


@pytest.fixture
def postgres_index(postgres_dsn: str) -> PostgresSearchIndex:
    with PostgresSearchIndex(postgres_dsn) as index:
        yield index


# --------------------------------------------------------------------------
# 6.1 — the hosted index answers exactly as the local one does
# --------------------------------------------------------------------------


def test_the_hosted_index_returns_identical_results_to_the_local_one(
    staged: Staged, postgres_index: PostgresSearchIndex, tmp_path: Path
) -> None:
    """One cascade, two stores. A difference here is a second search engine."""
    local = SqliteSearchIndex(tmp_path / "local")
    rebuild(staged, local)
    rebuild(staged, postgres_index)

    assert Answers.of(postgres_index) == Answers.of(local)


@pytest.mark.parametrize("term", TERMS)
def test_the_ranking_cascade_agrees_term_by_term(
    staged: Staged, postgres_index: PostgresSearchIndex, tmp_path: Path, term: str
) -> None:
    """Named per term, so a failure says which query the two stores disagreed on."""
    local = SqliteSearchIndex(tmp_path / "local")
    rebuild(staged, local)
    rebuild(staged, postgres_index)

    assert postgres_index.search(term, PROJECT) == local.search(term, PROJECT)


# --------------------------------------------------------------------------
# 6.2 — the migration set, applied as a release step
# --------------------------------------------------------------------------


def test_the_migration_set_is_ordered_and_numbered(repo_root: Path) -> None:
    versions = [migration.version for migration in migrations_in(repo_root / MIGRATIONS)]

    assert versions == sorted(versions)
    assert versions, "the migration set is empty"


def test_a_migration_applied_to_an_empty_database_is_populated_by_the_rebuild(
    postgres_server, repo_root: Path, staged: Staged
) -> None:
    """An empty database plus the release step plus the rebuild — no manual step."""
    postgres_server.psql("CREATE DATABASE fresh_index")
    dsn = postgres_server.get_uri(database="fresh_index")

    report = apply_migrations(dsn, repo_root / MIGRATIONS)
    with PostgresSearchIndex(dsn) as index:
        rebuild(staged, index)
        listed = index.list_assets(project=PROJECT)

    assert report.applied == tuple(
        migration.version for migration in migrations_in(repo_root / MIGRATIONS)
    )
    assert [entry.asset_id for entry in listed] == ["mech_scout", "mule"]


def test_running_the_release_step_twice_applies_nothing_the_second_time(
    postgres_server, repo_root: Path
) -> None:
    """A release step that could not be re-run would make a retried deploy a risk."""
    postgres_server.psql("CREATE DATABASE twice_migrated")
    dsn = postgres_server.get_uri(database="twice_migrated")

    apply_migrations(dsn, repo_root / MIGRATIONS)
    second = apply_migrations(dsn, repo_root / MIGRATIONS)

    assert second.applied == ()
    assert second.skipped


# --------------------------------------------------------------------------
# 6.3 — drop the database, rebuild, and answer identically
# --------------------------------------------------------------------------


def test_dropping_the_index_and_rebuilding_loses_no_answer(
    staged: Staged, postgres_dsn: str, repo_root: Path
) -> None:
    """`hosted-repository`: every lookup, listing, search and read is unchanged."""
    with PostgresSearchIndex(postgres_dsn) as index:
        rebuild(staged, index)
        before = Answers.of(index)
        specification_before = _read_specifications(staged)

    _drop_everything(postgres_dsn)
    apply_migrations(postgres_dsn, repo_root / MIGRATIONS)

    with PostgresSearchIndex(postgres_dsn) as rebuilt:
        rebuild(staged, rebuilt)
        after = Answers.of(rebuilt)
        specification_after = _read_specifications(staged)

    assert after == before
    assert specification_after == specification_before


def test_the_drop_really_removed_the_schema(staged: Staged, postgres_dsn: str) -> None:
    """Otherwise the drill above would be asserting that nothing happened."""
    with PostgresSearchIndex(postgres_dsn) as index:
        rebuild(staged, index)

    _drop_everything(postgres_dsn)

    with (
        psycopg.connect(postgres_dsn, autocommit=True) as connection,
        pytest.raises(psycopg.errors.UndefinedTable),
    ):
        connection.execute("SELECT count(*) FROM assets")


def _read_specifications(staged: Staged) -> Mapping[str, object]:
    """The specification content itself, read at the revision it is served from.

    The rebuild guarantee covers reads as well as lookups, and a read comes from
    the working copy rather than from the index — which is the point: dropping
    the index cannot change it.
    """
    read = read_at_revision(
        PROJECT,
        lambda store: {path: store.load(path).asset for path in (SCOUT_SPEC, MULE_SPEC)},
        repository_host=staged.host,
        spec_store=staged.spec_store(),
    )
    assert isinstance(read, Ok), read
    return read.value.value


def _drop_everything(dsn: str) -> None:
    """Drop the index entirely — schema and ledger, not just the rows."""
    with psycopg.connect(dsn, autocommit=True) as connection:
        for table in TABLES:
            connection.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
