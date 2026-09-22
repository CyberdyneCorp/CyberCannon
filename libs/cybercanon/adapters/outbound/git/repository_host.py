"""`GitRepositoryHost` — one persistent working copy per project (D1).

This is the adapter the whole hosted surface stands on, and it is deliberately
the least clever module in the change: every method is a small sequence of
`git` invocations whose failures are *classified* rather than forwarded. The
interesting decisions are all in the port and the use cases above it; what is
here is the mechanism, and the mechanism's job is to be boring.

What each piece owes a sentence in `hosted-repository`:

* **A clone per project on a persistent path** (task 5.1). A project that has
  not been cloned is `provisioning` and refuses reads; a clone that could not be
  obtained is `unavailable` *with a reason*, never an empty asset list.
* **Reads come out of the object database at a revision** (task 5.2, D3), never
  off the checked-out tree. That is what makes read isolation structural: a
  fetch moves a ref, and a reader that already resolved a revision never notices
  it moved. The checkout exists so that there is somewhere to write.
* **One writer per project** (task 5.7). :meth:`GitRepositoryHost.writer` is a
  re-entrant per-project lock, and `write_back` holds it across resolve, commit
  and push — which is what makes D5's per-file precondition mean anything. A
  lock taken only around the commit would let two edits both pass their
  precondition and the second silently win.
* **A failed push leaves nothing local** (task 5.9). The caller recovers, and
  recovery resets to the remote, so the working copy and the remote agree the
  moment the caller is told the edit did not apply.
* **Recovery re-obtains rather than repairs** (task 5.8). A working copy that is
  missing or is not a repository any more is re-cloned; one carrying commits the
  remote does not have is reset to the remote, and what was discarded is
  reported rather than quietly dropped.
* **Nothing about the deployment reaches a caller** (task 5.10). Git says
  `fatal: could not read Username for 'https://token@host/repo.git'`, and a
  service that forwarded that would put a credential in an error body. Every
  failure this module raises carries one of the :data:`REASONS` phrases and the
  project name, and :func:`redact` is the belt to that braces.

**Why classification and not the git message.** The three conditions
`hosted-repository` names — an unreachable remote, a rejected credential, a
missing branch — are different instructions to whoever is on call, and git's
wording for them varies by transport, version and host. Reading them once, here,
is the only place that variation is allowed to exist.
"""

from __future__ import annotations

import fcntl
import shutil
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cybercanon.adapters.outbound.git import commands
from cybercanon.application.ports.clock import Clock, system_clock
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

ORIGIN = "origin"
"""The one remote a working copy has. A second would be a second source of truth."""

LOCK_SUFFIX = ".writer.lock"
"""What a project's single-writer lock file is called, beside its working copy."""

UNIT = "\x1f"
"""The separator between fields of one `git log` line. A byte nobody types."""

HISTORY_FORMAT = f"--format=%H{UNIT}%an{UNIT}%ae{UNIT}%aI"
"""Revision, author name, author address and the author date, ISO-8601."""

CREDENTIAL_REFUSED = "the configured repository credential was refused by the remote"
REMOTE_UNREACHABLE = "the remote could not be reached"
BRANCH_MISSING = "the configured branch does not exist on the remote"
REMOTE_REFUSED = "the remote refused the operation"
NOT_CONFIGURED = "no such project is configured"

REASONS: tuple[str, ...] = (
    CREDENTIAL_REFUSED,
    REMOTE_UNREACHABLE,
    BRANCH_MISSING,
    REMOTE_REFUSED,
    NOT_CONFIGURED,
)
"""Every reason this adapter will ever give. A closed set, and none of it leaks.

`hosted-repository` requires the reason to be reported; `http-api` requires an
error body to carry no path, credential or connection string. Both are satisfied
by answering from a fixed vocabulary instead of from whatever git printed.
"""

CREDENTIAL_MARKERS: tuple[str, ...] = (
    "authentication failed",
    "could not read username",
    "could not read password",
    "permission denied",
    "publickey",
    "access denied",
    "invalid username or password",
    "403 forbidden",
    "401 unauthorized",
)

