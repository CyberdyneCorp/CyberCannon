"""Group 6 — the deploy overlap, and the write-back caught in the middle of it.

D7 is two sentences: *"Coolify starts the new instance, waits for `/readyz`,
routes to it, then signals the old one, which stops accepting requests and
drains"*, and *"the drain window is configured longer than the write-back
timeout, so an accepted write-back either finishes inside the window or is
abandoned by the timeout before termination."* Everything below is one of those
two claims, checked against something real.

**What is real here and what is modelled.** The *instances* are real: two
`uvicorn` processes serving the built application, started and retired the way a
release starts and retires them, which is the only way to assert a property
about processes. The *routing gate* is not Coolify — nobody can run Coolify from
a test — so it is written out here as the four steps Coolify is configured to
take, and `deploy/README.md` is asserted to configure those same four. That
distinction is stated rather than blurred: a test that pretended to be the
platform would be asserting its own fiction, and a test that skipped the
processes would be asserting nothing at all.

The write-back half needs no platform. A budget that runs out, a working copy
reset on the way back up, and a lock held across two instances sharing one
volume are all properties of this code over real git, and that is where they
are checked.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from staged_project import (
    BRANCH,
    CORPUS,
    MULE_SPEC,
    PROJECT,
    SCOUT_SPEC,
    Staged,
    ready,
)

from cybercanon.adapters.inbound.http.health import ALIVE, LIVE_PATH, READY, READY_PATH
from cybercanon.adapters.outbound.git.repository_host import (
    LOCK_SUFFIX,
    GitRepositoryHost,
    ProjectRemote,
)
from cybercanon.adapters.wiring.configuration import RolloverConfig
from cybercanon.application.results import succeeded
from cybercanon.application.testing.outcomes import refused
from cybercanon.application.use_cases.hosted_repository import (
    NOTHING_RECORDED,
    Edit,
    WriteBackAbandoned,
    resume_project,
    write_back,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.revisions import ContentHash

pytestmark = pytest.mark.integration

BOOT_TIMEOUT_S = 30.0
POLL_S = 0.05

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
ANA = GitAuthor(name="Ana", email="ana@cyberdyne.com")

LATER = datetime(2026, 9, 19, 12, 30, tzinfo=UTC)

SCOUT_EDIT = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"
MULE_EDIT = b"schema_version: 1\nid: mule\nname: Mule Hauler\nstatus: modeling\n"
HALF_WRITTEN = b"schema_version: 1\nid: mech_sc"

READY_SERVE = """\
import uvicorn

from cybercanon.adapters.inbound.http.app import build_app

uvicorn.run(build_app(), host="127.0.0.1", port={port}, log_level="warning")
"""
"""An instance that becomes ready: it owns nothing that is down."""

NEVER_READY_SERVE = """\
import uvicorn

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.surface import Surface
from cybercanon.application.use_cases.service_health import WORKING_COPY, unavailable

surface = Surface(observe=lambda: (unavailable(WORKING_COPY, "the volume is not mounted"),))
uvicorn.run(
    build_app(surface=surface), host="127.0.0.1", port={port}, log_level="warning"
)
"""
"""A new version whose readiness never reports ready: its own volume is missing.

