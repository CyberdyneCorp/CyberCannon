"""Tasks 11.4 and 11.5 — the two drills that make the slogans testable.

`project.md` says git is the source of truth and that PostgreSQL and MinIO are a
rebuildable index and a blob mirror. That is a claim about what happens when all
three are destroyed, and a claim of that shape is worth exactly as much as the
drill that runs it.

**11.4, the recovery drill.** Every answer a project gives is recorded — the
listing, every lookup, every search, the specification content itself, the
project's asset requests, and the bytes behind every mirrored blob. Then the
working copy is deleted, the bucket is emptied, the schema is dropped, and the
service is restarted from nothing but the remote. Every recorded answer must
come back identical, blobs included and **under the same keys**, because content
addressing is what makes that sentence sayable. The elapsed time is measured and
printed: the recovery procedure is documented in `docs/recovery.md`, and the
number there comes from this test rather than from an estimate.

**11.5, the concurrency drill.** Two people edit the same specification and two
edit different ones, with somebody pushing straight to the remote in between.
The specified outcome is exact: both edits to different files apply, the pair on
one file produces one success and one conflict, the outside commit survives, and
nothing is left local. D5 and D6 are the mechanism; this is the drill.

Both run against real git, a real PostgreSQL and a real S3 API. A drill over
fakes would be a drill over the assumptions being tested.
"""

from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import boto3
import psycopg
import pytest
from moto import mock_aws
from staged_project import (
    MULE_SPEC,
    PROJECT,
    SCOUT_EXPORT,
    SCOUT_SPEC,
    Staged,
    ready,
)
from test_postgres_index import Answers, fingerprints_under

from cybercanon.adapters.outbound.minio.blob_store import S3BlobStore
from cybercanon.adapters.outbound.postgres.migrations import apply_migrations
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.application.results import Conflict, Ok, succeeded
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.blob_mirror import mirror_project
from cybercanon.application.use_cases.hosted_repository import (
    Edit,
    rebuild_project_index,
    write_back,
)
from cybercanon.application.use_cases.requests import (
    list_requests,
    raise_request,
    transition_request,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.identity import ActorId
from cybercanon.domain.requests import (
    Discipline,
    RequestId,
    RequestState,
)
from cybercanon.domain.requests import raise_request as build_request
from cybercanon.domain.revisions import ContentHash

pytestmark = pytest.mark.integration

BUCKET = "cybercanon-blobs"
REGION = "us-east-1"

MIGRATIONS = Path("db/migrations")
TABLES = ("assets", "search_misses", "idempotency_keys", "dismissals", "schema_migrations")

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
ANA = GitAuthor(name="Ana", email="ana@cyberdyne.com")

RAFA_ID = ActorId("auth|rafa")
ANA_ID = ActorId("auth|ana")

EXPORTS = {"mech_scout": (SCOUT_EXPORT,)}

SCOUT_EDIT = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"
MULE_EDIT = b"schema_version: 1\nid: mule\nname: Mule Hauler\nstatus: modeling\n"
OTHER_EDIT = b"schema_version: 1\nid: mech_scout\nname: Scout Mech II\n"
OUTSIDE = b"schema_version: 1\nid: mule\nname: Mule Hauler\naliases: [hauler]\n"

MESSAGE = "mech_scout: set status"


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    return ready(tmp_path)


@pytest.fixture
def blobs() -> Iterator[S3BlobStore]:
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name=REGION,
            aws_access_key_id="integration",
            aws_secret_access_key="integration",
        )
        client.create_bucket(Bucket=BUCKET)
        yield S3BlobStore(
            client,
            BUCKET,
            base_url="https://blobs.cyberdyne.example",
            secret=b"a-configured-link-signing-key",
        )


# --------------------------------------------------------------------------
# 11.4 — delete the working copy, empty the store, drop the database
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Everything:
    """Every answer a project can give, as one comparable value.

    The point of one value rather than five assertions is that the drill has to
    be exhaustive to mean anything: a recovery that restored four of five kinds
    of answer would pass a test written as four assertions and be a data loss.
    """

    index: Mapping[str, object]
    specifications: Mapping[str, bytes]
    requests: tuple[tuple[str, str, str | None], ...]
    blobs: Mapping[str, bytes]

    @staticmethod
    def of(staged: Staged, index: PostgresSearchIndex, blobs: S3BlobStore) -> Everything:
        head = staged.host.head(PROJECT)
        listing = ran(list_requests(PROJECT, repository_host=staged.host))
        keys = _mirror(staged, blobs).keys
        return Everything(
            index=_answers(index),
            specifications={
                path: staged.host.read(PROJECT, path, head) or b""
                for path in (SCOUT_SPEC, MULE_SPEC)
            },
            requests=tuple(
                (str(one.id), str(one.state), _named(one.assignee)) for one in listing.requests
            ),
            blobs={key: blobs.verified(key) for key in sorted(set(keys.values()))},
        )


