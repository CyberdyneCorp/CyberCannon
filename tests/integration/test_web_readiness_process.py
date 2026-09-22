"""Task 2.4 (D10) — the built web application, running, with no API to reach.

`tests/tooling/test_web_readiness.py` asserts the *shape*: the readiness route
reaches for nothing, and the root screen renders a state rather than throwing.
`apps/cybercanon/web/tests/availability.test.ts` executes the degraded render
with a `fetch` that throws. Neither of those is the thing the specification
asks about, which is a **process**: *"given the HTTP API service is
unreachable, when the web application is deployed and its readiness is
evaluated, then readiness SHALL report ready"*.

So this suite runs the real artifact. It starts the node adapter's server — the
`node build` the image's `CMD` runs (D10) — points it at an API address where
nothing will answer, and asks it over HTTP. Two things are asserted that only a
running process can answer:

* it becomes ready with the API down, and
* **it never opened a connection to the API to decide that.** The address it is
  given is a socket this test owns, so a readiness that reached for the API
  would be recorded rather than inferred from the answer being quick.

The page itself is asked for too, and what is asserted about it is what a server
can be asked: it answers, rather than erroring. The application renders in the
browser (`ssr = false`, a session decision recorded in the frame's own load), so
the *unavailable state* it then renders is executed by the frontend suite above
and, in a browser, by the end-to-end layer — not here, where claiming it would
mean claiming to have rendered something this process did not render.

It needs the built application, which `just check` produces before this suite
runs (`web-check` precedes `test`, and `tests/tooling/test_justfile.py` asserts
that order). With no build and no node, it skips saying which recipe makes one:
a suite that reported green over a process it never started would be worse than
one that says it did not run.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

WEB = Path("apps") / "cybercanon" / "web"
SERVER = WEB / "build" / "index.js"
"""What the image runs: `CMD ["node", "build"]` over the node adapter's output."""

READY_PATH = "/readyz"
ROOT_PATH = "/"

READY = "ready"

START_TIMEOUT_S = 60.0
ANSWER_TIMEOUT_S = 10.0

NODE = "node"
NO_NODE = "node is what runs the web artifact, and there is none on this machine"
NO_BUILD = (
    f"{SERVER} is not built: `just web-check` (or `just web-build`) produces the "
    "artifact this suite runs, and `just check` runs it before this suite"
)


def free_port() -> int:
    """A port nothing is listening on yet."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class Unreachable:
    """An address where the API would be, and a record of who tried to reach it.

    It listens rather than refusing connections, so that an attempt is
    *recorded* instead of being guessed at from an error. Nothing is ever
    answered: a caller that reached here would hang, which is the other half of
    what readiness may not do.
    """

    port: int
    attempts: list[str] = field(default_factory=list)
    _listening: socket.socket | None = None
    _stop: threading.Event = field(default_factory=threading.Event)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        listening = socket.socket()
        listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listening.bind(("127.0.0.1", self.port))
        listening.listen(8)
        listening.settimeout(0.2)
        self._listening = listening
        threading.Thread(target=self._record, daemon=True).start()

    def _record(self) -> None:
        while not self._stop.is_set() and self._listening is not None:
            try:
                connection, _ = self._listening.accept()
            except (TimeoutError, OSError):
                continue
            self.attempts.append("connected")
            connection.close()

    def stop(self) -> None:
        self._stop.set()
        if self._listening is not None:
            self._listening.close()


def get(url: str, timeout: float = ANSWER_TIMEOUT_S) -> tuple[int, str]:
    """One request, answering the status and the body even for an error status."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:
            return int(answer.status), answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as refused:
        return int(refused.code), refused.read().decode("utf-8", "replace")


@dataclass
class Application:
    """The running artifact, and the address the API would have been at."""

    base_url: str
    api: Unreachable


@pytest.fixture(scope="module")
def application(repo_root: Path) -> Iterator[Application]:
    """Start the built application with nothing at the address of the API."""
    if shutil.which(NODE) is None:  # pragma: no cover — machine dependent
        pytest.skip(NO_NODE)
    if not (repo_root / SERVER).is_file():  # pragma: no cover — machine dependent
        pytest.skip(NO_BUILD)

    api = Unreachable(port=free_port())
    api.start()
    port = free_port()
    running = subprocess.Popen(
        [NODE, "build"],
        cwd=repo_root / WEB,
        env={
            "PATH": str(Path(shutil.which(NODE) or NODE).parent),
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "NODE_ENV": "production",
            "PUBLIC_CANON_API_URL": api.url,
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _await(running, base_url)
        yield Application(base_url=base_url, api=api)
    finally:
        running.terminate()
        running.wait(timeout=30)
        api.stop()


def _await(running: subprocess.Popen[str], base_url: str) -> None:
    """Wait for the process to be answering, or fail saying what it printed."""
    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if running.poll() is not None:  # pragma: no cover — only on a broken build
            raise AssertionError(f"the web artifact exited: {running.communicate()[0]}")
        try:
            get(f"{base_url}{READY_PATH}", timeout=1.0)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.2)
            continue
        return
    raise AssertionError("the web artifact never started")  # pragma: no cover


# --------------------------------------------------------------------------
# Readiness, with the API down
# --------------------------------------------------------------------------


def test_the_application_becomes_ready_with_no_api_answering(application: Application) -> None:
    status, body = get(f"{application.base_url}{READY_PATH}")

    assert status == 200
    assert READY in body


def test_readiness_never_reached_for_the_api(application: Application) -> None:
    """The mechanical half: an outage of the API cannot fail this deploy."""
    application.api.attempts.clear()

    get(f"{application.base_url}{READY_PATH}")
    time.sleep(0.3)

    assert application.api.attempts == [], (
        "the web application's readiness opened a connection to the API. It is "
        "process-only (D10): a readiness that calls the API turns that service's "
        "outage into a failed deploy of the application meant to render the outage"
    )


def test_readiness_keeps_answering_while_the_api_stays_down(application: Application) -> None:
    """Not a warm-up window: it is ready because the process is up, and stays so."""
    for _ in range(3):
        status, body = get(f"{application.base_url}{READY_PATH}")
        assert (status, READY in body) == (200, True)


# --------------------------------------------------------------------------
# The page, with the API down
# --------------------------------------------------------------------------


def test_a_page_is_served_rather_than_an_error_while_the_api_is_down(
    application: Application,
) -> None:
    """D10: *"no top-level load function may throw when the API is down"*."""
    status, body = get(f"{application.base_url}{ROOT_PATH}")

    assert status == 200, f"the application answered {status} with the API down"
    assert "<html" in body.lower()


def test_serving_that_page_did_not_require_the_api_either(application: Application) -> None:
    """The frame renders in the browser, so the server needs nothing from the API."""
    application.api.attempts.clear()

    get(f"{application.base_url}{ROOT_PATH}")
    time.sleep(0.3)

    assert application.api.attempts == []
