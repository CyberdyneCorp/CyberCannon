"""Running the three recovery procedures, and timing them (D9, task 7.5).

*"A scheduled job destroys a pre-production volume, runs the documented
procedure, measures the elapsed time and appends date, procedure and duration to
`deploy/recovery.md`."* This is that job, minus the schedule, which is the
platform's.

**Nothing here is a recovery.** Each drill destroys one volume and then calls
the entry point an operator calls by hand — `repository_host.recover` for a
working copy, `cybercanon.api.recover` for the index, `mirror_project` for the
blobs — because a drill that reimplemented the procedure would be drilling
itself. What this module adds is exactly three things a person does badly: it
destroys the volume first (so the procedure runs against a real loss rather than
against a warm cache), it measures, and it writes the record down.

**Ports, not URLs.** :func:`run_drills` takes the working copies, the database
and the blob store it was handed. That is what lets the suite run it against
real git, a real PostgreSQL and a real S3 API with nothing configured, and it is
also what stops this module growing a second opinion about how the service
connects to anything.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from canon_drill.records import (
    BLOB_RE_MIRROR,
    INDEX_REBUILD,
    WORKING_COPY_RE_CLONE,
    Drill,
)

type Procedure = Callable[[], object]


@dataclass(frozen=True)
class Timed:
    """One procedure, run against a destroyed volume, and what it cost."""

    procedure: str
    measured: timedelta
    detail: str = ""

    def recorded(self, on: date, environment: str) -> Drill:
        return Drill(
            on=on, procedure=self.procedure, measured=self.measured, environment=environment
        )


def timed(procedure: str, destroy: Procedure, recover: Procedure) -> Timed:
    """Destroy the volume, run the procedure, and measure only the procedure.

    The destruction is deliberately outside the measurement: what an operator
    waits for is the recovery, and a number that included deleting a directory
    would be a number about the wrong thing.
    """
    destroy()
    started = time.monotonic()
    outcome = recover()
    return Timed(
        procedure=procedure,
        measured=timedelta(seconds=time.monotonic() - started),
        detail=str(outcome) if outcome is not None else "",
    )


@dataclass
class Environment:
    """What one pre-production project's three volumes are, and how to reach them.

    `working_copies` is the volume the other two recover *from*, which is why
    the working-copy drill runs first when all three run together: the index and
    the blob mirror have no other source, so a drill order that rebuilt the index
    from a copy that had just been deleted would be measuring an error path.
    """

    project: str
    working_copy: Path
    re_clone: Procedure
    rebuild_index: Procedure
    re_mirror_blobs: Procedure
    blob_volume: Path | None = None
    drop_blobs: Procedure | None = None
    name: str = "pre-production"
    destroyed: list[str] = field(default_factory=list)

    def destroy_working_copy(self) -> None:
        """Delete the volume, so the procedure runs against a real loss."""
        shutil.rmtree(self.working_copy, ignore_errors=True)
        self.destroyed.append(WORKING_COPY_RE_CLONE)

    def destroy_blobs(self) -> None:
        """Empty the blob volume, however this environment holds it."""
        if self.drop_blobs is not None:
            self.drop_blobs()
        elif self.blob_volume is not None:
            shutil.rmtree(self.blob_volume, ignore_errors=True)
        self.destroyed.append(BLOB_RE_MIRROR)


def working_copy_drill(environment: Environment) -> Timed:
    """Delete the working-copy volume and re-clone it from the git host."""
    return timed(WORKING_COPY_RE_CLONE, environment.destroy_working_copy, environment.re_clone)


def index_drill(environment: Environment) -> Timed:
    """`drop → migrate → rebuild`, with no backup anywhere in it (D5).

    The destruction is the drop the procedure itself performs, so there is
    nothing to delete first: a schema that is dropped and recreated is exactly
    the loss this recovers from.
    """
    return timed(INDEX_REBUILD, lambda: None, environment.rebuild_index)


def blob_drill(environment: Environment) -> Timed:
    """Empty the blob volume and re-mirror it from the working copy."""
    return timed(BLOB_RE_MIRROR, environment.destroy_blobs, environment.re_mirror_blobs)


DRILLS: tuple[Callable[[Environment], Timed], ...] = (
    working_copy_drill,
    index_drill,
    blob_drill,
)
"""In the order the volumes depend on each other: the copy, then what derives from it."""


def run_drills(environment: Environment) -> tuple[Timed, ...]:
    """All three, against one pre-production project, each measured on its own."""
    return tuple(drill(environment) for drill in DRILLS)


def records_for(
    measured: Sequence[Timed], *, on: date, environment: str = "pre-production"
) -> tuple[Drill, ...]:
    """The lines the drill appends to `deploy/recovery.md` (D9)."""
    return tuple(one.recorded(on, environment) for one in measured)


def summary(measured: Sequence[Timed]) -> Mapping[str, timedelta]:
    """What each procedure took, for a job whose output somebody reads."""
    return {one.procedure: one.measured for one in measured}


__all__ = [
    "DRILLS",
    "Environment",
    "Timed",
    "blob_drill",
    "index_drill",
    "records_for",
    "run_drills",
    "summary",
    "timed",
    "working_copy_drill",
]
