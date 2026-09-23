"""Group 7 — the three recovery procedures, each destroyed, run, and timed.

*"For each of the three persistent volumes there SHALL be a documented recovery
procedure with a stated expected duration … Each procedure SHALL be executed
against a non-production environment on a recurring basis, and its measured
duration SHALL be recorded alongside the procedure."*

The word that does the work in that sentence is **executed**. `add-web-backend`
already drills all three *together*, as one property — destroy everything,
restart from the remote, compare every answer. This suite is the operational
half `deployment-operations` owns and it is deliberately not the same shape:
**one volume at a time**, because that is how a volume is actually lost, and
each with its own measurement, because a single number for all three tells an
operator nothing about which procedure is the one that grew.

So there are three drills here, and each one:

1. destroys exactly one volume, leaving the other two intact;
2. runs the procedure `deploy/recovery.md` documents, through the entry point an
   operator runs by hand — never a reimplementation;
3. measures only the recovery, and compares it against the duration that
   document states;
4. asserts the answers that existed before the loss come back.

The fourth step is what stops the other three from being theatre. A drill that
measured a procedure without checking what it restored would be timing a
formatting exercise.

Everything runs against real git, a real PostgreSQL and a real S3 API, for the
reason the other drill gives: a drill over fakes would be a drill over the
assumptions being tested.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import boto3
import psycopg
import pytest
from moto import mock_aws
from staged_project import CORPUS, PROJECT, SCOUT_SPEC, Staged, ready
from test_postgres_index import Answers, fingerprints_under

from canon_drill import records
from canon_drill.__main__ import run_and_record
from canon_drill.drills import Environment, run_drills
from canon_drill.records import (
    BLOB_RE_MIRROR,
    INDEX_REBUILD,
    PROCEDURES,
    WORKING_COPY_RE_CLONE,
    expectations,
    format_duration,
)
from cybercanon.adapters.outbound.minio.blob_store import S3BlobStore
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.api import recover as recovery
from cybercanon.application.results import Ok
from cybercanon.application.use_cases.blob_mirror import mirror_project
from cybercanon.application.use_cases.hosted_repository import rebuild_project_index

pytestmark = pytest.mark.integration

BUCKET = "cybercanon-blobs"
REGION = "us-east-1"

EXPORTS = {"mech_scout": ("characters/mech_scout/exports/SM_mech_scout_LOD0.glb",)}

TABLES = ("assets", "search_misses", "idempotency_keys", "dismissals", "schema_migrations")

LEDGER = Path("deploy") / "recovery.md"

TODAY = date(2026, 9, 22)
NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# One pre-production project, with all three volumes populated
# --------------------------------------------------------------------------


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


@pytest.fixture
def stated(repo_root: Path) -> Mapping[str, timedelta]:
    """What `deploy/recovery.md` says each procedure should take."""
    document = (repo_root / LEDGER).read_text(encoding="utf-8")
    return {one.procedure: one.expected for one in expectations(document)}


def _rebuild(staged: Staged, index: PostgresSearchIndex) -> None:
    outcome = rebuild_project_index(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        search_index=index,
        fingerprints=fingerprints_under(staged.working_copy),
    )
    assert isinstance(outcome, Ok), outcome


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


def _lookups(dsn: str) -> Mapping[str, object]:
    """Every answer the index gives, without the on-disk staleness hint.

    A fingerprint is a claim about a file's size and modification time on *this*
    disk, and a working copy re-cloned a second ago legitimately has new ones
    for the same bytes. The guarantee is that every answer comes back, not that
    the recovery forged the file system's clock.
    """
    with PostgresSearchIndex(dsn) as index:
        answered = Answers.of(index)
    return {
        "listing": tuple(replace(entry, fingerprint=None) for entry in answered.listing),
        "lookups": {
            name: None if entry is None else replace(entry, fingerprint=None)
            for name, entry in answered.lookups.items()
        },
        "searches": {
            term: tuple(hit.asset_id for hit in hits) for term, hits in answered.searches.items()
        },
    }


def _blob_bytes(staged: Staged, blobs: S3BlobStore) -> Mapping[str, bytes]:
    keys = _mirror(staged, blobs).keys
    return {key: blobs.verified(key) for key in sorted(set(keys.values()))}


def _drop_schema(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        for table in TABLES:
            connection.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def _measured(procedure: Callable[[], object]) -> tuple[object, timedelta]:
    started = time.monotonic()
    outcome = procedure()
    return outcome, timedelta(seconds=time.monotonic() - started)


def _within(procedure: str, elapsed: timedelta, stated: Mapping[str, timedelta]) -> None:
    """The comparison `deploy/recovery.md` exists to make possible."""
    assert elapsed <= stated[procedure], (
        f"{procedure} took {format_duration(elapsed)}, over the "
        f"{format_duration(stated[procedure])} deploy/recovery.md states"
    )


# --------------------------------------------------------------------------
# 7.2 — the index volume is destroyed
# --------------------------------------------------------------------------


def test_the_index_recovery_restores_the_answers_that_existed_before_the_loss(
    staged: Staged, postgres_dsn: str, stated: Mapping[str, timedelta], capsys
) -> None:
    """*"Lookups SHALL return the same results they returned before the loss,
    and the elapsed time SHALL be recorded and compared against the stated
    expected duration."*"""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
    before = _lookups(postgres_dsn)
    assert before["listing"], "the project has an index to lose"

    _drop_schema(postgres_dsn)
    report, elapsed = _measured(lambda: recovery.recover([staged.working_copy], dsn=postgres_dsn))

    assert _lookups(postgres_dsn) == before
    _within(INDEX_REBUILD, elapsed, stated)
    with capsys.disabled():
        print(f"\n{INDEX_REBUILD}: {format_duration(elapsed)} ({report})")


