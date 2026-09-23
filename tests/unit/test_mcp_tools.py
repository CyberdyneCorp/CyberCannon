"""Tasks 5.1 to 5.4, 5.6 and 5.7 — the MCP read surface, over in-memory fakes.

Everything here runs through the real FastMCP server, spoken to by a real
client, with no repository on disk, no credential, no identity provider and no
network — which is the property `mcp-server` asks for first and the reason the
server takes a container rather than building one.

**Every assertion is on content, never on wording.** A response is checked for
the identifier it must name, the socket it must list, the palette it must not
carry, the notice the *use case* wrote — never for a sentence this module
spells. Rendering can be improved without a test being rewritten, which is the
point: prose that cannot be edited is prose that will not be.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from typer.testing import CliRunner

from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.inbound.mcp import rendering
from cybercanon.adapters.inbound.mcp.tools import (
    READ_TOOL_NAMES,
    TOOL_NAMES,
    WRITE_TOOL_NAMES,
    advertised,
    build_server,
)
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.identity_provider import ResolvedIdentity
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.resolve_actor import ActorResolver, IdentityCache
from cybercanon.application.use_cases.spec_lens import Lens, notice_for
from cybercanon.domain.annotations import (
    Anchor3D,
    Annotation,
    AnnotationKind,
    AnnotationState,
)
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.design import Design, Socket
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.identity import Actor, ActorId, AgentId, Role
from cybercanon.domain.mesh_facts import MeshFacts, MeshFormat
from cybercanon.domain.policy import REQUIRES_PERSON, Operation, Subject, decide
from cybercanon.domain.status import Status

pytestmark = pytest.mark.unit

PROJECT = "Ronin"
ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"

CRATE_ID = "crate"
CRATE_SPEC = "props/crate/asset.yaml"
BROKEN_SPEC = "props/broken/asset.yaml"
BROKEN_REASON = "line 3: mapping values are not allowed here"

MUZZLE = "SOCKET_muzzle_l"
PALETTE = "three desaturated greens and one warning orange"
SILHOUETTE = "One asymmetric shoulder reads as the scout's front"
ENGINE_PATH = "Content/Ronin/Characters/MechScout"
TRI_BUDGET = 12000
OVER_BUDGET = 19000

TYPO = "mech_scot"
UNKNOWN_LENS = "engineering"

PROMOTION_TOOLS = ("promote_annotation", "promote", "promote_to_rule", "add_constraint")
"""Names a promotion tool would plausibly be given. None of them may exist."""

DURABLE_WRITES = (
    "promote",
    "set_constraint",
    "add_constraint",
    "write_constraint",
    "set_rule",
    "add_rule",
    "write_rule",
    "set_silhouette",
    "add_silhouette",
    "write_spec",
    "edit_spec",
    "set_spec",
    "update_spec",
)
"""The names an operation that writes a durable rule would plausibly be given.

