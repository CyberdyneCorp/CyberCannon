"""Freshness, per project, answerable without a shell inside a container.

`deployment-operations` asks for exactly five facts per project, and names them:
*"the revision the working copy is currently at, the time of the last successful
fetch, the outcome and time of the most recent fetch attempt, the revision the
index was last built from, and whether the index matches the working copy's
current revision."*

Four of the five come from somewhere; the fifth is arithmetic. What matters is
the separation the specification is really asking for:

* **the last successful fetch is not the last attempt.** A fetch that fails
  leaves the served revision and its confirmation time exactly where they were —
  that is `hosted-repository`'s rule and it is what keeps a read honest. But a
  deployment whose fetches have been failing for a day looks identical to one
  nobody has pushed to, unless the *attempt* is recorded separately. So it is:
  :class:`FetchAttempt` carries its own time, its outcome and its reason, and a
  run of failures moves it while `last_fetch_at` stands still;
* **the index is a cache with its own revision.** It is built *from* a revision,
  and the working copy then moves on. `in_sync` is a comparison of two strings,
  reported with both of them, because "stale" with nothing to compare is a
  status nobody can act on.

:class:`DeploymentJournal` is where the attempts and the index builds are kept.
It is process-local and deliberately so: it describes what *this* instance has
done, it is lost on a restart exactly as an uptime counter is, and nothing about
the canon depends on it. Persisting it would make it a second piece of durable
state to recover — for a number whose whole purpose is to describe right now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.repository_host import (
    ProjectState,
    ProjectStatus,
    RepositoryHost,
    RepositoryUnavailable,
)
from cybercanon.application.ports.search_index import SearchIndex
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.results import NotFound, Ok, Result, Unavailable
from cybercanon.application.use_cases.hosted_repository import (
    RefreshOutcome,
    rebuild_project_index,
    refresh_project,
)
from cybercanon.application.use_cases.index_assets import (
    Fingerprinter,
    Progress,
    RebuildReport,
    no_fingerprints,
    no_progress,
)

UNKNOWN = ""
"""What a revision reads as before anything has established one."""


@dataclass(frozen=True)
class FetchAttempt:
    """One attempt to refresh a working copy: when, whether, and why not."""

    project: str
    at: datetime
    succeeded: bool
    reason: str = ""

    @property
    def outcome(self) -> str:
        return "succeeded" if self.succeeded else "failed"


@dataclass(frozen=True)
class WorkingCopyStatus:
    """Where one project's working copy is, and how recently anybody checked.

    `last_fetch_at` moves only on a success. `attempt` moves on every try, which
    is what makes a silently failing fetch detectable rather than invisible.
    """

    project: str
    state: ProjectState
    revision: str = UNKNOWN
    last_fetch_at: datetime | None = None
    attempt: FetchAttempt | None = None
    reason: str = ""

    @property
    def reachable(self) -> bool:
        """Whether reads can be served from this working copy right now."""
        return self.state.serves_reads

    @property
    def fetching(self) -> str:
        """`succeeded`, `failed`, or nothing attempted yet."""
        return self.attempt.outcome if self.attempt is not None else "none"


@dataclass(frozen=True)
class IndexFreshness:
    """Which revision the index was built from, and whether that is still current."""

    project: str
    indexed_revision: str = UNKNOWN
    working_copy_revision: str = UNKNOWN
    rebuilding: bool = False

    @property
    def in_sync(self) -> bool:
        """Both revisions known and equal. An unbuilt index is never in sync."""
        return bool(self.indexed_revision) and self.indexed_revision == self.working_copy_revision


@dataclass(frozen=True)
class ProjectReport:
    """Everything the status surface says about one project."""

    project: str
    working_copy: WorkingCopyStatus
    index: IndexFreshness


@dataclass
class DeploymentJournal:
    """What this instance has done: fetch attempts, and index builds.

    Mutable, in memory, per process. The composition root holds one and hands it
    to whatever refreshes or rebuilds; the status surface reads it.
    """

    attempts: dict[str, FetchAttempt] = field(default_factory=dict)
    builds: dict[str, str] = field(default_factory=dict)
    rebuilding: set[str] = field(default_factory=set)

    def attempted(self, project: str, *, at: datetime, succeeded: bool, reason: str = "") -> None:
        """Record one fetch attempt, whatever it did."""
        self.attempts[project] = FetchAttempt(
            project=project, at=at, succeeded=succeeded, reason=reason
        )

    def attempt(self, project: str) -> FetchAttempt | None:
        return self.attempts.get(project)

    def built(self, project: str, revision: str) -> None:
        """Record the revision this project's index was last built from."""
        self.builds[project] = revision
        self.rebuilding.discard(project)

    def building(self, project: str) -> None:
        """Record that a rebuild is running, so `/status` can say so."""
        self.rebuilding.add(project)

    def indexed_revision(self, project: str) -> str:
        return self.builds.get(project, UNKNOWN)


