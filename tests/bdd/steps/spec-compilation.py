"""Step definitions for `spec-compilation` — the compiled briefing.

`compile_spec` is a pure function of the specification and the project
configuration, so every scenario here runs with no file on disk: the store hands
over the asset, the use case renders the briefing, and the assertions are about
what the text does and does not contain.

One scenario stays pending. "Compiled file edited by hand" is about a *writer*
overwriting an existing `art-spec.md`, and the writer lives in the CLI (group
6); the use case cannot express it, because the compiled file was never one of
its inputs — which is the very property that scenario is checking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when
from typer.testing import CliRunner

from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.compile_spec import compile_project_briefing, compile_spec
from cybercanon.domain.annotations import Anchor3D, Annotation, AnnotationKind
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.status import Status

ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
PART = "SM_MechScout_Shoulder_L"

OPEN_TEXT = "the pauldron reads as a backpack at 25 m"
RESOLVED_TEXTS = (
    "the left foot clips the ground in the idle pose",
    "the antenna is one segment too short",
    "the decals sit on the wrong shoulder",
)
PROMOTED_TEXT = "the silhouette must read as a scout, never as a brawler"


@pytest.fixture
def compilation() -> dict[str, Any]:
    """The store the scenario seeded, and whatever compiling produced."""
    return {"spec_store": InMemorySpecStore()}


def an_annotation(identifier: str, text: str) -> Annotation:
    return Annotation(
        id=identifier,
        author="rafa",
        kind=AnnotationKind.ART_DIRECTION,
        text=text,
        target=Anchor3D(part=PART),
    )


def an_asset(**blocks: Any) -> Asset:
    return Asset(
        id=AssetId(ASSET_ID),
        name="Scout Mech",
        status=Status.MODELING,
        owner_art="rafa",
        owner_design="dani",
        owner_code="leo",
        **blocks,
    )


def _seed(compilation: dict[str, Any], asset: Asset, project: ProjectConfig | None = None) -> None:
    compilation["spec_store"].add(SPEC_PATH, asset)
    if project is not None:
        compilation["spec_store"].set_project(project)


def _compile(compilation: dict[str, Any]) -> str:
    return compile_spec(SPEC_PATH, spec_store=compilation["spec_store"]).text


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Resolved annotation is excluded",
)
def test_resolved_annotation_is_excluded() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Promoted content appears as a rule, not as history",
)
def test_promoted_content_appears_as_a_rule() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Output does not grow with usage",
)
def test_output_does_not_grow_with_usage() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Read cold",
)
def test_read_cold() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Defaults merged into output",
)
def test_defaults_merged_into_output() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Repeated compilation is identical",
)
def test_repeated_compilation_is_identical() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Compiles while offline",
)
def test_compiles_while_offline() -> None: ...


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Project briefing excludes per-asset content",
)
def test_project_briefing_excludes_per_asset_content() -> None: ...


# --------------------------------------------------------------------------
# GIVEN
# --------------------------------------------------------------------------


@given("an asset with one open annotation and three resolved annotations")
def _one_open_three_resolved(compilation: dict[str, Any]) -> None:
    _seed(
        compilation,
        an_asset(
            annotations=(
                an_annotation("a1", OPEN_TEXT),
                *(
                    an_annotation(f"r{index}", text).resolved()
                    for index, text in enumerate(RESOLVED_TEXTS)
                ),
            )
        ),
    )


@given("an annotation that was promoted into the asset's rules")
def _a_promoted_annotation(compilation: dict[str, Any]) -> None:
    """Promotion moved the content into `silhouette_rules` and retired the thread."""
    _seed(
        compilation,
        an_asset(
            concept=Concept(silhouette_rules=(PROMOTED_TEXT,)),
            annotations=(an_annotation("a1", PROMOTED_TEXT).promoted(),),
        ),
    )


@given("an asset that accumulates and then resolves many annotations over time")
def _many_resolved_over_time(compilation: dict[str, Any]) -> None:
    compilation["before"] = an_asset(annotations=(an_annotation("a1", OPEN_TEXT),))
    compilation["after"] = an_asset(
        annotations=(
            an_annotation("a1", OPEN_TEXT),
            *(an_annotation(f"r{index}", f"issue {index}").resolved() for index in range(20)),
        )
    )


@given("a project default `up_axis: Z` and an asset that declares no up axis")
def _a_project_default_up_axis(compilation: dict[str, Any]) -> None:
    _seed(
        compilation,
        an_asset(constraints=Constraints(tri_budget=12000)),
        ProjectConfig(name="Ironwood", defaults=Constraints(up_axis="Z")),
    )


@given("no network connectivity")
def _no_network(compilation: dict[str, Any]) -> None:
    """Every network-capable port raising. Compilation must not notice."""
    blobs = InMemoryBlobStore()
    blobs.fail_with(ConnectionError("the network is unreachable"))
    compilation["blob_store"] = blobs
    _seed(compilation, an_asset(constraints=Constraints(tri_budget=12000)))


# --------------------------------------------------------------------------
# WHEN
# --------------------------------------------------------------------------


@when("its specification is compiled")
@when("the specification is compiled")
@when("a specification is compiled")
def _the_specification_is_compiled(compilation: dict[str, Any]) -> None:
    compilation["text"] = _compile(compilation)


@when("its specification is compiled after each resolution")
def _compiled_after_each_resolution(compilation: dict[str, Any]) -> None:
    compilation["texts"] = tuple(
        _one_off(compilation, compilation[stage]) for stage in ("before", "after")
    )


@when("the compiled output is read with no other context")
def _read_with_no_other_context(compilation: dict[str, Any]) -> None:
    _seed(
        compilation,
        an_asset(
            concept=Concept(silhouette_rules=("reads as a scout at 25 m",)),
            constraints=Constraints(tri_budget=12000),
        ),
    )
    compilation["text"] = _compile(compilation)


@when("the same unchanged specification is compiled twice")
def _compiled_twice(compilation: dict[str, Any]) -> None:
    _seed(
        compilation,
        an_asset(
            concept=Concept(views=("front", "side")),
            constraints=Constraints(tri_budget=12000, lods=(12000, 4000)),
            annotations=(an_annotation("a1", OPEN_TEXT),),
        ),
    )
    compilation["texts"] = (_compile(compilation), _compile(compilation))


@when("the project-level briefing is compiled")
def _the_project_briefing_is_compiled(compilation: dict[str, Any]) -> None:
    _seed(
        compilation,
        an_asset(annotations=(an_annotation("a1", OPEN_TEXT),)),
        ProjectConfig(
            name="Ironwood",
            defaults=Constraints(up_axis="Z", unit_scale=1.0),
            golden_rules=("Every design field constrains art, constrains code, or is checkable.",),
        ),
    )
    compilation["text"] = compile_project_briefing("", spec_store=compilation["spec_store"]).text


def _one_off(compilation: dict[str, Any], asset: Asset) -> str:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, asset)
    return compile_spec(SPEC_PATH, spec_store=store).text


# --------------------------------------------------------------------------
# THEN
# --------------------------------------------------------------------------


@then("the output SHALL contain the open annotation")
def _the_open_annotation_is_there(compilation: dict[str, Any]) -> None:
    assert OPEN_TEXT in compilation["text"]


@then("the output SHALL NOT contain any of the resolved annotations")
def _no_resolved_annotation_is_there(compilation: dict[str, Any]) -> None:
    assert all(text not in compilation["text"] for text in RESOLVED_TEXTS)


@then("the promoted content SHALL appear among the rules")
def _the_promoted_content_is_a_rule(compilation: dict[str, Any]) -> None:
    rules, _ = compilation["text"].split("## Open issues")
    assert PROMOTED_TEXT in rules


@then("the original annotation SHALL NOT appear as an open item")
def _the_promoted_thread_is_not_an_open_item(compilation: dict[str, Any]) -> None:
    _, issues = compilation["text"].split("## Open issues")
    assert PROMOTED_TEXT not in issues


@then("the compiled output SHALL NOT grow as a result of resolved annotations")
def _the_output_did_not_grow(compilation: dict[str, Any]) -> None:
    before, after = compilation["texts"]
    assert after == before


@then(
    "it SHALL identify the asset, its current status, and which discipline "
    "authored each part of the contract"
)
def _the_output_reads_cold(compilation: dict[str, Any]) -> None:
    text = compilation["text"]
    assert ASSET_ID in text
    assert "**Status:** modeling" in text
    for heading in (
        "## Concept — authored by art",
        "## Design — authored by design",
        "## Engineering constraints — authored by engineering",
    ):
        assert heading in text


@then("the output SHALL state an up axis of `Z`")
def _the_output_states_the_default_up_axis(compilation: dict[str, Any]) -> None:
    assert "- **Up axis**: Z" in compilation["text"]


@then("the two outputs SHALL be byte-identical")
def _the_two_outputs_are_identical(compilation: dict[str, Any]) -> None:
    first, second = compilation["texts"]
    assert first.encode("utf-8") == second.encode("utf-8")


@then("compilation SHALL succeed")
def _compilation_succeeded(compilation: dict[str, Any]) -> None:
    assert compilation["text"].startswith(f"# {ASSET_ID}")


@then("it SHALL contain the project's shared constraints and rules")
def _the_briefing_carries_the_project_rules(compilation: dict[str, Any]) -> None:
    text = compilation["text"]
    assert "Every design field constrains art" in text
    assert "- **Up axis**: Z" in text


@then("it SHALL NOT contain any individual asset's annotations")
def _the_briefing_carries_no_asset_content(compilation: dict[str, Any]) -> None:
    text = compilation["text"]
    assert OPEN_TEXT not in text
    assert ASSET_ID not in text


# --------------------------------------------------------------------------
# The writer, which lives in the CLI (group 6)
# --------------------------------------------------------------------------

HAND_EDIT = "The pauldron is fine, ship it. — edited by hand, 3 March"

HAND_EDITED_FILE = f"""\
# mech_scout — hand notes