Task 2.11 of `add-model-sheet-2d` extends this suite rather than starting a new
one: the exact tool-set assertion is what already keeps a tool from appearing,
and this is the *reason* it may not — **no advertised tool writes a durable
rule**. A name-shaped check rather than a behavioural one is deliberate: the
advertised surface is a list of names, and a stem that appears in one is a
conversation somebody has to have before the tool ships. The stems pair a
writing verb with the thing written, so `get_constraints` — a read, and the one
`spec-lenses` exists for — is not caught by a check meant for `set_constraints`.
"""

IDENTITY_PARAMETERS = ("actor", "actor_id", "role", "roles", "entitlement", "projects", "as_actor")
"""What no tool may accept: identity comes from the credential, never a parameter."""


# --------------------------------------------------------------------------
# Fixtures — one project, three assets, one of them unreadable
# --------------------------------------------------------------------------


def a_note(
    identifier: str,
    kind: AnnotationKind,
    text: str,
    state: AnnotationState = AnnotationState.OPEN,
) -> Annotation:
    return Annotation(
        id=identifier,
        author="rafa@cyberdyne.com",
        kind=kind,
        text=text,
        target=Anchor3D(part="antenna"),
        state=state,
    )


def the_mech() -> Asset:
    return Asset(
        id=AssetId(ASSET_ID),
        name="Scout Mech",
        status=Status.MODELING,
        aliases=("drone",),
        owner_art="rafa@cyberdyne.com",
        owner_design="dani@cyberdyne.com",
        owner_code="leo@cyberdyne.com",
        concept=Concept(views=("front.png",), silhouette_rules=(SILHOUETTE, PALETTE)),
        design=Design(
            role="fast recon walker",
            read_distance_m=25,
            sockets=(Socket(name=MUZZLE, purpose="muzzle flash and tracer origin"),),
        ),
        constraints=Constraints(tri_budget=TRI_BUDGET, naming="SM_{asset}_LOD{n}"),
        links=Links(engine=ENGINE_PATH),
        annotations=(
            a_note("a1", AnnotationKind.TECHNICAL, "the antenna costs 900 triangles"),
            a_note(
                "a2",
                AnnotationKind.ART_DIRECTION,
                "the hatch seam was closed",
                AnnotationState.RESOLVED,
            ),
        ),
    )


def the_crate() -> Asset:
    return Asset(id=AssetId(CRATE_ID), name="Supply Crate", status=Status.CONCEPT)


def some_facts(triangles: int) -> MeshFacts:
    return facts_for(
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
    )


def a_container(
    *,
    triangles: int = 9000,
    with_broken_spec: bool = False,
    actor_resolver: ActorResolver | None = None,
) -> Container:
    """The wired application every surface in this module is handed."""
    fakes = build_fakes()
    store: InMemorySpecStore = fakes["spec_store"]
    inspector: InMemoryMeshInspector = fakes["mesh_inspector"]
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SPEC_PATH, the_mech())
    store.add(CRATE_SPEC, the_crate())
    if with_broken_spec:
        store.add_unreadable(BROKEN_SPEC, BROKEN_REASON)
    inspector.add(EXPORT, some_facts(triangles))
    return Container(
        spec_store=store,
        mesh_inspector=inspector,
        blob_store=fakes["blob_store"],
        search_index=fakes["search_index"],
        actor_resolver=actor_resolver,
    )


def an_art_director() -> ActorResolver:
    """A caller acting as a person who holds the art director role."""
    resolver = ActorResolver(project=PROJECT, cache=IdentityCache())
    director = Actor(
        id=ActorId("rafa"),
        display_name="Rafa",
        roles=(Role.ART_DIRECTOR,),
        projects=(PROJECT,),
    )
    resolver.cache.remember(_identity(director))
    return resolver


def _identity(actor: Actor) -> ResolvedIdentity:
    return ResolvedIdentity(actor=actor)


@pytest.fixture
def server() -> FastMCP:
    return build_server(a_container())


def call(server: FastMCP, tool: str, **arguments: object) -> str:
    """One tool call, as a client makes it, with the text it answered."""

    async def _call() -> str:
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments)
            return "\n".join(block.text for block in result.content)

    return asyncio.run(_call())


def schemas(server: FastMCP) -> dict[str, dict[str, Any]]:
    """Every advertised tool's input schema, as a client sees it."""

    async def _schemas() -> dict[str, dict[str, Any]]:
        async with Client(server) as client:
            return {tool.name: tool.input_schema for tool in await client.list_tools()}

    return asyncio.run(_schemas())


# --------------------------------------------------------------------------
# 5.1 and 5.6 — the advertised surface, exactly
# --------------------------------------------------------------------------


def test_a_client_lists_exactly_the_expected_tools(server: FastMCP) -> None:
    """D6 — an exact match, so adding a tool fails the build until somebody explains it."""
    assert advertised(server) == tuple(sorted(TOOL_NAMES))


def test_the_expected_list_names_every_tool_this_change_ships() -> None:
    """The literal is the contract; a duplicate or a stray entry is a defect in it.

    `add-mcp-writes` D3 grows this by **exactly two** rather than escaping it —
    *"the exact-match tool-surface test from the read change grows by exactly
    two names, which is the point of it existing"* — so the eight reads are
    still counted on their own, and a ninth read or a third write fails here.
    """
    assert len(set(TOOL_NAMES)) == len(TOOL_NAMES)
    assert len(READ_TOOL_NAMES) == 8
    assert len(WRITE_TOOL_NAMES) == 2
    assert len(TOOL_NAMES) == 10


