"""Task 6.5 — a retried write is quiet, and it is still one commit (D11).

Three sentences of D11, each with a test:

* a replay within the period **returns the stored outcome** — the stored one,
  not a fresh derivation, which is the difference between a replay and a second
  attempt that happened to agree;
* a replay **with a different body** under the same key is refused;
* a retried write **produces exactly one commit** — asserted against a real
  write use case over the in-memory repository host, because a helper that is
  idempotent about nothing in particular proves nothing.

The fourth assertion is the one D11 argues for at length: idempotency is *not*
the safety mechanism. The key expires, an index rebuild forgets it, and what
stops a very late retry applying twice is D5's per-file content hash. So the
last test lets the key expire and shows the retry being refused as a conflict
rather than applying — the two mechanisms interlocking exactly as designed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.application.errors import FailureKind
from cybercanon.application.ports.idempotency import DEFAULT_LIFETIME
from cybercanon.application.results import Conflict, Ok
from cybercanon.application.testing.idempotency import InMemoryIdempotencyStore
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.use_cases.hosted_repository import Edit, write_back
from cybercanon.application.use_cases.idempotency import once
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.revisions import ContentHash

PROJECT = "cyberdyne-game"
SPEC = "characters/mech_scout/asset.yaml"
BEFORE = b"schema_version: 1\nid: mech_scout\nstatus: concept\n"
AFTER = b"schema_version: 1\nid: mech_scout\nstatus: modeling\n"

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
MESSAGE = "mech_scout: set status to modeling"

KEY = "6f1b0b7a-0d3d-4f2e-8f9a-7c1d2e3f4a5b"
BODY = b'{"path": "characters/mech_scout/asset.yaml", "status": "modeling"}'
OTHER_BODY = b'{"path": "characters/mech_scout/asset.yaml", "status": "approved"}'

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
MUCH_LATER = NOON + DEFAULT_LIFETIME + timedelta(minutes=1)


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC: BEFORE})
    built.clone(PROJECT)
    return built


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


def an_edit(content: bytes = AFTER, based_on: bytes = BEFORE) -> Edit:
    return Edit(path=SPEC, content=content, based_on=ContentHash.of(based_on))


def write(host: InMemoryRepositoryHost, edit: Edit | None = None):
    return write_back(
        PROJECT,
        [edit or an_edit()],
        repository_host=host,
        author=RAFA,
        message=MESSAGE,
    )


def attempt(
    host: InMemoryRepositoryHost,
    store: InMemoryIdempotencyStore,
    *,
    body: bytes = BODY,
    at: datetime = NOON,
    edit: Edit | None = None,
):
    """One attempt at the write, under the idempotency key."""
    return once(
        KEY,
        body,
        lambda: write(host, edit),
        store=store,
        clock=lambda: at,
        render=lambda outcome: str(outcome.commit.revision),
    )


# --------------------------------------------------------------------------
# A replay returns the original outcome
# --------------------------------------------------------------------------


def test_the_first_attempt_runs_the_operation_and_records_it(
    host: InMemoryRepositoryHost, store: InMemoryIdempotencyStore
) -> None:
    record = ran(attempt(host, store))

    assert record.succeeded
    assert record.payload
    assert host.remote_files(PROJECT)[SPEC] == AFTER


def test_a_replay_returns_the_stored_outcome(
    host: InMemoryRepositoryHost, store: InMemoryIdempotencyStore
) -> None:
    first = ran(attempt(host, store))

    replayed = ran(attempt(host, store))

    assert replayed == first


def test_a_retried_write_produces_exactly_one_commit(
    host: InMemoryRepositoryHost, store: InMemoryIdempotencyStore
) -> None:
    """The point of the whole mechanism, stated as the task states it."""
    ran(attempt(host, store))
    ran(attempt(host, store))
    ran(attempt(host, store))

    assert len(host.commits(PROJECT)) == 1


def test_a_replay_runs_nothing_at_all(
    host: InMemoryRepositoryHost, store: InMemoryIdempotencyStore
) -> None:
    """Not merely idempotent by outcome — the operation is not performed again."""
    ran(attempt(host, store))
    host.reject_next_pushes(PROJECT, times=99)

    assert isinstance(attempt(host, store), Ok)


# --------------------------------------------------------------------------
# A different body under the same key is refused
# --------------------------------------------------------------------------


def test_the_same_key_with_a_different_body_is_refused(
    host: InMemoryRepositoryHost, store: InMemoryIdempotencyStore
) -> None:
    ran(attempt(host, store))

    outcome = attempt(host, store, body=OTHER_BODY)

    assert isinstance(outcome, Conflict)
    assert refused(outcome).identifier == "idempotency.mismatch"


def test_a_refused_replay_writes_nothing(
    host: InMemoryRepositoryHost, store: InMemoryIdempotencyStore
) -> None:
    ran(attempt(host, store))

    attempt(host, store, body=OTHER_BODY)

    assert len(host.commits(PROJECT)) == 1


# --------------------------------------------------------------------------
# A refusal is replayed as a refusal
# --------------------------------------------------------------------------


def test_a_write_that_was_refused_replays_as_the_same_refusal(
    host: InMemoryRepositoryHost, store: InMemoryIdempotencyStore
) -> None:
    """A lost response on a refused write must not become an apply."""
    stale = an_edit(based_on=b"something else entirely")
    first = ran(attempt(host, store, edit=stale))

    replayed = ran(attempt(host, store, edit=an_edit()))

    assert not first.succeeded
    assert replayed == first
    assert host.commits(PROJECT) == ()


# --------------------------------------------------------------------------
# The content hash is the backstop, not the key
# --------------------------------------------------------------------------


def test_a_retry_after_the_key_expired_is_refused_by_the_content_precondition(
    host: InMemoryRepositoryHost, store: InMemoryIdempotencyStore
) -> None:
    """D11's interlock: the key makes a retry quiet, the hash makes it safe.

    The expired key means the operation really is performed again — and D5's
    per-file precondition is what refuses it. `once` itself succeeded: the
    refusal it reports is the write's, recorded, which is exactly the
    distinction between *this key was used for another request* (a refusal of
    the idempotency layer) and *the content moved* (a refusal of the write).
    """
    ran(attempt(host, store))

    late = ran(attempt(host, store, at=MUCH_LATER))

    assert not late.succeeded
    assert late.kind is FailureKind.CONFLICT
    assert late.identifier == "edit.conflict"
    assert len(host.commits(PROJECT)) == 1
