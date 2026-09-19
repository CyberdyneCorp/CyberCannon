"""The three hosted operations: refresh, write back, rebuild the index.

Everything the hosted surface does that a laptop never had to do is here, and
each of the three exists because a specification sentence demands it:

* :func:`refresh_project` — *"the service SHALL refresh each project's working
  copy at a configured interval"*, and *"a failed refresh keeps the last good
  revision"*. The scheduler is the guarantee and the webhook is only an
  optimisation (D4), so refreshing is an operation this layer performs rather
  than an event it waits for, and its failure is an ordinary outcome: the
  project stays available and the response says when it was last confirmed.
* :func:`write_back` — *"an accepted edit SHALL be written back as a commit on
  the project's configured branch and pushed"*, with D5's per-file precondition,
  D6's bounded retry and D8's refusal to substitute an author. One logical edit
  is one pushed commit, and a commit that cannot be pushed did not happen.
* :func:`rebuild_index` — *"the service SHALL provide an operation that discards
  the entire index and rebuilds it from the working copy"*, and, in the same
  breath, *"an ordinary read SHALL NOT trigger a full index rebuild"*. It is an
  operation, and `tests/unit/test_hosted_rebuild_is_not_a_read.py` is what keeps
  it one.

The three share one shape: they take ports, they return
:class:`~cybercanon.application.results.Result`, and they contain no rule about
an asset. What a specification *says* is still the domain's, and what it looks
like on disk is still an adapter's.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.repository_host import (
    Commit,
    FileChange,
    ProjectNotReady,
    ProjectStatus,
    PushRejected,
    RepositoryHost,
    RepositoryUnavailable,
)
from cybercanon.application.ports.search_index import SearchIndex
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.results import Result, as_result
from cybercanon.application.use_cases.index_assets import (
    Fingerprinter,
    Progress,
    RebuildReport,
    no_fingerprints,
    no_progress,
    rebuild_index,
)
from cybercanon.application.use_cases.resolve_actor import (
    GitIdentity,
    Resolution,
    resolve_git_identity,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.revisions import ContentHash, Revision, ServedRevision

DEFAULT_ATTEMPTS = 3
"""How many times a rejected push is re-evaluated before it becomes a conflict (D6).

