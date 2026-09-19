"""`drop → migrate → rebuild` — the recovery, and the only one there is (D5).

There is no index backup and there will not be one. `project.md` calls
PostgreSQL *"a rebuildable index"*, and `deployment-operations` spells out what
that costs and what it buys: *"the index SHALL be discarded, recreated at the
target schema version and rebuilt from the working copies"*, and *"the recovery
SHALL NOT require a database backup"*. D5 says why a restore path is refused
rather than merely unimplemented — the first time a restore is chosen over a
rebuild, the rebuild path rots and the claim that the index is a cache quietly
stops being true.

So this is the whole procedure, in the order an operator runs it:

1. **drop** — every table the migration set creates, ledger included, so the
   next step starts from an empty database rather than from whatever state no
   migration could advance;
2. **migrate** — the ordinary release step (`python -m cybercanon.api.migrate`),
   which is what makes the recovered schema the *target* version rather than the
   version the broken database happened to be at;
3. **rebuild** — per project, from its working copy, through the same
   `rebuild_index` use case the hosted service and `canon index` call. The
   working copy is the source: git is where the specifications live, and a
   rebuild that read anything else would be restoring, not rebuilding.

It takes the working copies as arguments rather than from the environment
because it is an *operation*, run against the volume an operator names, and
because the service does not otherwise need to know that the recovery exists.
The database is read from the same configuration the service reads, so a
recovery cannot rebuild one database while the service serves another.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.postgres.migrations import (
    DEFAULT_DIRECTORY,
    apply_migrations,
    drop_schema,
)
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.wiring.build import file_fingerprints
from cybercanon.api.migrate import database_url
from cybercanon.application.results import Ok
from cybercanon.application.use_cases.index_assets import (
    Progress,
    RebuildProgress,
    RebuildReport,
    no_progress,
    rebuild_index,
)


@dataclass(frozen=True)
class RecoveryReport:
    """What the recovery did: what it discarded, applied and rebuilt.

    Printed by the command, because a recovery whose output is silence is one
    nobody can tell finished — and because the rebuilt counts are the number
    `deploy/recovery.md` asks a drill to record.
    """

    dropped: tuple[str, ...] = ()
    applied: tuple[str, ...] = ()
    rebuilt: tuple[RebuildReport, ...] = ()

    @property
    def indexed(self) -> int:
        return sum(report.indexed_count for report in self.rebuilt)

    def __str__(self) -> str:
        applied = ", ".join(self.applied) or "nothing"
        return (
            f"dropped {len(self.dropped)} table(s); applied {applied}; "
            f"rebuilt {len(self.rebuilt)} project(s), {self.indexed} asset(s)"
        )


def rebuild_from(
    root: Path | str,
    *,
    dsn: str,
    progress: Progress = no_progress,
) -> RebuildReport:
    """Rebuild one project's index from the working copy at `root`.

    The same use case the command line runs, over the hosted store: *"the HTTP
    surface is a thin adapter over the SAME use cases"*, and a recovery that
    reindexed through a second implementation would recover a different index
    from the one it lost.
    """
    spec_store = GitSpecStore(root)
    with PostgresSearchIndex(dsn) as search_index:
        outcome = rebuild_index(
            "",
            spec_store=spec_store,
            search_index=search_index,
            fingerprints=file_fingerprints(spec_store.root),
            progress=progress,
        )
    if isinstance(outcome, Ok):
        return outcome.value
    raise RuntimeError(outcome.message)


def recover(
    roots: Sequence[Path | str],
    *,
    environment: Mapping[str, str] | None = None,
    directory: Path | str = DEFAULT_DIRECTORY,
    dsn: str = "",
    progress: Progress = no_progress,
) -> RecoveryReport:
    """Drop the index, migrate to the target version, rebuild from the copies."""
    url = dsn or database_url(environment)
    dropped = drop_schema(url, directory)
    applied = apply_migrations(url, directory)
    return RecoveryReport(
        dropped=dropped,
        applied=applied.applied,
        rebuilt=tuple(rebuild_from(root, dsn=url, progress=progress) for root in roots),
    )


def announce(progress: RebuildProgress) -> None:  # pragma: no cover — a process
    """One line per asset, so a long rebuild is visibly a rebuild and not a hang."""
    print(f"  {progress.done}/{progress.total} {progress.path}", flush=True)


def main(
    arguments: Sequence[str] | None = None, environment: Mapping[str, str] | None = None
) -> int:  # pragma: no cover — exercised as a subprocess
    """Run the recovery over the working copies named on the command line."""
    roots = [Path(argument) for argument in (sys.argv[1:] if arguments is None else arguments)]
    if not roots:
        print("usage: python -m cybercanon.api.recover <working copy>...", file=sys.stderr)
        return 2
    print(recover(roots, environment=environment, progress=announce))
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    raise SystemExit(main())