def note_refresh(journal: DeploymentJournal, outcome: RefreshOutcome, *, at: datetime) -> None:
    """Record what one refresh did. Success and failure are the same call."""
    journal.attempted(outcome.project, at=at, succeeded=outcome.refreshed, reason=outcome.reason)


def refresh_and_record(
    project: str,
    *,
    repository_host: RepositoryHost,
    journal: DeploymentJournal,
    clock: Clock = system_clock,
) -> Result[RefreshOutcome]:
    """Refresh one project and journal the attempt, whichever way it went.

    The refusal path is journalled too: a project that is not ready to be
    fetched has still been tried, and a status surface that only recorded the
    tries that reached the network would show the same silence as no tries.
    """
    at = clock()
    result = refresh_project(project, repository_host=repository_host, clock=lambda: at)
    if isinstance(result, Ok):
        note_refresh(journal, result.value, at=at)
        return result
    journal.attempted(project, at=at, succeeded=False, reason=result.message)
    return result


def rebuild_and_record(
    project: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    search_index: SearchIndex,
    fingerprints: Fingerprinter = no_fingerprints,
    progress: Progress = no_progress,
    journal: DeploymentJournal,
    resume: bool = False,
) -> Result[RebuildReport]:
    """Rebuild one project's index with the rebuild visible while it runs (task 5.7).

    The journal is marked *before* the first row is written and the revision is
    recorded only once the rebuild finished, which is what makes the two states
    `/status` reports mean different things: *rebuilding* is "do not trust the
    index's completeness", and an `indexed_revision` is "this index was built
    from that revision". A rebuild that failed halfway leaves neither claim
    standing, which is the honest report of what is in the database.
    """
    journal.building(project)
    revision = _revision_of(project, repository_host)
    outcome = rebuild_project_index(
        project,
        repository_host=repository_host,
        spec_store=spec_store,
        search_index=search_index,
        fingerprints=fingerprints,
        progress=progress,
        resume=resume,
    )
    if isinstance(outcome, Ok):
        journal.built(project, revision)
    else:
        journal.rebuilding.discard(project)
    return outcome


def _revision_of(project: str, repository_host: RepositoryHost) -> str:
    """The revision a rebuild is reading, or nothing when it cannot be resolved."""
    try:
        return repository_host.head(project).value
    except (RepositoryUnavailable, OSError):  # pragma: no cover — reported by the rebuild
        return UNKNOWN


# --------------------------------------------------------------------------
# Reading while the index is being rebuilt
# --------------------------------------------------------------------------

INDEX_REBUILDING = "index.rebuilding"
"""What a read refuses with while the rows it would have used are being written."""


