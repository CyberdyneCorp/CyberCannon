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

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import timedelta

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
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.index_assets import (
    Fingerprinter,
    RebuildReport,
    no_fingerprints,
    rebuild_index,
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
    for attempt in range(1, attempts + 1):
        try:
            return _apply(project, edits, repository_host, author, message, attempt)
        except PushRejected:
            _reset(project, repository_host)
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
) -> RebuildReport:
    """Discard the project's index rows and rebuild them from the working copy.

    Read at the served revision rather than off the checkout (D3), so a rebuild
    running while a fetch lands indexes one revision rather than a mixture of
    two — the same isolation every other read gets, for the same reason.

    An operation, never a side effect: nothing in a read path calls this, and a
    test asserts that rather than trusting it.
    """
    status = _ready(project, repository_host)
    assert status.served is not None
    pinned = spec_store.pinned(status.served.revision.value)
    return rebuild_index.raising(
        "", spec_store=pinned, search_index=search_index, fingerprints=fingerprints
    )


def _ready(project: str, repository_host: RepositoryHost) -> ProjectStatus:
    """The project's status, or the refusal that says why it cannot answer yet."""
    status = repository_host.status(project)
    if not status.is_ready:
        raise ProjectNotReady(project, status.state)
    return status


def served_after(outcome: RefreshOutcome, previous: ServedRevision) -> ServedRevision:
    """The served revision after a refresh — the previous one when it failed.

    A named function rather than a ternary at each call site, because "a failed
    refresh keeps the last good revision" is the requirement and a caller that
    re-derived it would eventually derive it differently.
    """
    return outcome.served if outcome.refreshed else replace(previous)


__all__ = [
    "DEFAULT_ATTEMPTS",
    "DEFAULT_INTERVAL",
    "AuthorUnmapped",
    "Edit",
    "RefreshOutcome",
    "WriteConflict",
    "WriteOutcome",
    "rebuild_project_index",
    "refresh_project",
    "served_after",
    "write_back",
]
