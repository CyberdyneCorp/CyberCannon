"""Tasks 6.1, 6.5 and 6.6 — the server as a *process*, launched the documented way.

Everything else about the read surface is provable in-process. Three things are
not, and all three are promises about a machine rather than about a function:

* **6.1 — it launches with no credential.** `canon mcp serve` is spawned as a
  subprocess with an environment stripped of every identity and configuration
  variable, and it answers `where_is` anyway. The resolution chain ends in a
  local unauthenticated actor (D4), and this is the only place that is true of a
  real process rather than of a fixture.
* **6.5 — it answers with the network denied.** The child runs under a
  `sitecustomize` that makes every outbound connection and every name lookup
  raise, and the four read tools complete regardless. Denying the network in the
  child rather than mocking a port is the point: a read that quietly reached for
  a service would fail here and nowhere else.
* **6.6 — the documented command string is the one that works.** The launch
  command is parsed out of `README.md` and run verbatim. Documentation that
  drifts from the binary is the same class of defect as a CI step that is not in
  the justfile, and the fix is to let the test read the document.

The transport is standard input and output throughout, which is also the
assertion that the server opens no port: an MCP client that can only speak over
pipes gets complete answers.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
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
BARREL = "barrel"

CONFIG_BLOCK = re.compile(r"```json\n(\{\n  \"mcpServers\".*?)```", re.DOTALL)
"""The one fenced block in `README.md` that documents how a client launches it."""

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
"""Denial in the child, not a mock in the parent.

`socket.socketpair` is deliberately left alone: asyncio builds its own
self-pipe from one, so blocking it would test that an event loop cannot start
rather than that a read needs no network.
"""


def bare_environment(**extra: str) -> dict[str, str]:
    """An environment with nothing that could identify or configure anybody.

    Built by subtraction from the real one, because `PATH` and the temporary
    directory have to survive for a subprocess to run at all — and because
    naming what is removed is what the requirement is about.
    """
    stripped = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CANON_", "CYBERDYNE_", "OPENAI_", "AWS_", "GIT_"))
        and name not in {"HOME", "USER", "LOGNAME", "SSH_AUTH_SOCK", "GITHUB_TOKEN"}
    }
    return {**stripped, **extra}


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real game repository on disk — the thing an agent client is pointed at."""
    return build_game_repo(tmp_path_factory.mktemp("game")).root


@pytest.fixture(scope="module")
def no_network(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A directory whose `sitecustomize` denies the network to anything importing it."""
    directory = tmp_path_factory.mktemp("offline")
    (directory / "sitecustomize.py").write_text(DENY_NETWORK, encoding="utf-8")
    return directory


def documented_launch(repo_root: Path) -> tuple[str, list[str]]:
    """The command and arguments `README.md` tells an agent client to use."""
    block = CONFIG_BLOCK.search((repo_root / "README.md").read_text(encoding="utf-8"))
    assert block is not None, "README.md no longer documents an agent client configuration"
    configured = json.loads(block.group(1))["mcpServers"]["cybercanon"]
    return configured["command"], list(configured["args"])


def ask(
    command: str,
    arguments: list[str],
    calls: dict[str, dict[str, Any]],
    *,
    cwd: Path,
    env: dict[str, str],
) -> dict[str, str]:
    """Spawn the server as a process and call tools over standard input and output."""

    async def _ask() -> dict[str, str]:
        transport = StdioTransport(command=command, args=arguments, env=env, cwd=str(cwd))
        async with Client(transport) as client:
            answers = {}
            for tool, payload in calls.items():
                result = await client.call_tool(tool, payload)
                answers[tool] = "\n".join(block.text for block in result.content)
            return answers

    return asyncio.run(_ask())


# --------------------------------------------------------------------------
# 6.1 — launched with no credential at all
# --------------------------------------------------------------------------


def test_it_serves_where_is_with_no_credential_configured(game: Path) -> None:
    """The requirement the read surface would be worthless without."""
    answers = ask(
        sys.executable,
        ["-m", "cybercanon.cli", "mcp", "serve", str(game)],
        {"where_is": {"asset_id": MECH}},
        cwd=game,
        env=bare_environment(),
    )

    assert MECH_DIRECTORY in answers["where_is"]


def test_it_serves_a_project_directory_it_was_not_started_in(game: Path, tmp_path: Path) -> None:
    """The directory is an argument, because an agent client names it in its config."""
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()

    answers = ask(
        sys.executable,
        ["-m", "cybercanon.cli", "mcp", "serve", str(game)],
        {"list_assets": {}},
        cwd=elsewhere,
        env=bare_environment(),
    )

    assert MECH in answers["list_assets"]
    assert BARREL in answers["list_assets"]


# --------------------------------------------------------------------------
# 6.5 — offline, end to end
# --------------------------------------------------------------------------


def test_the_whole_read_surface_completes_with_the_network_denied(
    game: Path, no_network: Path
) -> None:
    """Four tools, one process, every outbound connection raising."""
    answers = ask(
        sys.executable,
        ["-m", "cybercanon.cli", "mcp", "serve", str(game)],
        {
            "where_is": {"asset_id": MECH},
            "get_asset_spec": {"asset_id": MECH},
            "search_assets": {"term": MECH},
            "validate_export": {"export": MECH_EXPORT},
        },
        cwd=game,
        env=bare_environment(PYTHONPATH=str(no_network)),
    )

    assert MECH_DIRECTORY in answers["where_is"]
    assert "Scout Mech" in answers["get_asset_spec"]
    assert MECH in answers["search_assets"]
    assert "PASSING" in answers["validate_export"]


def test_the_denial_is_real(no_network: Path, game: Path) -> None:
    """A guard over nothing is a guard that passes for the wrong reason."""
    import subprocess

    probe = "import socket; socket.create_connection(('example.invalid', 80))"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=game,
        capture_output=True,
        text=True,
        check=False,
        env=bare_environment(PYTHONPATH=str(no_network)),
    )

    assert result.returncode != 0
    assert "network access is denied" in result.stderr


# --------------------------------------------------------------------------
# 6.6 — the documented command string
# --------------------------------------------------------------------------


def test_the_readme_documents_a_launch_command_that_works(game: Path, repo_root: Path) -> None:
    """Run what the documentation says, verbatim, and get a real answer back."""
    command, arguments = documented_launch(repo_root)
    installed = shutil.which(command)
    assert installed is not None, f"the documented command {command!r} is not installed"

    answers = ask(
        installed,
        arguments,
        {"where_is": {"asset_id": MECH}},
        cwd=game,
        env=bare_environment(),
    )

    assert MECH_DIRECTORY in answers["where_is"]


def test_the_agent_snippet_names_the_specification_and_where_it_lives(repo_root: Path) -> None:
    """The whole integration for an agent that does not speak MCP (openspec/project.md)."""
    snippet = (repo_root / "examples" / "ronin" / "CLAUDE.md").read_text(encoding="utf-8")

    assert "asset.yaml" in snippet
    assert "art-spec.md" in snippet
    assert ".canon/project.yaml" in snippet
    assert "never write constraints" in snippet
    assert snippet.count("where_is") >= 1
