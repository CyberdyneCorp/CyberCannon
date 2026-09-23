"""Task 6.4 — the offline guarantee, with the two write tools as the only exception.

`mcp-write-surface` makes a promise that is easy to state and easy to break by
accident: *"the entire read surface SHALL remain fully usable"* when no identity
is available, and *"the validation, compilation and lookup paths SHALL NOT
acquire an identity requirement because writes exist."* The way a change breaks
it is never deliberate — a resolver wired into a read path, a credential loaded
at construction, an import that opens a keychain — so the assertion has to be
made against a process that **cannot** reach anything.

The denial happens in the child, through a `sitecustomize` on its `PYTHONPATH`
(the same device `test_local_first_independence.py` uses), rather than as a
patch in this process: that is the difference between asserting the code does
not use the network and asserting this test remembered to mock everything it
does use.

Three things are executed with every socket refused:

* **all eight read tools answer.** Enumerated from the server's own
  `READ_TOOL_NAMES`, so a ninth read tool added later is covered here the day it
  arrives rather than the day somebody remembers;
* **`canon validate` exits clean.** The validator never required identity and
  still does not;
* **both write tools are refused, and only those two.** Once with nothing
  configured, where the refusal names the sign-in action, and once with a
  credential in the machine's store that cannot be verified because the issuer
  is unreachable — where the refusal says so and the reads keep working.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from game_repo import MECH_EXPORT, build_game_repo
from machine import AGENT, Issuing, bare_environment, signing_issuer, stub_keychain

from cybercanon.adapters.inbound.mcp.tools import READ_TOOL_NAMES, WRITE_TOOL_NAMES
from cybercanon.application.use_cases.observations import SIGN_IN_ACTION

pytestmark = pytest.mark.integration

MECH = "mech_scout"
CLEAN = 0

DENY_NETWORK = '''\
"""Every outbound connection and every name lookup raises in this process."""

import socket


class NetworkDenied(OSError):
    pass


def _denied(*arguments, **keywords):
    raise NetworkDenied("network access is denied")


socket.socket.connect = _denied
socket.socket.connect_ex = _denied
socket.create_connection = _denied
socket.getaddrinfo = _denied
socket.gethostbyname = _denied
'''

READS: dict[str, dict[str, Any]] = {
    "where_is": {"asset_id": MECH},
    "list_assets": {},
    "search_assets": {"term": "mech"},
    "get_asset_spec": {"asset_id": MECH},
    "get_constraints": {"asset_id": MECH},
    "get_open_annotations": {"asset_id": MECH},
    "diff_spec": {"asset_id": MECH, "revision": "HEAD"},
    "validate_export": {"export": MECH_EXPORT},
}
"""Every read tool, with arguments that make it do its work."""

WRITES: dict[str, dict[str, Any]] = {
    "add_annotation": {
        "asset": MECH,
        "target": "head",
        "text": "12000 triangles is unreachable without losing the head silhouette",
    },
    "report_export": {"asset": MECH, "path": MECH_EXPORT},
}


def test_the_enumerated_calls_are_the_whole_surface() -> None:
    """The lists above are the server's, not a second opinion about it."""
    assert tuple(READS) == READ_TOOL_NAMES
    assert tuple(WRITES) == WRITE_TOOL_NAMES


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_game_repo(tmp_path_factory.mktemp("offline")).root


@pytest.fixture(scope="module")
def offline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("denied")
    (directory / "sitecustomize.py").write_text(DENY_NETWORK, encoding="utf-8")
    return directory


def ask(calls: dict[str, dict[str, Any]], *, cwd: Path, env: dict[str, str]) -> dict[str, str]:
    """Spawn the agent server and put these calls to it over standard input and output."""

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
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


# --------------------------------------------------------------------------
# Nothing configured, nothing reachable
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def answers(game: Path, offline: Path) -> dict[str, str]:
    """One spawned server with the network denied, asked everything it offers."""
    return ask({**READS, **WRITES}, cwd=game, env=bare_environment(offline, CANON_AGENT=AGENT))


@pytest.mark.parametrize("tool", READ_TOOL_NAMES)
def test_every_read_tool_answers_with_the_network_denied(
    answers: dict[str, str], tool: str
) -> None:
    assert answers[tool].strip(), f"{tool} answered nothing"
    assert SIGN_IN_ACTION not in answers[tool], f"{tool} asked for an identity"


