"""The in-memory `RepositoryHost` — a repository with no git and no disk.

It models the thing the real adapter has to get right rather than the mechanism
it uses to do so: a **remote** (what the branch holds), a **working copy** (what
this service has fetched), and a **local commit queue** (what it has committed
and not yet pushed). Everything the specification asks for falls out of those
three:

* a project is provisioning until it has been cloned, and reads are refused
  rather than answered empty;
* a fetch advances the working copy to the remote's tip; a failed fetch leaves
  it exactly where it was, so reads keep being served from the last good
  revision;
* a read takes a revision and resolves against the snapshot of that revision, so
  a read that began before a fetch cannot observe content from after it;
* a push either lands, or is rejected because the remote advanced (D6), or fails
  because the remote is unreachable — and a rejected push leaves the local
  commits queued, which is what a retry re-evaluates;
* recovery throws away whatever is queued and resets to the remote, reporting
  what it discarded.

Four seams let a test stage the cases that matter and cannot be staged by
arranging content alone: :meth:`push_to_remote` is somebody else committing
directly, :meth:`fail_next_fetch` is the network going away for one call,
:meth:`reject_next_pushes` is the remote advancing between a commit and its
push, and :meth:`truncate_history` is a shallow clone that holds only part of a
file's history.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cybercanon.application.ports.repository_host import (
    Commit,
    FileChange,
    FileHistory,
    FileRevision,
    ProjectNotReady,
    ProjectState,
    ProjectStatus,
    PushRejected,
    Recovery,
    RepositoryUnavailable,
    RevisionUnreachable,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.revisions import ContentHash, Revision, ServedRevision

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
"""When a project that nobody dated was cloned."""


@dataclass
class _Project:
    """One project's remote, working copy and unpushed commits."""

    name: str
    state: ProjectState = ProjectState.PROVISIONING
    reason: str = ""
    remote: dict[str, bytes] = field(default_factory=dict)
    revisions: dict[str, dict[str, bytes]] = field(default_factory=dict)
    remote_head: str = ""
    served: ServedRevision | None = None
    queued: list[Commit] = field(default_factory=list)
    counter: int = 0
    fail_fetches: int = 0
    reject_pushes: int = 0
    unreachable: str = ""
    truncated_before: str = ""
    lock: threading.RLock = field(default_factory=threading.RLock)


