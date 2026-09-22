"""The fetch schedule: the guarantee, not the optimisation (D4).

*"A webhook is lost, misconfigured or silently disabled by a repository
administrator; a timer is not."* The webhook endpoint has had a test since the
hosted surface shipped; the timer that is supposed to be the guarantee had
nothing running it, because the deployable never built one. These are the
properties the deployment depends on it for.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest

from cybercanon.adapters.wiring.background import Ticker

pytestmark = pytest.mark.unit

QUICK = timedelta(milliseconds=5)
PATIENCE_S = 2.0


def test_the_first_tick_happens_without_waiting_an_interval() -> None:
    """A process that has just started holds a copy nobody has fetched since the
    last deploy; waiting five minutes to find out is five minutes of stale."""
    ticked = threading.Event()
    ticker = Ticker(ticked.set, timedelta(hours=1)).start()

    try:
        assert ticked.wait(PATIENCE_S), "the schedule waited an interval before its first tick"
    finally:
        ticker.stop()


def test_it_keeps_ticking() -> None:
    counted = _Counter(target=3)
    ticker = Ticker(counted, QUICK).start()

    try:
        assert counted.reached.wait(PATIENCE_S), f"only {counted.count} tick(s)"
    finally:
        ticker.stop()


def test_a_tick_that_raises_does_not_end_the_schedule() -> None:
    """One unreachable remote must not stop every later fetch for the process's life."""
    seen: list[BaseException] = []
    counted = _Counter(target=2, then=_raise)
    ticker = Ticker(counted, QUICK, on_error=seen.append).start()

    try:
        assert counted.reached.wait(PATIENCE_S), f"the schedule stopped after {counted.count}"
    finally:
        ticker.stop()

    assert seen, "the failure was swallowed instead of reported"


def test_stopping_is_idempotent_and_starting_twice_is_one_thread() -> None:
    """D7 retires an instance; a second ticker would be a second writer."""
    ticker = Ticker(lambda: None, QUICK)

    assert ticker.start() is ticker.start()

    ticker.stop()
    ticker.stop()


def test_one_tick_can_be_driven_by_hand_and_reports_its_failure() -> None:
    """The unit the thread runs, with no thread — for a test that wants determinism."""
    seen: list[BaseException] = []

    Ticker(_raise, QUICK, on_error=seen.append).tick_once()

    assert [type(one) for one in seen] == [RuntimeError]


def _raise() -> None:
    raise RuntimeError("the remote could not be reached")


class _Counter:
    """Counts ticks, sets an event at `target`, and optionally fails each time."""

    def __init__(self, target: int, then=lambda: None) -> None:
        self.count = 0
        self.target = target
        self.reached = threading.Event()
        self._then = then

    def __call__(self) -> None:
        self.count += 1
        if self.count >= self.target:
            self.reached.set()
        self._then()
