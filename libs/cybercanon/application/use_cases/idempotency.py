"""Run a write at most once per key, and replay its answer afterwards (D11).

One function, :func:`once`, and its shape is the whole of D11:

1. a key that is unknown or expired runs the operation, records its outcome and
   returns it;
2. a key that is known and carries **the same** request returns the recorded
   outcome without running anything — which is what makes *"a retried write
   produces exactly one commit"* true rather than hoped for;
3. a key that is known and carries a **different** request is refused, because
   serving somebody else's answer is worse than refusing.

It returns the :class:`~cybercanon.application.ports.idempotency.RecordedOutcome`
rather than the operation's value, and that is deliberate. *"A replay within
that period returns the stored outcome"* — the stored outcome, not a fresh
derivation of it, because deriving one would mean running the operation again.
The surface renders the record; the record is what a replay and a first attempt
have in common.

A refusal is recorded too. A retried write that was refused the first time must
be refused again rather than succeed because the repository moved in between —
otherwise a lost response would turn a conflict into an apply.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.idempotency import (
    DEFAULT_LIFETIME,
    IdempotencyMismatch,
    IdempotencyStore,
    RecordedOutcome,
    outcome_of,
)
from cybercanon.application.results import Result, as_result
from cybercanon.domain.revisions import ContentHash

type Rendering[T] = Callable[[T], str]
"""How a surface turns a successful value into the payload a replay returns."""


def nothing_rendered(value: object) -> str:
    """The default payload: none. A caller that renders nothing replays nothing."""
    return ""


@as_result
def once[T](
    key: str,
    request: bytes,
    operation: Callable[[], Result[T]],
    *,
    store: IdempotencyStore,
    clock: Clock = system_clock,
    lifetime: timedelta = DEFAULT_LIFETIME,
    render: Rendering[T] = nothing_rendered,
) -> RecordedOutcome:
    """Perform this operation under that key, or replay what it answered before."""
    now = clock()
    digest = ContentHash.of(request)
    replayed = store.recall(key, now=now)
    if replayed is not None:
        return _replay(replayed, key, digest)
    result = operation()
    record = outcome_of(
        key,
        digest,
        result,
        now=now,
        lifetime=lifetime,
        payload=_payload(result, render),
    )
    store.remember(record)
    return record


def _replay(record: RecordedOutcome, key: str, digest: ContentHash) -> RecordedOutcome:
    """The stored outcome, or a refusal when this key was used for something else."""
    if not record.matches(digest):
        raise IdempotencyMismatch(key)
    return record


def _payload[T](result: Result[T], render: Rendering[T]) -> str:
    """What a replay of a success returns. A refusal carries its message instead."""
    value = getattr(result, "value", None)
    return render(value) if value is not None else ""


__all__ = ["Rendering", "nothing_rendered", "once"]
