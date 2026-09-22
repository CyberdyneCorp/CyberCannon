"""Task 3.2 — the built web image serves the application, with no API reachable.

`tests/tooling/test_container_artifacts.py` reads `deploy/web.Dockerfile` and
asserts its shape: the node adapter (D10), the committed lock file, no client
secret, no endpoint of ours. `tests/integration/test_web_readiness_process.py`
runs the `node build` output on this machine. Neither of those is the artifact
that gets deployed, and the difference between them and the image is where the
deployment's surprises live: a multi-stage build that copied the wrong
directory, a `CMD` that works from a developer's shell and not from `WORKDIR`, a
runtime layer missing the dependencies the server imports.

So this builds the image and runs it, with `PUBLIC_CANON_API_URL` pointed at an
address where nothing will ever answer, and asks the container two questions:

* **is it ready** — D10 makes the web application's readiness its own process's
  answer, so the image has to become ready with the API down. An image whose
  readiness needed the API would make one service's outage a failed deploy of
  the application whose whole job at that moment is to render the outage;
* **does it serve the application** — the root address answers rather than
  erroring. What it *renders* is the frontend suite's and the end-to-end
  layer's: the application renders in the browser, so claiming a rendered
  unavailable state here would be claiming to have rendered something this
  process did not render.

Skipped with no container engine, saying so. A test that reported green because
it built nothing would be worse than one that says it did not run.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

DOCKERFILE = Path("deploy") / "web.Dockerfile"

ENGINE = "docker"
NO_ENGINE = (
    "no container engine on this machine: `docker` is what builds the artifact, "
    "and asking a container that was never built whether it serves would assert "
    "nothing"
)

READY_PATH = "/readyz"
ROOT_PATH = "/"
READY = "ready"

CONTAINER_PORT = 5173
"""What the image exposes, and what `deploy/coolify.yaml` routes to."""

BUILD_TIMEOUT_S = 900.0
START_TIMEOUT_S = 120.0
ANSWER_TIMEOUT_S = 15.0

UNREACHABLE_API = "http://api.unresolvable.invalid:8000"
"""Where the application is told the API is. Nothing will ever answer there."""


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _run(arguments: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [ENGINE, *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _get(url: str, timeout: float = ANSWER_TIMEOUT_S) -> tuple[int, str]:
    """One request, answering the status and the body even for an error status."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:
            return int(answer.status), answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as refused:
        return int(refused.code), refused.read().decode("utf-8", "replace")


@pytest.fixture(scope="module")
def served(repo_root: Path) -> Iterator[str]:
    """Build the image, run it with no API reachable, and answer its base URL."""
    if shutil.which(ENGINE) is None:  # pragma: no cover — machine dependent
        pytest.skip(NO_ENGINE)

    tag = f"cybercanon-web:serves-{uuid.uuid4().hex[:8]}"
    name = f"cybercanon-web-serves-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    _run(["build", "--file", str(DOCKERFILE), "--tag", tag, "."], repo_root, BUILD_TIMEOUT_S)
    _run(
        [
            "run",
            "--detach",
            "--name",
            name,
            "--publish",
            f"127.0.0.1:{port}:{CONTAINER_PORT}",
            "--env",
            f"PUBLIC_CANON_API_URL={UNREACHABLE_API}",
            tag,
        ],
        repo_root,
        ANSWER_TIMEOUT_S * 4,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _await(name, base_url, repo_root)
        yield base_url
    finally:
        subprocess.run([ENGINE, "rm", "--force", name], cwd=repo_root, capture_output=True)
        subprocess.run([ENGINE, "image", "rm", "--force", tag], cwd=repo_root, capture_output=True)


def _await(name: str, base_url: str, repo_root: Path) -> None:
    """Wait for the container to answer, or fail with what it printed instead."""
    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if not _running(name, repo_root):  # pragma: no cover — only on a broken image
            raise AssertionError(f"the web container exited: {_logs(name, repo_root)}")
        try:
            _get(f"{base_url}{READY_PATH}", timeout=2.0)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.3)
            continue
        return
    raise AssertionError(  # pragma: no cover — only on a broken image
        f"the web container never answered: {_logs(name, repo_root)}"
    )


def _running(name: str, repo_root: Path) -> bool:
    inspected = subprocess.run(
        [ENGINE, "inspect", name, "--format", "{{json .State.Running}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return inspected.returncode == 0 and json.loads(inspected.stdout.strip() or "false")


def _logs(name: str, repo_root: Path) -> str:  # pragma: no cover — only on a failure
    printed = subprocess.run(
        [ENGINE, "logs", "--tail", "40", name], cwd=repo_root, capture_output=True, text=True
    )
    return f"{printed.stdout}{printed.stderr}"


# --------------------------------------------------------------------------
# The two questions a running container can be asked
# --------------------------------------------------------------------------


def test_the_image_becomes_ready_with_no_api_reachable(served: str) -> None:
    """D10: the application's readiness is its own process's answer, not the API's."""
    status, body = _get(f"{served}{READY_PATH}")

    assert status == 200, body
    assert READY in body


def test_the_image_serves_the_application_with_no_api_reachable(served: str) -> None:
    """The artifact serves the application itself, not only its health endpoint."""
    status, body = _get(f"{served}{ROOT_PATH}")

    assert status == 200, body
    assert "<html" in body.lower(), body[:400]


def test_readiness_keeps_answering_while_the_api_stays_down(served: str) -> None:
    """Not a warm-up window: it is ready because the process is up, and stays so."""
    for _ in range(3):
        status, body = _get(f"{served}{READY_PATH}")

        assert (status, READY in body) == (200, True), body