A *lost working copy* is the one dependency `deployment-operations` says does
withhold traffic, so this is a genuinely not-ready instance rather than one with
a flag set — it is alive, it answers, and the routing gate must refuse it.
"""

DEPLOY_TIMEOUT_S = 2.0
"""How long the modelled deploy waits for readiness before giving up."""


# --------------------------------------------------------------------------
# Instances: real processes, started and retired
# --------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _scrubbed() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("CANON_") and name not in {"DATABASE_URL", "PGHOST"}
    }


@dataclass
class Instance:
    """One running version of the API, as a release manipulates it."""

    process: subprocess.Popen[str]
    base: str

    def get(self, path: str, timeout: float = 5.0) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(f"{self.base}{path}", timeout=timeout) as answer:
                return answer.status, answer.read().decode("utf-8")
        except urllib.error.HTTPError as answered:  # not-ready is an answer, not a failure
            return answered.code, answered.read().decode("utf-8")

    @property
    def is_ready(self) -> bool:
        try:
            return self.get(READY_PATH)[0] == 200
        except (urllib.error.URLError, OSError):
            return False

    @property
    def is_alive(self) -> bool:
        try:
            return self.get(LIVE_PATH)[0] == 200
        except (urllib.error.URLError, OSError):
            return False

    def retire(self, drain_window: timedelta) -> None:
        """Signal it, let it drain, and only then insist (D7)."""
        self.process.terminate()
        self.process.wait(timeout=drain_window.total_seconds() + 5)


def _start(script: str, repo_root: Path) -> Instance:
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-c", script.format(port=port)],
        cwd=repo_root,
        env=_scrubbed(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    instance = Instance(process=process, base=f"http://127.0.0.1:{port}")
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the instance exited: {process.communicate()[0]}")
        if instance.is_alive:
            return instance
        time.sleep(POLL_S)
    process.terminate()
    raise AssertionError(f"the instance did not answer {LIVE_PATH} within {BOOT_TIMEOUT_S}s")


def _await_ready(instance: Instance, within: float) -> bool:
    """The routing gate: is this instance ready before the deploy gives up?"""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        if instance.is_ready:
            return True
        time.sleep(POLL_S)
    return False


@pytest.fixture
def serving(repo_root: Path) -> Iterator[Instance]:
    """The version that is already deployed when the next release starts."""
    instance = _start(READY_SERVE, repo_root)
    try:
        yield instance
    finally:
        instance.process.terminate()
        instance.process.wait(timeout=10)


@pytest.fixture
def rollover() -> RolloverConfig:
    """The configured pair, shortened so a suite can run inside it."""
    return RolloverConfig(
        write_back_timeout=timedelta(seconds=1), drain_window=timedelta(seconds=3)
    )


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    return ready(tmp_path)


def _second_instance(staged: Staged) -> GitRepositoryHost:
    """The new version, mounting the same working-copy volume (D6, D7)."""
    return GitRepositoryHost(
        staged.host.root,
        [ProjectRemote(project=PROJECT, url=str(staged.bare), branch=BRANCH)],
        environment={"HOME": str(staged.home), "GIT_CONFIG_GLOBAL": "/dev/null"},
    )


def _edit(path: str, content: bytes) -> Edit:
    return Edit(path=path, content=content, based_on=ContentHash.of(CORPUS[path]))


# --------------------------------------------------------------------------
# 6.2 — reads are answered throughout the rollover
# --------------------------------------------------------------------------


@dataclass
class Caller:
    """Somebody reading continuously while the deploy happens around them."""

    answers: list[int]
    failures: list[str]


def _read_continuously(route: list[Instance], stop: threading.Event) -> Caller:
    """Issue reads against whichever instance the gate is currently routing to."""
    caller = Caller(answers=[], failures=[])
    while not stop.is_set():
        instance = route[-1]
        try:
            caller.answers.append(instance.get(LIVE_PATH)[0])
        except (urllib.error.URLError, OSError) as dropped:
            caller.failures.append(f"{instance.base}: {dropped}")
        time.sleep(POLL_S / 5)
    return caller


def test_every_read_issued_across_a_deploy_received_a_response(
    serving: Instance, repo_root: Path, rollover: RolloverConfig
) -> None:
    """*"Every request SHALL receive a response, and none SHALL fail."*

    The gate's four steps, in order: start the new instance, wait for its
    readiness, route to it, and only then retire the old one. The caller keeps
    reading the whole time and never learns that any of it happened.
    """
    route = [serving]
    stop = threading.Event()
    caller: list[Caller] = []
    reader = threading.Thread(target=lambda: caller.append(_read_continuously(route, stop)))
    reader.start()

    try:
        incoming = _start(READY_SERVE, repo_root)
        assert _await_ready(incoming, DEPLOY_TIMEOUT_S), "the new version never became ready"
        route.append(incoming)
        time.sleep(POLL_S * 4)
        serving.retire(rollover.drain_window)
        time.sleep(POLL_S * 4)
    finally:
        stop.set()
        reader.join(timeout=10)
        incoming.process.terminate()
        incoming.process.wait(timeout=10)

    answered = caller[0]
    assert answered.failures == [], "a read failed because of the rollover"
    assert len(answered.answers) > 10, "the caller was not really reading throughout"
    assert set(answered.answers) == {200}


def test_the_new_instance_is_only_routed_to_once_it_reports_ready(
    repo_root: Path,
) -> None:
    """The gate is readiness, not liveness: alive is not routable."""
    incoming = _start(READY_SERVE, repo_root)
    try:
        assert incoming.is_alive
        assert _await_ready(incoming, DEPLOY_TIMEOUT_S)
        assert incoming.get(READY_PATH)[0] == 200
        assert READY in incoming.get(READY_PATH)[1]
    finally:
        incoming.process.terminate()
        incoming.process.wait(timeout=10)


def test_a_retiring_instance_answers_what_it_accepted_and_then_stops(
    serving: Instance, rollover: RolloverConfig
) -> None:
    """*"It SHALL stop accepting new requests and complete in-flight ones."*"""
    assert serving.get(LIVE_PATH)[0] == 200

    serving.retire(rollover.drain_window)

    assert serving.process.poll() is not None, "it did not stop within the drain window"
    assert not serving.is_alive, "a retired instance still accepts requests"


# --------------------------------------------------------------------------
# 6.3 — a never-ready new version never replaces the old one
# --------------------------------------------------------------------------


def test_a_never_ready_new_version_leaves_the_previous_one_serving(
    serving: Instance, repo_root: Path
) -> None:
    """*"When the deploy times out, the previous version SHALL still be serving."*"""
    incoming = _start(NEVER_READY_SERVE, repo_root)
    try:
        became_ready = _await_ready(incoming, DEPLOY_TIMEOUT_S)

        assert not became_ready, "the artifact under test was supposed never to be ready"
        assert incoming.is_alive, "it is a running instance that is not ready, not a crash"
        assert incoming.get(READY_PATH)[0] == 503
        assert serving.get(LIVE_PATH) == (200, serving.get(LIVE_PATH)[1])
        assert ALIVE in serving.get(LIVE_PATH)[1]
        assert serving.is_ready, "the previous version is still the one serving traffic"
    finally:
        incoming.process.terminate()
        incoming.process.wait(timeout=10)


def test_the_deployment_document_configures_readiness_as_the_routing_gate(
    repo_root: Path,
) -> None:
    """The half a test cannot run: what Coolify is told to do with `/readyz`.

    The gate above is written out in this suite because nobody can run the
    platform from a test; this asserts that the platform is configured to take
    the same four steps, in the same document an operator reads.
    """
    document = (repo_root / "deploy" / "README.md").read_text(encoding="utf-8")

    assert "readiness gate → `/readyz`" in document
    assert "routed only once it" in document
    assert "stop grace period → `CANON_DRAIN_WINDOW_S`" in document


# --------------------------------------------------------------------------
# 6.4 — a write-back accepted just before retirement lands inside the window
# --------------------------------------------------------------------------


def test_a_write_back_accepted_just_before_retirement_commits_within_the_window(
    staged: Staged, rollover: RolloverConfig
) -> None:
    """*"The caller SHALL receive success, and the commit SHALL exist on the
    configured branch attributed to the acting person."*"""
    started = time.monotonic()
    outcome = write_back(
        PROJECT,
        [_edit(SCOUT_SPEC, SCOUT_EDIT)],
        repository_host=staged.host,
        author=RAFA,
        message="mech_scout: set status",
        timeout=rollover.write_back_timeout,
    )
    elapsed = time.monotonic() - started

    assert succeeded(outcome)
    assert elapsed < rollover.drain_window.total_seconds(), "it did not finish inside the window"
    landed = _second_instance(staged)
    landed.clone(PROJECT)
    landed.fetch(PROJECT, confirmed_at=LATER)
    head = landed.head(PROJECT)
    assert landed.read(PROJECT, SCOUT_SPEC, head) == SCOUT_EDIT, "the commit is on the branch"
    assert staged.host.unpushed(PROJECT) == (), "nothing was left local"
    commit = outcome.value.commit  # type: ignore[union-attr]
    assert commit.author == RAFA, "attributed to the acting person"


