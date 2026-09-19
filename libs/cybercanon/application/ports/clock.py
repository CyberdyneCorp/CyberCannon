"""The `Clock` port — what time it is, asked rather than taken.

The domain does not read a clock: a request records when it moved and a served
revision records when it was last confirmed, and both take the moment as an
argument. Something has to supply it, and that something is a port for the
ordinary reason — a use case that called :func:`datetime.now` would be
untestable without waiting, and a scheduled refresh would be untestable at all.

A callable rather than a class, matching
:data:`cybercanon.application.use_cases.resolve_actor.Clock`, which is the same
decision one layer down: the smallest port that answers the question.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

type Clock = Callable[[], datetime]
"""Returns the current moment, timezone-aware."""


def system_clock() -> datetime:
    """The real clock, in UTC. The default a composition root passes.

    UTC and not local time: these moments are committed to a repository and read
    by people in other places, and a naive timestamp is a bug that only shows up
    in March.
    """
    return datetime.now(UTC)


def fixed_clock(moment: datetime) -> Clock:
    """A clock that always answers the same moment — what a test passes."""
    return lambda: moment


__all__ = ["Clock", "fixed_clock", "system_clock"]
