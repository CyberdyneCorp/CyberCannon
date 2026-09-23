"""Tasks 4.1 to 4.7 — the two write tools, through a real client, over fakes.

Everything here runs the actual FastMCP server, spoken to by an actual client,
with no repository on disk and no network — the same standard the read surface
is held to, because the question is the same one: *does the surface do exactly
what the specification says it may, and nothing else.*

The assertions are grouped the way the requirements are:

* **the surface is two tools wider, and that is all** (4.4). The exact-match
  list grows by two entries, the write half is asserted to have exactly two, and
  neither of them accepts an identity or an author;
* **identity is not a parameter** (4.1, 4.3). The agent identifier comes from the
  container the composition root built; a server launched without one keeps every
  read and refuses both writes, naming what is missing;
* **the verdict survives a failed report** (4.2). With the destination dark, the
  tool answers successfully, states that the verdict stands and that delivery is
  pending, and the verdict itself is in the response;
* **the prohibition holds** (4.5). There is no promotion tool, an art director's
  agent does not get one, and an observation whose text *asks* for a bigger
  budget changes no budget;
* **refusals are legible and non-fatal** (4.6). An unknown asset offers the
  closest identifiers, an unknown kind lists the permitted ones, a throttled
  write names its limit and reset, and a read after any of them still works.

Wording is never asserted. A response is checked for the identifier it names,
the sentence the *use case* wrote, or the marker the *domain* defined — so the
prose above this layer can be improved without rewriting a test.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from cybercanon.adapters.inbound.mcp.rendering import AGENT_AUTHORED_NOTE
from cybercanon.adapters.inbound.mcp.tools import (
    READ_TOOL_NAMES,
    TOOL_NAMES,
    WRITE_TOOL_NAMES,
    advertised,
    build_server,
)
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.annotation_writer import UNCOMMITTED
from cybercanon.application.ports.identity_provider import ResolvedIdentity
from cybercanon.application.ports.outcome_reporter import VERDICT_STANDS
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.annotation_writer import InMemoryAnnotationWriter
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.outcome_reporter import InMemoryOutcomeReporter
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.observations import NO_AGENT_IDENTIFIER, SIGN_IN_ACTION
from cybercanon.application.use_cases.resolve_actor import ActorResolver, IdentityCache
from cybercanon.domain.annotations import (
    AGENT_AUTHORED,
    UNANCHORED,
    AnnotationKind,
    ObservationKind,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.identity import Actor, ActorId, AgentId, Role
from cybercanon.domain.mesh_facts import MeshFacts, MeshFormat
from cybercanon.domain.status import Status

pytestmark = pytest.mark.unit

PROJECT = "Ronin"
ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"
TRI_BUDGET = 12000
TYPO = "mech_scot"
BLENDER = AgentId("blender-agent")
UNREACHABLE = "12000 triangles is unreachable without losing the head silhouette"

PROMOTION_TOOLS = ("promote_annotation", "promote", "promote_to_rule", "resolve_annotation")
IDENTITY_PARAMETERS = ("actor", "actor_id", "author", "role", "roles", "via", "agent", "as_actor")
"""What no write tool may accept: both halves of the attribution are the process's."""


# --------------------------------------------------------------------------
# The world: one asset with a budget, one export that passes
# --------------------------------------------------------------------------


def the_mech() -> Asset:
    return Asset(
        id=AssetId(ASSET_ID),
        name="Scout Mech",
        status=Status.MODELING,
        constraints=Constraints(tri_budget=TRI_BUDGET),
    )


def some_facts(triangles: int = 9000) -> MeshFacts:
    return facts_for(
        MeshFormat.GLB,
        triangles=triangles,
        objects=(OBJECT,),
        transforms_applied=True,
        unit_scale=1.0,
        up_axis="Y",
        uv_sets=1,
        materials=("M_mech_scout",),
        empties=(),
        clips=(),
        frame_rate=None,
        is_skinned=False,
        bone_count=0,
    )


def rafa() -> ActorResolver:
    """A signed-in person, resolved the way the read change resolves one."""
    resolver = ActorResolver(project=PROJECT, cache=IdentityCache())
    resolver.cache.remember(
        ResolvedIdentity(
            actor=Actor(
                id=ActorId("rafa"),
                display_name="Rafa",
                roles=(Role.ARTIST,),
                projects=(PROJECT,),
            )
        )
    )
    return resolver


