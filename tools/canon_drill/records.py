"""The recovery ledger: what each procedure is expected to cost, and what it cost.

D9 is the whole of this module's reason to exist: *"a procedure nobody has
executed since it was written is a hope with formatting"*, and *"having the
drill write the record removes the step humans skip"*. So `deploy/recovery.md`
carries two tables — the procedures with their stated expected durations, and a
log the drill appends a line to every time it runs — and this reads both.

**The document is the ledger.** Not a database, not a JSON file beside it: the
runbook an on-call engineer opens at three in the morning is the same file the
staleness gate parses, so a procedure whose last run is six months old is
visible in the place somebody is already looking. The cost is a parser for two
markdown tables, which is this module, and it is cheap because the tables are
written by a machine.

Two failures the gate catches, and they fail for opposite reasons:

* **stale** — the most recent drill for a procedure is older than the stated
  interval, or there has never been one. The procedure is undrilled, so its
  duration is an assumption again;
* **overran** — the drill ran, and took longer than the procedure says it
  should. `add-coolify-deployment`'s risk register says what that means: *"a
  drill whose duration exceeds the stated expectation fails, which is the signal
  to change the architecture rather than the signal to add backups."*

Nothing here knows how to perform a recovery. :mod:`canon_drill.drills` runs
them, through the same entry points an operator runs by hand; this module only
reads and writes what they cost.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

LEDGER_PATH = Path("deploy") / "recovery.md"
"""The runbook and the ledger, which are deliberately the same file."""

INDEX_REBUILD = "index-rebuild"
BLOB_RE_MIRROR = "blob-re-mirror"
WORKING_COPY_RE_CLONE = "working-copy-re-clone"

PROCEDURES: tuple[str, ...] = (INDEX_REBUILD, BLOB_RE_MIRROR, WORKING_COPY_RE_CLONE)
"""One per persistent volume, which is what the specification asks for.

*"For each of the three persistent volumes there SHALL be a documented recovery
procedure with a stated expected duration."* Three volumes, three procedures,
and a fourth would mean a volume nobody wrote down.
"""

INTERVAL = timedelta(days=7)
"""How old the most recent drill may be before the gate fails (D9).

