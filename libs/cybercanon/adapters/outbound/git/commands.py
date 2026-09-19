"""Running `git`, with its output kept as bytes and its failures kept whole.

:mod:`cybercanon.adapters.outbound.git.revisions` already shells out to `git`,
and deliberately collapses every failure into one exception: reading history is
a question with two answers — *here it is* and *this checkout cannot say* — so a
collapsed error is the right shape there.

The hosted working copy needs the opposite. `clone`, `fetch`, `push` and
`reset` fail in ways that mean *different things to the caller*: a rejected
credential is a configuration problem, an unreachable remote resolves by itself,
and a rejected push is D6's retry signal. So this module hands the exit status
and the complaint back unclassified, and
:mod:`cybercanon.adapters.outbound.git.repository_host` decides what they mean.

Two properties it keeps that the history reader does not need:

* **stdout is bytes.** A specification is text, but an object read out of the
  git database is whatever was committed, and a reader that decoded first could
  not answer "what are the exact bytes this edit was composed against" — which
  is the whole of D5's precondition.
* **the environment is supplied, never inherited wholesale.** `git` reads a
  great deal of configuration from the machine it runs on, and a hosted service
  whose behaviour depended on a developer's `~/.gitconfig` would be a deployment
  behaving differently from how it is described.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

GIT = "git"
"""The binary. Absent, every operation fails as an unreachable remote."""

TIMEOUT_S = 300
"""A ceiling for a clone of a real repository, so nothing wedges forever."""

BASE_ENVIRONMENT: Mapping[str, str] = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_ADVICE": "0",
    "LC_ALL": "C",
}
"""What `git` runs with unless a caller says otherwise.

No terminal prompt, because a service that blocked on a credential prompt would
hang instead of reporting a rejected credential; no system configuration,
because the deployment's behaviour must not depend on the image's `/etc`; and a
fixed locale, so the classifier reads the same complaint everywhere.
"""

PASSTHROUGH: tuple[str, ...] = (
    "PATH",
    "HOME",
    "SSH_AUTH_SOCK",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "TMPDIR",
)
"""The only variables inherited from the process, and each for a stated reason.

`PATH` because `git` has to be found; `HOME` and `SSH_AUTH_SOCK` because that is
where a deployment's credential helper and agent live; the certificate paths
because an on-premises host is reached over TLS the image has to trust; `TMPDIR`
because a clone needs somewhere to work. Everything else a machine happens to
export is exactly the ambient configuration this service does not read.
"""


def inherited() -> dict[str, str]:
    """The passthrough variables this process actually has."""
    return {name: os.environ[name] for name in PASSTHROUGH if name in os.environ}


@dataclass(frozen=True)
class Completed:
    """One `git` invocation: what it exited with, what it wrote, what it said."""

    code: int
    out: bytes
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def text(self) -> str:
        """Standard output as text, for the commands that answer in identifiers."""
        return self.out.decode("utf-8", errors="replace")

    @property
    def lines(self) -> tuple[str, ...]:
        """Standard output split into non-empty, stripped lines."""
        return tuple(line.strip() for line in self.text.splitlines() if line.strip())


class GitUnavailable(RuntimeError):
    """`git` could not be run at all — not installed, or it timed out."""


def run(
    root: Path | None,
    arguments: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
) -> Completed:
    """One `git` command in `root`, never raising for a non-zero exit.

    A fixed argument list and no shell, so nothing a caller supplies is ever
    interpreted. Not running at all is the one condition that raises, because
    there is no exit status to classify.
    """
    located = ["-C", str(root)] if root is not None else []
    try:
        completed = subprocess.run(
            [GIT, *located, *arguments],
            capture_output=True,
            check=False,
            timeout=TIMEOUT_S,
            env=inherited() | dict(BASE_ENVIRONMENT) | dict(environment or {}),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GitUnavailable(f"git could not be run: {error}") from error
    return Completed(
        code=completed.returncode,
        out=completed.stdout,
        err=completed.stderr.decode("utf-8", errors="replace").strip(),
    )


def is_repository(root: Path) -> bool:
    """Whether that directory is a usable git working copy.

    Asked rather than assumed, because *the volume lost the working copy* is a
    specified condition the service recovers from rather than a crash.
    """
    if not root.is_dir():
        return False
    try:
        return run(root, ["rev-parse", "--git-dir"]).ok
    except GitUnavailable:
        return False


__all__ = [
    "BASE_ENVIRONMENT",
    "GIT",
    "PASSTHROUGH",
    "TIMEOUT_S",
    "Completed",
    "GitUnavailable",
    "inherited",
    "is_repository",
    "run",
]
