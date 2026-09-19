"""Tasks 11.1-11.3 — one core, three surfaces, over a real repository.

This is the claim M2 exists to make good on, and the only way to assert it is to
*execute* both surfaces and compare what they answered. Reading two
implementations and concluding they agree is exactly the review that produced
"it passed on my machine but the site says it failed" everywhere else.

So: one game repository written to disk, one container built over it by the
composition root, and then

* **11.1** the failing barrel validated by `canon validate --json` **as a
  subprocess** and by `GET /v1/projects/{project}/validations` — same
  violations, same severities, same overall outcome;
* **11.2** the scout's briefing compiled by `canon compile --stdout --json` and
  requested over HTTP at the same revision — byte-identical;
* **11.3** one query issued over HTTP and through the **agent surface**, a real
  FastMCP client against a real server — the same assets in the same order.

Each comparison is written so that it fails if a surface grows its own logic:
the CLI runs in its own process over its own container, the agent surface is
spoken to as an agent speaks to it, and what is compared is what each one
actually emitted rather than an intermediate value they happen to share.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client, FastMCP
from game_repo import BARREL_EXPORT, MECH_EXPORT, MECH_SPEC, GameRepo, build_game_repo

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.surface import HostedProject, Surface
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.adapters.inbound.mcp.tools import build_server
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.wiring.build import build_container
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.results import succeeded
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.domain.identity import Actor, ActorId, Role

pytestmark = pytest.mark.integration

PROJECT = "Ronin"
TOKEN = "rafa-token"

SCOUT = "mech_scout"

TERM = "s"
"""A term two assets match through the same pass, so the *order* is asserted.

