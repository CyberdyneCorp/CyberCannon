"""What every `OutcomeReporter` SHALL do, whoever implements it (tasks 2.2, 2.8).

Four requirements, and three of them are about failure — which is the right
proportion, because the whole design exists for the case where the destination
is not there:

* **reporting never raises.** `mcp-write-surface`: *"A failure to deliver a
  reported outcome SHALL NOT change a verdict, SHALL NOT block a commit, SHALL
  NOT fail a local validation run, and SHALL NOT block or error the automated
  caller."* A port that could raise is a port a pre-commit hook eventually
  awaits;
* **an undeliverable report is retained and retried.** It stays pending, a later
  flush delivers it, and it is then no longer pending;
* **identity is the triple, so a retry does not accumulate** (D7). Re-reporting
  the identical outcome leaves exactly one record; a re-export changes the
  export hash and is a second, distinguishable one;
* **the pending count is readable**, because that is what makes a silent outage
  visible where a person already looks.

The fake is the only implementation today and the local outbox adapter joins at
task 3.5. Writing the contract first is what stops the outbox from quietly
acquiring a different idea of what "the same outcome" means.
"""

from __future__ import annotations

from cybercanon.application.ports.outcome_reporter import OutcomeReporter, ReportedOutcome

PASSED = ReportedOutcome(
    asset_id="mech_scout",
    export="exports/mech_scout.glb",
    export_hash="sha256:aaaa",
    verdict_hash="sha256:vvvv",
    passed=True,
)
REEXPORTED = ReportedOutcome(
    asset_id="mech_scout",
    export="exports/mech_scout.glb",
    export_hash="sha256:bbbb",
    verdict_hash="sha256:vvvv",
    passed=True,
)


class OutcomeReporterContract:
    """The behaviour every outcome reporter shares.

    :meth:`outage` is the one seam: most of what is specified here is about a
    destination that is not answering, and *how* an implementation is made
    unreachable differs — the fake flips a flag, the local outbox is pointed at
    a destination that refuses. Each concrete suite supplies it, so the contract
    can assert the behaviour without knowing the mechanism, and a suite that
    forgot to supply one fails loudly rather than quietly testing the happy path.
    """

    def outage(self, implementation: OutcomeReporter, reachable: bool = False) -> None:
        """Make this implementation's destination (un)reachable."""
        raise NotImplementedError("a conformance suite says how its reporter goes dark")

    def test_nothing_is_pending_until_something_is(self, implementation: OutcomeReporter) -> None:
        assert implementation.pending() == ()

    def test_a_delivered_report_is_not_pending(self, implementation: OutcomeReporter) -> None:
        delivery = implementation.report(PASSED)

        assert delivery.delivered == 1
        assert delivery.complete
        assert implementation.pending() == ()

    def test_an_undeliverable_report_is_retained_rather_than_lost(
        self, implementation: OutcomeReporter
    ) -> None:
        self.outage(implementation)

        delivery = implementation.report(PASSED)

        assert delivery.delivered == 0
        assert delivery.pending == 1
        assert implementation.pending() == (PASSED,)

    def test_reporting_into_an_outage_does_not_raise(self, implementation: OutcomeReporter) -> None:
        """The whole design: a report that can fail is a report that blocks a commit."""
        self.outage(implementation)

        assert implementation.report(PASSED).reason

    def test_a_retained_report_is_delivered_by_a_later_flush(
        self, implementation: OutcomeReporter
    ) -> None:
        self.outage(implementation)
        implementation.report(PASSED)

        self.outage(implementation, reachable=True)
        delivery = implementation.flush()

        assert delivery.delivered == 1
        assert implementation.pending() == ()

    def test_re_reporting_the_identical_outcome_holds_one_record(
        self, implementation: OutcomeReporter
    ) -> None:
        """D7: retries are the normal case, so idempotency is a precondition."""
        self.outage(implementation)
        implementation.report(PASSED)
        implementation.report(PASSED)

        assert len(implementation.pending()) == 1

    def test_a_re_export_is_a_second_distinguishable_outcome(
        self, implementation: OutcomeReporter
    ) -> None:
        self.outage(implementation)
        implementation.report(PASSED)
        implementation.report(REEXPORTED)

        keys = {outcome.key for outcome in implementation.pending()}
        assert keys == {PASSED.key, REEXPORTED.key}

    def test_flushing_nothing_is_not_an_error(self, implementation: OutcomeReporter) -> None:
        """`canon report flush` on a machine with nothing waiting exits zero."""
        assert implementation.flush().complete
