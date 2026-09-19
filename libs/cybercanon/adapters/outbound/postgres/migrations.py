"""The migration runner — a release step, never something a read triggers.

`project.md` states both halves: *"Database migrations run as a release step,
and the index schema is droppable-and-rebuildable by definition, which makes a
failed migration recoverable by rebuilding rather than by restoring a backup."*
So this module applies ordered `.sql` files and records which ones it applied,
and it is invoked by `just migrate` — not by the adapter, not on connect, and
not by a request.

Why the adapter does not create its own schema: a store that creates its tables
on connect makes task 6.2's guarantee unobservable. *"A migration applied to an
empty database yields a schema the rebuild populates without manual
intervention"* is only a claim you can test if there is a moment when the
database is empty and the adapter has already been constructed. Self-creating
schemas also silently diverge per deployment, which is the failure the committed
lock file exists to prevent one layer down.

Three properties, and each is a test:

* **Ordered.** Files are applied in the sort order of their names, which is why
  they are numbered.
* **Idempotent.** An applied version is recorded in `schema_migrations`, so
  running the step twice applies nothing the second time. A release step that
  could not be re-run would make a retried deploy a data-loss event.
* **One transaction per file.** A file that fails leaves nothing of itself
  behind, so the recorded set always describes the schema that is actually
  there.

`deployment-operations` adds a fourth, and it is the one that makes this a
*release step* rather than a script: **a failed migration leaves the schema at a
recorded version the runner can report.** PostgreSQL's transactional DDL gives
the first half; :class:`MigrationFailed` and :func:`recorded_version` give the
second, so the operator's next decision — retry, or drop and rebuild — is made
against a number the runner printed rather than against a guess. And because the
index is rebuildable by definition, the recovery for a schema no migration can
advance is :func:`drop_schema` followed by this runner and a rebuild: D5's
`drop → migrate → rebuild`, with no backup anywhere in it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg

from cybercanon.application.errors import FailureKind, OperationFailed

DEFAULT_DIRECTORY = Path("db/migrations")
"""Where the migration set lives, relative to the repository or image root.

