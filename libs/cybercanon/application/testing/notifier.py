"""The in-memory `Notifier` — unread items in a list, and a way to break it.

`fail_with` is the point of this fake rather than a convenience on it. The
requirement `asset-requests` states is a *negative* one — recording a
notification must never fail or reverse the action that caused it — and a
negative is only testable against a notifier that is actually failing. A fake
that could only succeed would let the requirement pass by never being exercised.
"""

from __future__ import annotations

from cybercanon.application.ports.notifier import Notification
from cybercanon.domain.identity import ActorId


class InMemoryNotifier:
    """Keeps every notification it was handed, and fails on demand."""

    def __init__(self) -> None:
        self._recorded: list[Notification] = []
        self._failure: Exception | None = None

    def fail_with(self, error: Exception | None) -> None:
        """Make every call raise — the notifier that is down, on demand."""
        self._failure = error

    def notify(self, notification: Notification) -> None:
        if self._failure is not None:
            raise self._failure
        self._recorded.append(notification)

    # -- inspection ------------------------------------------------------

    @property
    def recorded(self) -> tuple[Notification, ...]:
        """Everything recorded, oldest first."""
        return tuple(self._recorded)

    def for_actor(self, actor: ActorId) -> tuple[Notification, ...]:
        """Everything addressed to one person."""
        return tuple(item for item in self._recorded if item.recipient == actor)


__all__ = ["InMemoryNotifier"]
