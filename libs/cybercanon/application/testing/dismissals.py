"""The in-memory `Dismissals` — a set per person, and nothing durable in it.

The real store is a table the index owns; this is the same behaviour in a
dictionary a unit test can hold. Both forget everything when the index is
rebuilt, which is not a limitation of either — it is D9's stated exception, and
the conformance suite asserts the shape rather than the storage.
"""

from __future__ import annotations

from cybercanon.application.ports.dismissals import Dismissal
from cybercanon.domain.identity import ActorId


class InMemoryDismissals:
    """Which subjects each person has dismissed, per project."""

    def __init__(self) -> None:
        self._dismissed: dict[tuple[str, str], set[str]] = {}

    def dismiss(self, dismissal: Dismissal) -> None:
        held = self._dismissed.setdefault(_key(dismissal.actor, dismissal.project), set())
        held.add(dismissal.subject)

    def dismissed_by(self, actor: ActorId, project: str) -> frozenset[str]:
        return frozenset(self._dismissed.get(_key(actor, project), ()))

    def clear(self) -> None:
        """Forget every dismissal — what dropping the index does (D9)."""
        self._dismissed.clear()


def _key(actor: ActorId, project: str) -> tuple[str, str]:
    return (str(actor), project)


__all__ = ["InMemoryDismissals"]