def test_a_write_back_that_runs_out_of_its_budget_records_nothing(
    staged: Staged,
) -> None:
    """The other exit D7 allows: abandoned by the timeout, before termination.

    The budget is exhausted before the first attempt, which is the shape the
    deadline actually has — a write-back is abandoned *between* attempts rather
    than torn in half during one, because an edit interrupted mid-push is the
    state the whole decision exists to prevent.
    """
    before = staged.host.head(PROJECT)

    refusal = refused(
        write_back(
            PROJECT,
            [_edit(SCOUT_SPEC, SCOUT_EDIT)],
            repository_host=staged.host,
            author=RAFA,
            message="mech_scout: set status",
            timeout=timedelta(seconds=-1),
        )
    )

    assert refusal is not None
    assert NOTHING_RECORDED in refusal.message
    assert staged.host.head(PROJECT) == before
    assert staged.host.unpushed(PROJECT) == ()
    assert (staged.working_copy / SCOUT_SPEC).read_bytes() == CORPUS[SCOUT_SPEC]


def test_the_abandonment_is_a_refusal_rather_than_a_crash() -> None:
    """A caller has to be *told*; a traceback is not a response."""
    abandoned = WriteBackAbandoned(SCOUT_SPEC, timedelta(seconds=30))

    assert NOTHING_RECORDED in str(abandoned)
    assert "30s" in str(abandoned)


