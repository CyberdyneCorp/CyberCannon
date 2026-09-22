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

**A stack that did not come up says why, in the failure.** This module used to
run ``docker compose`` with ``capture_output`` and ``check=True``, which meant
that every diagnosis docker had already written — the image that failed to
build, the container that exited, the variable the service refused to start
without — was captured into a `CalledProcessError` that prints none of it. A CI
log then said *"exit status 1"* about a hundred and sixteen tests and nothing
else, and the only way left to find the cause was to read the repository. That
is the bug behind the bug, so the three things docker knows travel with the
failure: **what it printed**, **what the containers are** (`compose ps`), and
**what the ones that are not healthy logged** (`compose logs`). Teardown happens
after the evidence is collected, because `down` deletes the containers whose
logs are the answer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

BASE_URL_VARIABLE = "CANON_E2E_BASE_URL"
COMPOSE_FILE = Path("deploy/e2e/compose.yaml")
PROJECT_NAME = "cybercanon-e2e"
DEFAULT_BASE_URL = "http://localhost:5173"
READY_TIMEOUT_S = 180
READY_PATH = "/"

LOG_LINES = "200"
"""How much of a failing container's log travels with the failure.

Enough for a traceback, a refused boot or a failed migration; not so much that
a CI log becomes unreadable at the moment somebody most needs to read it.
"""

ANSWER_TIMEOUT_S = 30
"""How long the application is given to answer after the stack reports healthy.

`up --wait` already waited for every health check, so this is the narrow window
between a container being healthy and its port being published — not a sleep
standing in for a health check.
"""

ANSWER_INTERVAL_S = 1.0

RUNNING = "running"
HEALTHY = "healthy"

NO_STACK = (
    f"no end-to-end stack: set {BASE_URL_VARIABLE} to one that is already "
    "running, or install docker so that `just test-e2e` can bring up "
    f"{COMPOSE_FILE} itself"
)

DID_NOT_START = "the end-to-end stack did not come up"
DID_NOT_ANSWER = (
    "the end-to-end stack reported healthy but nothing answered at {url} "
    f"within {ANSWER_TIMEOUT_S}s"
)


class ComposeFailed(RuntimeError):
    """A `docker compose` command that refused, carrying everything it said.

    The message is the whole point: it is what a CI log shows, and it has to
    contain docker's own words rather than the exit status they came with.
    """

    def __init__(self, command: Sequence[str], finished: subprocess.CompletedProcess) -> None:
        self.command = tuple(command)
        self.returncode = finished.returncode
        self.stdout = finished.stdout or ""
        self.stderr = finished.stderr or ""
        super().__init__(
            f"`{' '.join(self.command)}` exited {self.returncode}\n"
            f"{_section('stdout', self.stdout)}\n{_section('stderr', self.stderr)}"
        )


class StackDidNotStart(RuntimeError):
    """The stack is not usable, with docker's output and the failing logs."""


def declared_base_url() -> str | None:
    """A stack somebody else is running, if one was named."""
    return os.environ.get(BASE_URL_VARIABLE) or None


def docker_available() -> bool:
    return shutil.which("docker") is not None


def compose(repo_root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    """One `docker compose` invocation. A refusal raises, carrying its output."""
    command = [
        "docker",
        "compose",
        "--project-name",
        PROJECT_NAME,
        "--file",
        str(repo_root / COMPOSE_FILE),
        *arguments,
    ]
    finished = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, check=False)
    if check and finished.returncode != 0:
        raise ComposeFailed(command, finished)
    return finished


@contextmanager
def compose_stack(repo_root: Path) -> Iterator[str]:
    """`up --wait`, yield where the application is, and always `down --volumes`.

    ``--wait`` rather than a sleep: every service in the compose file declares a
    health check, so "it is up" is the stack's own answer instead of a guess
    that is too short on a cold machine and wasted time on a warm one.
    """
    _started(repo_root)
    try:
        yield DEFAULT_BASE_URL
    finally:
        compose(repo_root, "down", "--volumes", "--remove-orphans", check=False)


