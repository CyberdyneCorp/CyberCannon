"""The in-memory `OutcomeReporter` — an outbox, a destination, and an outage.

The fake models the three states D6 and D7 are about and no others: an outcome
retained, an outcome delivered, and a destination that cannot be reached. It
keys both the outbox and the destination on
:class:`~cybercanon.domain.validation_outcome.OutcomeIdentity`, so *"retrying or
re-reporting the same run replaces the existing record rather than adding
another"* is a property the fake shares with the real adapter rather than one
the real adapter has alone.

:meth:`InMemoryOutcomeReporter.unreachable` is the whole point of the fake
existing: every interesting requirement here is about what happens when delivery
fails, and a reporter that could only succeed would leave all of them untested.
"""

from __future__ import annotations

from cybercanon.application.ports.outcome_reporter import Delivery, ReportedOutcome

UNREACHABLE = "the reporting destination is unreachable"


class InMemoryOutcomeReporter:
    """An outbox and a destination, both keyed on the outcome's identity (D7)."""

    def __init__(self) -> None:
        self._outbox: dict[str, ReportedOutcome] = {}
        self._delivered: dict[str, ReportedOutcome] = {}
        self._reachable = True
        self.attempts = 0

    # -- seeding ---------------------------------------------------------

    def unreachable(self, reachable: bool = False) -> None:
        """Whether the destination can be reached. Delivery never raises either way."""
        self._reachable = reachable

    @property
    def delivered(self) -> tuple[ReportedOutcome, ...]:
        """What the destination holds — one record per identity, insertion ordered."""
        return tuple(self._delivered.values())

    # -- port ------------------------------------------------------------

    def report(self, outcome: ReportedOutcome) -> Delivery:
        self._outbox[outcome.key] = outcome
        return self.flush()

    def pending(self) -> tuple[ReportedOutcome, ...]:
        return tuple(self._outbox.values())

    def flush(self) -> Delivery:
        self.attempts += 1
        if not self._reachable:
            return Delivery(delivered=0, pending=len(self._outbox), reason=UNREACHABLE)
        sent = len(self._outbox)
        self._delivered.update(self._outbox)
        self._outbox.clear()
        return Delivery(delivered=sent, pending=0)


__all__ = ["UNREACHABLE", "InMemoryOutcomeReporter"]
