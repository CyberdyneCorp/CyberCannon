"""`PostgresIdempotencyStore` — the key table, with its bounded lifetime (D11).

Index state on purpose, and survivable on purpose: an index rebuild forgets
every key, and D11 says why that is not a hole — *"a very late retry could apply
twice. It cannot, in practice, because D5's per-file precondition refuses the
second apply."* Idempotency makes the retry quiet; the content hash makes it
safe.

Expiry is evaluated on read as well as swept, for the same reason the in-memory
fake evaluates it on read: the bound belongs to the record, and a store whose
correctness depended on a sweep having run would answer differently depending on
how busy the maintenance job was.
"""

from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from cybercanon.application.errors import FailureKind
from cybercanon.application.ports.idempotency import RecordedOutcome
from cybercanon.domain.revisions import ContentHash

COLUMNS = (
    "key",
    "request_digest",
    "kind",
    "identifier",
    "message",
    "subject",
    "payload",
    "stored_at",
    "expires_at",
)


class PostgresIdempotencyStore:
    """Idempotency records in PostgreSQL, keyed by the key the caller supplied."""

    def __init__(self, dsn: str | None = None, *, connection: psycopg.Connection | None = None):
        if connection is None and not dsn:
            raise ValueError("a PostgresIdempotencyStore needs a dsn or an open connection")
        self._owned = connection is None
        self._connection = connection or psycopg.connect(str(dsn), autocommit=True)
        self._connection.autocommit = True

    def close(self) -> None:
        if self._owned:
            self._connection.close()

    def __enter__(self) -> PostgresIdempotencyStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def remember(self, record: RecordedOutcome) -> None:
        """Store this key's outcome, replacing an expired record under the same key."""
        placeholders = ", ".join(["%s"] * len(COLUMNS))
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}" for column in COLUMNS if column != "key"
        )
        self._connection.execute(
            f"INSERT INTO idempotency_keys ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT (key) DO UPDATE SET {assignments}",
            _values(record),
        )

    def recall(self, key: str, *, now: datetime) -> RecordedOutcome | None:
        """That key's outcome, or ``None`` when it is unknown or past its bound."""
        with self._connection.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute(
                f"SELECT {', '.join(COLUMNS)} FROM idempotency_keys "
                "WHERE key = %s AND expires_at > %s",
                [key, now],
            ).fetchone()
        return _record(row) if row is not None else None

    def forget_expired(self, *, now: datetime) -> int:
        """Drop every record past its bound, and say how many. A maintenance call."""
        cursor = self._connection.execute(
            "DELETE FROM idempotency_keys WHERE expires_at <= %s", [now]
        )
        return cursor.rowcount


def _values(record: RecordedOutcome) -> list[object]:
    return [
        record.key,
        record.request_digest.value,
        None if record.kind is None else record.kind.value,
        record.identifier,
        record.message,
        record.subject,
        record.payload,
        record.stored_at,
        record.expires_at,
    ]


def _record(row: dict[str, object]) -> RecordedOutcome:
    kind = row["kind"]
    return RecordedOutcome(
        key=str(row["key"]),
        request_digest=ContentHash(str(row["request_digest"])),
        kind=None if kind is None else FailureKind(str(kind)),
        identifier=str(row["identifier"]),
        message=str(row["message"]),
        subject=str(row["subject"]),
        payload=str(row["payload"]),
        stored_at=row["stored_at"],  # type: ignore[arg-type]
        expires_at=row["expires_at"],  # type: ignore[arg-type]
    )


__all__ = ["COLUMNS", "PostgresIdempotencyStore"]
