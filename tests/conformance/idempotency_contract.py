"""What every `IdempotencyStore` SHALL do, whoever implements it (task 6.5).

Every clause below is a sentence of D11 rather than a property of a dictionary
or of a table: a key remembers its outcome, the record it remembers carries the
digest of the request it was first used for, and the whole thing has a bound
past which it is simply not there.

The bound is asserted by moving the clock rather than by sleeping. A record that
expires because a test waited would be a test asserting how fast the machine is.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cybercanon.application.errors import FailureKind
from cybercanon.application.ports.idempotency import IdempotencyStore, RecordedOutcome
from cybercanon.domain.revisions import ContentHash

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
LIFETIME = timedelta(hours=1)
LATER = NOON + LIFETIME + timedelta(seconds=1)

KEY = "6f1b0b7a-0d3d-4f2e-8f9a-7c1d2e3f4a5b"
OTHER_KEY = "9a2c4e6f-1b3d-5f7a-9c1e-3d5f7a9c1e3d"

BODY = b'{"description": "a supply crate for the loading dock"}'
OTHER_BODY = b'{"description": "a different crate entirely"}'


def a_record(
    key: str = KEY,
    body: bytes = BODY,
    *,
    kind: FailureKind | None = None,
    identifier: str = "ok",
    payload: str = '{"request": "req-0001"}',
    stored_at: datetime = NOON,
    lifetime: timedelta = LIFETIME,
) -> RecordedOutcome:
    return RecordedOutcome(
        key=key,
        request_digest=ContentHash.of(body),
        kind=kind,
        identifier=identifier,
        message="" if kind is None else "the content has changed since it was read",
        subject="characters/mech_scout/asset.yaml",
        payload=payload,
        stored_at=stored_at,
        expires_at=stored_at + lifetime,
    )


class IdempotencyStoreContract:
    """The behaviour every idempotency store shares."""

    def test_an_unknown_key_is_absent(self, implementation: IdempotencyStore) -> None:
        assert implementation.recall(KEY, now=NOON) is None

    def test_a_remembered_key_reads_back_whole(self, implementation: IdempotencyStore) -> None:
        record = a_record()

        implementation.remember(record)

        assert implementation.recall(KEY, now=NOON) == record

    def test_the_stored_digest_is_the_request_it_was_first_used_for(
        self, implementation: IdempotencyStore
    ) -> None:
        """What makes a replay with a different body refusable rather than served."""
        implementation.remember(a_record())

        recalled = implementation.recall(KEY, now=NOON)
        assert recalled is not None
        assert recalled.matches(ContentHash.of(BODY))
        assert not recalled.matches(ContentHash.of(OTHER_BODY))

    def test_a_refusal_is_remembered_as_a_refusal(self, implementation: IdempotencyStore) -> None:
        """A retried write that was refused must be refused again, not applied."""
        implementation.remember(
            a_record(kind=FailureKind.CONFLICT, identifier="edit.conflict", payload="")
        )

        recalled = implementation.recall(KEY, now=NOON)
        assert recalled is not None
        assert not recalled.succeeded
        assert recalled.kind is FailureKind.CONFLICT
        assert recalled.identifier == "edit.conflict"

    def test_keys_do_not_see_each_other(self, implementation: IdempotencyStore) -> None:
        implementation.remember(a_record())
        implementation.remember(a_record(key=OTHER_KEY, body=OTHER_BODY))

        first = implementation.recall(KEY, now=NOON)
        second = implementation.recall(OTHER_KEY, now=NOON)
        assert first is not None and second is not None
        assert first.request_digest != second.request_digest

    def test_a_record_past_its_bound_is_absent(self, implementation: IdempotencyStore) -> None:
        """Bounded lifetime: the index may not be where "has this been done" lives."""
        implementation.remember(a_record())

        assert implementation.recall(KEY, now=LATER) is None

    def test_sweeping_drops_the_expired_and_keeps_the_rest(
        self, implementation: IdempotencyStore
    ) -> None:
        implementation.remember(a_record())
        implementation.remember(a_record(key=OTHER_KEY, lifetime=timedelta(days=7)))

        dropped = implementation.forget_expired(now=LATER)

        assert dropped == 1
        assert implementation.recall(OTHER_KEY, now=LATER) is not None

    def test_a_sweep_with_nothing_expired_drops_nothing(
        self, implementation: IdempotencyStore
    ) -> None:
        implementation.remember(a_record())

        assert implementation.forget_expired(now=NOON) == 0
        assert implementation.recall(KEY, now=NOON) is not None