A week, because the thing being watched is *"rebuild duration grows silently
with asset count"* and a repository grows by the week. The document states the
same number, and a test asserts the two agree.
"""

DRILL_LOG_HEADING = "## Drill log"
PROCEDURES_HEADING = "## The three procedures"

_ROW = re.compile(r"^\|(?P<cells>.+)\|\s*$")
_DURATION = re.compile(r"^(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>[\d.]+)s)?$")

_UNIT_SECONDS = {"hours": 3600.0, "minutes": 60.0, "seconds": 1.0}


class LedgerMalformed(ValueError):
    """The document does not carry the tables the gate reads.

    A gate that quietly passed over a missing table would be the same failure it
    exists to catch: a procedure nobody checked, reported as fine.
    """


# --------------------------------------------------------------------------
# Durations: written by a machine, read by a person
# --------------------------------------------------------------------------


def parse_duration(written: str) -> timedelta:
    """`1.4s`, `12m`, `1h30m`, `3m12s` — whatever the tables are allowed to say."""
    matched = _DURATION.match(written.strip())
    if matched is None or not any(matched.groupdict().values()):
        raise LedgerMalformed(f"{written!r} is not a duration such as `90s`, `12m` or `1h30m`")
    total = sum(
        float(matched.group(unit)) * factor
        for unit, factor in _UNIT_SECONDS.items()
        if matched.group(unit) is not None
    )
    return timedelta(seconds=total)


def format_duration(elapsed: timedelta) -> str:
    """The shortest form that stays honest: seconds under a minute, else `NmSs`.

    Two decimals under a minute rather than one, because a fixture project
    recovers in hundredths and a record rounded to `0.0s` would be a record that
    the procedure took no time — which is the one thing it cannot have done.
    """
    total = elapsed.total_seconds()
    if total < 60:
        return f"{total:.2f}s"
    minutes, seconds = divmod(round(total), 60)
    return f"{minutes}m" if seconds == 0 else f"{minutes}m{seconds}s"


# --------------------------------------------------------------------------
# The two tables
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Expectation:
    """One procedure and what it is expected to cost."""

    procedure: str
    expected: timedelta


@dataclass(frozen=True)
class Drill:
    """One execution of one procedure: when it ran and what it took."""

    on: date
    procedure: str
    measured: timedelta
    environment: str = "pre-production"

    def row(self) -> str:
        return (
            f"| {self.on.isoformat()} | {self.procedure} | "
            f"{format_duration(self.measured)} | {self.environment} |"
        )


def _cells(line: str) -> tuple[str, ...] | None:
    matched = _ROW.match(line.strip())
    if matched is None:
        return None
    return tuple(cell.strip().strip("`") for cell in matched.group("cells").split("|"))


def _table_under(document: str, heading: str) -> tuple[tuple[str, ...], ...]:
    """Every data row of the first markdown table under `heading`."""
    if heading not in document:
        raise LedgerMalformed(f"{LEDGER_PATH} has no `{heading}` section")
    rest = document[document.index(heading) + len(heading) :]
    rows: list[tuple[str, ...]] = []
    for line in rest.splitlines():
        cells = _cells(line)
        if cells is None:
            if rows:
                break
            continue
        if not set("".join(cells)) <= set("-: "):
            rows.append(cells)
    return tuple(rows)


def expectations(document: str) -> tuple[Expectation, ...]:
    """What the runbook says each procedure should cost, in declared order."""
    found = {
        cells[0]: cells[-1]
        for cells in _table_under(document, PROCEDURES_HEADING)
        if cells[0] in PROCEDURES
    }
    missing = [name for name in PROCEDURES if name not in found]
    if missing:
        raise LedgerMalformed(f"{LEDGER_PATH} states no expected duration for {missing}")
    return tuple(
        Expectation(procedure=name, expected=parse_duration(found[name])) for name in PROCEDURES
    )


def drills(document: str) -> tuple[Drill, ...]:
    """Every recorded execution, oldest first as the log is appended to."""
    return tuple(
        Drill(
            on=date.fromisoformat(cells[0]),
            procedure=cells[1],
            measured=parse_duration(cells[2]),
            environment=cells[3] if len(cells) > 3 else "pre-production",
        )
        for cells in _table_under(document, DRILL_LOG_HEADING)
        if cells[0] not in {"Date", ""}
    )


def latest(recorded: Iterable[Drill], procedure: str) -> Drill | None:
    """The most recent execution of one procedure, or nothing if it never ran."""
    ran = [drill for drill in recorded if drill.procedure == procedure]
    return max(ran, key=lambda drill: drill.on) if ran else None


# --------------------------------------------------------------------------
# Appending: the drill writes its own record (D9)
# --------------------------------------------------------------------------


def appended(document: str, recorded: Sequence[Drill]) -> str:
    """The document with these executions added to the end of the drill log."""
    if DRILL_LOG_HEADING not in document:
        raise LedgerMalformed(f"{LEDGER_PATH} has no `{DRILL_LOG_HEADING}` section")
    lines = document.splitlines()
    last = max(
        index
        for index, line in enumerate(lines)
        if _cells(line) is not None and index > lines.index(DRILL_LOG_HEADING)
    )
    rows = [drill.row() for drill in recorded]
    return "\n".join([*lines[: last + 1], *rows, *lines[last + 1 :]]) + "\n"


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Complaint:
    """One reason the ledger fails its own check."""

    procedure: str
    reason: str

    def __str__(self) -> str:
        return f"{self.procedure}: {self.reason}"


def review(document: str, *, today: date, interval: timedelta = INTERVAL) -> tuple[Complaint, ...]:
    """Every procedure that is undrilled, overdue, or slower than it claims."""
    recorded = drills(document)
    return tuple(
        complaint
        for expectation in expectations(document)
        for complaint in _complaints_about(
            expectation, latest(recorded, expectation.procedure), today, interval
        )
    )


def _complaints_about(
    expectation: Expectation, most_recent: Drill | None, today: date, interval: timedelta
) -> tuple[Complaint, ...]:
    """The two ways one procedure fails, which fail for opposite reasons."""
    if most_recent is None:
        return (Complaint(expectation.procedure, "has never been drilled"),)
    age = today - most_recent.on
    found: list[Complaint] = []
    if age > interval:
        found.append(
            Complaint(
                expectation.procedure,
                f"was last drilled on {most_recent.on.isoformat()}, {age.days} days ago, "
                f"and the stated interval is {interval.days} days",
            )
        )
    if most_recent.measured > expectation.expected:
        found.append(
            Complaint(
                expectation.procedure,
                f"took {format_duration(most_recent.measured)} on "
                f"{most_recent.on.isoformat()}, over the stated "
                f"{format_duration(expectation.expected)}",
            )
        )
    return tuple(found)


__all__ = [
    "BLOB_RE_MIRROR",
    "DRILL_LOG_HEADING",
    "INDEX_REBUILD",
    "INTERVAL",
    "LEDGER_PATH",
    "PROCEDURES",
    "PROCEDURES_HEADING",
    "WORKING_COPY_RE_CLONE",
    "Complaint",
    "Drill",
    "Expectation",
    "LedgerMalformed",
    "appended",
    "drills",
    "expectations",
    "format_duration",
    "latest",
    "parse_duration",
    "review",
]
