"""The `RepositoryHost` port — a git repository the service does not own (D1).

`SpecStore` answers *what does this specification say*. This port answers the
question that only arises once the reader is a container rather than a laptop:
*where does the repository come from, and how does a change get back into it.*
Eight operations, and every one of them is in the specification rather than in
the convenience of an implementation:

* **clone** — a project is unavailable until its working copy is ready, and
  reports *provisioning* rather than an empty asset list while it is not;
* **fetch** — the scheduler is the guarantee and the webhook is an optimisation
  (D4), so refreshing is an operation the service performs, not an event it
  waits for;
* **head** — resolving the revision reads will be served from, once, so a
  multi-file read is assembled from one revision by construction (D3);
* **read at a revision** — never from the checked-out tree, which is what makes
  read isolation structural instead of a lock;
* **commit as an author** — the acting person's git identity, mapped through
  `.canon/actors.yaml` (D8). The port takes the author; it never invents one;
* **push** — one logical edit is one pushed commit, and a commit that cannot be
  pushed did not happen (D2);
* **list the paths at a revision** — the only way to enumerate content that has
  no index row, which is what an asset request is (D7);
* **recover** — a missing, corrupted or diverged working copy is restored from
  the remote, and what was only local is discarded and reported.

**Every failure is named, because each one means something different to the
caller.** An unreachable remote keeps serving the last good revision; a rejected
push is retried against the new tip (D6); a revision the repository cannot reach
is not the same as a file that is not in it. A single generic error would force
every caller to re-derive the distinction from a message.

Paths are repository-relative POSIX strings, exactly as `SpecStore` speaks them.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.revisions import ContentHash, Revision, ServedRevision


class ProjectState(Enum):
    """Where a project's working copy is. Reported, never faked.

    `hosted-repository` forbids the tempting fourth answer — an empty asset list
    — because a project that is still cloning and a project with no assets look
    identical to a caller and mean opposite things.
    """

    PROVISIONING = "provisioning"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    RECOVERING = "recovering"

    @property
    def serves_reads(self) -> bool:
        """Whether specifications can be read from this project right now."""
        return self is ProjectState.READY

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProjectStatus:
    """What a project's working copy is doing, and what it can answer with.

    `served` is present exactly when the project is ready — a project that has
    never cloned has no revision to name, and one that has is still serving its
    last good revision while a refresh fails (D4).
    """

    project: str
    state: ProjectState
    served: ServedRevision | None = None
    reason: str = ""

    @property
    def is_ready(self) -> bool:
        return self.state.serves_reads and self.served is not None


@dataclass(frozen=True)
class FileChange:
    """One file an edit touches: its new bytes, or its removal.

    `content` of ``None`` is a deletion. `based_on` is the digest of the content
    the edit was composed against and is the whole of D5's precondition: ``None``
    asserts the file did not exist, and any other value asserts it held exactly
    those bytes.
    """

    path: str
    content: bytes | None = None
    based_on: ContentHash | None = None

    @property
    def is_removal(self) -> bool:
        return self.content is None


@dataclass(frozen=True)
class Commit:
    """A commit this service made: what it is, who authored it, what it says."""

    revision: Revision
    author: GitAuthor
    message: str
    paths: tuple[str, ...] = ()
    at: datetime | None = None


@dataclass(frozen=True)
class Recovery:
    """What re-obtaining a working copy did.

    `discarded` names the local commits that were thrown away, because
    `hosted-repository` requires a recovery to *report* that it discarded them
    rather than to quietly resolve toward the remote.
    """

    project: str
    state: ProjectState
    discarded: tuple[str, ...] = ()
    reason: str = ""

    @property
    def discarded_anything(self) -> bool:
        return bool(self.discarded)


class RepositoryUnavailable(OperationFailed):
    """The remote cannot be reached, or the credential was refused.

    Unavailable rather than not-found: the project exists and the service simply
    cannot talk to it, which is a condition that resolves without anybody
    changing a request.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "repository.unavailable"

    def __init__(self, project: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"the repository for project {project!r} is unavailable{detail}", project)
        self.project = project
        self.reason = reason


class ProjectNotReady(OperationFailed):
    """The working copy is still being obtained. Reported, never faked as empty."""

    kind = FailureKind.UNAVAILABLE
    identifier = "repository.provisioning"

    def __init__(self, project: str, state: ProjectState = ProjectState.PROVISIONING) -> None:
        super().__init__(f"project {project!r} is {state} and cannot be read yet", project)
        self.project = project
        self.state = state


