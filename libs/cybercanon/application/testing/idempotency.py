"""The in-memory `IdempotencyStore` — records in a dict, expiring by comparison.

The real store is a table with an expiry column and a maintenance sweep; this is
the same behaviour with the dictionary that a unit test can hold in its hand.
Expiry is evaluated on read rather than by a timer, because the bound belongs to
the record and a test that had to wait for a sweep would be a slow test asserting
a scheduler.
"""

from __future__ import annotations

from datetime import datetime

from cybercanon.application.ports.idempotency import RecordedOutcome


class InMemoryIdempotencyStore:
    """Idempotency records keyed by the key, forgotten when they expire."""

    def __init__(self) -> None:
        self._records: dict[str, RecordedOutcome] = {}

    def remember(self, record: RecordedOutcome) -> None:
        self._records[record.key] = record

    def recall(self, key: str, *, now: datetime) -> RecordedOutcome | None:
        record = self._records.get(key)
        if record is None or record.has_expired(now):
            return None
        return record

    def forget_expired(self, *, now: datetime) -> int:
        expired = [key for key, record in self._records.items() if record.has_expired(now)]
        for key in expired:
            del self._records[key]
        return len(expired)

    def __len__(self) -> int:
        return len(self._records)


__all__ = ["InMemoryIdempotencyStore"]
