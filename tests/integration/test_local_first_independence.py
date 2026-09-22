"""Tasks 8.5 and 8.6 — the two surfaces that are never hosted, on a machine alone.

`deployment-operations` makes two promises about the un-hosted half of this
system, and both are promises about a **process** rather than about a function,
so both are executed here against real subprocesses:

* *"The agent server SHALL communicate over a local process-to-process channel
  only, and SHALL NOT be listening on a network port."* Asserted by denying the
  child the ability to open one: `socket.bind` and `socket.listen` raise inside
  the server's process, and it answers four read tools over standard input and
  output anyway. A server that opened a listener would fail here and nowhere
  else — and unlike reading the source, this survives the day somebody adds a
  transport flag. Where `lsof` exists the process's own open files are inspected
  as well, which is the check an operator would actually run.
* *"Both SHALL remain fully usable against a developer's own working copy with
  no hosted component reachable."* Asserted by denying the child the network
  entirely — every outbound connection and every name lookup raises — and then
  running the two things the milestone is judged on: a validation, and an agent
  asking where an asset lives. With no hosted component reachable, because there
  is no hosted component this process could reach.

The denial happens **in the child**, through a `sitecustomize` on its
`PYTHONPATH`, rather than as a patch in this process. That is the difference
between asserting that the code under test does not use the network and
asserting that this test remembered to mock everything it does use.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from game_repo import MECH_EXPORT, build_game_repo

pytestmark = pytest.mark.integration

MECH = "mech_scout"
MECH_DIRECTORY = "characters/mech_scout"

CLEAN = 0
"""What `canon validate` exits with when an export satisfies its specification."""

DENY_NETWORK = '''\
"""Every outbound connection and every name lookup raises in this process."""

import socket


class NetworkDenied(OSError):
    pass


def _denied(*_arguments, **_keywords):
    raise NetworkDenied("network access is denied")


socket.socket.connect = _denied
socket.socket.connect_ex = _denied
socket.create_connection = _denied
socket.getaddrinfo = _denied
socket.gethostbyname = _denied
'''
"""There is no hosted component to be unreachable, so unreachability is total.

`socket.socketpair` is deliberately left alone: asyncio builds its own self-pipe
from one, so blocking it would test that an event loop cannot start rather than
that a local tool needs no network.
"""

DENY_LISTENING = '''\
"""This process may not become a network server. Binding and listening raise."""

import socket


class ListenerDenied(OSError):
    pass


def _denied(*_arguments, **_keywords):
    raise ListenerDenied("this process may not listen on a network port")


socket.socket.bind = _denied
socket.socket.listen = _denied
socket.create_server = _denied
'''
"""The assertion, as a prohibition the child cannot talk its way out of.

`socketpair` and `connect` are untouched: the agent server is allowed to *be* a
process with an event loop and is allowed to reach a local file. What it is not
allowed to do is accept a connection from anywhere, and that is exactly the two
calls above.
"""


def bare_environment(**extra: str) -> dict[str, str]:
    """An environment with nothing that could identify or configure anybody."""
    stripped = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CANON_", "CYBERDYNE_", "OPENAI_", "AWS_", "GIT_"))
        and name not in {"HOME", "USER", "LOGNAME", "SSH_AUTH_SOCK", "GITHUB_TOKEN"}
    }
    return {**stripped, **extra}


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A developer's own working copy: real specifications, real exports, on disk."""
    return build_game_repo(tmp_path_factory.mktemp("game")).root


def _customised(tmp_path_factory: pytest.TempPathFactory, name: str, source: str) -> Path:
    directory = tmp_path_factory.mktemp(name)
    (directory / "sitecustomize.py").write_text(source, encoding="utf-8")
    return directory


@pytest.fixture(scope="module")
def offline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _customised(tmp_path_factory, "offline", DENY_NETWORK)