class RevisionUnreachable(OperationFailed):
    """This repository cannot resolve that revision — a shallow clone, a bad ref."""

    kind = FailureKind.NOT_FOUND
    identifier = "repository.revision_unreachable"

    def __init__(self, project: str, revision: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(
            f"project {project!r} cannot reach revision {revision!r}{detail}", revision
        )
        self.project = project
        self.revision = revision
        self.reason = reason


class PushRejected(OperationFailed):
    """The remote advanced under us. Retried against the new tip, never forced (D6)."""

    kind = FailureKind.CONFLICT
    identifier = "repository.push_rejected"

    def __init__(self, project: str, reason: str = "") -> None:
        detail = f": {reason}" if reason else ""
        super().__init__(f"the push to project {project!r} was rejected{detail}", project)
        self.project = project
        self.reason = reason


class RepositoryHost(Protocol):
    """Obtains, refreshes, reads and writes one project's repository."""

    def clone(self, project: str) -> ProjectStatus:
        """Obtain this project's working copy, reporting what state it reached.

        Never raises for an unreachable remote: an unavailable project is a
        *reported state* with a reason, because the surface has to keep
        answering "why can I not see this project" after the clone gave up.
        """
        ...

    def status(self, project: str) -> ProjectStatus:
        """Where this project's working copy is, and what revision it serves."""
        ...

    def fetch(self, project: str, *, confirmed_at: datetime) -> ServedRevision:
        """Refresh from the remote and advance what this project serves.

        The revision and the moment it was confirmed move together, as one
        value, which is what makes "advance the served revision atomically" a
        property of the type rather than of a lock: no reader can observe a
        revision paired with somebody else's confirmation time.

        `confirmed_at` is supplied rather than read, because the host has no
        clock and the caller has a port for one. Raises
        :class:`RepositoryUnavailable` when the remote cannot be reached, which
        the caller turns into "keep serving the last good revision" rather than
        into a failed read (D4).
        """
        ...

    def head(self, project: str) -> Revision:
        """The revision at the configured branch's tip in the working copy.

        Resolved once per logical operation, so every file a briefing is
        assembled from comes from one revision (D3). Raises
        :class:`ProjectNotReady` while the working copy is still being obtained.
        """
        ...

    def read(self, project: str, path: str, revision: Revision) -> bytes | None:
        """The bytes of that file at that revision, or ``None`` when it is absent.

        Absent is an answer — a new file's precondition is *that it does not
        exist* (D5) — while a revision this repository cannot reach is
        :class:`RevisionUnreachable`, because those are different problems.
        """
        ...

    def paths_at(self, project: str, revision: Revision) -> tuple[str, ...]:
        """Every tracked path at that revision — a tree listing, not a walk.

        The eighth operation, and the one a *listing* needs: an asset is found
        through the index, but a request is repository content with no index row
        of its own (D7), so the only way to enumerate the requests of a project
        is to ask the repository what is under `.canon/requests/` at the
        revision being served. Reading the tree rather than walking a checkout
        keeps that enumeration pinned exactly as :meth:`read` is (D3).

        Raises :class:`RevisionUnreachable` for a revision this repository
        cannot resolve, for the same reason :meth:`read` does: a revision that
        is not there and a tree that is empty are different answers.
        """
        ...

    def writer(self, project: str) -> AbstractContextManager[None]:
        """Hold this project's single-writer lock for the duration of one edit.

        The ninth operation, and the one that is not about git at all. D5's
        precondition — *the content this edit was composed against is still
        there* — is only a precondition if nothing can move between the check
        and the commit, and the design's *"no horizontal scaling of the API
        beyond one writer per project"* is exactly the statement that this lock
        is enough. It is re-entrant, because D6's retry recovers and re-fetches
        inside the same edit.

        Reads never take it: isolation for a reader is a revision it already
        resolved (D3), and a read that queued behind a slow write would be the
        reader-writer lock this design rejected.
        """
        ...

    def commit(
        self,
        project: str,
        changes: Sequence[FileChange],
        *,
        author: GitAuthor,
        message: str,
    ) -> Commit:
        """Record one logical edit as one commit authored by that git identity.

        The author is supplied, never derived: D8 refuses a write by a person
        with no mapping rather than substituting a service identity, and a port
        that could invent an author would make that refusal optional.
        """
        ...

    def push(self, project: str) -> Revision:
        """Send the commits to the remote and answer the revision now there.

        Raises :class:`PushRejected` when the remote advanced, which is D6's
        retry signal, and :class:`RepositoryUnavailable` when it cannot be
        reached at all.
        """
        ...

    def recover(self, project: str) -> Recovery:
        """Re-obtain the working copy, discarding whatever the remote does not have."""
        ...


__all__ = [
    "Commit",
    "FileChange",
    "ProjectNotReady",
    "ProjectState",
    "ProjectStatus",
    "PushRejected",
    "Recovery",
    "RepositoryHost",
    "RepositoryUnavailable",
    "RevisionUnreachable",
]
