"""The release step: bring the index schema up to the migration set.

`project.md`: *"Database migrations run as a release step, and the index schema
is droppable-and-rebuildable by definition, which makes a failed migration
recoverable by rebuilding rather than by restoring a backup."* This is that
step, reachable as `just migrate` and as `python -m cybercanon.api.migrate`,
which is the same command the image runs before the new version starts serving.

It reads the database URL from the same configuration the service reads, so a
deployment cannot migrate one database and serve another. It prints what it
applied, because a release step whose output is silence is a release step nobody
can tell ran.

**Its exit code is the release gate** (task 4.3). Coolify runs this as the
pre-deploy command on the API image; a non-zero exit aborts the release, so no
instance of the new version ever starts and the previous one keeps serving.
That is why a failed migration is reported here rather than raised through a
traceback: the message names the file that failed and the version the schema is
now at, which is the operator's next decision — retry, or `drop → migrate →
rebuild` (D5, `python -m cybercanon.api.recover`).

`--schema-version` asks the same question on its own, for the case the
specification names: *"given a migration failed partway through a release, when
the schema version is queried, it SHALL report a recorded version"*.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from cybercanon.adapters.outbound.postgres.migrations import (
    DEFAULT_DIRECTORY,
    MigrationFailed,
    MigrationReport,
    apply_migrations,
    schema_version,
)
from cybercanon.adapters.wiring.configuration import load

VERSION_FLAG = "--schema-version"
"""Report the version the schema is at and apply nothing."""

FAILED = 1
"""What the release step exits with when the schema could not be advanced."""


def directory_in(arguments: Sequence[str]) -> Path:
    """Which migration set to apply — the deployed one unless one was named."""
    named = [argument for argument in arguments if not argument.startswith("-")]
    return Path(named[0]) if named else DEFAULT_DIRECTORY


def database_url(environment: Mapping[str, str] | None = None) -> str:
    """The database this deployment serves, read the way the service reads it."""
    return load(environment).storage.database_url.value


def run(
    arguments: Sequence[str] = (), environment: Mapping[str, str] | None = None
) -> MigrationReport:
    """Apply the migration set to the configured database."""
    return apply_migrations(database_url(environment), directory_in(arguments))


def version(environment: Mapping[str, str] | None = None) -> str:
    """The version the configured database's schema is recorded at."""
    return schema_version(database_url(environment))


def main(
    arguments: Sequence[str] | None = None, environment: Mapping[str, str] | None = None
) -> int:
    """Run the release step, and answer with the code that gates the release."""
    given = tuple(sys.argv[1:] if arguments is None else arguments)
    if VERSION_FLAG in given:
        print(version(environment) or "no applied migration")
        return 0
    try:
        print(run(given, environment))
    except MigrationFailed as failure:
        print(failure.message, file=sys.stderr)
        return FAILED
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    raise SystemExit(main())