@pytest.fixture(scope="module")
def unlistenable(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _customised(tmp_path_factory, "unlistenable", DENY_LISTENING)


def ask(calls: dict[str, dict[str, Any]], *, cwd: Path, env: dict[str, str]) -> dict[str, str]:
    """Spawn the agent server and call tools over standard input and output."""

    async def _ask() -> dict[str, str]:
        transport = StdioTransport(
            command=sys.executable,
            args=["-m", "cybercanon.cli", "mcp", "serve", str(cwd)],
            env=env,
            cwd=str(cwd),
        )
        async with Client(transport) as client:
            answers = {}
            for tool, payload in calls.items():
                result = await client.call_tool(tool, payload)
                answers[tool] = "\n".join(block.text for block in result.content)
            return answers

    return asyncio.run(_ask())


def canon(cwd: Path, *arguments: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run `canon` as a process inside a working copy, exactly as a person does."""
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


# --------------------------------------------------------------------------
# 8.5 — the agent server listens on nothing
# --------------------------------------------------------------------------


def test_the_agent_server_answers_with_listening_denied(game: Path, unlistenable: Path) -> None:
    """*"it SHALL be listening on none"* — so it is denied the ability to."""
    answers = ask(
        {"where_is": {"asset_id": MECH}, "list_assets": {}},
        cwd=game,
        env=bare_environment(PYTHONPATH=str(unlistenable)),
    )

    assert MECH_DIRECTORY in answers["where_is"]
    assert MECH in answers["list_assets"]


def test_the_prohibition_is_real(game: Path, unlistenable: Path) -> None:
    """A denial nothing would have tripped over proves nothing, so trip over it."""
    result = subprocess.run(
        [sys.executable, "-c", "import socket; socket.create_server(('127.0.0.1', 0))"],
        cwd=game,
        capture_output=True,
        text=True,
        check=False,
        env=bare_environment(PYTHONPATH=str(unlistenable)),
    )

    assert result.returncode != 0
    assert "may not listen" in result.stderr


@pytest.mark.skipif(shutil.which("lsof") is None, reason="lsof is how an operator would look")
def test_the_running_agent_server_holds_no_network_socket(game: Path) -> None:
    """The check an operator runs: inspect the process's own open files."""
    server = subprocess.Popen(
        [sys.executable, "-m", "cybercanon.cli", "mcp", "serve", str(game)],
        cwd=game,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=bare_environment(),
    )
    try:
        assert server.stdin is not None
        server.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
        server.stdin.flush()
        listed = subprocess.run(
            ["lsof", "-a", "-p", str(server.pid), "-i"],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        server.terminate()
        server.wait(timeout=10)

    assert "LISTEN" not in listed.stdout, listed.stdout


# --------------------------------------------------------------------------
# 8.6 — both tools work with every hosted component unreachable
# --------------------------------------------------------------------------


def test_a_validation_completes_with_the_network_denied(game: Path, offline: Path) -> None:
    """*"the validator SHALL never require identity"* — and never a service either."""
    result = canon(game, "validate", MECH_EXPORT, env=bare_environment(PYTHONPATH=str(offline)))

    assert result.returncode == CLEAN, result.stdout + result.stderr
    assert "PASSING" in result.stdout


def test_an_agent_lookup_completes_with_the_network_denied(game: Path, offline: Path) -> None:
    """The M1 question, asked with nothing hosted in existence."""
    answers = ask(
        {"where_is": {"asset_id": MECH}, "get_constraints": {"asset_id": MECH}},
        cwd=game,
        env=bare_environment(PYTHONPATH=str(offline)),
    )

    assert MECH_DIRECTORY in answers["where_is"]
    assert "12000" in answers["get_constraints"]


def test_both_complete_in_the_same_denied_environment(game: Path, offline: Path) -> None:
    """One machine, one outage, both tools — which is how a person meets this."""
    environment = bare_environment(PYTHONPATH=str(offline))

    validated = canon(game, "validate", MECH_EXPORT, env=environment)
    located = ask({"where_is": {"asset_id": MECH}}, cwd=game, env=environment)

    assert validated.returncode == CLEAN
    assert MECH_DIRECTORY in located["where_is"]


def test_the_denial_is_real(game: Path, offline: Path) -> None:
    """The other half of the same discipline: prove the network really is denied."""
    result = subprocess.run(
        [sys.executable, "-c", "import socket; socket.create_connection(('1.1.1.1', 80))"],
        cwd=game,
        capture_output=True,
        text=True,
        check=False,
        env=bare_environment(PYTHONPATH=str(offline)),
    )

    assert result.returncode != 0
    assert "network access is denied" in result.stderr