def test_the_reads_carry_the_facts_and_not_only_prose(answers: dict[str, str]) -> None:
    """A tool that answered an empty template would pass the check above."""
    assert "characters/mech_scout" in answers["where_is"]
    assert "12000" in answers["get_constraints"]
    assert "PASSING" in answers["validate_export"]


def test_validate_exits_clean_with_the_network_denied(game: Path, offline: Path) -> None:
    result = canon(game, "validate", MECH_EXPORT, env=bare_environment(offline))

    assert result.returncode == CLEAN, result.stdout + result.stderr
    assert "PASSING" in result.stdout


@pytest.mark.parametrize("tool", WRITE_TOOL_NAMES)
def test_only_the_two_write_tools_are_refused(answers: dict[str, str], tool: str) -> None:
    """And the refusal is the remedy, not a stack trace: *"name the sign-in action"*."""
    assert SIGN_IN_ACTION in answers[tool], answers[tool]


def test_the_refusal_leaves_the_session_usable(game: Path, offline: Path) -> None:
    """*"When the caller then reads an asset that does exist, the read SHALL succeed."*"""
    session = ask(
        {"add_annotation": WRITES["add_annotation"], "where_is": {"asset_id": MECH}},
        cwd=game,
        env=bare_environment(offline, CANON_AGENT=AGENT),
    )

    assert SIGN_IN_ACTION in session["add_annotation"]
    assert "characters/mech_scout" in session["where_is"]


def test_the_report_tool_still_returns_the_verdict_it_was_asked_about(
    answers: dict[str, str],
) -> None:
    """Reporting is refused; the verdict is not the report's to withhold.

    The call answers the verdict the local validator produced *and* says the
    report was not delivered and why — which is the shape D6 requires of every
    reporting failure: the verdict stands, delivery is pending.
    """
    assert "PASSING" in answers["report_export"]
    assert "the verdict stands locally" in answers["report_export"]
    assert SIGN_IN_ACTION in answers["report_export"]


def test_the_denial_is_real(game: Path, offline: Path) -> None:
    """A denial nothing would have tripped over proves nothing, so trip over it."""
    result = subprocess.run(
        [sys.executable, "-c", "import socket; socket.create_connection(('1.1.1.1', 80))"],
        cwd=game,
        capture_output=True,
        text=True,
        check=False,
        env=bare_environment(offline),
    )

    assert result.returncode != 0
    assert "network access is denied" in result.stderr


# --------------------------------------------------------------------------
# Signed in, and the issuer gone
# --------------------------------------------------------------------------


def test_a_credential_that_cannot_be_verified_refuses_the_write_not_the_read(
    game: Path, offline: Path, tmp_path: Path
) -> None:
    """A stored credential, an unreachable issuer: the read runs, the write stops.

    The credential is genuinely in the machine's store and the issuer is
    genuinely unreachable, so the resolution chain degrades exactly as D4 says
    it does — provider declines, nothing is cached in a process that has just
    started, and the local unauthenticated actor answers. The write, which is
    the only thing that needed a verified identity, is the only thing that
    stops.

    **What this asserts is the refusal, not its wording.** In a process with a
    cold identity cache the chain cannot tell *no credential* from *a credential
    nobody could verify*, so the message names the sign-in action rather than
    saying `unverifiable`. That distinction is `add-mcp-read-server`'s
    resolution chain (D4) and is recorded in the milestone report rather than
    papered over here.
    """
    keychain = stub_keychain(tmp_path / "keychain")
    with signing_issuer() as running:
        environment = bare_environment(keychain, **running.environment, CANON_AGENT=AGENT)
        assert canon(game, "login", env=environment).returncode == CLEAN

    denied = bare_environment(offline, keychain, **_issuer_of(running), CANON_AGENT=AGENT)
    session = ask(
        {"where_is": {"asset_id": MECH}, "add_annotation": WRITES["add_annotation"]},
        cwd=game,
        env=denied,
    )

    assert "characters/mech_scout" in session["where_is"]
    assert SIGN_IN_ACTION in session["add_annotation"]
    assert "writes name the person" in session["add_annotation"]


def _issuer_of(running: Issuing) -> dict[str, str]:
    """The issuer's variables after the server itself has stopped answering."""
    return dict(running.environment)
