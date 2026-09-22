"""`LocalRepositoryHost` — the working copy an artist is already standing in.

`GitRepositoryHost` obtains a working copy per project on a volume and writes
back by pushing to a configured branch. That is the hosted shape, and it is
wrong for the command line in one specific way: **`canon` does not own the
checkout and has no business pushing it.** The artist cloned it, the artist
decides when it leaves her machine, and a tool that pushed on her behalf the
first time she ran `canon add-view` would be the enemy `project.md` warns about.

So this is the same port over a checkout that already exists:

* **clone** adopts what is there rather than obtaining anything;
* **fetch** re-reads the local head — there is no remote to confirm against, and
  saying so honestly is better than inventing a confirmation;
* **push** is a no-op that answers the local head, which makes *"a commit that
  cannot be pushed did not happen"* trivially true: there is nothing to push, so
  nothing can fail to;
* **recover** discards nothing, because nothing here is a throwaway copy of
  somebody else's branch — it is the person's own work.

Everything that *writes* — the single-writer lock, the commit with the mapped
author, the per-file precondition — is identical to the hosted adapter's,
because the use case above it is identical. That is the whole point of task 7.5:
`canon add-view` and the ingestion endpoint produce the same commit because they
run the same code over the same port.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from cybercanon.adapters.outbound.git import commands
from cybercanon.adapters.outbound.git.repository_host import (
    HISTORY_FORMAT,
    UNIT,
    stamped,
)
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.repository_host import (
    Commit,
    FileChange,
    FileHistory,
    FileRevision,
    ProjectNotReady,
    ProjectState,
    ProjectStatus,
    Recovery,
    RepositoryUnavailable,
    RevisionUnreachable,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.revisions import ContentHash, Revision, ServedRevision

NOT_A_REPOSITORY = "this directory is not a git working copy"
"""What a local host answers for a path that git does not recognise."""


class LocalRepositoryHost:
    """One checkout on this machine, addressed by whatever the caller calls it."""

    def __init__(self, root: str | Path, project: str = "", *, clock: Clock = system_clock) -> None:
        self._root = Path(root)
        self._project = project or self._root.name
        self._clock = clock
        self._lock = threading.RLock()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def project(self) -> str:
        """What this checkout is addressed as. One host, one working copy."""
        return self._project

    # -- the port --------------------------------------------------------

    def clone(self, project: str) -> ProjectStatus:
        """Adopt the checkout that is already here. Nothing is obtained."""
        return self.status(project)

    def status(self, project: str) -> ProjectStatus:
        if not commands.is_repository(self._root):
            return ProjectStatus(
                project=project, state=ProjectState.UNAVAILABLE, reason=NOT_A_REPOSITORY
            )
        return ProjectStatus(
            project=project,
            state=ProjectState.READY,
            served=ServedRevision(self._head(project), self._clock()),
        )

    def fetch(self, project: str, *, confirmed_at=None) -> ServedRevision:
        """Re-read the local head. There is no remote, and none is pretended."""
        return ServedRevision(self._head(project), confirmed_at or self._clock())

    def head(self, project: str) -> Revision:
        return self._head(project)

    def read(self, project: str, path: str, revision: Revision) -> bytes | None:
        self._resolve(project, revision.value)
        found = self._git(["cat-file", "-p", f"{revision.value}:{path}"])
        return found.out if found.ok else None

    def paths_at(self, project: str, revision: Revision) -> tuple[str, ...]:
        self._resolve(project, revision.value)
        listed = self._git(["ls-tree", "-r", "--name-only", revision.value])
        return tuple(sorted(listed.lines))

    @contextmanager
    def writer(self, project: str) -> Iterator[None]:
        """The same single-writer lock, for the same reason. Re-entrant."""
        _ = project
        with self._lock:
            yield

    def commit(
        self,
        project: str,
        changes: Sequence[FileChange],
        *,
        author: GitAuthor,
        message: str,
    ) -> Commit:
        """One logical edit as one commit, authored by the mapped person (D8)."""
        with self._lock:
            for change in changes:
                self._materialise(change)
            paths = tuple(change.path for change in changes)
            self._expect(["add", "--all", "--", *paths], project)
            self._expect(_commit_arguments(author, message), project)
            return Commit(
                revision=self._head(project),
                author=author,
                message=message,
                paths=paths,
                at=self._clock(),
            )

    def push(self, project: str) -> Revision:
        """Answer the local head. Nothing leaves this machine unless she says so."""
        return self._head(project)

    def history(self, project: str, path: str, limit: int | None = None) -> FileHistory:
        """Every commit that touched that path, newest first."""
        bounded = ["-n", str(limit)] if limit is not None else []
        listed = self._git(["log", HISTORY_FORMAT, *bounded, "--", path])
        if not listed.ok:
            return FileHistory(path=path)
        revisions = tuple(self._file_revision(line, path) for line in listed.lines if line.strip())
        return FileHistory(
            path=path, revisions=revisions, truncated_before=self._shallow(revisions)
        )

    def recover(self, project: str) -> Recovery:
        """Nothing to discard: this checkout is the person's, not a cached copy."""
        return Recovery(project=project, state=self.status(project).state)

    # -- internals -------------------------------------------------------

    def _file_revision(self, line: str, path: str) -> FileRevision:
        revision, name, email, stamp = [*line.split(UNIT), "", "", ""][:4]
        found = self._git(["cat-file", "-p", f"{revision}:{path}"])
        content = found.out if found.ok else None
        return FileRevision(
            revision=Revision(revision),
            author=GitAuthor(name=name, email=email),
            at=stamped(stamp),
            content=ContentHash.of(content) if content is not None else None,
            byte_size=len(content) if content is not None else 0,
        )

    def _shallow(self, revisions: Sequence[FileRevision]) -> str:
        if not revisions:
            return ""
        shallow = self._git(["rev-parse", "--is-shallow-repository"])
        if not shallow.ok or shallow.text.strip() != "true":
            return ""
        return revisions[-1].revision.value

    def _head(self, project: str) -> Revision:
        if not commands.is_repository(self._root):
            raise ProjectNotReady(project, ProjectState.UNAVAILABLE)
        resolved = self._git(["rev-parse", "HEAD"])
        if not resolved.ok or not resolved.text.strip():
            raise ProjectNotReady(project, ProjectState.PROVISIONING)
        return Revision(resolved.text.strip())

    def _resolve(self, project: str, revision: str) -> None:
        found = self._git(["rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"])
        if not found.ok or not found.text.strip():
            raise RevisionUnreachable(project, revision, "this working copy cannot reach it")

    def _materialise(self, change: FileChange) -> None:
        target = self._root / change.path
        if change.is_removal:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(change.content or b"")

    def _git(self, arguments: Sequence[str]):
        try:
            return commands.run(self._root, arguments)
        except commands.GitUnavailable:
            return commands.Completed(code=1, out=b"", err="git is not available")

    def _expect(self, arguments: Sequence[str], project: str) -> None:
        completed = self._git(arguments)
        if not completed.ok:
            raise RepositoryUnavailable(project, "the working copy refused the write")


def _commit_arguments(author: GitAuthor, message: str) -> tuple[str, ...]:
    """One commit, authored by the mapped person and committed by the same."""
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


__all__ = ["NOT_A_REPOSITORY", "LocalRepositoryHost"]