# --------------------------------------------------------------------------
# 6.5 — an instance terminated mid-write-back leaves no partial edit
# --------------------------------------------------------------------------


def test_a_service_killed_between_modifying_and_committing_leaves_nothing_behind(
    staged: Staged,
) -> None:
    """*"The working copy SHALL contain no uncommitted modification once the
    service is running again, and the specification file SHALL match the
    configured branch."*

    The instance is terminated at the worst possible moment: the file on the
    volume has been modified and no commit exists. There is no failed write-back
    to clean up after — the process that would have cleaned up is gone — so the
    only thing that can notice is the next one to mount the volume.
    """
    (staged.working_copy / SCOUT_SPEC).write_bytes(HALF_WRITTEN)
    (staged.working_copy / "half-written.yaml").write_bytes(b"and something untracked")

    successor = _second_instance(staged)
    successor.clone(PROJECT)
    resumed = resume_project(PROJECT, repository_host=successor)

    assert succeeded(resumed)
    assert (staged.working_copy / SCOUT_SPEC).read_bytes() == CORPUS[SCOUT_SPEC]
    assert not (staged.working_copy / "half-written.yaml").exists()
    assert successor.unpushed(PROJECT) == ()
    head = successor.head(PROJECT)
    assert successor.read(PROJECT, SCOUT_SPEC, head) == CORPUS[SCOUT_SPEC]


def test_the_successor_reports_a_local_commit_it_had_to_discard(staged: Staged) -> None:
    """Discarding is allowed; discarding silently is not (`hosted-repository`)."""
    staged.host.commit(
        PROJECT,
        [],
        author=RAFA,
        message="a commit that never reached the remote",
    )

    resumed = resume_project(PROJECT, repository_host=_resumed_over(staged))

    assert succeeded(resumed)
    assert resumed.value.discarded_anything  # type: ignore[union-attr]


def _resumed_over(staged: Staged) -> GitRepositoryHost:
    successor = _second_instance(staged)
    successor.clone(PROJECT)
    return successor


# --------------------------------------------------------------------------
# 6.6 — two instances, one volume, one writer at a time
# --------------------------------------------------------------------------


@dataclass
class Window:
    """When one instance held the lock, as the volume experienced it."""

    instance: int
    entered: float
    left: float

    def overlaps(self, other: Window) -> bool:
        return self.entered < other.left and other.entered < self.left


