"""Group 5 — the hosted working copy, against real repositories on disk.

The port conformance suite already runs `GitRepositoryHost` and the in-memory
fake through one contract, so what is left here is what only a real clone, a
real remote and a real push can show. Every test below is one of tasks 5.1-5.10,
and each is written against the thing the task says to verify rather than
against the implementation that satisfies it:

* **5.1** a project reports *provisioning* rather than an empty asset list;
* **5.2** a read that resolved its revision before a fetch still answers the
  pre-fetch content after it — D3's isolation, on real refs;
* **5.3** a commit pushed to the remote becomes visible when the interval
  elapses, with no notification involved at all;
* **5.4** the notification endpoint, through a real application and a real HMAC;
* **5.5** the revision and confirmation time on a read, and the staleness that
  appears when refreshes have been failing for longer than the interval;
* **5.6** `.canon/actors.yaml` on disk deciding who a commit is authored by, and
  refusing the person it does not name;
* **5.7** two edits at once, serialised, with the same-file pair producing one
  success and one conflict;
* **5.8** a deleted working copy and a diverged one;
* **5.9** a push that cannot happen leaving nothing local behind;
* **5.10** no credential, no volume path and no remote URL in anything a caller
  is told.

The remotes are bare repositories in a temporary directory, seeded through an
ordinary clone-and-push, so nothing here is a mock: when a push is rejected it
is git rejecting it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.webhooks import (
    SIGNATURE_HEADER,
    WEBHOOK_PATH,
    Notice,
    RepositoryNotifications,
    signature_for,
)
from cybercanon.adapters.outbound.git.repository_host import (
    CREDENTIAL_REFUSED,
    REASONS,
    GitRepositoryHost,
    ProjectRemote,
    classify,
)
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.ports.repository_host import FileChange, ProjectState
from cybercanon.application.results import Conflict, Forbidden, Unavailable, succeeded
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.hosted_repository import (
    AGENT_TRAILER,
    Edit,
    FetchSchedule,
    author_for,
    edit_message,
    read_at_revision,
    refresh_project,
    scheduled_refresh,
    write_back,
)
from cybercanon.application.use_cases.resolve_actor import (
    GitIdentitySource,
    IdentitySource,
    Resolution,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.revisions import ContentHash

pytestmark = pytest.mark.integration

PROJECT = "ronin"
BRANCH = "main"

SCOUT = "characters/mech_scout/asset.yaml"
MULE = "vehicles/mule/asset.yaml"
ACTORS = ".canon/actors.yaml"

SCOUT_CONTENT = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: concept\n"
MULE_CONTENT = b"schema_version: 1\nid: mule\nname: Mule\nstatus: concept\n"
SCOUT_EDIT = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"
MULE_EDIT = b"schema_version: 1\nid: mule\nname: Mule\nstatus: modeling\n"
OUTSIDE = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: validated\n"

ACTORS_YAML = b"""\
schema_version: 1
actors:
  - subject: auth|rafa
    display_name: Rafa
    emails:
      - rafa@cyberdyne.com
    default_role: ARTIST
