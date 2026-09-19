"""The `Dismissals` port — the one thing the index is allowed to own (D9).

There is no notification entity in this system. *"Unread items"* is a **derived
query**: the requests where a person is the assignee or the author, minus the
ones that person has already dismissed. The requests are repository content and
survive anything; the dismissals are a flag per person per subject, and D9 puts
them here and nowhere else:

    *"The state that must survive an index rebuild — the request, its assignee,
    its state, its attribution — is repository content; the state that may be
    lost is whether someone has already looked at it."*

So this port is **the one deliberate exception** to "the index holds nothing
durable", and the exception is stated rather than discovered: after an index
rebuild, previously dismissed items reappear as unread. The cost is one person
clicking dismiss again; the alternative is a commit per glance, in a repository
whose history is supposed to be worth reading.

Two consequences shape the Protocol:

* **A dismissal is per person, per subject, per project.** `asset-requests`
  requires that one person dismissing an item leaves it unread for the other, so
  the recipient is part of the key and never a scope the caller sets up front.
* **It answers a set, not a sequence.** The caller already has the items in
  their own order — they came from the repository — and a store that returned
  its own order would be a second opinion about how to list requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from cybercanon.domain.identity import ActorId


@dataclass(frozen=True)
class Dismissal:
    """One person saying they have seen one thing, and when.

    `subject` is the identifier of the thing — a request id — exactly as
    :class:`~cybercanon.application.ports.notifier.Notification` carries it, and
    for the same reason: the two people looking at one request dismiss it
    independently, and a free-text subject would make "the same item"
    unrecognisable between them.
    """

    project: str
    actor: ActorId
    subject: str
    at: datetime


class Dismissals(Protocol):
    """Remembers which items a person has already looked at."""

    def dismiss(self, dismissal: Dismissal) -> None:
        """Record it. Dismissing twice is not an error — it is the same fact."""
        ...

    def dismissed_by(self, actor: ActorId, project: str) -> frozenset[str]:
        """Every subject this person has dismissed in this project."""
        ...


__all__ = ["Dismissal", "Dismissals"]
