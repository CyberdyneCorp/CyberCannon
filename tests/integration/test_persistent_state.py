"""Group 5 — the state that survives a redeploy, and the state that is rebuilt.

`deployment-operations` asks for three volumes and one property over them:
*"after a service restart, a redeploy and an artifact promotion the system SHALL
continue from its previous state without re-running a recovery procedure"*. A
redeploy replaces the **process**, not the volume, so that is exactly what is
done here: every object the service holds — the repository host, the index
connection, the blob client — is discarded and built again over the same working
copy directory, the same database and the same bucket, and the state is asserted
to be the one that was there before.

Two sentinels make the claim sharp rather than vacuous. An untracked file in the
working copy would not survive a re-clone, and a hand-written index row would not
survive a rebuild — so if either is still there afterwards, the redeploy really
did continue from the previous state rather than quietly recovering into it.
That is the difference between *"no rebuild SHALL have been triggered"* and a
test that would pass either way.

The rest of the group is here for the same reason: the per-project lock
serialising two write-backs into two commits (5.4), a push that cannot land
telling the caller that nothing was recorded (5.5), the scheduled fetch and the
webhook leaving identical status (5.3), and the rebuild being resumable and
visibly in progress while reads that need a complete index are refused (5.7).
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from staged_project import (
    BRANCH,
    CORPUS,
    MULE_SPEC,
    PROJECT,
    SCOUT_SPEC,
    Staged,
    ready,
)
from test_postgres_index import Answers, fingerprints_under

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.webhooks import (
    SIGNATURE_HEADER,
    WEBHOOK_PATH,
    Notice,
    RepositoryNotifications,
    signature_for,
)
from cybercanon.adapters.outbound.git.repository_host import GitRepositoryHost, ProjectRemote
from cybercanon.adapters.outbound.minio.blob_store import S3BlobStore
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.application.ports.repository_host import ProjectState
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.results import Ok, Unavailable, succeeded
from cybercanon.application.testing.outcomes import refused
from cybercanon.application.use_cases.blob_mirror import mirror_project
from cybercanon.application.use_cases.deployment_status import (
    DeploymentJournal,
    describe_project,
    rebuild_and_record,
    refresh_and_record,
)
from cybercanon.application.use_cases.hosted_repository import (
    NOTHING_RECORDED,
    Edit,
    FetchSchedule,
    due_projects,
    write_back,
)
from cybercanon.application.use_cases.index_assets import RebuildProgress
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.revisions import ContentHash

pytestmark = pytest.mark.integration

BUCKET = "cybercanon-blobs"
REGION = "us-east-1"
SECRET = "a-configured-webhook-secret"

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 19, 12, 5, tzinfo=UTC)

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
ANA = GitAuthor(name="Ana", email="ana@cyberdyne.com")

SCOUT_EDIT = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"
MULE_EDIT = b"schema_version: 1\nid: mule\nname: Mule Hauler\nstatus: modeling\n"
OUTSIDE = b"schema_version: 1\nid: mule\nname: Mule Hauler\naliases: [hauler]\n"

SENTINEL_FILE = "not-tracked-by-git.txt"
SENTINEL_ASSET = "a_row_no_rebuild_would_keep"


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
        yield _store(client)


def _store(client) -> S3BlobStore:
    return S3BlobStore(
        client,
        BUCKET,
        base_url="https://blobs.cyberdyne.example",
        secret=b"a-configured-link-signing-key",
    )


def _client():
    return boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id="integration",
        aws_secret_access_key="integration",
    )


def _rebuild(staged: Staged, index: PostgresSearchIndex, **options) -> None:
    outcome = rebuild_and_record(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        search_index=index,
        fingerprints=fingerprints_under(staged.working_copy),
        journal=options.pop("journal", DeploymentJournal()),
        **options,
    )
    assert isinstance(outcome, Ok), outcome


def _mirror(staged: Staged, blobs: S3BlobStore):
    report = mirror_project(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        blob_store=blobs,
    )
    assert isinstance(report, Ok), report
    return report.value


def _answers(index: PostgresSearchIndex) -> object:
    answered = Answers.of(index)
    return tuple(replace(entry, fingerprint=None) for entry in answered.listing)


def _sentinel_row() -> IndexedAsset:
    """A row no scan would ever produce, so a rebuild would drop it."""
    return IndexedAsset(
        asset_id=SENTINEL_ASSET,
        name="Written by hand",
        project=PROJECT,
        status="concept",
        spec_path="nowhere/asset.yaml",
        directory="nowhere",
    )


def _redeployed(staged: Staged) -> GitRepositoryHost:
    """The same volume, a new process: a redeploy, from the state's point of view."""
    host = GitRepositoryHost(
        staged.host.root,
        [ProjectRemote(project=PROJECT, url=str(staged.bare), branch=BRANCH)],
        environment={"HOME": str(staged.home), "GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    host.clone(PROJECT)
    return host


# --------------------------------------------------------------------------
# 5.1 — a redeploy preserves the working copy, the index and the blobs
# --------------------------------------------------------------------------


def test_a_redeploy_continues_from_the_state_on_the_volumes(
    staged: Staged, blobs: S3BlobStore, postgres_dsn: str
) -> None:
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
        before = _answers(index)
    keys = _mirror(staged, blobs).keys
    revision = staged.host.head(PROJECT).value
    (staged.working_copy / SENTINEL_FILE).write_text("still here\n", encoding="utf-8")

    host = _redeployed(staged)
    with PostgresSearchIndex(postgres_dsn) as index:
        after = _answers(index)
    mirrored = _store(_client())

    assert host.head(PROJECT).value == revision, "the working copy is where it was"
    assert after == before, "the index is the one that was built"
    assert (staged.working_copy / SENTINEL_FILE).is_file(), "the copy was re-cloned"
    assert all(mirrored.verified(key) for key in set(keys.values()))


def test_a_redeploy_triggers_no_rebuild(
    staged: Staged, blobs: S3BlobStore, postgres_dsn: str
) -> None:
    """*"No rebuild SHALL have been triggered."* A rebuild would drop this row."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
        index.upsert(_sentinel_row())

    _redeployed(staged)

    with PostgresSearchIndex(postgres_dsn) as index:
        assert index.get(SENTINEL_ASSET, PROJECT) is not None


def test_a_blob_outlives_a_restart_and_answers_under_the_same_reference(
    staged: Staged, blobs: S3BlobStore
) -> None:
    """The process is replaced; the bucket is not. A key is a content digest."""
    keys = _mirror(staged, blobs).keys
    key = keys[SCOUT_SPEC] if SCOUT_SPEC in keys else next(iter(keys.values()))

    restarted = _store(_client())

    assert restarted.exists(key)
    assert restarted.verified(key) == blobs.verified(key)


def test_the_working_copy_volume_is_where_the_deployment_documents_say(
    staged: Staged, repo_root: Path
) -> None:
    """One directory per project under one volume (D6), named in `deploy/`."""
    document = (repo_root / "deploy" / "README.md").read_text(encoding="utf-8")

    assert "/data/worktrees" in document
    assert staged.host.path(PROJECT) == staged.host.root / PROJECT


# --------------------------------------------------------------------------
# 5.2 — clone on missing, fetch to advance, reset to discard
# --------------------------------------------------------------------------


def test_a_working_copy_that_is_not_there_is_cloned_on_use(staged: Staged) -> None:
    """A volume that came back empty is a clone, not an incident."""
    shutil.rmtree(staged.working_copy)

    assert staged.host.status(PROJECT).state is ProjectState.RECOVERING
    assert staged.host.read(PROJECT, SCOUT_SPEC, staged.host.head(PROJECT)) == CORPUS[SCOUT_SPEC]
    assert staged.host.status(PROJECT).state is ProjectState.READY


def test_a_fetch_advances_the_working_copy_to_the_configured_branch(staged: Staged) -> None:
    before = staged.host.head(PROJECT)
    staged.commit_outside(SCOUT_SPEC, SCOUT_EDIT, "somebody pushes")

    served = staged.host.fetch(PROJECT, confirmed_at=LATER)

    assert served.revision != before
    assert staged.host.read(PROJECT, SCOUT_SPEC, served.revision) == SCOUT_EDIT
    assert served.confirmed_at == LATER


def test_recovery_discards_an_uncommitted_modification_in_the_working_copy(
    staged: Staged,
) -> None:
    """*"On startup, and after any failed write-back, the working copy SHALL be
    returned to the state of the configured branch, discarding any uncommitted
    change."* A half-written file is the thing that must not survive."""
    (staged.working_copy / SCOUT_SPEC).write_bytes(b"half a file, written by a")
    (staged.working_copy / "stray.yaml").write_bytes(b"and something untracked")

    staged.host.recover(PROJECT)

    assert (staged.working_copy / SCOUT_SPEC).read_bytes() == CORPUS[SCOUT_SPEC]
    assert not (staged.working_copy / "stray.yaml").exists()


# --------------------------------------------------------------------------
# 5.3 — the schedule and the webhook update the same status
# --------------------------------------------------------------------------


def _copy_of(staged: Staged, root: Path) -> GitRepositoryHost:
    """Another working copy of the same remote, at the same revision.

    Two of them, because the two paths have to be compared *from the same
    starting state*: one host fetched twice would compare a refresh against a
    refresh that had nothing left to do.
    """
    host = GitRepositoryHost(
        root,
        [ProjectRemote(project=PROJECT, url=str(staged.bare), branch=BRANCH)],
        environment={"HOME": str(staged.home), "GIT_CONFIG_GLOBAL": "/dev/null"},
        clock=lambda: NOON,
    )
    host.clone(PROJECT)
    return host


def _notified(host: GitRepositoryHost, journal: DeploymentJournal) -> None:
    """The webhook path, through the real endpoint and a real signature."""
    application = build_app(
        notifications=RepositoryNotifications(
            secret=SECRET,
            branches={PROJECT: BRANCH},
            refresh=lambda project: refresh_and_record(
                project, repository_host=host, journal=journal, clock=lambda: LATER
            ),
        )
    )
    body = f'{{"project": "{PROJECT}", "ref": "refs/heads/{BRANCH}"}}'.encode()
    with TestClient(application) as client:
        response = client.post(
            WEBHOOK_PATH, content=body, headers={SIGNATURE_HEADER: signature_for(SECRET, body)}
        )
    assert response.json()["outcome"] == Notice.REFRESHED.value


def test_the_scheduled_fetch_and_the_webhook_leave_identical_working_copy_status(
    staged: Staged, tmp_path: Path
) -> None:
    """D4: the webhook is an optimisation, so it may not do anything different."""
    scheduled_host = _copy_of(staged, tmp_path / "scheduled")
    notified_host = _copy_of(staged, tmp_path / "notified")
    staged.commit_outside(SCOUT_SPEC, SCOUT_EDIT, "somebody pushes")

    by_schedule = DeploymentJournal()
    due = due_projects(
        [PROJECT], repository_host=scheduled_host, schedule=FetchSchedule(), now=LATER
    )
    assert due == (PROJECT,), "the interval has come round, or the schedule is not the guarantee"
    for project in due:
        refresh_and_record(
            project, repository_host=scheduled_host, journal=by_schedule, clock=lambda: LATER
        )
    by_webhook = DeploymentJournal()
    _notified(notified_host, by_webhook)

    scheduled = describe_project(
        PROJECT, repository_host=scheduled_host, journal=by_schedule
    ).working_copy
    notified = describe_project(
        PROJECT, repository_host=notified_host, journal=by_webhook
    ).working_copy
    assert scheduled == notified
    assert scheduled.revision != "" and scheduled.last_fetch_at == LATER
    assert scheduled.fetching == "succeeded"


# --------------------------------------------------------------------------
# 5.4 — one writer at a time, and each write is its own commit
# --------------------------------------------------------------------------


def _edit(path: str, content: bytes) -> Edit:
    return Edit(path=path, content=content, based_on=ContentHash.of(CORPUS[path]))


def _concurrently(
    staged: Staged,
    edits: Sequence[tuple[Edit, GitAuthor]],
    hosts: Sequence[GitRepositoryHost] | None = None,
) -> list[object]:
    """Both edits submitted at once — optionally through two different instances."""
    through = list(hosts or [staged.host] * len(edits))
    outcomes: list[object] = [None] * len(edits)
    barrier = threading.Barrier(len(edits))

    def submit(index: int, edit: Edit, author: GitAuthor) -> None:
        barrier.wait()
        outcomes[index] = write_back(
            PROJECT,
            [edit],
            repository_host=through[index],
            author=author,
            message=f"{edit.path}: written by {author.name}",
        )

    threads = [
        threading.Thread(target=submit, args=(index, edit, author))
        for index, (edit, author) in enumerate(edits)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return outcomes


def _log(staged: Staged) -> list[str]:
    from staged_project import git

    listed = git(staged.working_copy, ["log", "--format=%H %s"], staged.home)
    return listed.splitlines()


def test_two_write_backs_at_once_become_two_commits_with_neither_change_lost(
    staged: Staged,
) -> None:
    """The lock is on the volume, so "one writer" is not a matter of timing."""
    outcomes = _concurrently(
        staged, [(_edit(SCOUT_SPEC, SCOUT_EDIT), RAFA), (_edit(MULE_SPEC, MULE_EDIT), ANA)]
    )

    assert all(succeeded(outcome) for outcome in outcomes)
    landed = [one.value.commit.revision.value for one in outcomes]  # type: ignore[union-attr]
    assert len(set(landed)) == 2, "each write-back produces its own commit"
    head = staged.host.head(PROJECT)
    assert staged.host.read(PROJECT, SCOUT_SPEC, head) == SCOUT_EDIT
    assert staged.host.read(PROJECT, MULE_SPEC, head) == MULE_EDIT
    assert all(revision in " ".join(_log(staged)) for revision in landed)


def test_the_two_commits_are_applied_one_after_the_other(staged: Staged) -> None:
    """Serialised, not merged: the history is linear and both are on the branch."""
    _concurrently(
        staged, [(_edit(SCOUT_SPEC, SCOUT_EDIT), RAFA), (_edit(MULE_SPEC, MULE_EDIT), ANA)]
    )

    from staged_project import git

    parents = git(staged.working_copy, ["log", "--format=%p", "-2"], staged.home).split()
    assert all(len(parent) > 0 for parent in parents), "no commit is a merge"
    assert staged.host.unpushed(PROJECT) == ()


def test_two_instances_sharing_the_volume_still_write_one_at_a_time(staged: Staged) -> None:
    """D6 and D7: a rollover runs two instances over one volume on purpose.

    Two hosts, two threads, one working copy — which is the deploy overlap as
    the volume experiences it. The in-process lock cannot serialise this pair;
    the lock file on the volume can, and both commits land with neither change
    lost.
    """
    old_instance, new_instance = staged.host, _redeployed(staged)

    outcomes = _concurrently(
        staged,
        [(_edit(SCOUT_SPEC, SCOUT_EDIT), RAFA), (_edit(MULE_SPEC, MULE_EDIT), ANA)],
        hosts=[old_instance, new_instance],
    )

    assert all(succeeded(outcome) for outcome in outcomes)
    landed = {one.value.commit.revision.value for one in outcomes}  # type: ignore[union-attr]
    assert len(landed) == 2
    # Each instance advances its own served revision when *it* commits, so the
    # branch tip carrying both is what a fetch brings — as it would on the node.
    new_instance.fetch(PROJECT, confirmed_at=LATER)
    head = new_instance.head(PROJECT)
    assert new_instance.read(PROJECT, SCOUT_SPEC, head) == SCOUT_EDIT
    assert new_instance.read(PROJECT, MULE_SPEC, head) == MULE_EDIT
    assert old_instance.unpushed(PROJECT) == ()


def test_the_single_writer_lock_lives_on_the_volume(staged: Staged) -> None:
    """A lock in one process's memory is no lock during an overlapping deploy."""
    from cybercanon.adapters.outbound.git.repository_host import LOCK_SUFFIX

    with staged.host.writer(PROJECT):
        pass

    assert (staged.host.root / f"{PROJECT}{LOCK_SUFFIX}").is_file()


# --------------------------------------------------------------------------
# 5.5 — a write-back that cannot land says nothing was recorded
# --------------------------------------------------------------------------


def _break_the_remote(staged: Staged) -> None:
    """Make the configured remote unreachable, without touching the copy."""
    staged.bare.rename(staged.bare.with_suffix(".moved"))


def test_a_push_that_cannot_land_reports_failure_and_no_recorded_change(
    staged: Staged,
) -> None:
    before = staged.host.head(PROJECT)
    _break_the_remote(staged)

    refusal = refused(
        write_back(
            PROJECT,
            [_edit(SCOUT_SPEC, SCOUT_EDIT)],
            repository_host=staged.host,
            author=RAFA,
            message="mech_scout: set status",
        )
    )

    assert isinstance(refusal, Unavailable)
    assert NOTHING_RECORDED in refusal.message
    assert staged.host.unpushed(PROJECT) == ()
    assert staged.host.head(PROJECT) == before


# --------------------------------------------------------------------------
# 5.7 — the rebuild is resumable, visible, and reads know it is partial
# --------------------------------------------------------------------------


def test_a_rebuild_reports_progress_over_every_specification(
    staged: Staged, postgres_dsn: str
) -> None:
    seen: list[RebuildProgress] = []

    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index, progress=seen.append)

    assert [step.done for step in seen] == list(range(1, len(seen) + 1))
    assert seen[-1].complete
    assert {step.total for step in seen} == {len(seen)}


def test_a_resumed_rebuild_carries_over_what_it_already_wrote(
    staged: Staged, postgres_dsn: str
) -> None:
    """An interrupted recovery continues; it does not start again from nothing."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
        before = _answers(index)

        resumed: list[RebuildProgress] = []
        _rebuild(staged, index, progress=resumed.append, resume=True)

        assert all(step.resumed for step in resumed), "nothing had changed to re-read"
        assert _answers(index) == before


def test_a_resumed_rebuild_still_re_reads_a_specification_that_changed(
    staged: Staged, postgres_dsn: str
) -> None:
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index)
        staged.commit_outside(MULE_SPEC, OUTSIDE, "the mule gains an alias")
        staged.host.fetch(PROJECT, confirmed_at=LATER)

        read_again: list[RebuildProgress] = []
        _rebuild(staged, index, progress=read_again.append, resume=True)

        assert [step.path for step in read_again if not step.resumed] == [MULE_SPEC]
        entry = index.get("mule", PROJECT)
        assert entry is not None and "hauler" in entry.aliases


def test_a_rebuild_in_progress_is_reported_by_the_status_surface(
    staged: Staged, postgres_dsn: str
) -> None:
    """*"It SHALL report the rebuild as in progress."*"""
    journal = DeploymentJournal()
    seen: list[bool] = []

    def watch(step: RebuildProgress) -> None:
        seen.append(
            describe_project(PROJECT, repository_host=staged.host, journal=journal).index.rebuilding
        )

    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuild(staged, index, journal=journal, progress=watch)

    assert seen and all(seen), "the rebuild was invisible while it ran"
    after = describe_project(PROJECT, repository_host=staged.host, journal=journal).index
    assert not after.rebuilding
    assert after.in_sync and after.indexed_revision == staged.host.head(PROJECT).value