`project.md` puts it there (`db/migrations/ # SQL migrations for the cache/index`),
and the release step runs from that root — which is also why the path is a
parameter everywhere below rather than a constant somebody has to patch.
"""

SUFFIX = ".sql"

NO_VERSION = ""
"""What the schema version reads as before any migration has been applied."""

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text        PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""
"""The one statement this module owns. Everything else is a file on disk."""


class MigrationFailed(OperationFailed):
    """One migration file could not be applied, and the release must not continue.

    It carries the two facts the specification asks the release step to report:
    **which file failed**, and **the version the schema is now at** — the last
    file that completed, which is exactly what the ledger holds because each
    file lands in its own transaction. An operator reading this knows whether to
    fix the file and re-run, or to drop and rebuild.

    The database's own complaint travels as `detail` and is never the message:
    a connection string in a `psycopg` error is a credential, and a release log
    is not where one belongs.
    """

    kind = FailureKind.INVALID
    identifier = "migration.failed"

    def __init__(self, version: str, at_version: str, detail: str = "") -> None:
        super().__init__(
            f"{version} could not be applied; the schema is at "
            f"{at_version or 'no applied migration'} and the release must not continue",
            version,
        )
        self.version = version
        self.at_version = at_version
        self.detail = detail


@dataclass(frozen=True)
class Migration:
    """One numbered file, and the statements it carries."""

    version: str
    path: Path

    @property
    def statements(self) -> str:
        return self.path.read_text(encoding="utf-8")


@dataclass(frozen=True)
class MigrationReport:
    """What the release step did: what it applied, and what was already there."""

    applied: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()

    @property
    def changed_anything(self) -> bool:
        return bool(self.applied)

    def __str__(self) -> str:
        applied = ", ".join(self.applied) or "nothing"
        return f"applied {applied}; {len(self.skipped)} already present"


def migrations_in(directory: Path | str = DEFAULT_DIRECTORY) -> tuple[Migration, ...]:
    """Every migration under that directory, in the order it is applied.

    Sorted by file name, which is why the files are numbered: a directory
    listing is not an order, and "whatever the file system returned" is not a
    schema.
    """
    root = Path(directory)
    return tuple(
        Migration(version=path.name, path=path) for path in sorted(root.glob(f"*{SUFFIX}"))
    )


def applied_versions(connection: psycopg.Connection) -> frozenset[str]:
    """Which migrations this database already carries."""
    connection.execute(LEDGER)
    rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    return frozenset(str(row[0]) for row in rows)


def recorded_version(connection: psycopg.Connection) -> str:
    """The version this schema is at: the last file that completed, or nothing.

    "Last" is the highest recorded name, which is the applied order because the
    files are numbered — the same reason :func:`migrations_in` sorts. After a
    failure this is the answer to *"which migrations have been applied"*, and it
    is a fact in the database rather than something the runner remembered.
    """
    applied = applied_versions(connection)
    return max(applied) if applied else NO_VERSION


def schema_version(dsn: str) -> str:
    """That version, for a caller holding a connection string and no connection."""
    with psycopg.connect(dsn) as connection:
        return recorded_version(connection)


def apply_migrations(dsn: str, directory: Path | str = DEFAULT_DIRECTORY) -> MigrationReport:
    """Bring this database up to the migration set, and say what that took.

    The connection is **autocommit**, which is what makes *"one transaction per
    file"* true rather than decorative: inside an already-open transaction,
    `psycopg` turns :meth:`~psycopg.Connection.transaction` into a savepoint, so
    a file that failed would roll back every file before it and the schema would
    be left at a version the ledger no longer records. Autocommit makes each
    file its own top-level transaction, and the recorded version after a failure
    is the schema that is really there.
    """
    with psycopg.connect(dsn, autocommit=True) as connection:
        return apply_to(connection, migrations_in(directory))


def apply_to(connection: psycopg.Connection, migrations: Sequence[Migration]) -> MigrationReport:
    """Apply the ones this database does not have, each in its own transaction."""
    present = applied_versions(connection)
    applied: list[str] = []
    for migration in migrations:
        if migration.version in present:
            continue
        _apply_one(connection, migration)
        applied.append(migration.version)
    return MigrationReport(
        applied=tuple(applied),
        skipped=tuple(m.version for m in migrations if m.version in present),
    )


def _apply_one(connection: psycopg.Connection, migration: Migration) -> None:
    """One file, one transaction: it lands whole or it does not land.

    A file the database refuses is re-raised as :class:`MigrationFailed` naming
    the version the schema is left at. The transaction has already rolled back
    by the time this reads the ledger, so the number it reports is the schema
    that is really there — which is the whole of *"left at a recorded version
    that the runner can report"*.
    """
    try:
        with connection.transaction():
            connection.execute(migration.statements)
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", [migration.version]
            )
    except psycopg.Error as failure:
        raise MigrationFailed(
            migration.version, recorded_version(connection), str(failure).strip()
        ) from failure


# --------------------------------------------------------------------------
# D5 — there are no backups, so recovery starts by dropping what is there
# --------------------------------------------------------------------------

CREATES = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?([a-z0-9_]+)", re.IGNORECASE)
"""How a migration announces a table, over SQL with its commentary removed."""

COMMENT = "--"

LEDGER_TABLE = "schema_migrations"


def tables_in(migrations: Sequence[Migration]) -> tuple[str, ...]:
    """Every table the migration set creates, plus the ledger, in drop order.

    Read out of the SQL rather than listed in Python, because a second list is a
    list that goes out of date: a migration adding a table nobody added here
    would survive a drop, and the rebuild would then populate a schema carrying
    a row from before the loss. Reversed, so a table is dropped before anything
    it was created after — belt to `CASCADE`'s braces.
    """
    found: list[str] = []
    for migration in migrations:
        for name in CREATES.findall(_without_commentary(migration.statements)):
            if name not in found:
                found.append(name)
    return (*reversed(found), LEDGER_TABLE)


def _without_commentary(sql: str) -> str:
    """That SQL with its `--` commentary dropped.

    Every migration in this project opens with the paragraph explaining why the
    table exists, and those paragraphs contain semicolons and the words this
    reads for — so the prose goes before anything is looked for in the SQL.
    """
    return "\n".join(line.split(COMMENT, 1)[0] for line in sql.splitlines())


def drop_schema(dsn: str, directory: Path | str = DEFAULT_DIRECTORY) -> tuple[str, ...]:
    """Discard the index entirely — the first step of `drop → migrate → rebuild`.

    Deliberately not a "reset": nothing is preserved, nothing is dumped first,
    and the ledger goes too, so the next run of the release step applies the set
    from scratch. A restore path would make the index authoritative in practice
    even while `project.md` says it is not (D5).
    """
    dropped = tables_in(migrations_in(directory))
    with psycopg.connect(dsn, autocommit=True) as connection:
        for table in dropped:
            connection.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    return dropped


__all__ = [
    "DEFAULT_DIRECTORY",
    "LEDGER",
    "LEDGER_TABLE",
    "NO_VERSION",
    "Migration",
    "MigrationFailed",
    "MigrationReport",
    "applied_versions",
    "apply_migrations",
    "apply_to",
    "drop_schema",
    "migrations_in",
    "recorded_version",
    "schema_version",
    "tables_in",
]