class IndexRead(Enum):
    """How much of the index one read depends on being complete.

    The specification asks for one behaviour — *"reads that cannot be served
    from the partial index SHALL report unavailability rather than an incomplete
    answer"* — and answering it needs this distinction, because the two kinds of
    read fail differently:

    * :attr:`ENTRY` is a lookup of one asset. A **hit** is a fact: the row is
      there, it was written from the working copy, and it is the same answer the
      finished index will give, so it is served. A **miss** is not an answer at
      all — "no such asset" and "not rebuilt yet" are indistinguishable — so it
      becomes unavailability;
    * :attr:`EXHAUSTIVE` is a listing or a search, where completeness *is* the
      answer. A partial listing is wrong rather than short, and there is no way
      for the caller to tell, so it is refused for as long as the rebuild runs.

    :attr:`NONE` is everything served from the working copy, which a rebuild
    does not touch: specifications, briefings and validation keep answering,
    which is `deployment-operations`' rule that *"answers derivable from the
    working copy alone SHALL continue to be served"*.
    """

    NONE = "none"
    ENTRY = "entry"
    EXHAUSTIVE = "exhaustive"


def rebuilding(journal: DeploymentJournal, project: str) -> bool:
    """Whether this project's index is being rebuilt right now."""
    return project in journal.rebuilding


def served_from_index[T](
    answer: Result[T],
    *,
    project: str,
    journal: DeploymentJournal,
    read: IndexRead,
) -> Result[T]:
    """That answer, or unavailability when the index is too partial to give it."""
    if read is IndexRead.NONE or not rebuilding(journal, project):
        return answer
    if read is IndexRead.EXHAUSTIVE or isinstance(answer, NotFound):
        return Unavailable(
            identifier=INDEX_REBUILDING,
            message=(
                f"the index for {project} is being rebuilt, so this answer would be "
                "incomplete; specifications are still served from the working copy"
            ),
            subject=project,
        )
    return answer


def working_copy_status(
    project: str,
    *,
    repository_host: RepositoryHost | None,
    journal: DeploymentJournal,
) -> WorkingCopyStatus:
    """One project's working copy, as the operator asks about it.

    A host that raises rather than answering is reported as unavailable rather
    than allowed to fail the whole status surface: the question *"can you reach
    the working copy"* is exactly the one being asked, so an exception is an
    answer.
    """
    status = _status_of(project, repository_host)
    served = status.served
    return WorkingCopyStatus(
        project=project,
        state=status.state,
        revision=served.revision.value if served is not None else UNKNOWN,
        last_fetch_at=served.confirmed_at if served is not None else None,
        attempt=journal.attempt(project),
        reason=status.reason,
    )


def index_freshness(
    project: str,
    *,
    working_copy: WorkingCopyStatus,
    journal: DeploymentJournal,
) -> IndexFreshness:
    """Whether the index matches the working copy, with both revisions named."""
    return IndexFreshness(
        project=project,
        indexed_revision=journal.indexed_revision(project),
        working_copy_revision=working_copy.revision,
        rebuilding=project in journal.rebuilding,
    )


def describe_project(
    project: str,
    *,
    repository_host: RepositoryHost | None,
    journal: DeploymentJournal,
) -> ProjectReport:
    """The five facts, for one project."""
    working_copy = working_copy_status(project, repository_host=repository_host, journal=journal)
    return ProjectReport(
        project=project,
        working_copy=working_copy,
        index=index_freshness(project, working_copy=working_copy, journal=journal),
    )


def _status_of(project: str, repository_host: RepositoryHost | None) -> ProjectStatus:
    """The host's answer, or the one that describes a host that cannot answer."""
    if repository_host is None:
        return ProjectStatus(project=project, state=ProjectState.READY)
    try:
        return repository_host.status(project)
    except RepositoryUnavailable as failure:
        return ProjectStatus(project=project, state=ProjectState.UNAVAILABLE, reason=failure.reason)
    except OSError as failure:  # a working-copy volume that is simply not there
        return ProjectStatus(project=project, state=ProjectState.UNAVAILABLE, reason=str(failure))


__all__ = [
    "INDEX_REBUILDING",
    "UNKNOWN",
    "DeploymentJournal",
    "FetchAttempt",
    "IndexFreshness",
    "IndexRead",
    "ProjectReport",
    "WorkingCopyStatus",
    "describe_project",
    "index_freshness",
    "note_refresh",
    "rebuild_and_record",
    "rebuilding",
    "refresh_and_record",
    "served_from_index",
    "working_copy_status",
]