*"A pathologically busy branch can exhaust the attempts and report a conflict
for an edit that would have applied. Reporting a false conflict is safe; forcing
is not."*
"""

DEFAULT_INTERVAL = timedelta(minutes=5)
"""The staleness window a caller that configured none is measured against."""


class WriteConflict(OperationFailed):
    """The content this edit was composed against is not what is there now (D5).

    Per file, by digest, and deliberately not by branch tip: any unrelated commit
    anywhere in the repository would conflict with every in-flight edit, and a
    project with a busy branch would be unwritable.
    """

    kind = FailureKind.CONFLICT
    identifier = "edit.conflict"

    def __init__(
        self, path: str, reason: str = "the content has changed since it was read"
    ) -> None:
        super().__init__(f"{path} could not be written: {reason}", path)
        self.path = path
        self.reason = reason


class AuthorUnmapped(OperationFailed):
    """The acting person has no git identity, so nothing may be committed (D8).

    *"No mapping, no write."* Refused rather than committed under a shared or
    service identity, because that is precisely how `git blame` stops answering
    the question the tool exists to answer. The message names the missing entry,
    so the fix is obvious.
    """

    kind = FailureKind.FORBIDDEN
    identifier = "actor.unmapped"

    def __init__(self, subject: str, path: str = "") -> None:
        super().__init__(
            f"{subject} has no entry in .canon/actors.yaml, so an edit cannot be "
            "attributed to a git identity; add them to the mapping",
            path or subject,
        )
        self.subject = subject


@dataclass(frozen=True)
class RefreshOutcome:
    """What one refresh did, and what reads are served from now.

    `refreshed` is false for a refresh that could not reach the remote, and that
    is *not* a refusal: the project keeps answering from `served`, and `reason`
    is what a surface shows beside the staleness it is already obliged to show.
    """

    project: str
    served: ServedRevision
    refreshed: bool
    reason: str = ""

    def may_be_stale(self, now, interval: timedelta = DEFAULT_INTERVAL) -> bool:
        """Whether the last successful confirmation is older than the interval."""
        return self.served.may_be_stale(now, interval)


@dataclass(frozen=True)
class Edit:
    """One file an edit touches, and the content it was composed against.

    `based_on` of ``None`` asserts the file did not exist when the edit was
    composed, which is how a new specification is written without racing a
    second author who had the same idea.
    """

    path: str
    content: bytes
    based_on: ContentHash | None = None


@dataclass(frozen=True)
class WriteOutcome:
    """One logical edit, applied: the commit it became and where it landed."""

    project: str
    commit: Commit
    revision: Revision
    attempts: int = 1

    @property
    def paths(self) -> tuple[str, ...]:
        return self.commit.paths


@as_result
def refresh_project(
    project: str,
    *,
    repository_host: RepositoryHost,
    clock: Clock = system_clock,
) -> RefreshOutcome:
    """Fetch, advance the served revision atomically, and record the confirmation.

    "Atomically" is not a promise this function keeps by locking; it is one it
    keeps by *only ever replacing the whole value*. The served revision and the
    time it was confirmed move together or not at all, so no reader can observe
    a revision paired with somebody else's confirmation time.

    A remote that cannot be reached leaves both exactly as they were and reports
    itself, because *"reads SHALL continue to be served from the last good
    revision"* and *"the project SHALL NOT be reported as unavailable"*.
    """
    status = _ready(project, repository_host)
    assert status.served is not None
    try:
        served = repository_host.fetch(project, confirmed_at=clock())
    except RepositoryUnavailable as failure:
        return RefreshOutcome(
            project=project, served=status.served, refreshed=False, reason=failure.reason
        )
    return RefreshOutcome(project=project, served=served, refreshed=True)


@as_result
def write_back(
    project: str,
    edits: Sequence[Edit],
    *,
    repository_host: RepositoryHost,
    author: GitAuthor | None,
    message: str,
    subject: str = "",
    agent: str = "",
    attempts: int = DEFAULT_ATTEMPTS,
) -> WriteOutcome:
    """Apply one logical edit as one pushed commit, or refuse it (D2, D5, D6, D8).

    The loop is D6 exactly: check the precondition against the current revision,
    commit, push; if the remote advanced, fetch and start again, bounded. A
    retry whose file was untouched succeeds invisibly, and one whose file moved
    is refused — both of which were already the specified behaviour, so the
    retry is only the mechanism.

    Nothing here forces, merges or rebases, and an attempt budget that runs out
    recovers the working copy rather than leaving a commit that is local only.
    """
    if author is None:
        raise AuthorUnmapped(subject or project, edits[0].path if edits else "")
    if not edits:
        raise WriteConflict(project, "an edit changes at least one file")
    recorded = performed_by(message, agent)
    with repository_host.writer(project):
        return _attempt_until(project, edits, repository_host, author, recorded, attempts)


def _attempt_until(
    project: str,
    edits: Sequence[Edit],
    repository_host: RepositoryHost,
    author: GitAuthor,
    message: str,
    attempts: int,
) -> WriteOutcome:
    """D6's bounded loop, inside the project's single-writer lock (task 5.7).

    Two ways out other than success, and they are not the same. A **rejected**
    push means the remote advanced, which is the retry signal: recover, and
    evaluate the precondition again against what is there now. An
    **unavailable** remote is not retryable at all — nothing will have changed
    by the next line — so the working copy is put back and the caller is told,
    which is what makes *"a local commit that cannot be pushed is not reported
    as applied"* true for every way a push can fail rather than only for the
    interesting one (task 5.9).
    """
    for attempt in range(1, attempts + 1):
        try:
            return _apply(project, edits, repository_host, author, message, attempt)
        except PushRejected:
            _reset(project, repository_host)
        except RepositoryUnavailable as failure:
            _reset(project, repository_host)
            raise RepositoryUnavailable(project, _nothing_recorded(failure.reason)) from failure
    raise WriteConflict(
        edits[0].path,
        f"the branch moved under {attempts} attempts; nothing was written",
    )


def _apply(
    project: str,
    edits: Sequence[Edit],
    repository_host: RepositoryHost,
    author: GitAuthor,
    message: str,
    attempt: int,
) -> WriteOutcome:
    """One attempt: precondition, commit, push. Any of the three may refuse."""
    revision = repository_host.head(project)
    changes = [_change(project, edit, repository_host, revision) for edit in edits]
    commit = repository_host.commit(project, changes, author=author, message=message)
    pushed = repository_host.push(project)
    return WriteOutcome(project=project, commit=commit, revision=pushed, attempts=attempt)


def _change(
    project: str,
    edit: Edit,
    repository_host: RepositoryHost,
    revision: Revision,
) -> FileChange:
    """D5's precondition, evaluated against the revision this attempt is on."""
    current = repository_host.read(project, edit.path, revision)
    if _digest(current) != edit.based_on:
        raise WriteConflict(edit.path)
    return FileChange(path=edit.path, content=edit.content, based_on=edit.based_on)