def test_the_index_recovery_really_had_an_index_to_lose(staged: Staged, postgres_dsn: str) -> None:
    """Otherwise the drill above asserts that nothing happened."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)

    _drop_schema(postgres_dsn)

    with (
        psycopg.connect(postgres_dsn, autocommit=True) as connection,
        pytest.raises(psycopg.errors.UndefinedTable),
    ):
        connection.execute("SELECT count(*) FROM assets")


def test_the_index_recovery_leaves_the_working_copy_alone(
    staged: Staged, postgres_dsn: str
) -> None:
    """One volume at a time: the copy is what it rebuilt *from*."""
    revision = staged.host.head(PROJECT).value

    _drop_schema(postgres_dsn)
    recovery.recover([staged.working_copy], dsn=postgres_dsn)

    assert staged.host.head(PROJECT).value == revision
    assert (staged.working_copy / SCOUT_SPEC).is_file()


# --------------------------------------------------------------------------
# The rebuilt rows are keyed by the name the deployment serves (go-live B3)
# --------------------------------------------------------------------------

DECLARED = "Ronin"
"""What the working copy's `.canon/project.yaml` calls the project here.

Deliberately **not** :data:`PROJECT`. The rest of this suite stages a copy whose
declared name and served address are the same string, so every assertion it
makes about the recovery holds whichever of the two the rebuild keyed rows by —
which is exactly how a recovery that reported *"rebuilt 1 project(s), 1
asset(s)"* and left `/v1/projects/ronin/assets` answering `total: 0` went on
passing this suite. A fixture that agrees with the code under test cannot
disagree with it, and the only fix is a fixture that differs where the real
world differs: the address is configuration (`CANON_PROJECT`), the declared
name is repository content, and nothing keeps them equal — not even case.
"""

DIVERGENT = {**CORPUS, ".canon/project.yaml": f"schema_version: 1\nname: {DECLARED}\n".encode()}
"""The same project, declaring a name that is not the one it is served at."""


def test_the_index_recovery_keys_rows_by_the_name_the_deployment_serves(
    tmp_path: Path, postgres_dsn: str
) -> None:
    """B3: rows the hosted surface cannot read are not a recovered index.

    A deployment answers `/v1/projects/{project}/assets` at `CANON_PROJECT` and
    reads rows keyed by it, and the working copy lives at `<volume>/<that name>`
    — so the directory the operator names in the documented command *is* the
    key. A rebuild that took the name out of `.canon/project.yaml` instead was
    keying by repository content, which the address is deliberately not derived
    from.
    """
    staged = ready(tmp_path, DIVERGENT)
    assert DECLARED != PROJECT, "the fixture has to differ where the real world differs"
    assert staged.working_copy.name == PROJECT

    report = recovery.recover([staged.working_copy], dsn=postgres_dsn)

    with PostgresSearchIndex(postgres_dsn) as index:
        assert index.list_assets(project=PROJECT), (
            f"the recovery reported {report} and the deployment's own project has no rows to read"
        )
        assert not index.list_assets(project=DECLARED)


def test_the_divergent_fixture_really_declares_the_other_name(
    tmp_path: Path,
) -> None:
    """Otherwise the test above stages the agreeable corpus and proves nothing."""
    staged = ready(tmp_path, DIVERGENT)

    declared = (staged.working_copy / ".canon" / "project.yaml").read_text(encoding="utf-8")

    assert f"name: {DECLARED}" in declared
    assert f"name: {PROJECT}" not in declared


# --------------------------------------------------------------------------
# 7.3 — the blob volume is destroyed
# --------------------------------------------------------------------------


def test_the_blob_recovery_returns_every_derived_blob_under_the_same_reference(
    staged: Staged, blobs: S3BlobStore, stated: Mapping[str, timedelta], capsys
) -> None:
    """*"Every blob derived from repository content SHALL be retrievable again
    by the same reference."* Keys are content digests, which is what makes the
    sentence sayable at all."""
    before = _blob_bytes(staged, blobs)
    assert before, "the project has blobs to lose"

    blobs.empty()
    assert not any(blobs.exists(key) for key in before), "the volume was not really emptied"
    _, elapsed = _measured(lambda: _mirror(staged, blobs))

    assert _blob_bytes(staged, blobs) == before
    _within(BLOB_RE_MIRROR, elapsed, stated)
    with capsys.disabled():
        print(f"\n{BLOB_RE_MIRROR}: {format_duration(elapsed)} for {len(before)} blobs")


def test_the_blob_recovery_read_the_working_copy_and_not_a_backup(
    staged: Staged, blobs: S3BlobStore
) -> None:
    """A file the working copy no longer has cannot come back, and says so."""
    before = _blob_bytes(staged, blobs)
    blobs.empty()
    staged.commit_outside("characters/mech_scout/concept/front.png", None, "remove a view")
    staged.host.fetch(PROJECT, confirmed_at=NOON)

    report = _mirror(staged, blobs)

    assert set(report.keys.values()) < set(before), "it re-derived rather than restored"
    assert all(blobs.exists(key) for key in set(report.keys.values()))


# --------------------------------------------------------------------------
# 7.4 — a working-copy volume is destroyed
# --------------------------------------------------------------------------


def test_the_working_copy_recovery_restores_the_configured_branch_revision(
    staged: Staged, stated: Mapping[str, timedelta], capsys
) -> None:
    """*"The working copy SHALL be restored at the configured branch's current
    revision."*"""
    revision = staged.host.head(PROJECT).value
    shutil.rmtree(staged.working_copy)

    _, elapsed = _measured(lambda: staged.host.recover(PROJECT))

    assert staged.working_copy.is_dir()
    assert staged.host.head(PROJECT).value == revision
    _within(WORKING_COPY_RE_CLONE, elapsed, stated)
    with capsys.disabled():
        print(f"\n{WORKING_COPY_RE_CLONE}: {format_duration(elapsed)}")


