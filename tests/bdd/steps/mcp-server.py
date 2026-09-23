"""Step definitions for `mcp-server` — the local, read-only agent surface.

Group 5 of `add-mcp-read-server` adds the second inbound adapter, and these
scenarios are where the "one core, three surfaces" claim is checked rather than
asserted in a docstring: the same export is validated through the server and
through `canon`, and the two have to agree.

Three properties are proved mechanically rather than argued:

* **no network** — the scenarios that say so install a guard over `socket` that
  raises on `connect`, `bind` and `listen`, and then run the tools. A read that
  reached the network, or a transport that opened a port, fails the step rather
  than the reviewer's attention;
* **nothing is written** — every advertised tool is run against a real committed
  working tree and `git status` is the assertion;
* **the surface is exactly this** — the advertised names are compared with the
  literal the adapter declares (D6), so a promotion tool added in six months
  fails the build instead of shipping.

Every assertion is on content. A response is checked for the identifier it names,
the file it reports, the violation it carries — never for a sentence spelled
here, so the prose can be improved without a scenario being rewritten.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from pytest_bdd import given, scenario, then, when
from typer.testing import CliRunner

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.inbound.mcp import rendering, tools
from cybercanon.adapters.inbound.mcp.tools import (
    READ_TOOL_NAMES,
    TOOL_NAMES,
    WRITE_TOOL_NAMES,
    advertised,
    build_server,
)
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.adapters.outbound.sqlite.search_index import SqliteSearchIndex
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.identity_provider import ResolvedIdentity
from cybercanon.application.ports.search_index import FileFingerprint
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.index_assets import Fingerprinter
from cybercanon.application.use_cases.resolve_actor import ActorResolver, IdentityCache
from cybercanon.application.use_cases.spec_lens import Lens
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.design import Design, Socket
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.status import Status

PROJECT = "Ronin"
ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"
CRATE_ID = "crate"
CRATE_SPEC = "props/crate/asset.yaml"
BROKEN_SPEC = "props/broken/asset.yaml"
BROKEN_REASON = "line 4: mapping values are not allowed here"

MUZZLE = "SOCKET_muzzle_l"
SILHOUETTE = "One asymmetric shoulder reads as the scout's front"
ENGINE_PATH = "Content/Ronin/Characters/MechScout"
TRI_BUDGET = 12000
OVER_BUDGET = 19000
UNKNOWN_ASSET = "mech_scot"

PROMOTION_TOOLS = ("promote_annotation", "promote", "promote_to_rule", "add_constraint")
"""Names a promotion tool would plausibly be given. None of them may ever exist."""

MUTATION_VERBS = (
    "promote",
    "write",
    "create",
    "update",
    "delete",
    "remove",
    "set",
    "add",
    "commit",
    "report",
    "resolve",
)
"""A read surface advertises no tool whose name opens with one of these."""

REPO_PROJECT = """\
schema_version: 1
name: Ronin
"""

REPO_SPEC = """\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
constraints:
  tri_budget: 12000