BRANCH_MARKERS: tuple[str, ...] = (
    "couldn't find remote ref",
    "could not find remote ref",
    "remote branch",
    "not found in upstream",
    "unknown revision",
)

UNREACHABLE_MARKERS: tuple[str, ...] = (
    "could not resolve host",
    "connection refused",
    "connection timed out",
    "no route to host",
    "does not appear to be a git repository",
    "repository not found",
    "does not exist",
    "unable to access",
    "could not read from remote repository",
    "early eof",
)

REJECTION_MARKERS: tuple[str, ...] = (
    "non-fast-forward",
    "[rejected]",
    "! [remote rejected]",
    "fetch first",
    "updates were rejected",
    "cannot lock ref",
)
"""What a remote that advanced under us says. D6's signal, not a failure."""

REDACTED = "<redacted>"


def classify(complaint: str) -> str:
    """Which of the named reasons this git complaint is, without quoting it.

    Credentials first: a refused key produces *both* "Permission denied
    (publickey)" and "Could not read from remote repository", and the first of
    those is the one somebody can act on.
    """
    said = complaint.lower()
    if any(marker in said for marker in CREDENTIAL_MARKERS):
        return CREDENTIAL_REFUSED
    if any(marker in said for marker in BRANCH_MARKERS):
        return BRANCH_MISSING
    if any(marker in said for marker in UNREACHABLE_MARKERS):
        return REMOTE_UNREACHABLE
    return REMOTE_REFUSED


def was_rejected(complaint: str) -> bool:
    """Whether the remote advanced under this push, rather than refusing it."""
    said = complaint.lower()
    return any(marker in said for marker in REJECTION_MARKERS)


def redact(text: str, secrets: Sequence[str]) -> str:
    """`text` with every configured secret and path removed.

    Nothing is supposed to reach here — the reasons above are fixed phrases —
    which is exactly why it exists: the day somebody forwards a git message, the
    credential in it is already gone. Longest first, so a URL containing a token
    does not leave the token behind.
    """
    cleaned = text
    for secret in sorted((value for value in secrets if value), key=len, reverse=True):
        cleaned = cleaned.replace(secret, REDACTED)
    return cleaned


@dataclass(frozen=True)
class ProjectRemote:
    """Where one project's repository is, and which branch is written (D2).

    `credential` is carried so that it can be kept *out* of everything else: it
    is never rendered, never logged, and is one of the strings :func:`redact`
    removes.
    """

    project: str
    url: str
    branch: str = "main"
    credential: str = ""

    @property
    def tracking(self) -> str:
        """The remote-tracking ref reads and resets are measured against."""
        return f"{ORIGIN}/{self.branch}"

    @property
    def secrets(self) -> tuple[str, ...]:
        return tuple(value for value in (self.credential, self.url) if value)


@dataclass
class _Held:
    """One project's configured remote and what its working copy is doing."""

    remote: ProjectRemote
    state: ProjectState = ProjectState.PROVISIONING
    reason: str = ""
    served: ServedRevision | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)


