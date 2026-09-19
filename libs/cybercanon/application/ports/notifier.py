"""The `Notifier` port — an in-app unread item, and nothing more (D9).

`asset-requests` is unusually explicit about what notification is *not*: not
electronic mail, not device push, no digest, no subscription preferences. And it
is explicit about the property that matters more than any of those: **a failure
to record a notification SHALL NOT fail or reverse the action that caused it.**
Accepting a request while the notifier is down accepts the request.

That single sentence shapes the port. :meth:`Notifier.notify` returns nothing,
so there is no answer a caller could be tempted to branch on, and every caller
wraps it in :func:`notify_quietly`, which is the one place a notification
failure is swallowed. A use case that called the port directly would be one
`try` away from making an acceptance depend on a side channel.

D9 also fixes where the state lives, and it is the one deliberate exception to
"the index holds nothing durable": the request, its assignee, its state and its
attribution are repository content, and whether somebody has *looked* at it is a
dismissal flag in the index that an index rebuild is allowed to forget. So this
port carries no durable content and needs no rebuild story — which is exactly
why it can be allowed to fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from cybercanon.domain.identity import ActorId


@dataclass(frozen=True)
class Notification:
    """One thing a person should see, addressed to them and about something.

    `subject` is the identifier of the thing that happened — a request id — and
    not a sentence, because dismissal is per person *and per subject*: the two
    people looking at one request dismiss it independently, and a free-text
    subject would make "the same item" unrecognisable.
    """

    recipient: ActorId
    subject: str
    summary: str
    at: datetime


class Notifier(Protocol):
    """Records that a person has something unread."""

    def notify(self, notification: Notification) -> None:
        """Record it. May fail, and failing changes nothing about the action."""
        ...


def notify_quietly(notifier: Notifier | None, notification: Notification) -> bool:
    """Record a notification, absorbing any failure. Answers whether it stuck.

    The broad `except` is the decision rather than laziness, for the same reason
    preview emission has one (D7): *any* failure below this line — a notifier
    that is down, one that was never configured, one raising something nobody
    anticipated — is a notification failure and never the caller's failure. The
    boolean is for a caller that wants to say "we could not tell them"; no
    caller may use it to undo anything.
    """
    if notifier is None:
        return False
    try:
        notifier.notify(notification)
    except Exception:  # D9: a notification never fails or reverses the action
        return False
    return True


__all__ = ["Notification", "Notifier", "notify_quietly"]
