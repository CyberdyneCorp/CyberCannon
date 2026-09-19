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
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from cybercanon.adapters.outbound.postgres.migrations import (
    DEFAULT_DIRECTORY,
    MigrationReport,
    apply_migrations,
)
from cybercanon.adapters.wiring.configuration import load


def run(
    arguments: Sequence[str] = (), environment: Mapping[str, str] | None = None
) -> MigrationReport:
    """Apply the migration set to the configured database."""
    directory = Path(arguments[0]) if arguments else DEFAULT_DIRECTORY
    configuration = load(environment)
    return apply_migrations(configuration.storage.database_url.value, directory)


def main(arguments: Sequence[str] | None = None) -> None:  # pragma: no cover — a process
    report = run(sys.argv[1:] if arguments is None else arguments)
    print(report)


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    main()