class InMemoryRepositoryHost:
    """A repository host that keeps everything in dictionaries."""

    def __init__(self, *, now: datetime = EPOCH) -> None:
        self._projects: dict[str, _Project] = {}
        self._history: dict[str, list[Commit]] = {}
        self._now = now

    # -- seeding ---------------------------------------------------------

    def add_project(self, project: str, files: dict[str, bytes] | None = None) -> Revision:
        """Declare a project and what its branch currently holds."""
        held = self._projects.setdefault(project, _Project(name=project))
        held.remote = dict(files or {})
        return self._snapshot(held)

    def make_unreachable(self, project: str, reason: str) -> None:
        """The remote refuses this project from now on — a rejected credential."""
        self._projects.setdefault(project, _Project(name=project)).unreachable = reason

    def make_reachable(self, project: str) -> None:
        """Undo :meth:`make_unreachable`, so recovery can be exercised."""
        self._projects.setdefault(project, _Project(name=project)).unreachable = ""

    def push_to_remote(self, project: str, path: str, content: bytes | None) -> Revision:
        """Somebody else committed directly. The working copy does not know yet."""
        held = self._held(project)
        if content is None:
            held.remote.pop(path, None)
        else:
            held.remote[path] = content
        return self._snapshot(held)

    def fail_next_fetch(self, project: str, times: int = 1) -> None:
        """The network goes away for the next `times` fetches, then comes back."""
        self._held(project).fail_fetches = times

    def reject_next_pushes(self, project: str, times: int = 1) -> None:
        """The remote advanced: the next `times` pushes are rejected (D6)."""
        self._held(project).reject_pushes = times

    def truncate_history(self, project: str, before: str) -> None:
        """This working copy is shallow from `before` backwards — the fourth seam.

        `view-versioning`'s truncated-history requirement cannot be staged by
        arranging content, because content is exactly what a shallow clone still
        has: what it lacks is the commits behind it. So it is a seam, like an
        unreachable remote and a rejected push.
        """
        self._held(project).truncated_before = before

    def unpushed(self, project: str) -> tuple[Commit, ...]:
        """The commits this working copy holds and the remote does not."""
        return tuple(self._held(project).queued)

    def remote_files(self, project: str) -> dict[str, bytes]:
        """What the branch holds, for a test asserting what actually landed."""
        return dict(self._held(project).remote)

    def commits(self, project: str) -> tuple[Commit, ...]:
        """Every commit this host recorded for the project, oldest first."""
        return tuple(self._history.get(project, ()))

    # -- port ------------------------------------------------------------

    def clone(self, project: str) -> ProjectStatus:
        held = self._projects.setdefault(project, _Project(name=project))
        if held.unreachable:
            held.state, held.reason = ProjectState.UNAVAILABLE, held.unreachable
            return self.status(project)
        if not held.remote_head:
            self._snapshot(held)
        held.state, held.reason = ProjectState.READY, ""
        held.served = ServedRevision(Revision(held.remote_head), self._now)
        return self.status(project)

    def status(self, project: str) -> ProjectStatus:
        held = self._projects.setdefault(project, _Project(name=project))
        return ProjectStatus(
            project=project, state=held.state, served=held.served, reason=held.reason
        )

    def fetch(self, project: str, *, confirmed_at: datetime | None = None) -> ServedRevision:
        held = self._held(project)
        if held.fail_fetches > 0:
            held.fail_fetches -= 1
            raise RepositoryUnavailable(project, "the remote is unreachable")
        if held.unreachable:
            raise RepositoryUnavailable(project, held.unreachable)
        held.served = ServedRevision(Revision(held.remote_head), confirmed_at or self._now)
        return held.served

    def head(self, project: str) -> Revision:
        held = self._held(project)
        if not held.state.serves_reads:
            raise ProjectNotReady(project, held.state)
        assert held.served is not None
        return held.served.revision

    def paths_at(self, project: str, revision: Revision) -> tuple[str, ...]:
        """Every path that revision holds, sorted — a tree listing (D7).

        Sorted here so that the fake and git agree without a caller having to
        know that git's tree order happens to be one of them: a listing built
        over this port is deterministic because the port says so.
        """
        return tuple(sorted(self._snapshot_at(project, revision)))

    @contextmanager
    def writer(self, project: str) -> Iterator[None]:
        """The same single-writer lock the real host holds, for the same reason.

        A fake without it would let the unit suite pass a concurrency the real
        adapter serialises — which is the exact class of lie the conformance
        suite exists to catch.
        """
        with self._held(project).lock:
            yield

    def read(self, project: str, path: str, revision: Revision) -> bytes | None:
        return self._snapshot_at(project, revision).get(path)

    def commit(
        self,
        project: str,
        changes: Sequence[FileChange],
        *,
        author: GitAuthor,
        message: str,
    ) -> Commit:
        held = self._held(project)
        if not held.state.serves_reads:
            raise ProjectNotReady(project, held.state)
        assert held.served is not None
        working = dict(held.revisions[held.served.revision.value])
        for change in changes:
            if change.is_removal:
                working.pop(change.path, None)
            else:
                working[change.path] = change.content or b""
        recorded = Commit(
            revision=self._store(held, working),
            author=author,
            message=message,
            paths=tuple(change.path for change in changes),
            at=self._now,
        )
        held.served = ServedRevision(recorded.revision, held.served.confirmed_at)
        held.queued.append(recorded)
        self._history.setdefault(project, []).append(recorded)
        return recorded

    def push(self, project: str) -> Revision:
        held = self._held(project)
        if held.unreachable:
            raise RepositoryUnavailable(project, held.unreachable)
        if held.reject_pushes > 0:
            held.reject_pushes -= 1
            raise PushRejected(project, "the remote advanced")
        assert held.served is not None
        held.remote = dict(held.revisions[held.served.revision.value])
        held.remote_head = held.served.revision.value
        held.queued.clear()
        return Revision(held.remote_head)

    def history(self, project: str, path: str, limit: int | None = None) -> FileHistory:
        """Every commit this host recorded that changed `path`, newest first.

        Built from the recorded commits rather than from a second structure, so
        the fake cannot list a revision the commit log does not contain — which
        is the shape a caller gets from git and the shape the conformance suite
        pins both implementations to.
        """
        held = self._held(project)
        entries = [
            self._revision_of(held, commit, path)
            for commit in self._history.get(project, ())
            if path in commit.paths
        ]
        entries.reverse()
        bounded = entries if limit is None else entries[:limit]
        return FileHistory(
            path=path, revisions=tuple(bounded), truncated_before=held.truncated_before
        )

    def _revision_of(self, held: _Project, commit: Commit, path: str) -> FileRevision:
        """What `path` held at that commit — absent means the commit removed it."""
        content = held.revisions.get(commit.revision.value, {}).get(path)
        return FileRevision(
            revision=commit.revision,
            author=commit.author,
            at=commit.at or self._now,
            content=ContentHash.of(content) if content is not None else None,
            byte_size=len(content) if content is not None else 0,
        )

    def recover(self, project: str) -> Recovery:
        held = self._held(project)
        if held.unreachable:
            held.state, held.reason = ProjectState.UNAVAILABLE, held.unreachable
            return Recovery(project=project, state=held.state, reason=held.unreachable)
        discarded = tuple(commit.revision.value for commit in held.queued)
        held.queued.clear()
        self._snapshot(held)
        held.state, held.reason = ProjectState.READY, ""
        held.served = ServedRevision(Revision(held.remote_head), self._now)
        return Recovery(project=project, state=held.state, discarded=discarded)

    # -- internals -------------------------------------------------------

    def _snapshot_at(self, project: str, revision: Revision) -> dict[str, bytes]:
        """What that revision holds, or a named refusal — never a silent empty."""
        held = self._held(project)
        snapshot = held.revisions.get(revision.value)
        if snapshot is None:
            raise RevisionUnreachable(project, revision.value, "no such revision")
        return snapshot

    def _held(self, project: str) -> _Project:
        held = self._projects.get(project)
        if held is None:
            raise RepositoryUnavailable(project, "no such project is configured")
        return held

    def _snapshot(self, held: _Project) -> Revision:
        """Record the remote's current contents as a new revision, and point at it."""
        revision = self._store(held, dict(held.remote))
        held.remote_head = revision.value
        return revision

    def _store(self, held: _Project, files: dict[str, bytes]) -> Revision:
        held.counter += 1
        revision = Revision(f"{held.name}-rev-{held.counter:04d}")
        held.revisions[revision.value] = files
        return revision


__all__ = ["EPOCH", "InMemoryRepositoryHost"]