"""

REPO_EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.obj"


@pytest.fixture
def mcp() -> dict[str, Any]:
    """What this scenario set up, and what each tool answered."""
    return {}


# --------------------------------------------------------------------------
# Building a surface: fakes for most scenarios, a real repository for two
# --------------------------------------------------------------------------


def the_mech() -> Asset:
    return Asset(
        id=AssetId(ASSET_ID),
        name="Scout Mech",
        status=Status.MODELING,
        aliases=("drone",),
        owner_art="rafa@cyberdyne.com",
        concept=Concept(views=("front.png",), silhouette_rules=(SILHOUETTE,)),
        design=Design(
            role="fast recon walker",
            sockets=(Socket(name=MUZZLE, purpose="muzzle flash and tracer origin"),),
        ),
        constraints=Constraints(tri_budget=TRI_BUDGET, naming="SM_{asset}_LOD{n}"),
        links=Links(engine=ENGINE_PATH),
    )


def a_container(
    *,
    triangles: int = 9000,
    with_broken_spec: bool = False,
    actor_resolver: ActorResolver | None = None,
) -> Container:
    fakes = build_fakes()
    store = fakes["spec_store"]
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SPEC_PATH, the_mech())
    store.add(CRATE_SPEC, Asset(id=AssetId(CRATE_ID), name="Supply Crate"))
    if with_broken_spec:
        store.add_unreadable(BROKEN_SPEC, BROKEN_REASON)
    fakes["mesh_inspector"].add(
        EXPORT,
        facts_for(
            MeshFormat.GLB,
            triangles=triangles,
            objects=(OBJECT,),
            transforms_applied=True,
            unit_scale=1.0,
            up_axis="Y",
            uv_sets=1,
            materials=("M_mech_scout",),
            empties=(MUZZLE,),
            clips=(),
            frame_rate=None,
            is_skinned=False,
            bone_count=0,
        ),
    )
    return Container(
        spec_store=store,
        mesh_inspector=fakes["mesh_inspector"],
        blob_store=fakes["blob_store"],
        search_index=fakes["search_index"],
        actor_resolver=actor_resolver,
    )


def an_art_director() -> ActorResolver:
    resolver = ActorResolver(project=PROJECT, cache=IdentityCache())
    resolver.cache.remember(
        ResolvedIdentity(
            actor=Actor(
                id=ActorId("rafa"),
                display_name="Rafa",
                roles=(Role.ART_DIRECTOR,),
                projects=(PROJECT,),
            )
        )
    )
    return resolver


def server_of(mcp: dict[str, Any], **kwargs: Any) -> FastMCP:
    """The scenario's server, built once and reused by every later step."""
    if "server" not in mcp:
        mcp["container"] = a_container(**kwargs)
        mcp["server"] = build_server(mcp["container"])
    return mcp["server"]


def call(server: FastMCP, tool: str, **arguments: object) -> str:
    async def _call() -> str:
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments)
            return "\n".join(block.text for block in result.content)

    return asyncio.run(_call())


def forbid_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """No connect, no bind, no listen — the guard the offline scenarios run under."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the read surface touched a network socket")

    for name in ("connect", "connect_ex", "bind", "listen"):
        monkeypatch.setattr(socket.socket, name, refuse, raising=False)
    monkeypatch.setattr(socket, "create_connection", refuse, raising=False)


def git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = {
        **os.environ,
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Rafa",
        "GIT_AUTHOR_EMAIL": "rafa@cyberdyne.com",
        "GIT_COMMITTER_NAME": "Rafa",
        "GIT_COMMITTER_EMAIL": "rafa@cyberdyne.com",
    }
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, env=environment
    )


def a_committed_repository(root: Path, ignore: str) -> Path:
    """A real working copy with a specification, an export and nothing uncommitted."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    _write(root / ".canon/project.yaml", REPO_PROJECT)
    _write(root / SPEC_PATH, REPO_SPEC)
    _write(root / ".gitignore", ignore)
    fixtures.write_static_obj(root / REPO_EXPORT, name=OBJECT)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "the canon, as an artist committed it")
    return root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fingerprinter(root: Path) -> Fingerprinter:
    def fingerprints(path: str) -> FileFingerprint | None:
        absolute = root / path
        if not absolute.is_file():
            return None
        stat = absolute.stat()
        return FileFingerprint(path=path, size=stat.st_size, mtime_ns=stat.st_mtime_ns)

    return fingerprints


def a_real_container(root: Path) -> Container:
    store = GitSpecStore(root)
    return Container(
        spec_store=store,
        mesh_inspector=TrimeshInspector(root=store.root),
        search_index=SqliteSearchIndex(root),
        fingerprints=fingerprinter(root),
    )


def every_call() -> dict[str, dict[str, object]]:
    """One call per advertised tool — what "every available read tool" means."""
    return {
        "where_is": {"asset_id": ASSET_ID},
        "list_assets": {},
        "search_assets": {"term": ASSET_ID},
        "get_asset_spec": {"asset_id": ASSET_ID, "lens": Lens.MODELING.value},
        "get_constraints": {"asset_id": ASSET_ID},
        "get_open_annotations": {"asset_id": ASSET_ID},
        "diff_spec": {"asset_id": ASSET_ID, "revision": "HEAD"},
        "validate_export": {"export": REPO_EXPORT},
    }


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario("../features/add-mcp-read-server/mcp-server.feature", "Server runs with no network")
def test_server_runs_with_no_network() -> None: ...


@scenario("../features/add-mcp-read-server/mcp-server.feature", "No listening port")
def test_no_listening_port() -> None: ...


@scenario("../features/add-mcp-read-server/mcp-server.feature", "Identical results across clients")
def test_identical_results_across_clients() -> None: ...