class Recording(GitRepositoryHost):
    """A host that records when it actually held the working copy.

    The timestamps are taken **inside** :meth:`writer`, after the lock is held
    and before it is released, so a window is the critical section itself rather
    than the call around it. Measuring the call would include the wait, and two
    calls that waited for each other would look like two calls that overlapped —
    which is the opposite of what is being asserted.
    """

    def __init__(self, instance: int, *arguments: object, **options: object) -> None:
        super().__init__(*arguments, **options)  # type: ignore[arg-type]
        self.instance = instance
        self.windows: list[Window] = []

    @contextmanager
    def writer(self, project: str) -> Iterator[None]:
        with super().writer(project):
            entered = time.monotonic()
            try:
                yield
            finally:
                self.windows.append(
                    Window(instance=self.instance, entered=entered, left=time.monotonic())
                )


def _recording(staged: Staged, instance: int) -> Recording:
    """One instance of the service, over the volume the other one also mounts."""
    host = Recording(
        instance,
        staged.host.root,
        [ProjectRemote(project=PROJECT, url=str(staged.bare), branch=BRANCH)],
        environment={"HOME": str(staged.home), "GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    host.clone(PROJECT)
    return host


def _timed_write_backs(
    hosts: Sequence[Recording], edits: Sequence[tuple[str, bytes, GitAuthor]]
) -> tuple[list[object], list[Window]]:
    """Both instances write at once; each records when it held the lock."""
    outcomes: list[object] = [None] * len(hosts)
    barrier = threading.Barrier(len(hosts))

    def submit(index: int) -> None:
        path, content, author = edits[index]
        barrier.wait()
        outcomes[index] = write_back(
            PROJECT,
            [_edit(path, content)],
            repository_host=hosts[index],
            author=author,
            message=f"{path}: written by instance {index}",
        )

    threads = [threading.Thread(target=submit, args=(index,)) for index in range(len(hosts))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return outcomes, [window for host in hosts for window in host.windows]


def test_the_lock_serialised_two_write_backs_driven_at_both_instances(
    staged: Staged,
) -> None:
    """*"They SHALL be applied one after the other."*

    Not merely *both landed* — which two commits would satisfy by luck — but
    that the two critical sections did not overlap in time. The lock is on the
    volume, so it is the thing that serialised them, and the rollover deliberately
    runs both instances over that volume at once.
    """
    old, new = _recording(staged, 0), _recording(staged, 1)

    outcomes, windows = _timed_write_backs(
        [old, new],
        [(SCOUT_SPEC, SCOUT_EDIT, RAFA), (MULE_SPEC, MULE_EDIT, ANA)],
    )

    assert all(succeeded(outcome) for outcome in outcomes)  # type: ignore[arg-type]
    assert len(windows) == 2
    first, second = sorted(windows, key=lambda window: window.entered)
    assert not first.overlaps(second), (
        f"instance {first.instance} still held the working copy when "
        f"instance {second.instance} entered: the lock did not serialise them"
    )
    assert first.instance != second.instance


def test_neither_instances_change_was_lost(staged: Staged) -> None:
    """Serialised and *both applied* — a lock that dropped one would be no better."""
    old, new = _recording(staged, 0), _recording(staged, 1)

    _timed_write_backs(
        [old, new],
        [(SCOUT_SPEC, SCOUT_EDIT, RAFA), (MULE_SPEC, MULE_EDIT, ANA)],
    )

    new.fetch(PROJECT, confirmed_at=LATER)
    head = new.head(PROJECT)
    assert new.read(PROJECT, SCOUT_SPEC, head) == SCOUT_EDIT
    assert new.read(PROJECT, MULE_SPEC, head) == MULE_EDIT
    assert old.unpushed(PROJECT) == () and new.unpushed(PROJECT) == ()


def test_the_lock_the_two_instances_contended_for_is_on_the_volume(
    staged: Staged,
) -> None:
    """A lock in one process's memory is no lock during an overlapping deploy."""
    with staged.host.writer(PROJECT):
        pass

    assert (staged.host.root / f"{PROJECT}{LOCK_SUFFIX}").is_file()
    assert staged.host.root == _resumed_over(staged).root, "one volume, two instances"