def test_the_other_two_recoveries_run_from_the_restored_copy(
    staged: Staged, blobs: S3BlobStore, postgres_dsn: str
) -> None:
    """*"The index and blob recoveries SHALL be able to run from it."*

    The order the runbook states, and the reason it is an order: the copy is the
    only source the other two have.
    """
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
    before = (_lookups(postgres_dsn), _blob_bytes(staged, blobs))

    shutil.rmtree(staged.working_copy)
    blobs.empty()
    _drop_schema(postgres_dsn)
    staged.host.recover(PROJECT)
    recovery.recover([staged.working_copy], dsn=postgres_dsn)

    assert (_lookups(postgres_dsn), _blob_bytes(staged, blobs)) == before


def test_the_working_copy_recovery_advances_to_a_revision_pushed_since(
    staged: Staged,
) -> None:
    """*Current* revision, not the one the deleted copy happened to be at."""
    staged.commit_outside(SCOUT_SPEC, b"schema_version: 1\nid: mech_scout\nname: Scout II\n")
    before = staged.host.head(PROJECT).value
    shutil.rmtree(staged.working_copy)

    staged.host.recover(PROJECT)

    assert staged.host.head(PROJECT).value != before
    assert staged.host.read(PROJECT, SCOUT_SPEC, staged.host.head(PROJECT)) is not None


