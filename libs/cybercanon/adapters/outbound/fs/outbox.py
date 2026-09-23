"""The local report outbox — a file, an attempt, and a retry later (D6, D7).

`report_export` must succeed whether or not anything is listening. The
requirement is absolute — *"a failure to deliver a reported outcome SHALL NOT
change a verdict, SHALL NOT block a commit, SHALL NOT fail a local validation
run, and SHALL NOT block or error the automated caller"* — and the only
construction under which that survives a pre-commit hook is one where the call's
success does not depend on delivery at all. So:

* **the outcome is written down first, and delivered second.** What cannot be
  delivered stays in the file and is retried on the next report and by `canon
  report flush`. There is no queue, no broker and no daemon: D6 settles that in
  as many words — *"the retry mechanism is a file and an opportunistic flush"*;
* **the file is keyed on D7's triple**, so a restarted agent reporting the same
  run replaces its record instead of appending a copy. Deduplicating only at the
  destination was rejected precisely because *"it leaves the outbox itself
  growing copies and makes the local `canon report flush` output misleading"*;
* **a line that will not parse is reported and skipped**, never fatal. An outbox
  that refused to deliver ten good reports because an eleventh line was truncated
  by a full disk would have turned a cosmetic failure into a silent outage;
* **the file is bounded.** :data:`CAPACITY` records, oldest dropped first, so a
  machine that has never been able to reach a destination does not grow a file
  without limit. Outcomes are telemetry and the verdict is authoritative
  locally — D6 accepts that they *"can be permanently lost with the machine"*.

It lives under `.canon/` beside the index and the query log, which are already
git-ignored derived state, and the same `.gitignore` entry keeps it out of
`git status`. That matters more here than for a cache: a delivered report is a
fact about a verdict, and committing one would put a *second* copy of it in the
repository beside the `asset.validation.json` that G2 makes the real one.

The record's field names are deliberately the ones
:func:`~cybercanon.application.use_cases.validation_records.to_document` uses
for the same facts — `asset`, `export`, `export_hash`, `passed`, `errors`,
`warnings`, `attributed_to`. One outcome, one vocabulary, whichever file it is
sitting in.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path

from cybercanon.application.ports.outcome_reporter import (
    Delivery,
    OutcomeReportUnavailable,
    ReportedOutcome,
)

CANON_DIRECTORY = ".canon"
OUTBOX_FILENAME = "reports.ndjson"
OUTBOX_PATH = f"{CANON_DIRECTORY}/{OUTBOX_FILENAME}"
"""Where retained reports wait, relative to the working copy's root.

Newline-delimited JSON because the file is appended to under failure and read
back under recovery: one corrupt line costs one record, where one corrupt
document would cost the file.
"""

CAPACITY = 1000
"""How many retained reports the file keeps. The oldest are dropped first."""

NO_DESTINATION = (
    "no reporting destination is configured on this machine, so the outcome is "
    "retained and will be delivered when one is"
)
"""What a local-only machine is told. Not an error: it is the ordinary case.

A laptop with no server to report to is the machine `canon validate` is built
for, and a reporting path that treated it as broken would be the identity
requirement the validator is forbidden to acquire, arriving through the back
door.
"""

SKIPPED = "{count} unreadable record(s) in the outbox were skipped"
"""What a corrupt line costs: itself, and a sentence. Never the rest of the file."""


type Destination = Callable[[ReportedOutcome], None]
"""Where a retained outcome is delivered, when there is somewhere to deliver it.