@scenario("../features/add-mcp-read-server/mcp-server.feature", "No mutating tool is advertised")
def test_no_mutating_tool_is_advertised() -> None: ...


@scenario("../features/add-mcp-read-server/mcp-server.feature", "Repository is unchanged by reads")
def test_repository_is_unchanged_by_reads() -> None: ...


@scenario(
    "../features/add-mcp-read-server/mcp-server.feature", "Art director's agent cannot promote"
)
def test_art_directors_agent_cannot_promote() -> None: ...


@scenario(
    "../features/add-mcp-read-server/mcp-server.feature",
    "Specification returned as readable markdown",
)
def test_specification_returned_as_readable_markdown() -> None: ...


@scenario("../features/add-mcp-read-server/mcp-server.feature", "Listings are compact")
def test_listings_are_compact() -> None: ...


@scenario("../features/add-mcp-read-server/mcp-server.feature", "Agent and command line agree")
def test_agent_and_command_line_agree() -> None: ...


@scenario("../features/add-mcp-read-server/mcp-server.feature", "Unknown asset identifier")
def test_unknown_asset_identifier() -> None: ...


@scenario(
    "../features/add-mcp-read-server/mcp-server.feature",
    "Unparseable specification does not kill the server",
)
def test_unparseable_specification_does_not_kill_the_server() -> None: ...


@scenario("../features/add-mcp-read-server/mcp-server.feature", "Launch without credentials")
def test_launch_without_credentials() -> None: ...


# --------------------------------------------------------------------------
# Local process transport
# --------------------------------------------------------------------------