# --------------------------------------------------------------------------
# 7.5 — the scheduled job runs all three and writes its own record (D9)
# --------------------------------------------------------------------------


@pytest.fixture
def environment(staged: Staged, blobs: S3BlobStore, postgres_dsn: str) -> Environment:
    """The pre-production project, as the scheduled drill job addresses it."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
    _mirror(staged, blobs)
    return Environment(
        project=PROJECT,
        working_copy=staged.working_copy,
        re_clone=lambda: staged.host.recover(PROJECT),
        rebuild_index=lambda: recovery.recover([staged.working_copy], dsn=postgres_dsn),
        re_mirror_blobs=lambda: _mirror(staged, blobs),
        drop_blobs=blobs.empty,
        name="pre-production",
    )


@pytest.fixture
def ledger(tmp_path: Path, repo_root: Path) -> Path:
    """A copy of the committed runbook, so a drill can append to it for real."""
    copy = tmp_path / "recovery.md"
    copy.write_text((repo_root / LEDGER).read_text(encoding="utf-8"), encoding="utf-8")
    return copy


def test_one_scheduled_run_executes_all_three_procedures(environment: Environment) -> None:
    measured = run_drills(environment)

    assert tuple(one.procedure for one in measured) == (
        WORKING_COPY_RE_CLONE,
        INDEX_REBUILD,
        BLOB_RE_MIRROR,
    )
    assert all(one.measured > timedelta(0) for one in measured)
    assert set(environment.destroyed) == {WORKING_COPY_RE_CLONE, BLOB_RE_MIRROR}


def test_the_run_appends_date_procedure_and_measured_duration(
    environment: Environment, ledger: Path
) -> None:
    """*"A scheduled job … appends date, procedure and duration to
    `deploy/recovery.md`"* — written by the drill, not by whoever ran it."""
    before = records.drills(ledger.read_text(encoding="utf-8"))

    rows = run_and_record(environment, ledger=ledger, on=TODAY)

    after = records.drills(ledger.read_text(encoding="utf-8"))
    added = after[len(before) :]
    assert len(rows) == len(PROCEDURES)
    assert {one.procedure for one in added} == set(PROCEDURES)
    assert {one.on for one in added} == {TODAY}
    assert {one.environment for one in added} == {"pre-production"}
    assert all(one.measured > timedelta(0) for one in added), [one.row() for one in added]


def test_the_appended_record_satisfies_the_staleness_gate(
    environment: Environment, ledger: Path
) -> None:
    """The run is what makes the gate pass, which is the point of D9."""
    run_and_record(environment, ledger=ledger, on=TODAY)

    assert records.review(ledger.read_text(encoding="utf-8"), today=TODAY) == ()


def test_the_run_leaves_the_rest_of_the_runbook_untouched(
    environment: Environment, ledger: Path
) -> None:
    """It appends a row; it does not rewrite the procedures somebody follows."""
    before = ledger.read_text(encoding="utf-8")

    run_and_record(environment, ledger=ledger, on=TODAY)

    after = ledger.read_text(encoding="utf-8")
    assert after.startswith(before[: before.index(records.DRILL_LOG_HEADING)])
    assert records.expectations(after) == records.expectations(before)


def test_the_measured_durations_are_the_ones_written_down(
    environment: Environment, ledger: Path
) -> None:
    """A record that did not come from the measurement would be a record of nothing."""
    rows = run_and_record(environment, ledger=ledger, on=TODAY)
    recorded = records.drills(ledger.read_text(encoding="utf-8"))[-len(PROCEDURES) :]

    for drill, row in zip(recorded, rows, strict=True):
        assert drill.row() == row
        assert format_duration(drill.measured) in row