"""

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
MESSAGE = edit_message("mech_scout", "set status to modeling")

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
INTERVAL = timedelta(minutes=5)

CORPUS = {SCOUT: SCOUT_CONTENT, MULE: MULE_CONTENT, ACTORS: ACTORS_YAML}

SECRET = "a-configured-webhook-secret"
TOKEN = "s3cret-deploy-token"


# --------------------------------------------------------------------------
# A remote, a host, and the two things a test stages from outside
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Staged:
    """One project: its bare remote, the host serving it, and where both live."""

    host: GitRepositoryHost
    remote: ProjectRemote
    bare: Path
    home: Path
    root: Path

    def outside_commit(self, path: str, content: bytes | None, message: str = "outside") -> None:
        """Somebody commits straight to the repository, past this service."""
        scratch = self.root / "outside"
        if not scratch.exists():
            _git(None, ["clone", "--quiet", str(self.bare), str(scratch)], self.home)
        _git(scratch, ["fetch", "--quiet", "origin", BRANCH], self.home)
        _git(scratch, ["reset", "--quiet", "--hard", f"origin/{BRANCH}"], self.home)
        _write(scratch, path, content)
        _commit(scratch, message, self.home)
        _git(scratch, ["push", "--quiet", "origin", f"HEAD:refs/heads/{BRANCH}"], self.home)

    def spec_store(self) -> GitSpecStore:
        return GitSpecStore(self.host.path(PROJECT))

    def log(self, *fields: str) -> str:
        """`git log -1` over the working copy, in whatever format was asked for."""
        return _git(
            self.host.path(PROJECT), ["log", "-1", f"--format={''.join(fields)}"], self.home
        ).strip()


def _git(root: Path | None, arguments: Sequence[str], home: Path) -> str:
    """One git command, isolated from whatever this machine's git is configured to do."""
    located = ["-C", str(root)] if root is not None else []
    completed = subprocess.run(
        ["git", *located, *arguments],
        check=True,
        capture_output=True,
        env={
            "PATH": _path(),
            "HOME": str(home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )
    return completed.stdout.decode("utf-8", errors="replace")


def _path() -> str:
    return os.environ.get("PATH", "/usr/bin:/bin")


def _write(root: Path, path: str, content: bytes | None) -> None:
    target = root / path
    if content is None:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _commit(root: Path, message: str, home: Path) -> None:
    _git(root, ["add", "--all"], home)
    _git(
        root,
        [
            "-c",
            "user.name=Seed",
            "-c",
            "user.email=seed@cyberdyne.example",
            "commit",
            "--quiet",
            "--allow-empty",
            "--message",
            message,
        ],
        home,
    )


def stage(tmp_path: Path, *, url: str | None = None, files: dict[str, bytes] | None = None):
    """A seeded bare remote and a host configured for it. Nothing is cloned yet."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    bare = tmp_path / "remote.git"
    _git(None, ["init", "--quiet", "--bare", f"--initial-branch={BRANCH}", str(bare)], home)
    seed = tmp_path / "seed"
    _git(None, ["clone", "--quiet", str(bare), str(seed)], home)
    for path, content in (CORPUS if files is None else files).items():
        _write(seed, path, content)
    _commit(seed, "seed the project", home)
    _git(seed, ["push", "--quiet", "origin", f"HEAD:refs/heads/{BRANCH}"], home)
    remote = ProjectRemote(project=PROJECT, url=url or str(bare), branch=BRANCH, credential=TOKEN)
    host = GitRepositoryHost(
        tmp_path / "working-copies",
        [remote],
        environment={"HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    return Staged(host=host, remote=remote, bare=bare, home=home, root=tmp_path)


def ready(tmp_path: Path, **options) -> Staged:
    """A staged project whose working copy has been obtained."""
    staged = stage(tmp_path, **options)
    staged.host.clone(PROJECT)
    return staged


def an_edit(path: str = SCOUT, content: bytes = SCOUT_EDIT, based_on: bytes = SCOUT_CONTENT):
    return Edit(path=path, content=content, based_on=ContentHash.of(based_on))


def rafa() -> Resolution:
    """The acting person, as the identity chain would have resolved them."""
    return Resolution(
        actor=Actor(id=ActorId("auth|rafa"), display_name="Rafa", roles=(Role.ARTIST,)),
        source=IdentitySource.PROVIDER,
        verified=True,
    )


def newcomer() -> Resolution:
    """Somebody the project's mapping has never heard of."""
    return Resolution(
        actor=Actor(id=ActorId("auth|newcomer"), display_name="Newcomer"),
        source=IdentitySource.PROVIDER,
        verified=True,
    )


# --------------------------------------------------------------------------
# 5.1 — a clone per project, and the four states it can be in
# --------------------------------------------------------------------------


def test_a_configured_project_is_provisioning_before_it_has_been_cloned(tmp_path: Path) -> None:
    staged = stage(tmp_path)

    assert staged.host.status(PROJECT).state is ProjectState.PROVISIONING


def test_listing_a_provisioning_project_reports_not_ready_rather_than_no_assets(
    tmp_path: Path,
) -> None:
    """`hosted-repository`: provisioning is reported, never faked as an empty list."""
    staged = stage(tmp_path)

    outcome = read_at_revision(
        PROJECT,
        lambda store: store.specs_under(""),
        repository_host=staged.host,
        spec_store=staged.spec_store(),
    )

    assert isinstance(outcome, Unavailable)
    assert "provisioning" in outcome.message


def test_cloning_puts_the_working_copy_on_the_configured_path_and_serves_its_head(
    tmp_path: Path,
) -> None:
    staged = stage(tmp_path)

    status = staged.host.clone(PROJECT)

    assert status.is_ready
    assert (staged.host.path(PROJECT) / SCOUT).read_bytes() == SCOUT_CONTENT
    assert status.served is not None
    assert status.served.revision == staged.host.head(PROJECT)


def test_a_remote_that_cannot_be_obtained_is_unavailable_with_a_named_reason(
    tmp_path: Path,
) -> None:
    staged = stage(tmp_path, url=str(tmp_path / "there-is-no-repository-here.git"))

    status = staged.host.clone(PROJECT)

    assert status.state is ProjectState.UNAVAILABLE
    assert status.reason in REASONS


def test_a_branch_the_remote_does_not_have_is_reported_as_the_missing_branch(
    tmp_path: Path,
) -> None:
    staged = stage(tmp_path)
    staged.host.configure(ProjectRemote(project=PROJECT, url=str(staged.bare), branch="canon"))

    status = staged.host.clone(PROJECT)

    assert status.state is ProjectState.UNAVAILABLE
    assert "branch" in status.reason


def test_a_refused_credential_is_read_out_of_what_the_transport_actually_said() -> None:
    """The classifier, over the complaint an ssh remote refusing a key produces."""
    refusal = "Permission denied (publickey).\nfatal: Could not read from remote repository."

    assert classify(refusal) == CREDENTIAL_REFUSED


# --------------------------------------------------------------------------
# 5.2 — reads come from the object database at a pinned revision (D3)
# --------------------------------------------------------------------------


def test_a_read_resolved_before_a_fetch_answers_the_pre_fetch_content(tmp_path: Path) -> None:
    staged = ready(tmp_path)
    held = staged.host.head(PROJECT)

    staged.outside_commit(SCOUT, OUTSIDE)
    ran(refresh_project(PROJECT, repository_host=staged.host))

    assert staged.host.read(PROJECT, SCOUT, held) == SCOUT_CONTENT
    assert staged.host.read(PROJECT, SCOUT, staged.host.head(PROJECT)) == OUTSIDE


def test_a_read_at_a_revision_never_looks_at_the_checked_out_tree(tmp_path: Path) -> None:
    """The tree is for writing. A file scribbled into it is not what a read answers."""
    staged = ready(tmp_path)
    (staged.host.path(PROJECT) / SCOUT).write_bytes(b"scribbled over by something else\n")

    assert staged.host.read(PROJECT, SCOUT, staged.host.head(PROJECT)) == SCOUT_CONTENT


def test_a_multi_file_read_at_one_revision_sees_one_revision(tmp_path: Path) -> None:
    staged = ready(tmp_path)
    held = staged.host.head(PROJECT)

    staged.outside_commit(SCOUT, OUTSIDE)
    staged.outside_commit(MULE, MULE_EDIT)
    ran(refresh_project(PROJECT, repository_host=staged.host))

    assert staged.host.read(PROJECT, SCOUT, held) == SCOUT_CONTENT
    assert staged.host.read(PROJECT, MULE, held) == MULE_CONTENT


# --------------------------------------------------------------------------
# 5.3 — the scheduled fetch, with no notification involved (D4)
# --------------------------------------------------------------------------


def test_a_commit_pushed_to_the_remote_arrives_when_the_interval_elapses(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)
    ran(refresh_project(PROJECT, repository_host=staged.host, clock=lambda: NOON))
    staged.outside_commit(SCOUT, OUTSIDE)
    schedule = FetchSchedule(interval=INTERVAL)

    early = scheduled_refresh(
        [PROJECT], repository_host=staged.host, schedule=schedule, clock=lambda: NOON
    )
    due = scheduled_refresh(
        [PROJECT],
        repository_host=staged.host,
        schedule=schedule,
        clock=lambda: NOON + INTERVAL,
    )

    assert early == ()
    assert ran(due[0]).refreshed
    assert staged.host.read(PROJECT, SCOUT, staged.host.head(PROJECT)) == OUTSIDE


def test_a_project_that_is_not_ready_is_never_due_a_scheduled_fetch(tmp_path: Path) -> None:
    staged = stage(tmp_path)

    assert (
        scheduled_refresh(
            [PROJECT],
            repository_host=staged.host,
            schedule=FetchSchedule(interval=INTERVAL),
            clock=lambda: NOON + INTERVAL,
        )
        == ()
    )


# --------------------------------------------------------------------------
# 5.4 — the notification endpoint (D4)
# --------------------------------------------------------------------------


@dataclass
class Refreshes:
    """What the endpoint asked to be refreshed, in order."""

    asked: list[str]

    def __call__(self, project: str) -> None:
        self.asked.append(project)


def notified_client(tmp_path: Path) -> tuple[TestClient, Refreshes]:
    asked = Refreshes(asked=[])
    application = build_app(
        notifications=RepositoryNotifications(
            secret=SECRET, branches={PROJECT: BRANCH}, refresh=asked
        )
    )
    return TestClient(application), asked


def post(client: TestClient, body: bytes, *, signature: str | None = None):
    offered = signature_for(SECRET, body) if signature is None else signature
    return client.post(WEBHOOK_PATH, content=body, headers={SIGNATURE_HEADER: offered})


def test_an_authenticated_notification_refreshes_the_named_project(tmp_path: Path) -> None:
    client, asked = notified_client(tmp_path)

    response = post(client, f'{{"project": "{PROJECT}", "ref": "refs/heads/{BRANCH}"}}'.encode())

    assert response.json()["outcome"] == Notice.REFRESHED.value
    assert asked.asked == [PROJECT]


def test_an_unauthenticated_notification_is_ignored_and_refreshes_nothing(
    tmp_path: Path,
) -> None:
    client, asked = notified_client(tmp_path)

    response = post(
        client,
        f'{{"project": "{PROJECT}", "ref": "refs/heads/{BRANCH}"}}'.encode(),
        signature="sha256=not-the-signature",
    )

    assert response.status_code == 401
    assert response.json()["outcome"] == Notice.UNAUTHENTICATED.value
    assert asked.asked == []


def test_a_notification_for_an_unknown_project_is_accepted_and_discarded(
    tmp_path: Path,
) -> None:
    client, asked = notified_client(tmp_path)

    response = post(client, b'{"project": "some-other-game", "ref": "refs/heads/main"}')

    assert response.status_code == 202
    assert response.json()["outcome"] == Notice.UNKNOWN_PROJECT.value
    assert asked.asked == []


def test_a_notification_about_another_branch_is_accepted_and_discarded(
    tmp_path: Path,
) -> None:
    client, asked = notified_client(tmp_path)

    response = post(client, f'{{"project": "{PROJECT}", "ref": "refs/heads/spike"}}'.encode())

    assert response.status_code == 202
    assert response.json()["outcome"] == Notice.OTHER_BRANCH.value
    assert asked.asked == []


def test_a_deployment_with_no_configured_hook_has_no_endpoint_at_all() -> None:
    """The scheduler is the guarantee: a hook-less deployment is correct, not broken."""
    with TestClient(build_app()) as client:
        assert client.post(WEBHOOK_PATH, content=b"{}").status_code == 404


def test_a_notification_end_to_end_brings_a_commit_into_the_working_copy(
    tmp_path: Path,
) -> None:
    """The endpoint over the real refresh, over a real clone."""
    staged = ready(tmp_path)
    staged.outside_commit(SCOUT, OUTSIDE)
    application = build_app(
        notifications=RepositoryNotifications(
            secret=SECRET,
            branches={PROJECT: BRANCH},
            refresh=lambda project: ran(refresh_project(project, repository_host=staged.host)),
        )
    )

    with TestClient(application) as client:
        post(client, f'{{"project": "{PROJECT}", "ref": "refs/heads/{BRANCH}"}}'.encode())

    assert staged.host.read(PROJECT, SCOUT, staged.host.head(PROJECT)) == OUTSIDE


# --------------------------------------------------------------------------
# 5.5 — every read states its revision, its confirmation and its staleness
# --------------------------------------------------------------------------


def test_a_read_names_the_revision_and_when_it_was_confirmed(tmp_path: Path) -> None:
    staged = ready(tmp_path)
    ran(refresh_project(PROJECT, repository_host=staged.host, clock=lambda: NOON))

    served = ran(
        read_at_revision(
            PROJECT,
            lambda store: store.load(SCOUT).asset.id.value,
            repository_host=staged.host,
            spec_store=staged.spec_store(),
            clock=lambda: NOON,
            interval=INTERVAL,
        )
    )

    assert served.value == "mech_scout"
    assert served.revision == staged.host.head(PROJECT)
    assert served.confirmed_at == NOON
    assert not served.may_be_stale


def test_a_read_after_an_outage_longer_than_the_interval_is_marked_possibly_stale(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)
    ran(refresh_project(PROJECT, repository_host=staged.host, clock=lambda: NOON))
    _break_the_remote(staged)
    outage = ran(
        refresh_project(PROJECT, repository_host=staged.host, clock=lambda: NOON + 2 * INTERVAL)
    )

    served = ran(
        read_at_revision(
            PROJECT,
            lambda store: store.load(SCOUT).asset.id.value,
            repository_host=staged.host,
            spec_store=staged.spec_store(),
            clock=lambda: NOON + 2 * INTERVAL,
            interval=INTERVAL,
        )
    )

    assert not outage.refreshed
    assert served.confirmed_at == NOON
    assert served.may_be_stale


def _break_the_remote(staged: Staged) -> None:
    """The remote goes away, without the working copy knowing anything about it."""
    staged.bare.rename(staged.bare.with_name("moved-away.git"))


# --------------------------------------------------------------------------
# 5.6 — `.canon/actors.yaml` decides who a commit is authored by (D8)
# --------------------------------------------------------------------------


def test_a_mapped_persons_edit_is_authored_by_their_git_identity(tmp_path: Path) -> None:
    staged = ready(tmp_path)
    identity = author_for(rafa(), staged.spec_store())

    outcome = ran(
        write_back(
            PROJECT,
            [an_edit()],
            repository_host=staged.host,
            author=identity.author,
            message=MESSAGE,
        )
    )

    assert identity.source is GitIdentitySource.MAPPING
    assert outcome.commit.author == RAFA
    assert staged.log("%an <%ae>") == str(RAFA)


def test_an_unmapped_person_is_refused_naming_the_missing_entry_and_nothing_is_committed(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)
    before = staged.host.head(PROJECT)
    identity = author_for(newcomer(), staged.spec_store())

    refusal = refused(
        write_back(
            PROJECT,
            [an_edit()],
            repository_host=staged.host,
            author=identity.author,
            message=MESSAGE,
            subject="auth|newcomer",
        )
    )

    assert identity.is_unmapped
    assert isinstance(refusal, Forbidden)
    assert ".canon/actors.yaml" in refusal.message
    assert "auth|newcomer" in refusal.message
    assert staged.host.head(PROJECT) == before


def test_a_commit_message_names_the_asset_and_what_changed(tmp_path: Path) -> None:
    staged = ready(tmp_path)

    ran(write_back(PROJECT, [an_edit()], repository_host=staged.host, author=RAFA, message=MESSAGE))

    assert staged.log("%s") == "mech_scout: set status to modeling"


def test_an_agent_performed_write_is_authored_by_the_person_and_names_the_agent(
    tmp_path: Path,
) -> None:
    """*"The agent is an instrument, not an author."* Both are recorded, one authors."""
    staged = ready(tmp_path)

    ran(
        write_back(
            PROJECT,
            [an_edit()],
            repository_host=staged.host,
            author=RAFA,
            message=MESSAGE,
            agent="blender-agent",
        )
    )

    assert staged.log("%an <%ae>") == str(RAFA)
    assert staged.log("%(trailers:key=", AGENT_TRAILER, ",valueonly)").strip() == "blender-agent"


# --------------------------------------------------------------------------
# 5.7 — one writer per project
# --------------------------------------------------------------------------


def _concurrently(staged: Staged, first: Edit, second: Edit) -> list[object]:
    """Both edits submitted at once, by two threads, against one host."""
    outcomes: list[object] = [None, None]
    barrier = threading.Barrier(2)

    def submit(index: int, edit: Edit, author: GitAuthor) -> None:
        barrier.wait()
        outcomes[index] = write_back(
            PROJECT,
            [edit],
            repository_host=staged.host,
            author=author,
            message=MESSAGE,
        )

    threads = [
        threading.Thread(target=submit, args=(0, first, RAFA)),
        threading.Thread(
            target=submit, args=(1, second, GitAuthor(name="Ana", email="ana@cyberdyne.com"))
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return outcomes


def test_two_concurrent_edits_to_different_files_both_apply(tmp_path: Path) -> None:
    staged = ready(tmp_path)

    outcomes = _concurrently(
        staged, an_edit(), an_edit(path=MULE, content=MULE_EDIT, based_on=MULE_CONTENT)
    )

    assert all(succeeded(outcome) for outcome in outcomes)
    head = staged.host.head(PROJECT)
    assert staged.host.read(PROJECT, SCOUT, head) == SCOUT_EDIT
    assert staged.host.read(PROJECT, MULE, head) == MULE_EDIT


def test_two_concurrent_edits_to_the_same_file_produce_one_success_and_one_conflict(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)

    outcomes = _concurrently(staged, an_edit(), an_edit(content=OUTSIDE))

    assert len([outcome for outcome in outcomes if succeeded(outcome)]) == 1
    assert len([outcome for outcome in outcomes if isinstance(outcome, Conflict)]) == 1
    assert staged.host.unpushed(PROJECT) == ()


# --------------------------------------------------------------------------
# 5.8 — recovery by re-obtaining the working copy
# --------------------------------------------------------------------------


def test_a_deleted_working_copy_is_restored_and_serves_every_specification(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)
    shutil.rmtree(staged.host.path(PROJECT))

    assert staged.host.status(PROJECT).state is ProjectState.RECOVERING
    head = staged.host.head(PROJECT)
    assert staged.host.read(PROJECT, SCOUT, head) == SCOUT_CONTENT
    assert staged.host.read(PROJECT, MULE, head) == MULE_CONTENT
    assert staged.host.status(PROJECT).state is ProjectState.READY


def test_a_diverged_working_copy_resets_to_the_remote_and_reports_the_discarded_commits(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)
    stranded = staged.host.commit(
        PROJECT,
        [_change(SCOUT, SCOUT_EDIT)],
        author=RAFA,
        message=MESSAGE,
    )

    recovery = staged.host.recover(PROJECT)

    assert recovery.discarded == (stranded.revision.value,)
    assert staged.host.unpushed(PROJECT) == ()
    assert staged.host.read(PROJECT, SCOUT, staged.host.head(PROJECT)) == SCOUT_CONTENT


def _change(path: str, content: bytes):
    return FileChange(path=path, content=content, based_on=ContentHash.of(content))


# --------------------------------------------------------------------------
# 5.9 — a push that cannot happen leaves nothing local
# --------------------------------------------------------------------------


def test_an_edit_whose_push_fails_leaves_the_working_copy_matching_the_remote(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)
    _break_the_remote(staged)

    refusal = refused(
        write_back(PROJECT, [an_edit()], repository_host=staged.host, author=RAFA, message=MESSAGE)
    )

    assert isinstance(refusal, Unavailable)
    assert staged.host.unpushed(PROJECT) == ()
    assert staged.host.read(PROJECT, SCOUT, staged.host.head(PROJECT)) == SCOUT_CONTENT


def test_a_push_rejected_because_the_remote_advanced_is_retried_and_applies(
    tmp_path: Path,
) -> None:
    """D6: the other file moved, so the edit is still valid and the retry is invisible."""
    staged = ready(tmp_path)
    staged.outside_commit(MULE, MULE_EDIT)

    outcome = ran(
        write_back(PROJECT, [an_edit()], repository_host=staged.host, author=RAFA, message=MESSAGE)
    )

    head = staged.host.head(PROJECT)
    assert staged.host.read(PROJECT, SCOUT, head) == SCOUT_EDIT
    assert staged.host.read(PROJECT, MULE, head) == MULE_EDIT
    assert outcome.revision == head


def test_an_edit_whose_file_moved_under_it_is_refused_and_the_outside_commit_stands(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)
    staged.outside_commit(SCOUT, OUTSIDE)
    ran(refresh_project(PROJECT, repository_host=staged.host))

    refusal = refused(
        write_back(PROJECT, [an_edit()], repository_host=staged.host, author=RAFA, message=MESSAGE)
    )

    assert isinstance(refusal, Conflict)
    assert staged.host.read(PROJECT, SCOUT, staged.host.head(PROJECT)) == OUTSIDE


# --------------------------------------------------------------------------
# 5.10 — nothing about the deployment reaches a caller
# --------------------------------------------------------------------------


def _leaks(text: str, staged: Staged) -> list[str]:
    """Every deployment detail this message gave away."""
    return [
        secret
        for secret in (TOKEN, staged.remote.url, str(staged.host.root), str(staged.bare))
        if secret and secret in text
    ]


def test_no_failure_this_adapter_reports_names_a_credential_a_path_or_a_remote(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path, url=None)
    _break_the_remote(staged)

    outage = ran(refresh_project(PROJECT, repository_host=staged.host))
    write = refused(
        write_back(PROJECT, [an_edit()], repository_host=staged.host, author=RAFA, message=MESSAGE)
    )
    unobtainable = stage(tmp_path / "second", url=f"https://oauth2:{TOKEN}@git.invalid/ronin.git")
    reported = unobtainable.host.clone(PROJECT)

    assert _leaks(write.message, staged) == []
    assert _leaks(outage.reason, staged) == []
    assert reported.reason in REASONS
    assert _leaks(reported.reason, unobtainable) == []


def test_the_refusal_still_says_which_project_and_which_specification(
    tmp_path: Path,
) -> None:
    """Redaction that removed the subject would make the error useless."""
    staged = ready(tmp_path)
    staged.outside_commit(SCOUT, OUTSIDE)
    ran(refresh_project(PROJECT, repository_host=staged.host))

    refusal = refused(
        write_back(PROJECT, [an_edit()], repository_host=staged.host, author=RAFA, message=MESSAGE)
    )

    assert refusal is not None
    assert refusal.subject == SCOUT