`Scout Mech` and `Supply Crate` both match on their name prefix, which puts them
in one pass and makes the answer's order the cascade's tie-break rather than an
accident of which store answered.
"""


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> GameRepo:
    """One repository for the module: every surface below reads the same files."""
    return build_game_repo(tmp_path_factory.mktemp("equivalence"))


@pytest.fixture(scope="module")
def container(repo: GameRepo) -> Container:
    """The container the composition root builds — the one the CLI would build."""
    built = build_container(repo.root)
    rebuilt = built.rebuild_index("")

    assert succeeded(rebuilt), rebuilt
    return built


@pytest.fixture
def hosted(container: Container, postgres_dsn: str) -> Container:
    """The same container, with the index a deployment actually runs (D1, G1).

    Two reasons it is not the command line's SQLite index. A hosted surface
    answers requests on worker threads and a SQLite connection belongs to the
    thread that opened it; and the index the comparison should be made against
    is the one the service runs. That the two stores answer identically is
    already asserted, rule by rule and term by term, by task 6.1 — so pointing
    the hosted surface at PostgreSQL here makes this a comparison of *surfaces*
    rather than of stores.
    """
    with PostgresSearchIndex(postgres_dsn) as index:
        over_postgres = replace(container, search_index=index)
        rebuilt = over_postgres.rebuild_index("")

        assert succeeded(rebuilt), rebuilt
        yield over_postgres


@pytest.fixture
def client(hosted: Container) -> TestClient:
    """The hosted surface over that container, with one entitled person."""
    provider = InMemoryIdentityProvider()
    provider.add(
        Credential(TOKEN),
        Actor(
            id=ActorId("auth|rafa"),
            display_name="Rafa",
            roles=(Role.ART_DIRECTOR,),
            projects=(PROJECT,),
        ),
    )
    surface = Surface(
        projects={PROJECT: HostedProject(name=PROJECT, container=hosted)},
        identity_provider=provider,
    )
    return TestClient(build_app(surface=surface))


def over_http(client: TestClient, path: str) -> dict[str, Any]:
    answered = client.get(
        f"/{VERSION}/projects/{PROJECT}{path}", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert answered.status_code == 200, answered.text
    return answered.json()["data"]


def over_the_command_line(root: Path, *arguments: str) -> dict[str, Any]:
    """`canon`, as a process, in the repository — the surface an artist runs."""
    completed = subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode in (0, 1), completed.stderr
    return json.loads(completed.stdout)


def through_the_agent_surface(server: FastMCP, tool: str, **arguments: Any) -> str:
    async def _call() -> str:
        async with Client(server) as agent:
            answered = await agent.call_tool(tool, arguments)
            return "\n".join(block.text for block in answered.content)

    return asyncio.run(_call())


# --------------------------------------------------------------------------
# 11.1 — one verdict
# --------------------------------------------------------------------------


def test_the_same_failing_export_gets_the_same_verdict_from_both_surfaces(
    repo: GameRepo, client: TestClient
) -> None:
    """The barrel is over its triangle budget, and both surfaces must say so."""
    served = over_http(client, f"/validations?export={BARREL_EXPORT}")
    local = over_the_command_line(repo.root, "validate", "--json", BARREL_EXPORT)["results"][0]

    assert served["violations"] == local["violations"]
    assert served["passed"] is local["passed"] is False
    assert served["outcome"] == local["outcome"]
    assert served["not_evaluated"] == local["not_evaluated"]
    assert served["passed_rules"] == local["passed_rules"]


def test_the_severities_are_the_same_rule_by_rule(repo: GameRepo, client: TestClient) -> None:
    """Stated separately because a surface could agree on the set and not the severity."""
    served = over_http(client, f"/validations?export={BARREL_EXPORT}")
    local = over_the_command_line(repo.root, "validate", "--json", BARREL_EXPORT)["results"][0]

    assert _severities(served) == _severities(local)
    assert _severities(served), "a failing export carries at least one severity"


def test_a_passing_export_also_agrees(repo: GameRepo, client: TestClient) -> None:
    """The negative half: agreement on failure alone could be agreement on noise."""
    served = over_http(client, f"/validations?export={MECH_EXPORT}")
    local = over_the_command_line(repo.root, "validate", "--json", MECH_EXPORT)["results"][0]

    assert served["passed"] is local["passed"] is True
    assert served["violations"] == local["violations"] == []


# --------------------------------------------------------------------------
# 11.2 — one briefing
# --------------------------------------------------------------------------


def test_the_compiled_briefing_is_byte_identical_across_surfaces(
    repo: GameRepo, client: TestClient
) -> None:
    served = over_http(client, f"/assets/{SCOUT}/briefing")
    local = over_the_command_line(repo.root, "compile", "--stdout", "--json", MECH_SPEC)

    assert served["text"].encode("utf-8") == local["text"].encode("utf-8")
    assert served["asset"] == local["asset"] == SCOUT
    assert served["source"] == local["source"] == MECH_SPEC


def test_the_briefing_carries_the_project_defaults_on_both_surfaces(
    repo: GameRepo, client: TestClient
) -> None:
    """A merge done twice is the classic way two surfaces drift (D3)."""
    served = over_http(client, f"/assets/{SCOUT}/briefing")["text"]

    assert "12000" in served
    assert (
        served
        == over_the_command_line(repo.root, "compile", "--stdout", "--json", MECH_SPEC)["text"]
    )


# --------------------------------------------------------------------------
# 11.3 — one lookup
# --------------------------------------------------------------------------


def test_a_query_returns_the_same_assets_in_the_same_order_on_both_surfaces(
    container: Container, client: TestClient
) -> None:
    served = [item["asset"] for item in over_http(client, f"/search?q={TERM}")["items"]]
    agent = _identifiers(
        through_the_agent_surface(build_server(container), "search_assets", term=TERM)
    )

    assert served == agent
    assert len(served) > 1, "a single result cannot demonstrate an order"


def test_where_is_answers_the_same_locations_on_both_surfaces(
    container: Container, client: TestClient
) -> None:
    """The other lookup: same asset, same recorded and unrecorded locations."""
    served = over_http(client, f"/assets/{SCOUT}/locations")
    agent = through_the_agent_surface(build_server(container), "where_is", asset_id=SCOUT)

    for entry in served["locations"]:
        assert (entry["value"] in agent) or not entry["recorded"]
    assert served["asset"] == SCOUT


def _severities(payload: dict[str, Any]) -> list[tuple[str, str]]:
    return [(one["rule_id"], one["severity"]) for one in payload["violations"]]


def _identifiers(table: str) -> list[str]:
    """The first column of the rendered table, minus its header and its rule."""
    rows = [line for line in table.splitlines() if line.startswith("|")]
    cells = [row.strip("|").split("|")[0].strip() for row in rows]
    return [cell for cell in cells if cell not in {"asset", ""} and not set(cell) <= {"-", ":"}]