def test_the_recovery_drill_restores_every_answer(
    staged: Staged, blobs: S3BlobStore, postgres_dsn: str, repo_root: Path, capsys
) -> None:
    """Destroy all three stores, restart, and compare every answer (11.4)."""
    _raise_two_requests(staged)
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
        before = Everything.of(staged, index, blobs)

    _destroy(staged, blobs, postgres_dsn)
    started = time.monotonic()
    apply_migrations(postgres_dsn, repo_root / MIGRATIONS)
    staged.host.recover(PROJECT)
    with PostgresSearchIndex(postgres_dsn) as rebuilt:
        _rebuild(staged, rebuilt)
        after = Everything.of(staged, rebuilt, blobs)
    elapsed = time.monotonic() - started

    assert after == before
    assert after.requests, "the drill is empty unless the project had requests"
    with capsys.disabled():
        print(f"\nrecovery drill: {elapsed:.2f}s for {len(after.blobs)} blobs")


def test_the_destruction_really_destroyed_all_three(
    staged: Staged, blobs: S3BlobStore, postgres_dsn: str
) -> None:
    """Otherwise the drill above would be asserting that nothing happened."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
    keys = _mirrored_keys(staged, blobs)

    _destroy(staged, blobs, postgres_dsn)

    assert not staged.host.path(PROJECT).exists()
    assert not any(blobs.exists(key) for key in keys)
    with (
        psycopg.connect(postgres_dsn, autocommit=True) as connection,
        pytest.raises(psycopg.errors.UndefinedTable),
    ):
        connection.execute("SELECT count(*) FROM assets")


def test_the_blobs_come_back_under_the_keys_they_had(
    staged: Staged, blobs: S3BlobStore, postgres_dsn: str, repo_root: Path
) -> None:
    """Content addressing is what lets recovery be stated as *the same keys*."""
    before = _mirror(staged, blobs).keys

    _destroy(staged, blobs, postgres_dsn)
    apply_migrations(postgres_dsn, repo_root / MIGRATIONS)
    staged.host.recover(PROJECT)
    after = _mirror(staged, blobs).keys

    assert after == before
    assert all(blobs.exists(key) for key in set(before.values()))


def test_a_request_raised_before_the_drill_keeps_its_state_and_attribution(
    staged: Staged, blobs: S3BlobStore, postgres_dsn: str, repo_root: Path
) -> None:
    """Requests are repository content (D7), so the index never held them."""
    _raise_two_requests(staged)
    before = ran(list_requests(PROJECT, repository_host=staged.host)).requests

    _destroy(staged, blobs, postgres_dsn)
    apply_migrations(postgres_dsn, repo_root / MIGRATIONS)
    staged.host.recover(PROJECT)

    assert ran(list_requests(PROJECT, repository_host=staged.host)).requests == before
    assert [str(one.state) for one in before] == ["open", "accepted"]
    assert all(one.history[0].actor == RAFA_ID for one in before)


# --------------------------------------------------------------------------
# 11.5 — two pairs of writers, and somebody pushing in between
# --------------------------------------------------------------------------


def test_the_concurrency_drill_produces_exactly_the_specified_outcomes(
    staged: Staged,
) -> None:
    """Different files both apply; the same file is one success and one conflict."""
    apart = _concurrently(
        staged,
        (_edit(SCOUT_SPEC, SCOUT_EDIT), RAFA),
        (_edit(MULE_SPEC, MULE_EDIT), ANA),
    )

    assert [succeeded(outcome) for outcome in apart] == [True, True]

    staged.commit_outside(MULE_SPEC, OUTSIDE, "somebody edits the mule directly")
    staged.host.fetch(PROJECT, confirmed_at=NOON)
    head = staged.host.head(PROJECT)
    together = _concurrently(
        staged,
        (_edit(SCOUT_SPEC, OTHER_EDIT, staged.host.read(PROJECT, SCOUT_SPEC, head)), RAFA),
        (_edit(SCOUT_SPEC, MULE_EDIT, staged.host.read(PROJECT, SCOUT_SPEC, head)), ANA),
    )

    assert len([one for one in together if succeeded(one)]) == 1
    assert len([one for one in together if isinstance(one, Conflict)]) == 1


def test_the_outside_commit_survives_the_drill(staged: Staged) -> None:
    """A retry re-evaluates the precondition; it never forces, merges or rebases."""
    _concurrently(
        staged,
        (_edit(SCOUT_SPEC, SCOUT_EDIT), RAFA),
        (_edit(MULE_SPEC, MULE_EDIT), ANA),
    )
    staged.commit_outside("props/crate/asset.yaml", b"schema_version: 1\nid: crate\n", "a crate")
    staged.host.fetch(PROJECT, confirmed_at=NOON)
    head = staged.host.head(PROJECT)

    ran(
        write_back(
            PROJECT,
            [_edit(SCOUT_SPEC, OTHER_EDIT, staged.host.read(PROJECT, SCOUT_SPEC, head))],
            repository_host=staged.host,
            author=RAFA,
            message=MESSAGE,
        )
    )

    after = staged.host.head(PROJECT)
    assert staged.host.read(PROJECT, "props/crate/asset.yaml", after) is not None
    assert staged.host.read(PROJECT, SCOUT_SPEC, after) == OTHER_EDIT
    assert staged.host.unpushed(PROJECT) == ()


# --------------------------------------------------------------------------
# The drill's moving parts
# --------------------------------------------------------------------------


def _answers(index: PostgresSearchIndex) -> Mapping[str, object]:
    """Every answer the index gives, with the staleness fingerprint left out.

    A fingerprint is the index's hint about a file *on this disk* — its size and
    its modification time — and a working copy that was re-cloned legitimately
    has new timestamps for the same bytes. The guarantee is that every answer
    comes back identical, not that the recovery forged the file system's clock.
    """
    answered = Answers.of(index)
    return {
        "listing": _rows(answered.listing),
        "filtered": {name: _rows(rows) for name, rows in answered.filtered.items()},
        "lookups": {name: _row(entry) for name, entry in answered.lookups.items()},
        "searches": {
            term: tuple((hit.asset_id, hit.kind.value) for hit in hits)
            for term, hits in answered.searches.items()
        },
    }


def _rows(entries: Sequence[object]) -> tuple[object, ...]:
    return tuple(_row(entry) for entry in entries)


def _row(entry: object) -> object:
    return None if entry is None else replace(entry, fingerprint=None)


def _destroy(staged: Staged, blobs: S3BlobStore, dsn: str) -> None:
    """Delete the working copy, empty the object store, drop the schema."""
    shutil.rmtree(staged.host.path(PROJECT))
    blobs.empty()
    with psycopg.connect(dsn, autocommit=True) as connection:
        for table in TABLES:
            connection.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def _mirrored_keys(staged: Staged, blobs: S3BlobStore) -> tuple[str, ...]:
    """Every key this project's content is stored under, right now."""
    return tuple(sorted(set(_mirror(staged, blobs).keys.values())))