def _started(repo_root: Path) -> None:
    """Bring the stack up, or fail saying what docker said and what it logged."""
    try:
        compose(repo_root, "up", "--detach", "--wait", "--remove-orphans")
    except ComposeFailed as failure:
        raise _diagnosed(repo_root, DID_NOT_START, str(failure)) from failure
    if not await_reachable(DEFAULT_BASE_URL):
        raise _diagnosed(repo_root, DID_NOT_ANSWER.format(url=DEFAULT_BASE_URL), "")


def _diagnosed(repo_root: Path, headline: str, reported: str) -> StackDidNotStart:
    """The failure to raise: what docker said, what is running, what it logged.

    Collected **before** the teardown that follows it, because `down` removes
    the containers whose logs are the diagnosis.
    """
    failure = StackDidNotStart(f"{headline}\n\n{diagnosis(repo_root, reported)}")
    compose(repo_root, "down", "--volumes", "--remove-orphans", check=False)
    return failure


def diagnosis(repo_root: Path, reported: str = "") -> str:
    """Everything docker can be asked about this stack, as one message."""
    listing = compose(repo_root, "ps", "--all", check=False)
    parts = [reported, _section("docker compose ps", listing.stdout + listing.stderr)]
    parts += [_logs(repo_root, service) for service in unhealthy(repo_root)]
    return "\n".join(part for part in parts if part.strip())


def _logs(repo_root: Path, service: str) -> str:
    """The tail of one service's log, under a heading naming the service."""
    written = compose(repo_root, "logs", "--no-color", "--tail", LOG_LINES, service, check=False)
    return _section(f"docker compose logs {service}", written.stdout + written.stderr)


def unhealthy(repo_root: Path) -> tuple[str, ...]:
    """The services that are not running and healthy — the ones worth reading.

    Every service in this stack declares a health check, so "not healthy" is the
    stack's own verdict. A listing this cannot parse yields **every** service
    rather than none: too many logs is a nuisance, and no logs is the failure
    this module exists to stop repeating.
    """
    listing = compose(repo_root, "ps", "--all", "--format", "json", check=False)
    states = _states(listing.stdout)
    if states is None:
        return services(repo_root)
    return tuple(name for name, ok in states if not ok)


def _states(reported: str) -> list[tuple[str, bool]] | None:
    """Each service in `compose ps --format json`, and whether it is up.

    Docker has published this as a JSON array and as one object per line
    depending on the version, so both are read rather than one being assumed.
    """
    entries = _entries(reported)
    if entries is None:
        return None
    return [(str(entry.get("Service", "")), _is_up(entry)) for entry in entries]


def _entries(reported: str) -> list[dict] | None:
    lines = [line for line in reported.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        if len(lines) == 1 and lines[0].lstrip().startswith("["):
            return list(json.loads(lines[0]))
        return [json.loads(line) for line in lines]
    except (ValueError, TypeError):
        return None


def _is_up(entry: dict) -> bool:
    """Whether one `compose ps` entry is a container nobody needs to read."""
    health = str(entry.get("Health", "") or "")
    return str(entry.get("State", "")) == RUNNING and health in ("", HEALTHY)


def services(repo_root: Path) -> tuple[str, ...]:
    """Every service the compose file declares, as docker itself lists them."""
    listed = compose(repo_root, "config", "--services", check=False)
    return tuple(line.strip() for line in listed.stdout.splitlines() if line.strip())


def _section(heading: str, body: str) -> str:
    """One labelled block, or nothing when there was nothing to say."""
    if not body.strip():
        return ""
    return f"--- {heading} ---\n{body.rstrip()}"


def await_reachable(base_url: str, timeout_s: float = ANSWER_TIMEOUT_S) -> bool:
    """Whether the application answers within the window after a healthy stack."""
    deadline = time.monotonic() + timeout_s
    while True:
        if reachable(base_url):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(ANSWER_INTERVAL_S)


def reachable(base_url: str, timeout_s: float = 5.0) -> bool:
    """Whether something answers there at all — the check before a browser starts."""
    try:
        with urllib.request.urlopen(f"{base_url}{READY_PATH}", timeout=timeout_s) as response:
            return response.status < 500
    except (urllib.error.URLError, OSError):
        return False