def _digest(content: bytes | None) -> ContentHash | None:
    """What is there now, in the shape an edit states its precondition in."""
    return ContentHash.of(content) if content is not None else None


NOTHING_RECORDED = "no change was recorded"
"""What a caller is told when a write-back did not land (`deployment-operations`).

*"A caller SHALL NOT be told a write-back succeeded unless its commit exists on
the configured branch"*, and the refusal *"SHALL state that no change was
recorded"*. The recovery above is what makes the sentence true; this is the
sentence.
"""


def _nothing_recorded(reason: str) -> str:
    """That reason, with the thing the caller actually needs to know appended."""
    return f"{reason}; {NOTHING_RECORDED}" if reason else NOTHING_RECORDED


def _reset(project: str, repository_host: RepositoryHost) -> None:
    """Throw away the commit the rejected push left behind, then re-fetch.

    Recovering rather than keeping it is what makes *"a local commit that cannot
    be pushed is not reported as applied"* true at the end of the loop as well
    as in the middle: whatever happens next, the working copy matches the remote.
    """
    repository_host.recover(project)
    try:
        repository_host.fetch(project, confirmed_at=system_clock())
    except RepositoryUnavailable:  # the next attempt will refuse on its own terms
        return


@as_result
def rebuild_project_index(
    project: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    search_index: SearchIndex,
    fingerprints: Fingerprinter = no_fingerprints,
    progress: Progress = no_progress,
    resume: bool = False,
) -> RebuildReport:
    """Discard the project's index rows and rebuild them from the working copy.

    Read at the served revision rather than off the checkout (D3), so a rebuild
    running while a fetch lands indexes one revision rather than a mixture of
    two — the same isolation every other read gets, for the same reason.

    An operation, never a side effect: nothing in a read path calls this, and a
    test asserts that rather than trusting it.

    `progress` and `resume` are the recovery's two needs (`deployment-operations`
    task 5.7): a rebuild long enough to be a recovery has to be watchable while
    it runs, and one that was interrupted has to continue rather than start
    again.
    """
    status = _ready(project, repository_host)
    assert status.served is not None
    pinned = spec_store.pinned(status.served.revision.value)
    return rebuild_index.raising(
        "",
        spec_store=pinned,
        search_index=search_index,
        fingerprints=fingerprints,
        progress=progress,
        resume=resume,
    )


def _ready(project: str, repository_host: RepositoryHost) -> ProjectStatus:
    """The project's status, or the refusal that says why it cannot answer yet."""
    status = repository_host.status(project)
    if not status.is_ready:
        raise ProjectNotReady(project, status.state)
    return status


def author_for(resolution: Resolution, spec_store: SpecStore) -> GitIdentity:
    """The git identity this person's edits are committed under (task 5.6, D8).

    The mapping is repository content, so it is read through the same store, at
    the same revision, as the specifications it explains — a project whose
    `.canon/actors.yaml` was added in the commit being read gains the person in
    that same commit, and never a moment earlier.

    The answer is always a :class:`GitIdentity`, and an unmapped person is one
    with no address rather than a raise. Refusing is `write_back`'s job, and it
    refuses *naming the missing entry*: the fix is adding a line to a file, and a
    message that did not say so would send somebody to a support channel.
    """
    return resolve_git_identity(resolution, spec_store.load_actor_mapping().mapping)


AGENT_TRAILER = "Performed-by"
"""The trailer that records the agent a person's write was performed through.

*"A write performed by an agent on a person's behalf SHALL record both the
person and the agent."* The author stays the person — an agent is an instrument,
not an author — so the agent goes where git keeps the things a commit is *about*
rather than who made it, and `git log --format=%(trailers)` answers "what did
the Blender agent write" without a second store.
"""


def edit_message(asset: str, change: str) -> str:
    """The commit message for one edit: the asset it concerns, then what changed.

    *"Its commit message SHALL name the asset and describe what changed."*
    Composed here rather than at each call site, because a message format
    derived independently in three surfaces is a history nobody can grep.
    """
    return f"{asset}: {change}"


def performed_by(message: str, agent: str = "") -> str:
    """That message, with the performing agent recorded when there was one."""
    return f"{message}\n\n{AGENT_TRAILER}: {agent}" if agent else message


