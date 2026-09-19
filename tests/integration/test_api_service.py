"""Task 1.1 — uvicorn serves the health endpoint on a clean checkout.

The claim is a *deployment* claim, so it is checked the way a deployment would
check it: a real `uvicorn` process, a real socket, a real HTTP request — and an
environment scrubbed of every `CANON_` variable, with no database running, no
identity service reachable and no repository configured anywhere.

That combination is what `http-api` requires and what `project.md` requires of
every deployed service: readiness must not need a model, an identity service or
a sibling backend, because otherwise one dependency's outage becomes a failed
deploy. A test that used `TestClient` would prove the handler; this proves the
process.

The counterpart is here too and it is the opposite behaviour: the *deployable*
refuses to start when its configuration is missing, naming every absent variable
at once. Unset configuration and an unreachable dependency are different
conditions, and this pair is where that distinction is asserted rather than
described.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from cybercanon.adapters.inbound.http.health import ALIVE, LIVE_PATH, READY, READY_PATH
from cybercanon.adapters.wiring.configuration import REQUIRED, ConfigurationIncomplete
from cybercanon.api.main import application

BOOT_TIMEOUT_S = 30.0
POLL_S = 0.1

SERVE = """\
import uvicorn

from cybercanon.adapters.inbound.http.app import build_app

uvicorn.run(build_app(), host="127.0.0.1", port={port}, log_level="warning")
"""


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _scrubbed() -> dict[str, str]:
    """The environment with nothing configured — no database, no identity, no repo."""
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("CANON_") and name not in {"DATABASE_URL", "PGHOST"}
    }


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


@pytest.fixture(scope="module")
def served(repo_root: Path) -> Iterator[str]:
    """A uvicorn process serving the app, and the base URL it is listening on."""
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-c", SERVE.format(port=port)],
        cwd=repo_root,
        env=_scrubbed(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _await(process, f"{base}{LIVE_PATH}")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


def _await(process: subprocess.Popen[str], url: str) -> None:
    """Wait for the server to answer, or fail with what it printed instead."""
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the server exited: {process.communicate()[0]}")
        try:
            _get(url)
        except (urllib.error.URLError, OSError):
            time.sleep(POLL_S)
        else:
            return
    process.terminate()
    raise AssertionError(f"the server did not answer {url} within {BOOT_TIMEOUT_S}s")


def test_uvicorn_serves_liveness_with_nothing_else_running(served: str) -> None:
    status, body = _get(f"{served}{LIVE_PATH}")

    assert status == 200
    assert ALIVE in body


def test_uvicorn_serves_readiness_with_no_database_identity_or_repository(
    served: str,
) -> None:
    """`http-api`: readiness needs none of them, so none of them is running."""
    status, body = _get(f"{served}{READY_PATH}")

    assert status == 200
    assert READY in body


def test_the_deployable_refuses_to_start_naming_every_missing_variable() -> None:
    """The other side of the same coin: unset configuration is a boot failure."""
    with pytest.raises(ConfigurationIncomplete) as refused:
        application({})

    assert refused.value.missing == REQUIRED