class GitRepositoryHost:
    """A persistent working copy per project, under one root directory."""

    def __init__(
        self,
        root: str | Path,
        remotes: Sequence[ProjectRemote] = (),
        *,
        environment: Mapping[str, str] | None = None,
        clock: Clock = system_clock,
    ) -> None:
        """Serve these projects out of `root`, one directory each.

        `environment` is what `git` runs with beyond
        :data:`~cybercanon.adapters.outbound.git.commands.BASE_ENVIRONMENT` — an
        SSH command, a credential helper, a committer identity. A parameter
        because it is deployment configuration, and because a test that could
        not stage a refusing remote could not check that a refusal is reported.
        """
        self._root = Path(root)
        self._environment = dict(environment or {})
        self._clock = clock
        self._projects: dict[str, _Held] = {}
        for remote in remotes:
            self.configure(remote)

    # -- configuration ---------------------------------------------------

    def configure(self, remote: ProjectRemote) -> None:
        """Declare a project. It is `provisioning` until it has been cloned."""
        self._projects[remote.project] = _Held(remote=remote)

    @property
    def root(self) -> Path:
        """The volume every working copy lives under."""
        return self._root

    def path(self, project: str) -> Path:
        """Where this project's working copy is kept."""
        return self._root / project

    def remote_of(self, project: str) -> ProjectRemote:
        """The configured remote for a project, or a refusal naming nothing else."""
        return self._held(project).remote

    # -- the port --------------------------------------------------------

    def clone(self, project: str) -> ProjectStatus:
        """Obtain the working copy, reporting the state it reached.

        Re-entrant on purpose: a project already cloned is re-adopted rather
        than re-fetched, which is what a restarted service does with a volume
        that survived it.
        """
        held = self._held(project)
        with held.lock:
            if commands.is_repository(self.path(project)):
                return self._adopt(held)
            return self._obtain(held)

    def status(self, project: str) -> ProjectStatus:
        """What this project can answer with. Reports, never repairs.

        A working copy that has vanished from the volume is reported as
        `recovering` here and re-obtained by the next read, so a caller watching
        the state sees the recovery rather than a silent gap.
        """
        held = self._held(project)
        if held.served is not None and not commands.is_repository(self.path(project)):
            held.state = ProjectState.RECOVERING
        return ProjectStatus(
            project=project, state=held.state, served=held.served, reason=held.reason
        )

    def fetch(self, project: str, *, confirmed_at: datetime | None = None) -> ServedRevision:
        """Refresh from the remote and advance what this project serves.

        The served revision and its confirmation time are replaced as one value,
        so no reader can observe a revision paired with somebody else's
        confirmation time. A working copy carrying unpushed commits is fetched
        but not moved: discarding somebody's commit is :meth:`recover`'s job and
        it says so when it does it.
        """
        held = self._ensure(project)
        with held.lock:
            self._remote_call(held, ["fetch", "--quiet", ORIGIN, held.remote.branch])
            if not self.unpushed(project):
                self._reset_to_remote(held)
            held.served = ServedRevision(self._head(held), confirmed_at or self._clock())
            return held.served

    def head(self, project: str) -> Revision:
        """The revision reads are served from, restoring the copy if it vanished."""
        held = self._ensure(project)
        assert held.served is not None
        return held.served.revision

    def read(self, project: str, path: str, revision: Revision) -> bytes | None:
        """The bytes of that file at that revision, out of the object database (D3).

        Absent is an answer — a new file's precondition is that it does not
        exist (D5) — and a revision this copy cannot reach is a different
        problem, so the revision is resolved before the path is looked for.
        """
        held = self._ensure(project)
        self._resolve(held, revision.value)
        found = self._git(held, ["cat-file", "-p", f"{revision.value}:{path}"])
        return found.out if found.ok else None

    def paths_at(self, project: str, revision: Revision) -> tuple[str, ...]:
        """Every tracked path at that revision — a tree listing, not a walk.

        Sorted rather than left in git's order. Git walks trees depth-first and
        orders entries as if a directory ended in a slash, so `a.b/x` and `ab/y`
        come out in an order a caller would have to know git to predict. The
        port promises a deterministic listing, and the cheapest way for both
        implementations to keep that promise is the obvious one.
        """
        held = self._ensure(project)
        self._resolve(held, revision.value)
        listed = self._git(held, ["ls-tree", "-r", "--name-only", revision.value])
        return tuple(sorted(listed.lines))

    @contextmanager
    def writer(self, project: str) -> Iterator[None]:
        """Hold this project's single-writer lock (task 5.7, and D6).

        Re-entrant, so the retry loop's recover-and-fetch runs inside the same
        edit's lock. Held across resolve, commit and push, because a lock taken
        only around the commit would let two edits pass the same precondition
        and the later one win silently.

        **Two locks, because there are two ways to be two writers.** The
        in-process lock serialises this instance's own threads; the file lock on
        the volume serialises *instances*, which is what D6 requires and D7
        depends on: a rollover deliberately runs the old and the new instance at
        once, both mounting the same working copies, and an exclusive lock that
        lived in one process's memory would be no lock at all for the twenty
        seconds that matters most. The lock file sits beside the working copy on
        the volume it protects, because a lock somewhere else is a lock that a
        restored volume does not carry.
        """
        held = self._held(project)
        with held.lock, self._volume_lock(project):
            yield

    @contextmanager
    def _volume_lock(self, project: str) -> Iterator[None]:
        """An exclusive lock on this project's lock file, held for the write.

        `flock` is per open file description, so two instances — and two hosts
        in one process, which is how the drill stages an overlapping deploy —
        contend for it exactly as two containers on one node do. A platform
        without it degrades to the in-process lock and says so here rather than
        pretending: every environment this service is deployed to has it.
        """
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{project}{LOCK_SUFFIX}"
        with path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def commit(
        self,
        project: str,
        changes: Sequence[FileChange],
        *,
        author: GitAuthor,
        message: str,
    ) -> Commit:
        """Record one logical edit as one commit authored by that git identity.

        `--allow-empty`, deliberately: *one logical edit is one commit* is the
        specified behaviour, and an edit that happens to restate the current
        content is still an edit somebody made and is still attributable.
        """
        held = self._ensure(project)
        with held.lock:
            for change in changes:
                self._materialise(held, change)
            paths = tuple(change.path for change in changes)
            self._git(held, ["add", "--all", "--", *paths], expect=True)
            self._git(held, self._commit_arguments(author, message), expect=True)
            revision = self._head(held)
            assert held.served is not None
            held.served = ServedRevision(revision, held.served.confirmed_at)
            return Commit(
                revision=revision,
                author=author,
                message=message,
                paths=paths,
                at=self._clock(),
            )

    def push(self, project: str) -> Revision:
        """Send the commits to the remote and answer the revision now there."""
        held = self._ensure(project)
        with held.lock:
            attempted = self._git(held, ["push", ORIGIN, f"HEAD:refs/heads/{held.remote.branch}"])
            if not attempted.ok:
                raise self._push_failure(held, attempted.err)
            self._git(held, ["fetch", "--quiet", ORIGIN, held.remote.branch])
            return self._head(held)

    def unpushed(self, project: str) -> tuple[Commit, ...]:
        """The commits this working copy holds and the remote does not, newest first.

        A real question rather than a test seam: *"a local commit that cannot be
        pushed is not reported as applied"* is only checkable if somebody can
        ask what is local.
        """
        held = self._held(project)
        if not commands.is_repository(self.path(project)):
            return ()
        listed = self._git(held, ["log", "--format=%H%x1f%an%x1f%ae%x1f%s", self._range(held)])
        return tuple(_parsed(line) for line in listed.lines) if listed.ok else ()

    def history(self, project: str, path: str, limit: int | None = None) -> FileHistory:
        """Every commit that touched that path, newest first (`view-versioning`).

        The content hash of each revision is taken from the bytes that revision
        holds rather than from git's own blob id: the product addresses content
        by `sha256` everywhere — blob keys, edit preconditions, view identity —
        and a second hash that only history spoke would be a second answer to
        *are these the same bytes*.

        A shallow working copy is reported rather than presented as complete.
        `git log` in one stops where the graft does, with no error, which is
        precisely the silent truncation `view-versioning` forbids, so the
        shallow flag is read and the oldest revision reached is named.
        """
        held = self._ensure(project)
        bounded = ["-n", str(limit)] if limit is not None else []
        listed = self._git(held, ["log", HISTORY_FORMAT, *bounded, "--", path])
        if not listed.ok:
            return FileHistory(path=path)
        revisions = tuple(
            self._file_revision(held, line, path) for line in listed.lines if line.strip()
        )
        return FileHistory(
            path=path, revisions=revisions, truncated_before=self._shallow_from(held, revisions)
        )

    def _file_revision(self, held: _Held, line: str, path: str) -> FileRevision:
        """One `git log` line plus the bytes that revision held at `path`."""
        revision, name, email, stamp = [*line.split(UNIT), "", "", ""][:4]
        found = self._git(held, ["cat-file", "-p", f"{revision}:{path}"])
        content = found.out if found.ok else None
        return FileRevision(
            revision=Revision(revision),
            author=GitAuthor(name=name, email=email),
            at=stamped(stamp),
            content=ContentHash.of(content) if content is not None else None,
            byte_size=len(content) if content is not None else 0,
        )

    def _shallow_from(self, held: _Held, revisions: Sequence[FileRevision]) -> str:
        """The revision earlier history is unavailable from, or the empty string."""
        if not revisions:
            return ""
        shallow = self._git(held, ["rev-parse", "--is-shallow-repository"])
        if not shallow.ok or shallow.text.strip() != "true":
            return ""
        return revisions[-1].revision.value

    def recover(self, project: str) -> Recovery:
        """Re-obtain the working copy, discarding whatever the remote does not have."""
        held = self._held(project)
        with held.lock:
            held.state = ProjectState.RECOVERING
            if not commands.is_repository(self.path(project)):
                return self._recovered_by_cloning(held)
            return self._recovered_by_resetting(held)

    # -- clone and adopt -------------------------------------------------

    def _obtain(self, held: _Held) -> ProjectStatus:
        """Clone the configured branch onto the volume, or report why not."""
        destination = self.path(held.remote.project)
        shutil.rmtree(destination, ignore_errors=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cloned = self._run(
            None,
            [
                "clone",
                "--quiet",
                "--single-branch",
                "--branch",
                held.remote.branch,
                held.remote.url,
                str(destination),
            ],
        )
        if not cloned.ok:
            return self._unavailable(held, classify(cloned.err))
        return self._adopt(held)

    def _adopt(self, held: _Held) -> ProjectStatus:
        """Take an existing working copy as this project's, and serve its head."""
        held.state, held.reason = ProjectState.READY, ""
        held.served = ServedRevision(self._head(held), self._clock())
        return self.status(held.remote.project)

    def _unavailable(self, held: _Held, reason: str) -> ProjectStatus:
        held.state, held.reason = ProjectState.UNAVAILABLE, reason
        return self.status(held.remote.project)

    # -- recovery --------------------------------------------------------

    def _recovered_by_cloning(self, held: _Held) -> Recovery:
        """The working copy is gone: obtain a fresh one. Nothing local survives."""
        status = self._obtain(held)
        return Recovery(
            project=held.remote.project,
            state=status.state,
            reason=status.reason,
        )

    def _recovered_by_resetting(self, held: _Held) -> Recovery:
        """The working copy diverged: reset to the remote and say what was dropped.

        The fetch is best effort and the reset is not. `origin/<branch>` is
        knowledge this copy already holds, so a remote that is unreachable
        changes only how *current* the state we resolve toward is — never
        whether a commit that could not be pushed is still sitting here. A
        recovery that refused to act without the network would leave exactly the
        local-only commit the specification says must not survive.
        """
        project = held.remote.project
        fetched = self._git(held, ["fetch", "--quiet", ORIGIN, held.remote.branch])
        discarded = tuple(commit.revision.value for commit in self.unpushed(project))
        self._reset_to_remote(held)
        held.state, held.reason = ProjectState.READY, ""
        held.served = ServedRevision(self._head(held), self._clock())
        return Recovery(
            project=project,
            state=held.state,
            discarded=discarded,
            reason="" if fetched.ok else classify(fetched.err),
        )

    def _reset_to_remote(self, held: _Held) -> None:
        """Make the checkout exactly the remote's branch, tracked and untracked."""
        self._git(held, ["reset", "--quiet", "--hard", held.remote.tracking], expect=True)
        self._git(held, ["clean", "--quiet", "-fd"])

    # -- plumbing --------------------------------------------------------

    def _held(self, project: str) -> _Held:
        held = self._projects.get(project)
        if held is None:
            raise RepositoryUnavailable(project, NOT_CONFIGURED)
        return held

    def _ensure(self, project: str) -> _Held:
        """The project, restored first if its working copy vanished from the volume."""
        held = self._held(project)
        if self.status(project).state is ProjectState.RECOVERING:
            self.recover(project)
        if not held.state.serves_reads or held.served is None:
            raise ProjectNotReady(project, held.state)
        return held

    def _git(self, held: _Held, arguments: Sequence[str], *, expect: bool = False):
        """One command in this project's working copy."""
        completed = self._run(self.path(held.remote.project), arguments)
        if expect and not completed.ok:
            raise RepositoryUnavailable(held.remote.project, classify(completed.err))
        return completed

    def _run(self, root: Path | None, arguments: Sequence[str]):
        try:
            return commands.run(root, arguments, environment=self._environment)
        except commands.GitUnavailable:
            return commands.Completed(code=1, out=b"", err="unable to access the remote")

    def _remote_call(self, held: _Held, arguments: Sequence[str]) -> None:
        """A command that talks to the remote: its failure is an unavailability."""
        completed = self._git(held, arguments)
        if not completed.ok:
            raise RepositoryUnavailable(held.remote.project, classify(completed.err))

    def _push_failure(self, held: _Held, complaint: str) -> Exception:
        """D6's signal, or a genuine unavailability — never the same answer."""
        project = held.remote.project
        if was_rejected(complaint):
            return PushRejected(project, "the remote advanced")
        return RepositoryUnavailable(project, classify(complaint))

    def _head(self, held: _Held) -> Revision:
        resolved = self._git(held, ["rev-parse", "HEAD"], expect=True)
        return Revision(resolved.text.strip())

    def _range(self, held: _Held) -> str:
        return f"{held.remote.tracking}..HEAD"

    def _resolve(self, held: _Held, revision: str) -> str:
        """That revision as a commit, or a named refusal — never a silent miss."""
        found = self._git(held, ["rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"])
        if not found.ok or not found.text.strip():
            raise RevisionUnreachable(
                held.remote.project, revision, "this working copy cannot reach it"
            )
        return found.text.strip()

    def _materialise(self, held: _Held, change: FileChange) -> None:
        """Put one file change into the checkout, which is what a commit reads."""
        target = self.path(held.remote.project) / change.path
        if change.is_removal:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(change.content or b"")

    def _commit_arguments(self, author: GitAuthor, message: str) -> tuple[str, ...]:
        """One commit, authored by the person and committed by this service.

        The author is the mapped person and nothing substitutes for it (D8). The
        committer is the same identity for want of anything better to say: a
        service identity there would be accurate and would also be the first
        step toward it creeping into the author field.
        """
        return (
            "-c",
            f"user.name={author.name}",
            "-c",
            f"user.email={author.email}",
            "commit",
            "--quiet",
            "--allow-empty",
            "--author",
            str(author),
            "--message",
            message,
        )


def stamped(value: str) -> datetime:
    """An ISO-8601 author date, or the epoch when git gave none.

    The epoch rather than a refusal: a revision whose date could not be read is
    still a revision, and losing the whole listing over a timestamp would be a
    truncation reported as an error.
    """
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.fromtimestamp(0, tz=UTC)


def _parsed(line: str) -> Commit:
    """One `git log` line back into a :class:`Commit`."""
    revision, name, email, subject = [*line.split(UNIT), "", "", ""][:4]
    return Commit(
        revision=Revision(revision),
        author=GitAuthor(name=name, email=email),
        message=subject,
    )


__all__ = [
    "BRANCH_MISSING",
    "CREDENTIAL_REFUSED",
    "LOCK_SUFFIX",
    "NOT_CONFIGURED",
    "ORIGIN",
    "REASONS",
    "REDACTED",
    "REMOTE_REFUSED",
    "REMOTE_UNREACHABLE",
    "GitRepositoryHost",
    "ProjectRemote",
    "classify",
    "redact",
    "was_rejected",
]