@given("a machine with no network connectivity")
def _no_network(mcp: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_sockets(monkeypatch)
    mcp["offline"] = True


@when("an agent spawns the server and calls a read tool")
def _spawn_and_read(mcp: dict[str, Any]) -> None:
    mcp["response"] = call(server_of(mcp), "where_is", asset_id=ASSET_ID)


@then("the call SHALL succeed from local files")
def _the_call_succeeded(mcp: dict[str, Any]) -> None:
    response = mcp["response"]

    assert mcp["offline"], "the guard was installed"
    assert ASSET_ID in response
    assert ENGINE_PATH in response


@when("the server is running")
def _the_server_is_running(mcp: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_sockets(monkeypatch)
    started: list[object] = []
    monkeypatch.setattr(
        FastMCP, "run", lambda _self, transport=None, **_kwargs: started.append(transport)
    )
    tools.serve(a_container())
    mcp["transports"] = started


@then("it SHALL NOT be reachable from any network socket")
def _nothing_is_listening(mcp: dict[str, Any]) -> None:
    """Building and starting the server bound nothing: the guard never fired."""
    assert mcp["transports"] == [tools.STDIO]


# --------------------------------------------------------------------------
# One server, both audiences
# --------------------------------------------------------------------------


@given("two different MCP clients configured with the same credential and lens")
def _two_clients(mcp: dict[str, Any]) -> None:
    mcp["servers"] = (
        build_server(a_container(actor_resolver=an_art_director())),
        build_server(a_container(actor_resolver=an_art_director())),
    )


@when("both request the same asset's specification")
def _both_request_the_specification(mcp: dict[str, Any]) -> None:
    mcp["responses"] = tuple(
        call(server, "get_asset_spec", asset_id=ASSET_ID, lens=Lens.DESIGN.value)
        for server in mcp["servers"]
    )


@then("both SHALL receive identical content")
def _identical_content(mcp: dict[str, Any]) -> None:
    first, second = mcp["responses"]

    assert first == second
    assert ASSET_ID in first


# --------------------------------------------------------------------------
# Read-only tool surface
# --------------------------------------------------------------------------


@when("a client lists the server's available tools")
def _list_the_tools(mcp: dict[str, Any]) -> None:
    mcp["advertised"] = advertised(server_of(mcp))


@then("no advertised tool SHALL modify repository content")
def _nothing_advertised_writes(mcp: dict[str, Any]) -> None:
    """Except the enumerated set, which is what the requirement itself says.

    `mcp-server` anticipated this change in its own wording: the surface is
    reads, index maintenance, *"plus — once a later change introduces them — the
    explicitly enumerated proposal-shaped write tools of the
    `mcp-write-surface` capability and nothing else."* So the check is sharper
    now rather than looser: every advertised name that is **not** one of those
    two is still held to naming no action that writes, and the two that are must
    be exactly the enumerated pair.
    """
    advertised_names = mcp["advertised"]

    assert advertised_names == tuple(sorted(TOOL_NAMES)), "the surface is exactly this list (D6)"
    assert set(WRITE_TOOL_NAMES) == {"add_annotation", "report_export"}
    for name in advertised_names:
        if name in WRITE_TOOL_NAMES:
            continue
        assert not name.startswith(MUTATION_VERBS), f"{name} names an action that writes"


@given("a clean repository working tree")
def _a_clean_repository(mcp: dict[str, Any], tmp_path: Path, repo_root: Path) -> None:
    ignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    root = a_committed_repository(tmp_path / "game", ignore)
    mcp["repo"] = root
    mcp["server"] = build_server(a_real_container(root))

    assert git(root, "status", "--porcelain").stdout == b""


@when("an agent calls every available read tool")
def _call_every_tool(mcp: dict[str, Any]) -> None:
    """Every read tool, which is what this scenario is about.

    The write tools are exercised against a real repository by
    `mcp-write-surface`'s own *"no other repository content is touched by a
    write"*, where the assertion is the refined one (D3): one changed path, and
    one changed block inside it. Calling them here would make this scenario
    answer a question it did not ask.
    """
    server = mcp["server"]
    assert tuple(sorted(every_call())) == tuple(sorted(READ_TOOL_NAMES)), (
        "every advertised read tool is exercised"
    )
    assert set(every_call()) < set(advertised(server))
    mcp["answers"] = {
        tool: call(server, tool, **arguments) for tool, arguments in every_call().items()
    }


@then("the repository working tree SHALL remain clean")
def _the_tree_is_clean(mcp: dict[str, Any]) -> None:
    assert all(mcp["answers"].values()), "every tool answered"
    assert git(mcp["repo"], "status", "--porcelain").stdout == b""


# --------------------------------------------------------------------------
# Promotion is prohibited, not deferred
# --------------------------------------------------------------------------


@given("a caller acting as an actor holding the art director role")
def _an_art_director_calls(mcp: dict[str, Any]) -> None:
    mcp["container"] = a_container(actor_resolver=an_art_director())
    mcp["server"] = build_server(mcp["container"])

    assert mcp["container"].resolve_actor().actor.holds(Role.ART_DIRECTOR)


@when("it attempts to promote an annotation to a rule")
def _it_attempts_promotion(mcp: dict[str, Any]) -> None:
    refusals = {}
    for name in PROMOTION_TOOLS:
        with pytest.raises(Exception) as failure:
            call(mcp["server"], name, asset_id=ASSET_ID, annotation_id="a1")
        refusals[name] = str(failure.value)
    mcp["refusals"] = refusals


@then("no such tool SHALL exist")
def _no_promotion_tool_exists(mcp: dict[str, Any]) -> None:
    for name in PROMOTION_TOOLS:
        assert name not in advertised(mcp["server"])


@then("the request SHALL be refused")
def _the_promotion_was_refused(mcp: dict[str, Any]) -> None:
    assert set(mcp["refusals"]) == set(PROMOTION_TOOLS)
    for name, message in mcp["refusals"].items():
        assert name in message, "the refusal names what was asked for"
    assert ASSET_ID in call(mcp["server"], "get_asset_spec", asset_id=ASSET_ID), (
        "the caller is refused promotion, not refused reads"
    )


# --------------------------------------------------------------------------
# Responses are prose
# --------------------------------------------------------------------------


@when("an agent requests an asset's specification")
def _request_the_specification(mcp: dict[str, Any]) -> None:
    mcp["response"] = call(server_of(mcp), "get_asset_spec", asset_id=ASSET_ID)


@then("the response SHALL be the markdown briefing a person would read")
def _the_response_is_the_briefing(mcp: dict[str, Any]) -> None:
    response = mcp["response"]
    compiled = ran(mcp["container"].compile_spec(SPEC_PATH))

    assert response.strip() == compiled.text.strip(), "one compilation, not a second renderer"
    assert response.startswith("#")
    for content in (ASSET_ID, SILHOUETTE, MUZZLE, str(TRI_BUDGET)):
        assert content in response


@when("an agent lists assets")
def _list_the_assets(mcp: dict[str, Any]) -> None:
    server = server_of(mcp, with_broken_spec=mcp.get("malformed", False))
    mcp["response"] = call(server, "list_assets")


@then("the response SHALL be a compact table rather than a full record dump")
def _the_listing_is_compact(mcp: dict[str, Any]) -> None:
    response = mcp["response"]

    assert ASSET_ID in response and CRATE_ID in response
    assert response.count("|") >= len(rendering.ASSET_COLUMNS)
    assert SILHOUETTE not in response, "a listing is not a record dump"
    assert str(TRI_BUDGET) not in response


# --------------------------------------------------------------------------
# Validation reuses the single implementation
# --------------------------------------------------------------------------


@given("an export that fails its triangle budget")
def _an_over_budget_export(mcp: dict[str, Any]) -> None:
    mcp["container"] = a_container(triangles=OVER_BUDGET)
    mcp["server"] = build_server(mcp["container"])


@when("it is validated through the server and through the command line")
def _validated_both_ways(mcp: dict[str, Any]) -> None:
    mcp["response"] = call(mcp["server"], "validate_export", export=EXPORT)
    result = CliRunner().invoke(build_app(mcp["container"]), ["validate", "--json", EXPORT])
    mcp["payload"] = json.loads(result.stdout)["results"][0]


@then("both SHALL report the same violations with the same severities")
def _both_agree(mcp: dict[str, Any]) -> None:
    response, payload = mcp["response"], mcp["payload"]

    assert payload["violations"], "the export is over its budget"
    assert not payload["passed"]
    assert rendering.FAILING in response
    for violation in payload["violations"]:
        assert violation["rule_id"] in response
        assert violation["severity"] in response
        assert violation["subject"] in response
    assert str(len(payload["passed_rules"])) in response


# --------------------------------------------------------------------------
# Failures are legible to an agent
# --------------------------------------------------------------------------


@when("a tool is called with an asset identifier that does not exist")
def _call_with_an_unknown_identifier(mcp: dict[str, Any]) -> None:
    mcp["response"] = call(server_of(mcp), "where_is", asset_id=UNKNOWN_ASSET)


@then("the response SHALL say so and SHALL offer the closest matching identifiers")
def _the_response_offers_the_nearest(mcp: dict[str, Any]) -> None:
    response = mcp["response"]

    assert UNKNOWN_ASSET in response
    assert rendering.NEAREST in response
    assert ASSET_ID in response


@then("the session SHALL remain usable")
def _the_session_survives(mcp: dict[str, Any]) -> None:
    assert ASSET_ID in call(mcp["server"], "where_is", asset_id=ASSET_ID)
    assert CRATE_ID in call(mcp["server"], "list_assets")


@given("one specification file in the project is malformed")
def _a_malformed_specification(mcp: dict[str, Any]) -> None:
    mcp["malformed"] = True


@then("the listing SHALL return the readable assets")
def _the_readable_assets_are_listed(mcp: dict[str, Any]) -> None:
    response = mcp["response"]

    assert ASSET_ID in response
    assert CRATE_ID in response


@then("SHALL report the malformed file separately")
def _the_malformed_file_is_reported(mcp: dict[str, Any]) -> None:
    response = mcp["response"]

    assert rendering.UNREADABLE_HEADING in response
    assert BROKEN_SPEC in response
    assert response.index(ASSET_ID) < response.index(BROKEN_SPEC), "beside the listing, not in it"


# --------------------------------------------------------------------------
# Server is launchable from the command line
# --------------------------------------------------------------------------


@given("no identity is configured on the machine")
def _no_identity(mcp: dict[str, Any]) -> None:
    container = a_container()
    mcp["container"] = container
    mcp["server"] = build_server(container)
    resolution = container.resolve_actor()

    assert not resolution.verified, "nothing was configured, so nothing is verified"
    assert resolution.actor.roles == (), "the local actor holds no role"


@when("the server is launched and a read tool is called")
def _launch_and_read(mcp: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[object] = []
    monkeypatch.setattr(
        FastMCP, "run", lambda _self, transport=None, **_kwargs: launched.append(transport)
    )
    tools.serve(mcp["container"])
    mcp["transports"] = launched
    mcp["response"] = call(mcp["server"], "where_is", asset_id=ASSET_ID)


@then("the call SHALL succeed")
def _the_read_succeeded(mcp: dict[str, Any]) -> None:
    assert mcp["transports"] == [tools.STDIO]
    assert ASSET_ID in mcp["response"]
    assert ENGINE_PATH in mcp["response"]