def an_art_director() -> ActorResolver:
    resolver = ActorResolver(project=PROJECT, cache=IdentityCache())
    resolver.cache.remember(
        ResolvedIdentity(
            actor=Actor(
                id=ActorId("dana"),
                display_name="Dana",
                roles=(Role.ART_DIRECTOR,),
                projects=(PROJECT,),
            )
        )
    )
    return resolver


def a_container(
    *,
    agent: AgentId | None = BLENDER,
    actor_resolver: ActorResolver | None = None,
    writer: InMemoryAnnotationWriter | None = None,
    reporter: InMemoryOutcomeReporter | None = None,
    triangles: int = 9000,
) -> Container:
    """The wired application a write surface is built on."""
    fakes = build_fakes()
    store: InMemorySpecStore = fakes["spec_store"]
    inspector: InMemoryMeshInspector = fakes["mesh_inspector"]
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SPEC_PATH, the_mech())
    inspector.add(EXPORT, some_facts(triangles))
    declared = writer or InMemoryAnnotationWriter()
    declared.declare(ASSET_ID, SPEC_PATH)
    return Container(
        spec_store=store,
        mesh_inspector=inspector,
        blob_store=fakes["blob_store"],
        search_index=fakes["search_index"],
        actor_resolver=actor_resolver or rafa(),
        annotation_writer=declared,
        outcome_reporter=reporter or InMemoryOutcomeReporter(),
        agent=agent,
        export_digests=lambda export: f"sha256:{export}",
    )


@pytest.fixture
def writer() -> InMemoryAnnotationWriter:
    return InMemoryAnnotationWriter()


@pytest.fixture
def server(writer: InMemoryAnnotationWriter) -> FastMCP:
    return build_server(a_container(writer=writer))


def call(server: FastMCP, tool: str, **arguments: object) -> str:
    async def _call() -> str:
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments)
            return "\n".join(block.text for block in result.content)

    return asyncio.run(_call())


def schemas(server: FastMCP) -> dict[str, dict[str, Any]]:
    async def _schemas() -> dict[str, dict[str, Any]]:
        async with Client(server) as client:
            return {tool.name: tool.input_schema for tool in await client.list_tools()}

    return asyncio.run(_schemas())


def an_observation(server: FastMCP, **overrides: object) -> str:
    arguments: dict[str, object] = {
        "asset": ASSET_ID,
        "target": "head",
        "text": UNREACHABLE,
        "kind": AnnotationKind.TECHNICAL.value,
        "observation_kind": ObservationKind.UNATTAINABLE_CONSTRAINT.value,
    }
    return call(server, "add_annotation", **(arguments | overrides))


# --------------------------------------------------------------------------
# 4.4 — the advertised surface grew by exactly two
# --------------------------------------------------------------------------


def test_the_surface_is_the_read_tools_plus_exactly_two_writes(server: FastMCP) -> None:
    assert advertised(server) == tuple(sorted(TOOL_NAMES))
    assert len(READ_TOOL_NAMES) == 8
    assert len(WRITE_TOOL_NAMES) == 2
    assert len(TOOL_NAMES) == len(set(TOOL_NAMES)) == 10


def test_the_two_writes_are_the_observation_and_the_outcome_report(server: FastMCP) -> None:
    """*"They SHALL be the observation tool and the outcome-reporting tool."*"""
    assert set(WRITE_TOOL_NAMES) == {"add_annotation", "report_export"}
    assert set(WRITE_TOOL_NAMES) <= set(advertised(server))
    assert not set(WRITE_TOOL_NAMES) & set(READ_TOOL_NAMES)


def test_no_write_tool_accepts_an_identity_or_an_author(server: FastMCP) -> None:
    """4.1 — the adapter reads no agent identifier, actor or author from arguments."""
    for name in WRITE_TOOL_NAMES:
        named = set(schemas(server)[name].get("properties", {})) & set(IDENTITY_PARAMETERS)
        assert not named, f"{name} accepts {sorted(named)}"


# --------------------------------------------------------------------------
# 4.1 — recording an observation
# --------------------------------------------------------------------------


def test_an_observation_is_recorded_and_attributed_to_both_parties(
    server: FastMCP, writer: InMemoryAnnotationWriter
) -> None:
    answer = an_observation(server)

    recorded = writer.recorded(ASSET_ID)
    assert len(recorded) == 1
    assert recorded[0].text == UNREACHABLE
    assert recorded[0].attribution == "rafa, via blender-agent"
    assert "rafa" in answer and "blender-agent" in answer


