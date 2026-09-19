"""Shared fixtures.

The tooling tests read the justfile and the CI workflow as data, because the
project's central convention — CI runs `just check` and nothing else — is only
worth anything if it is checked mechanically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_lint.justfile import Recipe, parse_justfile

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def justfile_text(repo_root: Path) -> str:
    return (repo_root / "justfile").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def recipes(justfile_text: str) -> dict[str, Recipe]:
    return parse_justfile(justfile_text)


# --------------------------------------------------------------------------
# A real PostgreSQL, for the adapters that have one (group 6)
# --------------------------------------------------------------------------
#
# `PostgresSearchIndex` has to answer the `SearchIndex` contract exactly as the
# in-memory fake and `SqliteSearchIndex` do — that equivalence is the whole
# point of the port. A conformance suite that only ran where somebody happened
# to have a database would not check it, which is the same failure as a fake
# that lies, so the server is a wheel (`pgserver`) rather than a daemon, a
# container or a credential.
#
# One server and one database for the session; every test truncates. Creating a
# database per test is a file copy per test, and the isolation a truncate gives
# is the isolation these suites need.


@pytest.fixture(scope="session")
def postgres_server(tmp_path_factory: pytest.TempPathFactory):
    """A PostgreSQL server for this session, started from the packaged binaries."""
    pgserver = pytest.importorskip("pgserver", reason="no PostgreSQL binaries on this platform")
    server = pgserver.get_server(tmp_path_factory.mktemp("pgdata"))
    yield server
    server.cleanup()


@pytest.fixture(scope="session")
def migrated_dsn(postgres_server, repo_root: Path) -> str:
    """A database with the migration set applied, as the release step applies it."""
    from cybercanon.adapters.outbound.postgres.migrations import apply_migrations

    postgres_server.psql("CREATE DATABASE canon")
    dsn = postgres_server.get_uri(database="canon")
    apply_migrations(dsn, repo_root / "db" / "migrations")
    return dsn


@pytest.fixture
def postgres_dsn(migrated_dsn: str) -> str:
    """That database, emptied — every test starts from a schema with no rows."""
    import psycopg

    with psycopg.connect(migrated_dsn, autocommit=True) as connection:
        connection.execute("TRUNCATE assets, search_misses, idempotency_keys")
    return migrated_dsn