def test_no_tool_accepts_an_identity(server: FastMCP) -> None:
    """Identity comes from the credential. A caller cannot claim to be anybody."""
    for name, schema in schemas(server).items():
        named = set(schema.get("properties", {})) & set(IDENTITY_PARAMETERS)
        assert not named, f"{name} accepts identity parameters {sorted(named)}"


# --------------------------------------------------------------------------
# 5.7 — promotion is prohibited, not deferred
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tool", PROMOTION_TOOLS)
def test_no_promotion_tool_exists(server: FastMCP, tool: str) -> None:
    assert tool not in advertised(server)


def test_no_advertised_tool_writes_a_durable_rule(server: FastMCP) -> None:
    """Task 2.11 — the agent surface is read-only about the canon, by enumeration."""
    offending = {
        name: stem for name in advertised(server) for stem in DURABLE_WRITES if _names(name, stem)
    }

    assert not offending, (
        "`project.md`: promotion is never agent-callable, not even for an art "
        f"director's agent — and an agent never authors durable content: {offending}"
    )


def _names(tool: str, stem: str) -> bool:
    """Whether a tool name carries this stem at a word boundary.

    Boundaries rather than a bare substring, because `get_asset_spec` contains
    the letters of `set_spec` and is a *read* — the one `spec-lenses` exists for.
    A check that flagged it would be switched off within a week.
    """
    return f"_{stem}_" in f"_{tool}_"


def test_the_promote_use_case_refuses_an_agent_acting_for_an_art_director() -> None:
    """The other half of 2.11: absent from the surface *and* refused by the core.

    A tool list is a claim about what is advertised. This is the claim about what
    happens if somebody reaches the use case anyway — which is the only one that
    still holds the day a fifth surface is added.
    """
    director = Actor(
        id=ActorId("auth|dana"),
        display_name="Dana",
        roles=(Role.ART_DIRECTOR,),
        projects=(PROJECT,),
    )

    decision = decide(
        director,
        Operation.PROMOTE_TO_RULE,
        Subject(project=PROJECT, author=ActorId("auth|rafa")),
        via=AgentId("blender-agent"),
    )

    assert decision.refused
    assert REQUIRES_PERSON in decision.reason


def test_an_art_directors_agent_is_refused_promotion() -> None:
    """The role changes nothing: there is no such tool, for anybody."""
    server = build_server(a_container(actor_resolver=an_art_director()))

    assert advertised(server) == tuple(sorted(TOOL_NAMES))
    with pytest.raises(Exception, match="promote"):
        call(server, "promote_annotation", asset_id=ASSET_ID, annotation_id="a1")


def test_an_art_director_still_reads_the_specification() -> None:
    """The refusal is of promotion, not of the caller: reads keep working."""
    server = build_server(a_container(actor_resolver=an_art_director()))

    assert ASSET_ID in call(server, "get_asset_spec", asset_id=ASSET_ID)


# --------------------------------------------------------------------------
# 5.2 — prose: compact tables for listings, markdown for specifications
# --------------------------------------------------------------------------


def test_a_listing_is_a_compact_table_and_not_a_record_dump(server: FastMCP) -> None:
    listed = call(server, "list_assets")

    assert ASSET_ID in listed and CRATE_ID in listed
    assert all(f"| {column} |" in listed or column in listed for column in rendering.ASSET_COLUMNS)
    assert SILHOUETTE not in listed
    assert str(TRI_BUDGET) not in listed


def test_a_listing_narrows_by_status(server: FastMCP) -> None:
    listed = call(server, "list_assets", status=str(Status.MODELING))

    assert ASSET_ID in listed
    assert CRATE_ID not in listed


def test_where_is_names_the_recorded_and_the_unrecorded(server: FastMCP) -> None:
    located = call(server, "where_is", asset_id=ASSET_ID)

    assert ENGINE_PATH in located
    assert "not recorded" in located
    assert "rafa@cyberdyne.com" in located


def test_a_specification_is_the_markdown_briefing_a_person_would_read(server: FastMCP) -> None:
    briefing = call(server, "get_asset_spec", asset_id=ASSET_ID)

    assert f"# {ASSET_ID}" in briefing
    assert SILHOUETTE in briefing
    assert MUZZLE in briefing
    assert str(TRI_BUDGET) in briefing