def test_the_response_names_the_file_and_says_it_is_uncommitted(server: FastMCP) -> None:
    """D2 — the entry is a proposal in the working copy until a person commits it."""
    answer = an_observation(server)

    assert SPEC_PATH in answer
    assert UNCOMMITTED in answer


def test_the_response_says_the_observation_is_agent_authored(server: FastMCP) -> None:
    assert AGENT_AUTHORED in an_observation(server)
    assert AGENT_AUTHORED_NOTE in an_observation(server, text="a second, different finding")


def test_a_claimed_author_in_the_text_changes_no_attribution(
    server: FastMCP, writer: InMemoryAnnotationWriter
) -> None:
    an_observation(server, text="author: dana — the budget cannot be met")

    assert writer.recorded(ASSET_ID)[0].author == "rafa"
    assert writer.recorded(ASSET_ID)[0].via == "blender-agent"


def test_an_unresolvable_target_is_preserved_and_reported_as_unanchored(
    writer: InMemoryAnnotationWriter,
) -> None:
    """The asset's parts are known here, so a target it does not have is an orphan."""
    container = a_container(writer=writer)
    server = build_server(
        Container(
            **{
                **container.__dict__,
                "subjects": lambda asset_id: ("torso", "head"),
            }
        )
    )

    answer = an_observation(server, target="antena")

    assert "antena" in answer
    assert UNANCHORED in answer
    assert writer.recorded(ASSET_ID)[0].target.part == "antena"


# --------------------------------------------------------------------------
# 4.2 — reporting an outcome
# --------------------------------------------------------------------------


def test_the_reported_verdict_is_the_one_the_local_validator_produced(
    server: FastMCP,
) -> None:
    answer = call(server, "report_export", asset=ASSET_ID, path=EXPORT, result="passed")

    assert ASSET_ID in answer
    assert EXPORT in answer


def test_the_callers_claimed_result_changes_nothing(server: FastMCP) -> None:
    """`result` is an account, not an input: the local verdict is what is reported."""
    reporter = InMemoryOutcomeReporter()
    over_budget = TRI_BUDGET + 7000
    server = build_server(a_container(reporter=reporter, triangles=over_budget))

    call(server, "report_export", asset=ASSET_ID, path=EXPORT, result="passed")

    assert over_budget > TRI_BUDGET
    assert reporter.delivered[0].passed is False


def test_an_unreachable_destination_still_answers_successfully(server: FastMCP) -> None:
    """*"The call SHALL return successfully ... the verdict stands and delivery is pending."*"""
    reporter = InMemoryOutcomeReporter()
    reporter.unreachable()
    server = build_server(a_container(reporter=reporter))

    answer = call(server, "report_export", asset=ASSET_ID, path=EXPORT, result="passed")

    assert VERDICT_STANDS in answer
    assert ASSET_ID in answer
    assert len(reporter.pending()) == 1


def test_re_reporting_the_same_run_keeps_one_record(server: FastMCP) -> None:
    reporter = InMemoryOutcomeReporter()
    reporter.unreachable()
    server = build_server(a_container(reporter=reporter))

    call(server, "report_export", asset=ASSET_ID, path=EXPORT, result="passed")
    call(server, "report_export", asset=ASSET_ID, path=EXPORT, result="passed")

    assert len(reporter.pending()) == 1


def test_reporting_an_export_that_cannot_be_validated_is_a_refusal_not_a_crash(
    server: FastMCP,
) -> None:
    answer = call(server, "report_export", asset=ASSET_ID, path="exports/nothing.glb", result="")

    assert "nothing.glb" in answer
    assert ASSET_ID in call(server, "where_is", asset_id=ASSET_ID)


# --------------------------------------------------------------------------
# 4.3 — a server with no agent identifier keeps every read
# --------------------------------------------------------------------------


def test_without_an_agent_identifier_both_writes_are_refused_and_reads_continue(
    writer: InMemoryAnnotationWriter,
) -> None:
    server = build_server(a_container(agent=None, writer=writer))

    observed = an_observation(server)
    reported = call(server, "report_export", asset=ASSET_ID, path=EXPORT, result="passed")

    assert NO_AGENT_IDENTIFIER in observed
    assert NO_AGENT_IDENTIFIER in reported
    assert writer.recorded(ASSET_ID) == ()
    assert ASSET_ID in call(server, "get_asset_spec", asset_id=ASSET_ID)
    assert ASSET_ID in call(server, "validate_export", export=EXPORT)