def _rebuild(staged: Staged, index: PostgresSearchIndex) -> None:
    outcome = rebuild_project_index(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        search_index=index,
        fingerprints=fingerprints_under(staged.working_copy),
    )

    assert isinstance(outcome, Ok), outcome
    assert outcome.value.is_complete, outcome.value.unreadable


def _mirror(staged: Staged, blobs: S3BlobStore):
    report = mirror_project(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        blob_store=blobs,
        exports=EXPORTS,
    )

    assert isinstance(report, Ok), report
    return report.value


def _raise_two_requests(staged: Staged) -> None:
    """One open and one accepted, so the drill covers a request with a history."""
    for identifier in ("req-0001", "req-0002"):
        ran(
            raise_request(
                PROJECT,
                build_request(
                    RequestId(identifier),
                    author=RAFA_ID,
                    discipline=Discipline.MODELING,
                    description="a supply crate for the loading dock",
                    at=NOON,
                    assignee=ANA_ID,
                ),
                repository_host=staged.host,
                author=RAFA,
                clock=lambda: NOON,
            )
        )
    ran(
        transition_request(
            PROJECT,
            RequestId("req-0002"),
            RequestState.ACCEPTED,
            actor=ANA_ID,
            repository_host=staged.host,
            author=ANA,
            clock=lambda: NOON,
        )
    )


def _edit(path: str, content: bytes, based_on: bytes | None = None) -> Edit:
    current = based_on if based_on is not None else _current(path)
    return Edit(path=path, content=content, based_on=ContentHash.of(current))


def _current(path: str) -> bytes:
    """The seeded content an edit is composed against, read from the corpus."""
    from staged_project import CORPUS

    return CORPUS[path]


def _concurrently(
    staged: Staged, first: tuple[Edit, GitAuthor], second: tuple[Edit, GitAuthor]
) -> list[object]:
    """Both edits submitted at once, by two threads, against one host."""
    outcomes: list[object] = [None, None]
    barrier = threading.Barrier(2)

    def submit(index: int, edit: Edit, author: GitAuthor) -> None:
        barrier.wait()
        outcomes[index] = write_back(
            PROJECT, [edit], repository_host=staged.host, author=author, message=MESSAGE
        )

    _run((lambda: submit(0, *first), lambda: submit(1, *second)))
    return outcomes


def _run(work: Sequence[Callable[[], None]]) -> None:
    threads = [threading.Thread(target=one) for one in work]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)


def _named(value: object) -> str | None:
    return str(value) if value is not None else None
