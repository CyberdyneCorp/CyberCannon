"""Task 6.2 — the stack the end-to-end suite runs against, brought up and down.

There is exactly one way to run an operation and it is a `just` recipe, so
`just test-e2e` stays a single `uv run --locked pytest -m e2e` line and the
stack is brought up *from inside the run* rather than from two extra lines in
the recipe. That is not a workaround: it is what makes the teardown reliable.
A recipe with `up` before pytest and `down` after leaks containers the moment
pytest is interrupted, and a leaked Postgres is the reason the next run fails
for a reason nobody can reproduce.

Three ways in, in this order:

1. ``CANON_E2E_BASE_URL`` — a stack somebody else is running. CI's e2e job, a
   developer with the application already up, or a staging deployment.
2. ``docker compose`` over ``deploy/e2e/compose.yaml`` — the stack this
   repository provides, started here and stopped with its volumes afterwards.
3. neither available → **skip, naming the two ways in**. Never a silent pass:
   an e2e suite that reports green because it ran nothing is worse than one
   that does not run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

BASE_URL_VARIABLE = "CANON_E2E_BASE_URL"
COMPOSE_FILE = Path("deploy/e2e/compose.yaml")
PROJECT_NAME = "cybercanon-e2e"
DEFAULT_BASE_URL = "http://localhost:5173"
READY_TIMEOUT_S = 180
READY_PATH = "/"

NO_STACK = (
    f"no end-to-end stack: set {BASE_URL_VARIABLE} to one that is already "
    "running, or install docker so that `just test-e2e` can bring up "
    f"{COMPOSE_FILE} itself"
)


def declared_base_url() -> str | None:
    """A stack somebody else is running, if one was named."""
    return os.environ.get(BASE_URL_VARIABLE) or None


def docker_available() -> bool:
    return shutil.which("docker") is not None


def compose(repo_root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT_NAME,
            "--file",
            str(repo_root / COMPOSE_FILE),
            *arguments,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=check,
    )


@contextmanager
def compose_stack(repo_root: Path) -> Iterator[str]:
    """`up --wait`, yield where the application is, and always `down --volumes`.

    ``--wait`` rather than a sleep: every service in the compose file declares a
    health check, so "it is up" is the stack's own answer instead of a guess
    that is too short on a cold machine and wasted time on a warm one.
    """
    compose(repo_root, "up", "--detach", "--wait", "--remove-orphans")
    try:
        yield DEFAULT_BASE_URL
    finally:
        compose(repo_root, "down", "--volumes", "--remove-orphans", check=False)


def reachable(base_url: str, timeout_s: float = 5.0) -> bool:
    """Whether something answers there at all — the check before a browser starts."""
    try:
        with urllib.request.urlopen(f"{base_url}{READY_PATH}", timeout=timeout_s) as response:
            return response.status < 500
    except (urllib.error.URLError, OSError):
        return False
