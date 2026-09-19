"""`GitRepositoryHost` with the seams the port contract stages a remote through.

The contract asks an implementation to stage five conditions that belong to the
*other side* of the network — a repository exists and holds these files, somebody
pushed directly to it, the remote refuses our credential, the network is gone for
one call, the remote advanced between a commit and its push. The in-memory fake
has them as fields. A real host has to produce them with real git, and none of
them is a thing production code should be able to do, so they live here.

Every one is staged **for real** rather than simulated:

* `add_project` initialises a bare repository and seeds it through an ordinary
  clone-and-push, so the host clones something that actually exists;
* `push_to_remote` commits through a second working copy — which is exactly what
  "somebody pushed directly to the repository" is;
* `make_unreachable` points the project at an `ssh://` remote whose transport
  refuses the key, so git genuinely fails and
  :func:`~cybercanon.adapters.outbound.git.repository_host.classify` genuinely
  reads a rejected credential out of its complaint;
* `fail_next_fetch` re-points the remote at a path that is not there for exactly
  one call;
* `reject_next_pushes` advances the remote branch immediately before the push,
  so the rejection is git's own non-fast-forward refusal and not a flag.

Nothing here overrides a decision: `fetch` and `push` still run the adapter's own
code, and what the subclass changes is the world they run against.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from cybercanon.adapters.outbound.git import commands
from cybercanon.adapters.outbound.git.repository_host import (
    GitRepositoryHost,
    ProjectRemote,
)
from cybercanon.domain.revisions import Revision, ServedRevision

BRANCH = "main"
DECOY = ".canon/outside.txt"
"""What a decoy commit touches: a file no contract test asserts about."""

REFUSING_REMOTE = "ssh://git@canon.invalid/refused.git"
REFUSING_TRANSPORT = "sh -c 'echo \"Permission denied (publickey).\" >&2; exit 255'"
"""An ssh transport that refuses the key, so the refusal is git's, not ours."""

SEED_AUTHOR = ("Seed", "seed@cyberdyne.example")


