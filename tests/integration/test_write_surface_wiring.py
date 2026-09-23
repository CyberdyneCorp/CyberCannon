"""Task 6.3 — the composition root binds a write destination, and it is the local one.

D1 puts the choice of destination in exactly one place: *"the local MCP server
wires `AnnotationWriter` to the git working copy and `OutcomeReporter` to the
local outbox; the hosted API wires the same ports to its own implementations"*.
That is a claim about the object graph, so it is asserted against the object
graph — built by the real composition root, over a real working copy.

What each group holds down:

* **the ports are bound, and bound locally** — the annotation writer modifies
  *this* checkout and the outcome reporter keeps its file under *this*
  `.canon/`, so a write made through the agent server and a write made through
  the command line land in the same place;
* **the agent identifier comes from the launch configuration** (D4) — present,
  it is the container's; absent, the container has none, and the server that
  gets built from it keeps every read and refuses both writes;
* **both write use cases are reachable from the surface the milestone is about**
  — the MCP server built from this container advertises `add_annotation` and
  `report_export`, and calling one reaches the use case rather than a missing
  port: with nobody signed in the answer is the use case's refusal naming the
  sign-in action, which a container with no writer could not produce;
* **nothing in the read path acquires an identity requirement** — with no issuer
  configured the resolver holds no provider and no credential, so `canon
  validate` never asks the machine's keychain anything.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport
from game_repo import build_game_repo
from machine import AGENT, stub_keychain

from cybercanon.adapters.inbound.mcp.tools import WRITE_TOOL_NAMES, advertised, build_server
from cybercanon.adapters.outbound.fs.outbox import OUTBOX_PATH, FileOutbox
from cybercanon.adapters.outbound.git.annotation_writer import GitAnnotationWriter
from cybercanon.adapters.wiring.build import build_container, writing_resolver
from cybercanon.application.testing.credential_store import InMemoryCredentialStore
from cybercanon.application.use_cases.observations import SIGN_IN_ACTION
from cybercanon.domain.identity import AgentId

pytestmark = pytest.mark.integration

MECH = "mech_scout"


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A working copy the composition root can be pointed at."""
    return build_game_repo(tmp_path_factory.mktemp("wired")).root


def call(server: Any, tool: str, arguments: dict[str, Any]) -> str:
    """One tool call against a server built in this process."""

    async def _call() -> str:
        async with Client(FastMCPTransport(server)) as client:
            result = await client.call_tool(tool, arguments)
            return "\n".join(block.text for block in result.content)

    return asyncio.run(_call())


# --------------------------------------------------------------------------
# The two ports, bound to this machine
# --------------------------------------------------------------------------


def test_the_annotation_writer_is_this_working_copy(game: Path) -> None:
    container = build_container(game, {})

    assert isinstance(container.annotation_writer, GitAnnotationWriter)
    assert container.annotation_writer.root == game


def test_the_outcome_reporter_is_the_local_outbox(game: Path) -> None:
    container = build_container(game, {})

    assert isinstance(container.outcome_reporter, FileOutbox)
    assert container.outcome_reporter.path == game / OUTBOX_PATH


def test_the_agent_identifier_comes_from_the_launch_configuration(game: Path) -> None:
    container = build_container(game, {"CANON_AGENT": AGENT})

    assert container.agent == AgentId(AGENT)


def test_a_server_launched_without_an_agent_identifier_has_none(game: Path) -> None:
    """The specified state, and the reason `agent` is optional rather than defaulted."""
    assert build_container(game, {}).agent is None


def test_an_export_is_digested_the_way_the_worker_digests_it(game: Path) -> None:
    """D7's triple needs the export's hash, and a missing file hashes to nothing."""
    from cybercanon.domain.revisions import ContentHash

    container = build_container(game, {})
    export = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

    assert container.export_digests(export) == ContentHash.of((game / export).read_bytes()).value
    assert container.export_digests("characters/mech_scout/exports/nothing.glb") == ""


# --------------------------------------------------------------------------
# Both write use cases, reachable from the agent server
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tool", WRITE_TOOL_NAMES)
def test_the_server_built_from_this_container_advertises_both_writes(game: Path, tool: str) -> None:
    assert tool in advertised(build_server(build_container(game, {"CANON_AGENT": AGENT})))


def test_the_observation_tool_reaches_the_use_case_rather_than_a_missing_port(
    game: Path,
) -> None:
    """The refusal proves the wiring: only the use case names the sign-in action.

    A container with no `AnnotationWriter` answers *"built with no write
    destination"* instead, so this assertion fails the moment the binding is
    dropped — which is what makes it a wiring test rather than a refusal test.
    """
    server = build_server(build_container(game, {"CANON_AGENT": AGENT}))

    answer = call(server, "add_annotation", {"asset": MECH, "target": "head", "text": "no"})

    assert SIGN_IN_ACTION in answer
    assert "no write destination" not in answer


def test_the_reporting_tool_reaches_the_outbox_rather_than_a_missing_port(
    game: Path,
) -> None:
    """The verdict comes back, and the report is refused for want of an identity.

    Reporting is a write: it is attributed to the person and the agent, so a
    machine nobody has signed into cannot deliver one — and the verdict it was
    asked about still arrives, because that is the one thing reporting may never
    take away.
    """
    server = build_server(build_container(game, {"CANON_AGENT": AGENT}))

    answer = call(
        server,
        "report_export",
        {"asset": MECH, "path": "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"},
    )

    assert SIGN_IN_ACTION in answer
    assert "nowhere to keep a reported outcome" not in answer


# --------------------------------------------------------------------------
# And the read path is untouched by all of it
# --------------------------------------------------------------------------


def test_with_no_issuer_configured_nothing_holds_a_credential(game: Path) -> None:
    """*"Writes require an identity; reads do not."* — so a read never asks for one."""
    resolver = writing_resolver("Ronin", InMemoryCredentialStore(), {})

    assert resolver.provider is None
    assert resolver.credential is None


def test_the_credential_store_is_not_read_while_no_issuer_is_configured(
    tmp_path: Path, game: Path
) -> None:
    """A locked keychain is not a reason a validator cannot run (D5).

    The store raises on every call, and building the container still works —
    because with no issuer configured nothing asks it anything.
    """
    stub_keychain(tmp_path / "locked", locked=True)
    container = build_container(game, {})

    assert container.credential_store is not None
    assert container.actor_resolver is not None
    assert container.actor_resolver.credential is None


def test_a_configured_issuer_resolves_through_the_stored_credential(game: Path) -> None:
    """One sign-in, and the machine writes as that person — the D5 wiring."""
    store = InMemoryCredentialStore()
    from cybercanon.application.ports.identity_provider import Credential

    store.store(Credential("a-stored-credential"))

    resolver = writing_resolver(
        "Ronin",
        store,
        {
            "CANON_AUTH_ISSUER": "https://auth.example",
            "CANON_AUTH_AUDIENCE": "https://api.example",
            "CANON_AUTH_KEY_SET_URL": "https://auth.example/jwks.json",
        },
    )

    assert resolver.provider is not None
    assert resolver.credential == Credential("a-stored-credential")
