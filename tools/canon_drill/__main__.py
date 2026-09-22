"""The scheduled drill and the staleness gate — two commands, two exit codes.

D9: *"A scheduled job destroys a pre-production volume, runs the documented
procedure, measures the elapsed time and appends date, procedure and duration to
`deploy/recovery.md`. A drill older than its stated interval is a failing
check."* Those are the two commands, and they are deliberately different kinds
of thing:

* ``run`` **performs** the three recoveries against a pre-production project and
  writes what they cost. It needs that environment, so it is the platform's
  scheduled job and nothing else runs it;
* ``check`` **reads** the ledger and fails when a procedure is undrilled,
  overdue, or slower than the runbook says it is. It touches nothing, needs no
  database and no network, so it runs on every `just check` from a plain
  checkout — which is the point. A gate that only the scheduler could evaluate
  would be a gate nobody sees fail.

**Why `run` takes paths rather than reading them from configuration.** The
pre-production project's three volumes are a thing an operator names when
scheduling the job; a command that inferred them from the service's own
environment would be a command that could destroy the *service's* volumes
because somebody ran it in the wrong container. The database is the one
exception, read from `CANON_DATABASE_URL` like `migrate` and `recover`, because
a drill that rebuilt one database while the environment served another would be
measuring nothing.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TextIO

from canon_drill.drills import Environment, records_for, run_drills, summary
from canon_drill.records import (
    LEDGER_PATH,
    Complaint,
    LedgerMalformed,
    appended,
    format_duration,
    review,
)

RUN = "run"
CHECK = "check"

FAILED = 1
"""What a scheduled job or a gate exits with when the claim is not true."""


def today() -> date:
    """The drill's own date, in UTC, because the log is read across time zones."""
    return datetime.now(UTC).date()


# --------------------------------------------------------------------------
# run — perform the three procedures and write down what they cost
# --------------------------------------------------------------------------


def run_and_record(
    environment: Environment,
    *,
    ledger: Path,
    on: date | None = None,
    out: TextIO = sys.stdout,
) -> tuple[str, ...]:
    """Run all three, append one line per procedure, and say what happened.

    The record is written by the drill rather than by the person who ran it,
    which is D9's entire argument: *"having the drill write the record removes
    the step humans skip."*
    """
    measured = run_drills(environment)
    recorded = records_for(measured, on=on or today(), environment=environment.name)
    ledger.write_text(appended(ledger.read_text(encoding="utf-8"), recorded), encoding="utf-8")
    for procedure, elapsed in summary(measured).items():
        print(f"{procedure}: {format_duration(elapsed)}", file=out)
    return tuple(drill.row() for drill in recorded)


# --------------------------------------------------------------------------
# check — the gate, runnable from a checkout
# --------------------------------------------------------------------------


def check(ledger: Path, *, on: date | None = None, out: TextIO = sys.stdout) -> int:
    """Zero when every procedure is drilled, recent and within its expectation."""
    try:
        complaints: Sequence[Complaint] = review(
            ledger.read_text(encoding="utf-8"), today=on or today()
        )
    except (OSError, LedgerMalformed) as unreadable:
        print(f"{ledger}: {unreadable}", file=sys.stderr)
        return FAILED
    for complaint in complaints:
        print(str(complaint), file=sys.stderr)
    if complaints:
        print(
            f"{len(complaints)} recovery procedure(s) are undrilled, overdue or slower "
            "than stated; a procedure nobody has executed is an assumption",
            file=sys.stderr,
        )
        return FAILED
    print(f"{ledger}: every procedure is drilled, recent and within its expectation", file=out)
    return 0


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    parsed = argparse.ArgumentParser(prog="canon_drill", description=__doc__)
    commands = parsed.add_subparsers(dest="command", required=True)
    commands.add_parser(CHECK, help="fail when a drill is overdue or overran")
    running = commands.add_parser(RUN, help="run the three procedures and record them")
    running.add_argument("--project", required=True)
    running.add_argument("--working-copy", required=True, type=Path)
    running.add_argument("--blobs", required=True, type=Path)
    for command in (parsed, commands.choices[CHECK], running):
        command.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    return parsed


def environment_for(
    project: str,
    working_copy: Path,
    blobs: Path,
    *,
    dsn: str = "",
) -> Environment:
    """One pre-production project's three volumes, as ports over real adapters.

    Built here rather than taken from the service's own composition root for the
    reason the module docstring gives: this command destroys volumes, and a
    command that inferred which ones could destroy the wrong ones. The imports
    are local because `check` — the half that runs on every build — must not
    need a database driver to be installed to tell somebody a drill is overdue.
    """
    from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
    from cybercanon.adapters.outbound.git.repository_host import GitRepositoryHost, ProjectRemote
    from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
    from cybercanon.adapters.wiring.configuration import load
    from cybercanon.api import recover as recovery
    from cybercanon.application.use_cases.blob_mirror import mirror_project

    configured = load()
    host = GitRepositoryHost(
        working_copy.parent,
        [
            ProjectRemote(
                project=project,
                url=configured.repository.url,
                branch=configured.repository.branch,
            )
        ],
    )
    url = dsn or configured.storage.database_url.value

    return Environment(
        project=project,
        working_copy=working_copy,
        blob_volume=blobs,
        re_clone=lambda: host.recover(project),
        rebuild_index=lambda: recovery.recover([working_copy], dsn=url),
        re_mirror_blobs=lambda: mirror_project(
            project,
            repository_host=host,
            spec_store=GitSpecStore(working_copy),
            blob_store=FsBlobStore(blobs),
        ),
    )


def main(arguments: Sequence[str] | None = None) -> int:  # pragma: no cover — a process
    """`check` anywhere; `run` only where a pre-production environment exists."""
    parsed = parser().parse_args(list(sys.argv[1:] if arguments is None else arguments))
    if parsed.command == CHECK:
        return check(parsed.ledger)
    run_and_record(
        environment_for(parsed.project, parsed.working_copy, parsed.blobs),
        ledger=parsed.ledger,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    raise SystemExit(main())
