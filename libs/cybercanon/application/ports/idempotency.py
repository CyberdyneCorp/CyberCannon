"""The `IdempotencyStore` port — making a retried write quiet (D11).

A lost response on a write that already committed is the *common* case, not the
exotic one: a mobile network, a proxy timeout, a browser reloaded at the wrong
moment. So the surface has to be safe to retry, and D11 says how: *"A key stores
the request digest and the original outcome for a bounded period; a replay
within that period returns the stored outcome, and a replay with a different
body is refused."*

Three things follow, and the third is the interesting one:

* **The digest travels with the key.** A replay carrying a different body under
  the same key is a caller's mistake, and serving it somebody else's answer
  would be worse than refusing it.
* **The record expires.** A key that lived forever would make the index the
  place where "has this been done" is decided, which is a fact originating in
  the index — the one thing it may never be.
* **Losing the record is safe, and that is by design.** This is index state and
  an index rebuild forgets it. D11 spells out why that is not a hole: *"a very
  late retry could apply twice. It cannot, in practice, because D5's per-file
  precondition refuses the second apply."* Idempotency makes the retry quiet;
  the content hash makes it safe. Two mechanisms, interlocking deliberately.

What is stored is the *outcome*, not the value: a rendered payload the surface
produced, kept verbatim. Re-deriving a value on replay would mean running the
operation again, which is the one thing a replay must not do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.results import OK, Ok, Refusal, Result
from cybercanon.domain.revisions import ContentHash

DEFAULT_LIFETIME = timedelta(hours=24)
"""How long a key remembers its answer.

Long enough to cover a person retrying after a bad network, short enough that
the table does not become a log. The number is configuration in a deployment;
this is what a caller that configured none is measured against.
"""


@dataclass(frozen=True)
class RecordedOutcome:
    """What one idempotency key answered the first time, and until when.

    `kind` of ``None`` means the operation succeeded; any other value is the
    refusal it produced, which is replayed exactly as it was first given — a
    retry of a refused write must not succeed by accident because the world
    moved on in between.
    """

    key: str
    request_digest: ContentHash
    kind: FailureKind | None = None
    identifier: str = OK
    message: str = ""
    subject: str = ""
    payload: str = ""
    stored_at: datetime | None = None
    expires_at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        return self.kind is None

    def has_expired(self, now: datetime) -> bool:
        """Whether this record is past its bound and must be treated as absent."""
        return self.expires_at is not None and now >= self.expires_at

    def matches(self, digest: ContentHash) -> bool:
        """Whether a replay is carrying the body this key was first used for."""
        return self.request_digest == digest


class IdempotencyMismatch(OperationFailed):
    """The same key, a different request. Refused rather than answered.

    A conflict rather than an invalid request, because nothing about the body is
    wrong: it disagrees with something the service already did, which is the
    same shape of problem as D5's stale content hash and gets the same answer.
    """

    kind = FailureKind.CONFLICT
    identifier = "idempotency.mismatch"

    def __init__(self, key: str) -> None:
        super().__init__(
            f"idempotency key {key!r} was already used for a different request; "
            "use a new key for a new request",
            key,
        )
        self.key = key


class IdempotencyStore(Protocol):
    """Remembers what a key answered, for a bounded period."""

    def remember(self, record: RecordedOutcome) -> None:
        """Store this key's outcome, replacing nothing that has not expired."""
        ...

    def recall(self, key: str, *, now: datetime) -> RecordedOutcome | None:
        """That key's outcome, or ``None`` when it is unknown or expired."""
        ...

    def forget_expired(self, *, now: datetime) -> int:
        """Drop every record past its bound, and say how many. A maintenance call."""
        ...


def outcome_of[T](
    key: str,
    digest: ContentHash,
    result: Result[T],
    *,
    now: datetime,
    lifetime: timedelta = DEFAULT_LIFETIME,
    payload: str = "",
) -> RecordedOutcome:
    """One result as the record a replay will be answered from.

    Here rather than at each call site for the same reason the link shape is in
    `blob_store`: two surfaces that each decided what to store would eventually
    store different things, and a replay would then depend on which surface the
    first attempt reached.
    """
    refused = None if isinstance(result, Ok) else result
    return RecordedOutcome(
        key=key,
        request_digest=digest,
        kind=None if refused is None else refused.kind,
        identifier=result.identifier,
        message=_message(result, refused),
        subject=result.subject,
        payload=payload,
        stored_at=now,
        expires_at=now + lifetime,
    )


def _message(result: Result[object], refused: Refusal | None) -> str:
    return refused.message if refused is not None else result.message


__all__ = [
    "DEFAULT_LIFETIME",
    "IdempotencyMismatch",
    "IdempotencyStore",
    "RecordedOutcome",
    "outcome_of",
]