Injected by the composition root (D1), so the outbox knows nothing about HTTP,
about a repository or about who ends up holding the record. A destination
signals an outage by raising; the outbox catches it, keeps the outcome, and
answers. It is never asked to be idempotent by *this* layer — D7's triple is
what makes a retry safe at both ends.
"""


class FileOutbox:
    """Retained outcomes in one newline-delimited file, delivered when possible."""

    def __init__(
        self,
        root: str | Path,
        *,
        deliver: Destination | None = None,
        path: str | Path | None = None,
        capacity: int = CAPACITY,
    ) -> None:
        """Keep the outbox under `root`, delivering through `deliver` when given.

        `deliver` of ``None`` is a machine with nowhere to report — the ordinary
        local case — and everything is retained. That is a state, not a failure:
        nothing about it stops a verdict, a commit or an agent.
        """
        self._path = Path(path) if path else Path(root) / OUTBOX_PATH
        self._deliver = deliver
        self._capacity = max(1, capacity)
        self.skipped: tuple[str, ...] = ()
        """The lines the last read could not parse. Reported, never fatal (3.6)."""

    @property
    def path(self) -> Path:
        """The file retained reports live in — git-ignored, and outside the canon."""
        return self._path

    @property
    def description(self) -> str:
        """How a message names this outbox to a person."""
        return str(self._path)

    # -- port ------------------------------------------------------------

    def report(self, outcome: ReportedOutcome) -> Delivery:
        """Retain this outcome, then try to deliver everything retained.

        Retained **first**, so a delivery that dies halfway — or a process that
        does — leaves the outcome where the next flush will find it. The answer
        says what happened; it never says *no*.
        """
        self.skipped = ()
        self._retain(outcome)
        return self._flush()

    def pending(self) -> tuple[ReportedOutcome, ...]:
        """Every outcome still waiting, oldest first."""
        self.skipped = ()
        return tuple(self._read())

    def flush(self) -> Delivery:
        """Try to deliver everything retained. What could not be sent stays."""
        self.skipped = ()
        return self._flush()

    def _flush(self) -> Delivery:
        """One delivery pass, keeping whatever the operation has skipped so far.

        Separate from :meth:`flush` so that a report which *drops* a corrupt
        line while retaining still tells the caller it happened. Rewriting the
        file removes the bad line — that is the self-healing half — and a pass
        that then reported nothing would have healed it silently, which is the
        half that matters to whoever has to find out why an outcome vanished.
        """
        retained = list(self._read())
        skipped = self.skipped
        if not retained:
            return Delivery(delivered=0, pending=0, reason=_note(skipped))
        delivered, kept = self._attempt(retained)
        self._write(kept)
        return Delivery(
            delivered=len(delivered),
            pending=len(kept),
            reason=_reason(kept, skipped, self._deliver),
        )

    # -- delivery --------------------------------------------------------

    def _attempt(
        self, retained: Sequence[ReportedOutcome]
    ) -> tuple[list[ReportedOutcome], list[ReportedOutcome]]:
        """One pass over the outbox: what went, and what is still here.

        A destination that fails stops the pass. Trying the rest after one
        refusal would turn a server's bad afternoon into one failed request per
        retained report, which is how an agent's next call becomes slow rather
        than instant.
        """
        if self._deliver is None:
            return [], list(retained)
        delivered: list[ReportedOutcome] = []
        for index, outcome in enumerate(retained):
            if not self._sent(outcome):
                return delivered, list(retained[index:])
            delivered.append(outcome)
        return delivered, []

    def _sent(self, outcome: ReportedOutcome) -> bool:
        """Whether the destination took it. Never raises, whatever it did.

        The blanket catch is the decision, not an oversight: a report that can
        raise is a report that eventually fails a commit, and *every* way a
        destination can fail — a refusal, a socket, a library nobody expected to
        throw — has to come out of here as *not yet delivered*.
        """
        if self._deliver is None:
            return False
        try:
            self._deliver(outcome)
        except Exception:
            return False
        return True

    # -- the file --------------------------------------------------------

    def _retain(self, outcome: ReportedOutcome) -> None:
        """Keep this outcome, replacing the record of the same run (D7)."""
        kept = {record.key: record for record in self._read()}
        kept[outcome.key] = outcome
        self._write(list(kept.values()))

    def _read(self) -> Iterator[ReportedOutcome]:
        """Every parseable record in the file, remembering what was not.

        A missing file is an empty outbox: nothing has been reported here, which
        is the state every machine starts in.
        """
        if not self._path.is_file():
            return iter(())
        try:
            lines = self._path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as failure:
            raise OutcomeReportUnavailable(str(self._path), str(failure)) from failure
        return iter(self._parsed(lines))

    def _parsed(self, lines: Iterable[str]) -> list[ReportedOutcome]:
        """The records those lines hold; the ones they do not are remembered."""
        outcomes: list[ReportedOutcome] = []
        skipped: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            outcome = _record(line)
            if outcome is None:
                skipped.append(line)
                continue
            outcomes.append(outcome)
        self.skipped = (*self.skipped, *skipped)
        return outcomes

    def _write(self, outcomes: Sequence[ReportedOutcome]) -> None:
        """The whole outbox, bounded, written as one file.

        Rewritten rather than appended to, because a retry replaces a record and
        a delivery removes one: an append-only file would need compaction, which
        is a second mechanism to get wrong for a file that holds telemetry.
        """
        bounded = list(outcomes)[-self._capacity :]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                "".join(
                    f"{json.dumps(_document(outcome), sort_keys=True)}\n" for outcome in bounded
                ),
                encoding="utf-8",
            )
        except OSError as failure:
            raise OutcomeReportUnavailable(str(self._path), str(failure)) from failure


def _document(outcome: ReportedOutcome) -> dict[str, object]:
    """One outcome as its line — the same field names the committed record uses."""
    return {
        "asset": outcome.asset_id,
        "export": outcome.export,
        "export_hash": outcome.export_hash,
        "verdict_hash": outcome.verdict_hash,
        "passed": outcome.passed,
        "errors": outcome.errors,
        "warnings": outcome.warnings,
        "reported_at": outcome.reported_at,
        "attributed_to": outcome.attributed_to,
        "via": outcome.via,
    }


def _record(line: str) -> ReportedOutcome | None:
    """The outcome that line holds, or ``None`` when it holds nothing readable."""
    try:
        document = json.loads(line)
        return ReportedOutcome(
            asset_id=str(document["asset"]),
            export=str(document.get("export") or ""),
            export_hash=str(document.get("export_hash") or ""),
            verdict_hash=str(document["verdict_hash"]),
            passed=bool(document["passed"]),
            errors=int(document.get("errors") or 0),
            warnings=int(document.get("warnings") or 0),
            reported_at=str(document.get("reported_at") or ""),
            attributed_to=str(document.get("attributed_to") or ""),
            via=str(document.get("via") or ""),
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def _note(skipped: Sequence[str]) -> str:
    """What a caller is told about lines that could not be read."""
    return SKIPPED.format(count=len(skipped)) if skipped else ""


def _reason(
    kept: Sequence[ReportedOutcome], skipped: Sequence[str], deliver: Destination | None
) -> str:
    """Why something is still waiting, when something is."""
    if not kept:
        return _note(skipped)
    outage = NO_DESTINATION if deliver is None else "the reporting destination is unreachable"
    return "; ".join(part for part in (outage, _note(skipped)) if part)


__all__ = [
    "CANON_DIRECTORY",
    "CAPACITY",
    "NO_DESTINATION",
    "OUTBOX_FILENAME",
    "OUTBOX_PATH",
    "SKIPPED",
    "Destination",
    "FileOutbox",
]