{HAND_EDIT}
"""


@scenario(
    "../features/add-asset-spec-and-validator/spec-compilation.feature",
    "Compiled file edited by hand",
)
def test_compiled_file_edited_by_hand() -> None: ...


@given("a hand-edited `art-spec.md`")
def _a_hand_edited_briefing(compilation: dict[str, Any], tmp_path: Path) -> None:
    """The compiled file was never an input, so a hand edit is a doomed edit."""
    _seed(compilation, an_asset(concept=Concept(silhouette_rules=("Reads at 25 m.",))))
    briefing = tmp_path / "art-spec.md"
    briefing.write_text(HAND_EDITED_FILE, encoding="utf-8")
    compilation["briefing"] = briefing


@when("the specification is compiled again")
def _compiled_again_over_the_edited_file(compilation: dict[str, Any]) -> None:
    container = Container(
        spec_store=compilation["spec_store"],
        mesh_inspector=InMemoryMeshInspector(),
    )
    result = CliRunner().invoke(
        build_app(container),
        ["compile", "--out", str(compilation["briefing"]), SPEC_PATH],
    )
    assert result.exit_code == 0, result.output


@then("the hand edits SHALL be replaced by the output derived from `asset.yaml`")
def _the_hand_edits_are_gone(compilation: dict[str, Any]) -> None:
    written = compilation["briefing"].read_text(encoding="utf-8")
    assert HAND_EDIT not in written
    assert written == _compile(compilation)
