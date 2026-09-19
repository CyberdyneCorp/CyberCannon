"""Reading an earlier revision of a file out of the working copy's history (D10).

`diff_spec` is the one capability in this product that genuinely needs version
control rather than a file system, and this is the whole of that need: list the
revisions that touched a specification file, and hand back the bytes of one of
them. Everything above it compares *parsed specifications*, never file text, so
nothing here knows what a specification is.

The implementation shells out to `git` rather than linking a library, for the
same reason the store reads a working copy rather than a git host's API: the
repository on disk is the source of truth, `git` is already installed wherever a
checkout exists, and a library would add a dependency and a second opinion about
what a revision is.

**Every failure is one of two answers, and neither is an exception the caller
cannot plan for.** A repository that cannot reach the revision at all — a
shallow clone, a directory that is not a repository, a machine with no `git` —
raises :class:`RevisionUnreachable`; a revision that exists and does not contain
the file raises :class:`PathAbsent`. The store turns the first into
`HistoryUnavailable` (the degraded answer the design prefers to a broken
session) and decides between the two for the second.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT = "git"
"""The binary. Absent, every history question answers *unavailable*."""

TIMEOUT_S = 15
"""A ceiling, so a wedged git never wedges a read."""

REVISION_FORMAT = "--format=%H"
AUTHOR_FORMAT = "--format=%ae"
COMMIT = "^{commit}"


class RevisionUnreachable(RuntimeError):
    """This repository cannot reach that revision — or cannot answer at all."""


class PathAbsent(RuntimeError):
    """The revision is reachable and does not contain that file."""


def revisions(root: Path, relative: str, limit: int | None = None) -> tuple[str, ...]:
    """The revisions that touched this file, newest first — empty when there are none.

    Empty is an answer, not a failure: a file that was never committed, a
    directory that is not a repository and a checkout with no history all look
    the same to a caller, and all three mean *there is nothing to compare with*.
    """
    bounded = ["-n", str(limit)] if limit is not None else []
    try:
        output = _run(root, "log", REVISION_FORMAT, *bounded, "--", relative)
    except RevisionUnreachable:
        return ()
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def authors(root: Path) -> tuple[str, ...]:
    """Every distinct commit-author address in this repository's history.

    Newest first, deduplicated, and empty whenever history cannot be read at
    all — a directory that is not a repository, a checkout with no commits, a
    machine with no `git`. Empty is an answer here for the same reason it is in
    :func:`revisions`: *there is nobody to bind yet* and *this is not a
    repository* are the same instruction to the caller, which is to leave the
    mapping alone.
    """
    try:
        output = _run(root, "log", AUTHOR_FORMAT)
    except RevisionUnreachable:
        return ()
    seen = (line.strip() for line in output.splitlines())
    return tuple(dict.fromkeys(address for address in seen if address))


def paths_at(root: Path, revision: str) -> tuple[str, ...]:
    """Every tracked path at that revision, repository-relative POSIX.

    The pinned store's answer to "what is there" (D3). A tree listing rather
    than a directory walk, because the checked-out tree is not what a pinned
    read is about: a file added after the pinned revision is not in it, and a
    file deleted since still is.
    """
    return tuple(
        line.strip()
        for line in _run(root, "ls-tree", "-r", "--name-only", revision).splitlines()
        if line.strip()
    )


def file_at(root: Path, revision: str, relative: str) -> str:
    """The contents of that file as it stood at that revision.

    The revision is resolved first so that *unknown revision* and *file not in
    this revision* stay distinguishable — they are different answers, and one of
    them is not the history's fault.
    """
    resolve(root, revision)
    try:
        return _run(root, "show", f"{revision}:{relative}")
    except RevisionUnreachable as error:
        raise PathAbsent(f"{relative} is not in revision {revision!r}") from error


def resolve(root: Path, revision: str) -> str:
    """That revision as a commit hash, or :class:`RevisionUnreachable`."""
    return _run(root, "rev-parse", "--verify", "--quiet", f"{revision}{COMMIT}").strip()


def _run(root: Path, *arguments: str) -> str:
    """One git command in the working copy, with its failure named rather than raised."""
    try:
        # A fixed argument list and no shell: nothing a caller supplies is ever
        # interpreted, and a path is passed after `--` where git expects one.
        completed = subprocess.run(
            [GIT, "-C", str(root), *arguments],
            capture_output=True,
            check=False,
            timeout=TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RevisionUnreachable(f"git could not be run: {error}") from error
    if completed.returncode != 0:
        raise RevisionUnreachable(_reason(completed.stderr))
    return _decoded(completed.stdout)


def _reason(stderr: bytes) -> str:
    """The first line git complained with, or a statement that it said nothing."""
    text = _decoded(stderr).strip()
    return text.splitlines()[0] if text else "git reported no reason"


def _decoded(output: bytes) -> str:
    """Specification files are text; anything else is not history we can read."""
    try:
        return output.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RevisionUnreachable("that revision is not readable as text") from error


__all__ = [
    "GIT",
    "PathAbsent",
    "RevisionUnreachable",
    "authors",
    "file_at",
    "paths_at",
    "resolve",
    "revisions",
]
