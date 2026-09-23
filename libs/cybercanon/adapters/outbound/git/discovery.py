"""Upward discovery, bounded by the repository root (D9).

`canon validate exports/SM_mech_scout_LOD0.glb` has to just work, and the MCP
server's `where_is` needs the identical walk next change, so the walk lives
behind the `SpecStore` port once and no adapter does path arithmetic of its own.

Two boundaries make the walk safe:

* **It stops at the repository root.** A repository is the unit git versions, so
  a specification above it governs a different project — and on a machine where
  the checkout sits in a home directory, climbing further would read a stranger's
  file. The root is where `.git` is, falling back to the directory the store was
  opened at when there is no `.git` (a tarball, a container image, a test).
* **It never leaves the root downward either.** A path outside the repository is
  not resolved at all; discovery answers ``None`` rather than reaching for it.

Paths are handled lexically: a walk over a path whose directories do not exist —
an export that has not been written yet — must still find the governing
specification.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from cybercanon.application.ports.spec_store import PROJECT_CONFIG_PATH

GIT_DIR = ".git"
SPEC_FILENAME = "asset.yaml"
PROJECT_CONFIG = PROJECT_CONFIG_PATH


def find_repository_root(start: Path) -> Path | None:
    """The nearest ancestor containing `.git`, or ``None`` outside a repository."""
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        if (candidate / GIT_DIR).exists():
            return candidate
    return None


def relative_to(root: Path, path: str | Path) -> str | None:
    """`path` as a repository-relative POSIX string, or ``None`` when it is outside.

    Both forms a caller may hold are accepted — a repository-relative path as it
    appears in a report, and an absolute path as a shell hands it over — because
    refusing one of them would push the conversion into every caller.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        return _posix(candidate)
    try:
        return _posix(candidate.resolve().relative_to(root.resolve()))
    except ValueError:
        return None


def upward(start: str) -> Iterator[str]:
    """`start` and every directory above it, up to and including the root.

    `start` is yielded first because it may itself be a directory; the caller
    tests each candidate for a specification file, so a path that is really a
    file simply finds nothing at its own level.
    """
    path = PurePosixPath(start)
    yield path.as_posix()
    for parent in path.parents:
        yield parent.as_posix()


def join(directory: str, name: str) -> str:
    """A repository-relative path, with the root spelled as the empty string."""
    return name if directory in ("", ".") else f"{directory}/{name}"


def _posix(path: Path | PurePosixPath) -> str:
    return PurePosixPath(str(path).replace("\\", "/")).as_posix().removeprefix("./")


__all__ = [
    "GIT_DIR",
    "PROJECT_CONFIG",
    "SPEC_FILENAME",
    "find_repository_root",
    "join",
    "relative_to",
    "upward",
]
