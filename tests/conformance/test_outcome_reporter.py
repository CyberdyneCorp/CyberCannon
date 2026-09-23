"""Tasks 2.2 and 3.5 — the `OutcomeReporter` contract against every implementation.

Two implementations now: the in-memory fake every unit test reports through, and
:class:`~cybercanon.adapters.outbound.fs.outbox.FileOutbox`, which is what an
agent on a developer's machine actually reports through — a git-ignored,
newline-delimited file under `.canon/` and an opportunistic flush (D6).

The seam the contract names is :meth:`outage`, and the two implementations go
dark differently on purpose: the fake flips a flag, and the outbox is pointed at
a destination that refuses. Both then have to answer the same way — *retained,
not lost; answered, not raised; delivered on the next flush* — which is the
whole reason the contract exists before the second implementation does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contract import implementation_fixture
from outcome_reporter_contract import OutcomeReporterContract

from cybercanon.adapters.outbound.fs.outbox import FileOutbox
from cybercanon.application.ports.outcome_reporter import OutcomeReporter, ReportedOutcome
from cybercanon.application.testing.outcome_reporter import InMemoryOutcomeReporter


@dataclass
class StubDestination:
    """A destination that can be switched off — the outbox's half of `outage`."""

    reachable: bool = True
    delivered: list[ReportedOutcome] = field(default_factory=list)

    def __call__(self, outcome: ReportedOutcome) -> None:
        if not self.reachable:
            raise ConnectionError("the reporting destination is unreachable")
        self.delivered.append(outcome)


def in_memory(directory: Path) -> InMemoryOutcomeReporter:
    return InMemoryOutcomeReporter()


def outbox(directory: Path) -> FileOutbox:
    return FileOutbox(directory, deliver=StubDestination())


implementation = implementation_fixture(fake=in_memory, real=outbox)


class TestOutcomeReporter(OutcomeReporterContract):
    """The `OutcomeReporter` contract, against every implementation there is."""

    def outage(self, implementation: OutcomeReporter, reachable: bool = False) -> None:
        """The fake's destination is a flag; the outbox's is one that refuses."""
        if isinstance(implementation, InMemoryOutcomeReporter):
            implementation.unreachable(reachable)
            return
        assert isinstance(implementation, FileOutbox)
        destination = implementation._deliver
        assert isinstance(destination, StubDestination)
        destination.reachable = reachable
