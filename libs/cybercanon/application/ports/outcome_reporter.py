"""The `OutcomeReporter` port — a verdict delivered, or kept and retried (D6, D7).

The verdict is produced locally, offline, by the existing validator, and it is
authoritative there. Reporting is *"an after-the-fact delivery that may fail,
retry, or never arrive without changing anything a person sees on their own
machine"* — so the port is shaped to make blocking impossible rather than
unlikely:

* :meth:`OutcomeReporter.report` **never raises for a delivery failure.** It
  retains the outcome and answers what happened. A port that could raise would
  eventually be awaited by a pre-commit hook, and then a reporting server's bad
  afternoon would stop an artist committing — the one outcome the requirement
  names: *"a failure to deliver ... SHALL NOT block a commit."*
* :meth:`OutcomeReporter.pending` is the count that makes a silent outage
  visible, because `canon whoami` and `canon report flush` both report it and
  *"a growing outbox is visible where a person already looks."*
* :meth:`OutcomeReporter.flush` retries what was retained. There is no daemon
  and no queue; D6 settles that deliberately — *"the retry mechanism is a file
  and an opportunistic flush."*

Identity is D7's triple and it lives in the domain
(:class:`~cybercanon.domain.validation_outcome.OutcomeIdentity`): the asset, the
export's content hash and the verdict's hash. Both the retained record and the
destination key on it, so a retry replaces rather than accumulates and a
re-export is a new, distinguishable outcome.

Nothing here evaluates a rule. There is no `MeshInspector`, no specification and
no rule registry in this module's imports, which is how *"no validation rule
SHALL be evaluated as part of the report"* is a property of the boundary rather
than a promise about a function body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.domain.validation_outcome import FAILED, PASSED, OutcomeIdentity

VERDICT_STANDS = (
    "the verdict stands locally; delivery of the report is pending and will be "
    "retried on the next report or by `canon report flush`"
)
"""What a caller is told when delivery did not happen (D6).

*"The caller SHALL be told that the verdict stands and delivery is pending."*
One sentence, defined once, because the agent surface and the command line
saying it differently is how somebody concludes that one of them failed.
"""


@dataclass(frozen=True)
class ReportedOutcome:
    """One validation run, as it is delivered — a verdict, never a re-evaluation.

    Every field is a copy of what the local run already produced. There is no
    field here a destination could use to change the answer, and no field for a
    rule to be re-run into: the reported outcome *"SHALL be identical to the
    verdict the same caller already received locally."*
    """

    asset_id: str
    export: str
    export_hash: str
    verdict_hash: str
    passed: bool
    errors: int = 0
    warnings: int = 0
    reported_at: str = ""
    attributed_to: str = ""
    via: str = ""

    @property
    def identity(self) -> OutcomeIdentity:
        """D7's triple — what makes a retry the same outcome and a re-export a new one."""
        return OutcomeIdentity(
            asset_id=self.asset_id,
            export_hash=self.export_hash,
            verdict_hash=self.verdict_hash,
        )

    @property
    def key(self) -> str:
        return self.identity.key

    @property
    def verdict(self) -> str:
        return PASSED if self.passed else FAILED


@dataclass(frozen=True)
class Delivery:
    """What an attempt to deliver achieved, and what is still waiting.

    `reason` is populated when something was retained rather than delivered. It
    is never a failure the caller has to handle: a report that could fail a call
    is a report that can block a commit.
    """

    delivered: int = 0
    pending: int = 0
    reason: str = ""

    @property
    def complete(self) -> bool:
        """Whether nothing is waiting — what `canon report flush` exits zero on."""
        return self.pending == 0

    def __str__(self) -> str:
        if self.complete:
            return f"{self.delivered} delivered"
        return f"{self.delivered} delivered, {self.pending} pending: {VERDICT_STANDS}"


class OutcomeReportUnavailable(OperationFailed):
    """The retained reports could not be read or written at all.

    Raised only by the *storage* half — a corrupt or unwritable outbox — never
    by a failed delivery, which is an ordinary answer. The distinction matters:
    "I cannot keep your report" is a condition somebody has to fix, and "I could
    not deliver it yet" is Tuesday.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "outcome_reporter.unavailable"

    def __init__(self, subject: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"the outcome report store for {subject} is unavailable{detail}", subject)
        self.reason = reason


class OutcomeReporter(Protocol):
    """Keeps reported outcomes and delivers them, without ever blocking a caller."""

    def report(self, outcome: ReportedOutcome) -> Delivery:
        """Retain this outcome and attempt to deliver it. Answers either way.

        It does **not** raise when the destination is unreachable: that is the
        ordinary case D6 designs for, and the answer carries the pending count.
        Re-reporting an identical outcome replaces the retained record rather
        than adding one (D7), so an agent in a loop cannot grow the outbox.
        """
        ...

    def pending(self) -> tuple[ReportedOutcome, ...]:
        """Every outcome retained and not yet delivered, oldest first."""
        ...

    def flush(self) -> Delivery:
        """Attempt to deliver everything retained. Answers what is left."""
        ...


__all__ = [
    "VERDICT_STANDS",
    "Delivery",
    "OutcomeReportUnavailable",
    "OutcomeReporter",
    "ReportedOutcome",
]