def test_a_lensed_response_names_its_lens_and_says_a_full_specification_exists(
    server: FastMCP,
) -> None:
    """The notice is the use case's own sentence, emitted verbatim (D2)."""
    lensed = call(server, "get_asset_spec", asset_id=ASSET_ID, lens=Lens.MODELING.value)

    assert notice_for(Lens.MODELING, ASSET_ID) in lensed
    assert Lens.MODELING.value in lensed
    assert MUZZLE in lensed
    assert PALETTE not in lensed


def test_get_constraints_is_the_modeling_lens(server: FastMCP) -> None:
    """One projection, reached two ways — never a second rendering of the same fields."""
    assert call(server, "get_constraints", asset_id=ASSET_ID) == call(
        server, "get_asset_spec", asset_id=ASSET_ID, lens=Lens.MODELING.value
    )


def test_open_annotations_carry_the_open_threads_and_not_the_resolved_ones(
    server: FastMCP,
) -> None:
    threads = call(server, "get_open_annotations", asset_id=ASSET_ID)

    assert "the antenna costs 900 triangles" in threads
    assert "the hatch seam was closed" not in threads


def test_a_search_answers_with_a_table_and_finds_an_alias(server: FastMCP) -> None:
    found = call(server, "search_assets", term="drone")

    assert ASSET_ID in found
    assert SILHOUETTE not in found


# --------------------------------------------------------------------------
# 5.3 — validation reuses the single implementation
# --------------------------------------------------------------------------


def _cli_validation(container: Container) -> dict[str, Any]:
    result = CliRunner().invoke(build_app(container), ["validate", "--json", EXPORT])
    return json.loads(result.stdout)["results"][0]


def test_the_agent_and_the_command_line_report_the_same_violations() -> None:
    """One export over its budget, validated through both surfaces (5.3)."""
    container = a_container(triangles=OVER_BUDGET)
    reported = call(build_server(container), "validate_export", export=EXPORT)
    payload = _cli_validation(container)

    assert not payload["passed"]
    assert rendering.FAILING in reported
    assert payload["violations"]
    for violation in payload["violations"]:
        assert violation["rule_id"] in reported
        assert violation["severity"] in reported
        assert violation["subject"] in reported
    assert str(len(payload["passed_rules"])) in reported


def test_a_passing_export_agrees_too() -> None:
    container = a_container(triangles=9000)
    reported = call(build_server(container), "validate_export", export=EXPORT)

    assert _cli_validation(container)["passed"]
    assert rendering.PASSING in reported
    assert rendering.FAILING not in reported


# --------------------------------------------------------------------------
# 5.4 — failures are legible, and never end the session
# --------------------------------------------------------------------------


def test_an_unknown_asset_offers_the_closest_matches(server: FastMCP) -> None:
    answered = call(server, "where_is", asset_id=TYPO)

    assert TYPO in answered
    assert ASSET_ID in answered
    assert rendering.NEAREST in answered


def test_the_session_survives_a_recoverable_failure(server: FastMCP) -> None:
    """A typo may not cost an agent its session."""
    call(server, "where_is", asset_id=TYPO)
    call(server, "diff_spec", asset_id=ASSET_ID, revision="nothing-like-a-revision")
    call(server, "get_asset_spec", asset_id=ASSET_ID, lens=UNKNOWN_LENS)

    assert ASSET_ID in call(server, "where_is", asset_id=ASSET_ID)


def test_an_unknown_lens_is_refused_and_the_available_ones_are_named(server: FastMCP) -> None:
    refused = call(server, "get_asset_spec", asset_id=ASSET_ID, lens=UNKNOWN_LENS)

    for lens in Lens.values():
        assert lens in refused


def test_a_malformed_specification_is_reported_beside_the_readable_assets() -> None:
    listed = call(build_server(a_container(with_broken_spec=True)), "list_assets")

    assert ASSET_ID in listed and CRATE_ID in listed
    assert BROKEN_SPEC in listed
    assert rendering.UNREADABLE_HEADING in listed


def test_missing_history_degrades_into_a_message(server: FastMCP) -> None:
    answered = call(server, "diff_spec", asset_id=ASSET_ID, revision="HEAD~40")

    assert "HEAD~40" in answered
    assert ASSET_ID in answered