@dataclass(frozen=True)
class Freshness:
    """What a read was served from, and whether anybody has checked recently.

    Both halves of *"every read states the revision it was served from and how
    stale it may be"*, as one value, so a surface cannot render the revision and
    quietly drop the staleness — the two arrive together or not at all.
    """

    revision: Revision
    confirmed_at: datetime
    may_be_stale: bool

    @classmethod
    def of(cls, served: ServedRevision, now: datetime, interval: timedelta) -> Freshness:
        """The freshness of that served revision, judged against the interval."""
        return cls(
            revision=served.revision,
            confirmed_at=served.confirmed_at,
            may_be_stale=served.may_be_stale(now, interval),
        )


@dataclass(frozen=True)
class Served[T]:
    """One read's answer, and the revision it came from."""

    value: T
    freshness: Freshness

    @property
    def revision(self) -> Revision:
        return self.freshness.revision

    @property
    def confirmed_at(self) -> datetime:
        return self.freshness.confirmed_at

    @property
    def may_be_stale(self) -> bool:
        return self.freshness.may_be_stale


type PinnedRead[T] = Callable[[SpecStore], T]
"""A read, given the store pinned to the revision it is being served from."""


@as_result
def read_at_revision[T](
    project: str,
    read: PinnedRead[T],
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    clock: Clock = system_clock,
    interval: timedelta = DEFAULT_INTERVAL,
) -> Served[T]:
    """Serve one read from one revision, and state which one (task 5.5).

    The revision is resolved **once**, before the read runs, and the store is
    pinned to it — so a briefing assembled from six files is assembled from one
    revision by construction (D3) and a fetch landing mid-read changes nothing
    the reader can see.

    A project whose working copy is not ready refuses here rather than answering
    an empty listing, which is the distinction `hosted-repository` insists on:
    *still cloning* and *has no assets* look identical to a caller and mean
    opposite things.
    """
    revision = repository_host.head(project)
    status = repository_host.status(project)
    served = status.served or ServedRevision(revision, clock())
    return Served(
        value=read(spec_store.pinned(revision.value)),
        freshness=Freshness.of(served, clock(), interval),
    )


@dataclass(frozen=True)
class FetchSchedule:
    """When a project is next due a fetch. The guarantee, not the optimisation (D4).

    A webhook is lost, misconfigured or silently disabled by a repository
    administrator; a timer is not. So the schedule is what makes a project's
    staleness bounded, and the webhook only shortens the wait.
    """

    interval: timedelta = DEFAULT_INTERVAL

    def due(self, status: ProjectStatus, now: datetime) -> bool:
        """Whether this project has gone the whole interval without a confirmation."""
        if not status.is_ready or status.served is None:
            return False
        return status.served.age(now) >= self.interval


DEFAULT_SCHEDULE = FetchSchedule()
"""The schedule a caller that configured none is measured against."""


def due_projects(
    projects: Sequence[str],
    *,
    repository_host: RepositoryHost,
    schedule: FetchSchedule,
    now: datetime,
) -> tuple[str, ...]:
    """Which of these projects the schedule says to fetch at `now`."""
    return tuple(
        project for project in projects if schedule.due(repository_host.status(project), now)
    )


def scheduled_refresh(
    projects: Sequence[str],
    *,
    repository_host: RepositoryHost,
    schedule: FetchSchedule = DEFAULT_SCHEDULE,
    clock: Clock = system_clock,
) -> tuple[Result[RefreshOutcome], ...]:
    """Refresh every project the interval has come round for (task 5.3).

    One tick of the timer. It returns outcomes rather than raising, because a
    remote that is down must not stop the other projects being refreshed — the
    failure is one project's staleness, and staleness is already reported.
    """
    now = clock()
    return tuple(
        refresh_project(project, repository_host=repository_host, clock=clock)
        for project in due_projects(
            projects, repository_host=repository_host, schedule=schedule, now=now
        )
    )


def served_after(outcome: RefreshOutcome, previous: ServedRevision) -> ServedRevision:
    """The served revision after a refresh — the previous one when it failed.

    A named function rather than a ternary at each call site, because "a failed
    refresh keeps the last good revision" is the requirement and a caller that
    re-derived it would eventually derive it differently.
    """
    return outcome.served if outcome.refreshed else replace(previous)


__all__ = [
    "AGENT_TRAILER",
    "DEFAULT_ATTEMPTS",
    "DEFAULT_INTERVAL",
    "NOTHING_RECORDED",
    "AuthorUnmapped",
    "Edit",
    "FetchSchedule",
    "Freshness",
    "PinnedRead",
    "RefreshOutcome",
    "Served",
    "WriteConflict",
    "WriteOutcome",
    "author_for",
    "due_projects",
    "edit_message",
    "performed_by",
    "read_at_revision",
    "rebuild_project_index",
    "refresh_project",
    "scheduled_refresh",
    "served_after",
    "write_back",
]
