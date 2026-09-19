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
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg

DEFAULT_DIRECTORY = Path("db/migrations")
"""Where the migration set lives, relative to the repository or image root.

`project.md` puts it there (`db/migrations/ # SQL migrations for the cache/index`),
and the release step runs from that root — which is also why the path is a
parameter everywhere below rather than a constant somebody has to patch.
"""

SUFFIX = ".sql"

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text        PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""
"""The one statement this module owns. Everything else is a file on disk."""


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


def apply_migrations(dsn: str, directory: Path | str = DEFAULT_DIRECTORY) -> MigrationReport:
    """Bring this database up to the migration set, and say what that took."""
    with psycopg.connect(dsn) as connection:
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
    """One file, one transaction: it lands whole or it does not land."""
    with connection.transaction():
        connection.execute(migration.statements)
        connection.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s)", [migration.version]
        )


__all__ = [
    "DEFAULT_DIRECTORY",
    "LEDGER",
    "Migration",
    "MigrationReport",
    "applied_versions",
    "apply_migrations",
    "apply_to",
    "migrations_in",
]