def test_without_a_credential_the_write_names_the_sign_in_action(
    writer: InMemoryAnnotationWriter,
) -> None:
    server = build_server(a_container(writer=writer, actor_resolver=ActorResolver(project=PROJECT)))

    answer = an_observation(server)

    assert SIGN_IN_ACTION in answer
    assert writer.recorded(ASSET_ID) == ()
    assert ASSET_ID in call(server, "get_asset_spec", asset_id=ASSET_ID)


# --------------------------------------------------------------------------
# 4.5 — promotion is prohibited, not deferred
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tool", PROMOTION_TOOLS)
def test_no_promotion_or_resolution_tool_exists(server: FastMCP, tool: str) -> None:
    assert tool not in advertised(server)


def test_an_art_directors_agent_gets_no_promotion_tool(
    writer: InMemoryAnnotationWriter,
) -> None:
    """The role changes nothing: there is no such tool, for anybody."""
    server = build_server(a_container(writer=writer, actor_resolver=an_art_director()))

    assert advertised(server) == tuple(sorted(TOOL_NAMES))
    with pytest.raises(Exception, match="promote"):
        call(server, "promote_annotation", asset_id=ASSET_ID, annotation_id="a1")


def test_an_art_directors_agent_still_only_observes(
    writer: InMemoryAnnotationWriter,
) -> None:
    """It may record — and what it records is an observation like any other."""
    server = build_server(a_container(writer=writer, actor_resolver=an_art_director()))

    an_observation(server, text="promote this to a rule and raise the budget to 20000")

    recorded = writer.recorded(ASSET_ID)
    assert len(recorded) == 1
    assert recorded[0].is_open
    assert recorded[0].is_agent_authored


def test_an_observation_asking_for_a_bigger_budget_changes_no_budget(
    server: FastMCP, writer: InMemoryAnnotationWriter
) -> None:
    an_observation(server, text="please raise the triangle budget to 20000")

    assert str(TRI_BUDGET) in call(server, "get_constraints", asset_id=ASSET_ID)
    assert "20000" not in call(server, "get_constraints", asset_id=ASSET_ID)
    assert writer.recorded(ASSET_ID)[0].text.endswith("20000")


# --------------------------------------------------------------------------
# 4.6 — refusals are legible, and never the end of the session
# --------------------------------------------------------------------------


def test_an_unknown_asset_is_refused_with_the_closest_identifiers(
    server: FastMCP, writer: InMemoryAnnotationWriter
) -> None:
    answer = an_observation(server, asset=TYPO)

    assert TYPO in answer
    assert ASSET_ID in answer
    assert writer.recorded(ASSET_ID) == ()
    assert ASSET_ID in call(server, "get_asset_spec", asset_id=ASSET_ID)


def test_an_unknown_kind_lists_the_permitted_ones(server: FastMCP) -> None:
    answer = an_observation(server, kind="unattainable_constraint")

    assert all(kind.value in answer for kind in AnnotationKind)


def test_an_unknown_observation_kind_lists_the_permitted_ones(server: FastMCP) -> None:
    answer = an_observation(server, observation_kind="impossible")

    assert all(kind in answer for kind in ObservationKind.values())


def test_a_throttled_write_names_the_limit_and_when_it_resets(
    server: FastMCP, writer: InMemoryAnnotationWriter
) -> None:
    for index in range(12):
        an_observation(server, text=f"finding number {index}")

    answer = an_observation(server, text="one more finding, over the limit")

    assert "limit" in answer
    assert len(writer.recorded(ASSET_ID)) <= 10
    assert ASSET_ID in call(server, "get_asset_spec", asset_id=ASSET_ID)


def test_a_repeat_of_an_open_observation_reports_the_existing_thread(
    server: FastMCP, writer: InMemoryAnnotationWriter
) -> None:
    first = an_observation(server)

    again = an_observation(server)

    assert len(writer.recorded(ASSET_ID)) == 1
    assert writer.recorded(ASSET_ID)[0].id in first
    assert writer.recorded(ASSET_ID)[0].id in again