class StagedGitRepositoryHost(GitRepositoryHost):
    """The real host, over real repositories, with the remote side stageable."""

    def __init__(self, directory: Path) -> None:
        self._remotes = directory / "remotes"
        self._scratch = directory / "scratch"
        self._home = directory / "home"
        self._home.mkdir(parents=True, exist_ok=True)
        super().__init__(
            directory / "working-copies",
            environment={"HOME": str(self._home), "GIT_CONFIG_GLOBAL": "/dev/null"},
        )
        self._fetch_failures: dict[str, int] = {}
        self._push_rejections: dict[str, int] = {}
        self._decoys = 0

    # -- staging ---------------------------------------------------------

    def add_project(self, project: str, files: dict[str, bytes] | None = None) -> Revision:
        """Create this project's remote holding those files, and configure it."""
        bare = self._remotes / f"{project}.git"
        bare.parent.mkdir(parents=True, exist_ok=True)
        self._run_at(None, ["init", "--quiet", "--bare", f"--initial-branch={BRANCH}", str(bare)])
        self.configure(ProjectRemote(project=project, url=str(bare), branch=BRANCH))
        seed = self._seed_clone(project)
        for path, content in (files or {}).items():
            self._write(seed, path, content)
        self._commit_all(seed, "seed the project")
        self._run_at(seed, ["push", "--quiet", "origin", f"HEAD:refs/heads/{BRANCH}"])
        return self._remote_head(project)

    def push_to_remote(self, project: str, path: str, content: bytes | None) -> Revision:
        """Somebody else commits directly, through their own working copy."""
        seed = self._seed_clone(project)
        self._run_at(seed, ["fetch", "--quiet", "origin", BRANCH])
        self._run_at(seed, ["reset", "--quiet", "--hard", f"origin/{BRANCH}"])
        self._write(seed, path, content)
        self._commit_all(seed, f"outside change to {path}")
        self._run_at(seed, ["push", "--quiet", "origin", f"HEAD:refs/heads/{BRANCH}"])
        return self._remote_head(project)

    def remote_files(self, project: str) -> dict[str, bytes]:
        """What the remote branch holds, read straight out of the bare repository."""
        bare = self._bare(project)
        listed = self._run_at(bare, ["ls-tree", "-r", "--name-only", BRANCH])
        return {
            path: self._run_at(bare, ["cat-file", "-p", f"{BRANCH}:{path}"]).out
            for path in listed.lines
        }

    def make_unreachable(self, project: str, reason: str = "") -> None:
        """Point the project at a remote whose transport refuses our credential."""
        remote = self.remote_of(project)
        self.configure(ProjectRemote(project=project, url=REFUSING_REMOTE, branch=remote.branch))
        self._environment["GIT_SSH_COMMAND"] = REFUSING_TRANSPORT

    def make_reachable(self, project: str) -> None:
        """Undo :meth:`make_unreachable`, so recovery can be exercised."""
        self._environment.pop("GIT_SSH_COMMAND", None)
        self.configure(ProjectRemote(project=project, url=str(self._bare(project)), branch=BRANCH))

    def fail_next_fetch(self, project: str, times: int = 1) -> None:
        self._fetch_failures[project] = times

    def reject_next_pushes(self, project: str, times: int = 1) -> None:
        self._push_rejections[project] = times

    # -- the port, with the staged condition applied first ----------------

    def fetch(self, project: str, *, confirmed_at: datetime | None = None) -> ServedRevision:
        if self._fetch_failures.get(project, 0) > 0:
            self._fetch_failures[project] -= 1
            with self._broken_remote(project):
                return super().fetch(project, confirmed_at=confirmed_at)
        return super().fetch(project, confirmed_at=confirmed_at)

    def push(self, project: str) -> Revision:
        if self._push_rejections.get(project, 0) > 0:
            self._push_rejections[project] -= 1
            self._decoys += 1
            self.push_to_remote(project, DECOY, f"advanced {self._decoys}\n".encode())
        return super().push(project)

    # -- internals -------------------------------------------------------

    @contextmanager
    def _broken_remote(self, project: str) -> Iterator[None]:
        """The remote is briefly somewhere that is not there."""
        remote = self.remote_of(project)
        missing = str(self._remotes / "gone.git")
        self._run_at(self.path(project), ["remote", "set-url", "origin", missing])
        try:
            yield
        finally:
            self._run_at(self.path(project), ["remote", "set-url", "origin", remote.url])

    def _bare(self, project: str) -> Path:
        return self._remotes / f"{project}.git"

    def _remote_head(self, project: str) -> Revision:
        found = self._run_at(self._bare(project), ["rev-parse", BRANCH])
        return Revision(found.text.strip())

    def _seed_clone(self, project: str) -> Path:
        """A second working copy of the project, for staging what others do."""
        seed = self._scratch / project
        if not commands.is_repository(seed):
            seed.parent.mkdir(parents=True, exist_ok=True)
            self._run_at(None, ["clone", "--quiet", str(self._bare(project)), str(seed)])
        return seed

    def _write(self, root: Path, path: str, content: bytes | None) -> None:
        target = root / path
        if content is None:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def _commit_all(self, root: Path, message: str) -> None:
        name, email = SEED_AUTHOR
        self._run_at(root, ["add", "--all"])
        self._run_at(
            root,
            [
                "-c",
                f"user.name={name}",
                "-c",
                f"user.email={email}",
                "commit",
                "--quiet",
                "--allow-empty",
                "--message",
                message,
            ],
        )

    def _run_at(self, root: Path | None, arguments: list[str]) -> commands.Completed:
        return commands.run(root, arguments, environment=self._environment)


__all__ = ["BRANCH", "DECOY", "REFUSING_REMOTE", "StagedGitRepositoryHost"]
