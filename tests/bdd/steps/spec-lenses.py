"""Step definitions for `spec-lenses` — one compilation, four projections.

Group 3 of `add-mcp-read-server` implements `compile_spec_for_lens` as a
**projection over the single compiled specification** (D2): the lens removes
content from the document the CLI's `canon compile` produces, so a field two
lenses present is byte-identical in both because there is no second renderer
that could disagree.

The other half is ordering (D3). Authorization is evaluated before the lens is
looked at, which is why the refusal a caller receives is the same sentence
whatever lens it sent — and why the scenarios below can assert that property by
comparing refusals rather than by inspecting code.

Every assertion is on content: which socket a response lists, whether the
palette is present, whether two responses agree. Nothing here depends on
wording, so the MCP renderer can be improved without rewriting a scenario.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.resolve_actor import (
    ActorResolver,
    IdentitySource,
    Resolution,
)
from cybercanon.application.use_cases.spec_lens import (
    Lens,
    ReadRefused,
    UnknownLens,
    compile_spec_for_lens,
)
from cybercanon.domain.annotations import Anchor3D, Annotation, AnnotationKind
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig, Texture
from cybercanon.domain.design import Design, Socket, State
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.status import Status

PROJECT = "cyberdyne-game"
OTHER_PROJECT = "another-game"
SPEC_PATH = "characters/mech_scout/asset.yaml"

MUZZLE = "SOCKET_muzzle_l"
PALETTE = "the palette holds to three desaturated greens"
RESOLVED_TEXT = "the hatch seam was closed in the second pass"
UNKNOWN_LENS = "engineering"

ANTENNA = Anchor3D(part="antenna")


def an_annotation(identifier: str, kind: AnnotationKind, text: str) -> Annotation:
    return Annotation(
        id=identifier, author="rafa@cyberdyne.com", kind=kind, text=text, target=ANTENNA
    )


OPEN_NOTES = (
    an_annotation("a1", AnnotationKind.ART_DIRECTION, "the antenna reads as a weapon"),
    an_annotation("a2", AnnotationKind.TECHNICAL, "the antenna costs 900 triangles"),
    an_annotation("a3", AnnotationKind.DESIGN, "the antenna hides the muzzle socket"),
)
RESOLVED_NOTES = tuple(
    an_annotation(f"r{index}", kind, f"{RESOLVED_TEXT} ({kind})").resolved()
    for index, kind in enumerate(AnnotationKind)
)

SCOUT = Asset(
    id=AssetId("mech_scout"),
    name="Scout Mech",
    status=Status.MODELING,
    owner_art="rafa@cyberdyne.com",
    owner_design="ana@cyberdyne.com",
    owner_code="joe@cyberdyne.com",
    concept=Concept(views=("front.png",), silhouette_rules=(PALETTE,)),
    design=Design(
        role="scout",
        read_distance_m=8.0,
        silhouette_priority="high",
        scale_ref="human",
        states=(State(name="idle", clip="A_idle"),),
        sockets=(Socket(name=MUZZLE, purpose="muzzle flash"),),
    ),
    constraints=Constraints(
        tri_budget=12000,
        up_axis="Z",
        unit_scale=1.0,
        naming="SM_{asset}",
        texture=Texture(size=2048, sets=2, channels=("BC", "N")),
        rig=Rig(skeleton="humanoid", max_bones=80),
        animation=AnimationDefaults(clip_naming="A_{asset}_{state}", frame_rate=30),
    ),
    links=Links(source="art/mech_scout.blend", engine="/Game/Chars/MechScout"),
    annotations=(*OPEN_NOTES, *RESOLVED_NOTES),
)


@pytest.fixture
def lenses() -> dict[str, Any]:
    """What this scenario set up, and what each lens answered."""
    return {}


def a_store(asset: Asset = SCOUT) -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SPEC_PATH, asset)
    return store


def an_entitled_caller() -> Resolution:
    """No credential configured: the local actor reads the project it stands in (D4)."""
    return ActorResolver(project=PROJECT).resolve()


def a_caller(*roles: Role, projects: tuple[str, ...] = (PROJECT,)) -> Resolution:
    return Resolution(
        actor=Actor(
            id=ActorId("auth|joe"),
            display_name="Joe",
            roles=roles,
            projects=projects,
        ),
        source=IdentitySource.PROVIDER,
        verified=True,
    )


def prepared(lenses: dict[str, Any]) -> dict[str, Any]:
    """The default world: this asset, and a caller entitled to read it."""
    lenses.setdefault("store", a_store())
    lenses.setdefault("caller", an_entitled_caller())
    return lenses


def read(lenses: dict[str, Any], lens: str | None) -> Any:
    return compile_spec_for_lens(
        SPEC_PATH,
        lens,
        spec_store=lenses["store"],
        resolution=lenses["caller"],
        project=PROJECT,
    )


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-mcp-read-server/spec-lenses.feature", "Modeling lens returns constraints"
)
def test_modeling_lens_returns_constraints() -> None: ...


@scenario("../features/add-mcp-read-server/spec-lenses.feature", "No lens returns everything")
def test_no_lens_returns_everything() -> None: ...


@scenario("../features/add-mcp-read-server/spec-lenses.feature", "Unknown lens is rejected clearly")
def test_unknown_lens_is_rejected_clearly() -> None: ...


@scenario(
    "../features/add-mcp-read-server/spec-lenses.feature",
    "Lens cannot reveal an inaccessible asset",
)
def test_lens_cannot_reveal_an_inaccessible_asset() -> None: ...


@scenario("../features/add-mcp-read-server/spec-lenses.feature", "Lens choice is unrestricted")
def test_lens_choice_is_unrestricted() -> None: ...


@scenario(
    "../features/add-mcp-read-server/spec-lenses.feature", "Sockets surfaced before modelling"
)
def test_sockets_surfaced_before_modelling() -> None: ...


@scenario(
    "../features/add-mcp-read-server/spec-lenses.feature",
    "Shared field is identical across lenses",
)
def test_shared_field_is_identical_across_lenses() -> None: ...


@scenario(
    "../features/add-mcp-read-server/spec-lenses.feature",
    "Resolved annotation absent under every lens",
)
def test_resolved_annotation_absent_under_every_lens() -> None: ...


# --------------------------------------------------------------------------
# The four lenses
# --------------------------------------------------------------------------


@when("an asset's specification is read with the `modeling` lens")
def _read_with_the_modeling_lens(lenses: dict[str, Any]) -> None:
    lenses["response"] = read(prepared(lenses), "modeling")


@then("the response SHALL contain the effective constraints and required sockets")
def _the_response_carries_the_constraints(lenses: dict[str, Any]) -> None:
    body = lenses["response"].body

    assert "12000" in body, "the effective triangle budget"
    assert "humanoid" in body, "the effective rig"
    assert MUZZLE in body


@then("SHALL NOT contain the concept palette")
def _the_response_omits_the_palette(lenses: dict[str, Any]) -> None:
    body = lenses["response"].body

    assert PALETTE not in body
    assert "front.png" not in body, "no part of the concept block reaches modelling"


@when("an asset's specification is read with no lens")
def _read_with_no_lens(lenses: dict[str, Any]) -> None:
    lenses["response"] = read(prepared(lenses), None)


@then("the response SHALL contain all authored blocks")
def _the_response_carries_every_block(lenses: dict[str, Any]) -> None:
    body = lenses["response"].body
    compiled = ran(compile_spec(SPEC_PATH, spec_store=lenses["store"]))

    assert body == compiled.text, "omitting the lens is the whole compilation"
    for content in (PALETTE, MUZZLE, "12000", "/Game/Chars/MechScout", "scout"):
        assert content in body


@when("a specification is read with a lens outside the defined set")
def _read_with_an_unknown_lens(lenses: dict[str, Any]) -> None:
    with pytest.raises(UnknownLens) as failure:
        read(prepared(lenses), UNKNOWN_LENS)
    lenses["refusal"] = failure.value


@then("the system SHALL refuse and name the available lenses")
def _the_refusal_names_the_lenses(lenses: dict[str, Any]) -> None:
    message = lenses["refusal"].message

    assert UNKNOWN_LENS in message
    for name in Lens.values():
        assert name in message


# --------------------------------------------------------------------------
# A lens narrows presentation and never widens access (D3)
# --------------------------------------------------------------------------


@given("a caller not entitled to read a given project")
def _an_unentitled_caller(lenses: dict[str, Any]) -> None:
    lenses["store"] = a_store()
    lenses["caller"] = a_caller(Role.ENGINEER, projects=(OTHER_PROJECT,))


@when("it reads an asset of that project under any lens")
def _it_reads_under_every_lens(lenses: dict[str, Any]) -> None:
    refusals = {}
    for lens in (None, *Lens.values()):
        with pytest.raises(ReadRefused) as failure:
            read(lenses, lens)
        refusals[lens] = failure.value.message
    lenses["refusals"] = refusals


@then("the request SHALL be refused identically for every lens")
def _every_lens_is_refused_identically(lenses: dict[str, Any]) -> None:
    refusals = lenses["refusals"]

    assert len(refusals) == len(Lens) + 1, "no lens was skipped"
    assert len(set(refusals.values())) == 1, (
        "authorization is evaluated before the lens, so the lens cannot change the answer"
    )
    assert all(lens is None or lens not in message for lens, message in refusals.items())


@given("a caller acting as an actor whose role is engineer")
def _an_engineer(lenses: dict[str, Any]) -> None:
    lenses["store"] = a_store()
    lenses["caller"] = a_caller(Role.ENGINEER)


@when("it reads a specification with the `art` lens")
def _it_reads_with_the_art_lens(lenses: dict[str, Any]) -> None:
    lenses["response"] = read(lenses, "art")


@then("the request SHALL be served")
def _the_request_was_served(lenses: dict[str, Any]) -> None:
    response = lenses["response"]

    assert response.is_lensed
    assert response.lens is Lens.ART
    assert PALETTE in response.body, "a lens carries no authority, so any caller may pick one"


# --------------------------------------------------------------------------
# Sockets, shared fields, and closed annotations
# --------------------------------------------------------------------------


@given("an asset whose design declares `SOCKET_muzzle_l`")
def _an_asset_declaring_a_socket(lenses: dict[str, Any]) -> None:
    prepared(lenses)
    design = SCOUT.design
    assert design is not None and MUZZLE in design.socket_names


@when("its specification is read with the `modeling` lens")
def _its_specification_is_read_for_modelling(lenses: dict[str, Any]) -> None:
    lenses["response"] = read(prepared(lenses), "modeling")


@then("the response SHALL list `SOCKET_muzzle_l` as required in the export")
def _the_socket_is_listed_as_required(lenses: dict[str, Any]) -> None:
    lines = [line for line in lenses["response"].lines if MUZZLE in line]

    assert lines, "the modelling agent learns the socket before modelling"
    context = lenses["response"].body
    assert "Required attachment points" in context
    assert "rejected without them" in context, "it is stated as an export requirement"


@given("a field presented by both the `design` and `modeling` lenses")
def _a_field_in_two_lenses(lenses: dict[str, Any]) -> None:
    prepared(lenses)
    lenses["shared_field"] = MUZZLE


@when("the specification is read under each")
def _read_under_each_of_the_two(lenses: dict[str, Any]) -> None:
    lenses["responses"] = {lens: read(lenses, lens) for lens in ("design", "modeling")}


@then("that field's content SHALL be identical in both responses")
def _the_shared_field_is_identical(lenses: dict[str, Any]) -> None:
    field = lenses["shared_field"]
    rendered = {
        lens: [line for line in response.lines if field in line]
        for lens, response in lenses["responses"].items()
    }

    assert rendered["design"], "the design lens presents the sockets"
    assert rendered["design"] == rendered["modeling"], (
        "both lenses project the same compilation, so the field cannot differ"
    )


@given("an asset with resolved annotations of every kind")
def _an_asset_with_resolved_threads(lenses: dict[str, Any]) -> None:
    prepared(lenses)
    assert len(RESOLVED_NOTES) == len(AnnotationKind)


@when("it is read under each lens in turn")
def _read_under_every_lens(lenses: dict[str, Any]) -> None:
    lenses["responses"] = {lens.value: read(lenses, lens.value) for lens in Lens}


@then("no resolved annotation SHALL appear in any response")
def _no_resolved_annotation_appears(lenses: dict[str, Any]) -> None:
    for lens, response in lenses["responses"].items():
        assert RESOLVED_TEXT not in response.body, f"the {lens} lens carried a closed thread"
    assert any(OPEN_NOTES[2].text in response.body for response in lenses["responses"].values()), (
        "open annotations are still carried, so the check above is not vacuous"
    )
