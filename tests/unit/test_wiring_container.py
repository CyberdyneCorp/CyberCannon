"""Task 6.1 — the composition root, constructed with fakes and fully resolvable.

The container is what makes "one verdict across every surface" structural: the
CLI in this change, the MCP server in the next one and the HTTP app after it all
call these methods. So what is asserted here is that **every** use case the
change ships can be reached from it, walked from
:data:`cybercanon.adapters.wiring.container.USE_CASES` rather than listed by
hand — a use case added without a way to reach it fails the build instead of
waiting to be noticed.

Everything runs over the in-memory fakes, with no file on disk: building the
container must not require a repository, a mesh library or a blob directory,
which is the same property that lets an inbound adapter be tested at all.
"""

from __future__ import annotations

from typing import Any

import pytest

from cybercanon.adapters.wiring.container import USE_CASES, Container
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.compile_spec import CompiledBriefing, CompiledSpec
from cybercanon.application.use_cases.lint_spec import LintReport
from cybercanon.application.use_cases.validate_export import ValidationOutcome
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.status import Status

ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"


def an_asset() -> Asset:
    return Asset(
        id=AssetId(ASSET_ID),
        name="Scout Mech",
        status=Status.MODELING,
        constraints=Constraints(tri_budget=12000, naming="SM_{asset}_LOD{n}"),
    )


def some_facts() -> Any:
    return facts_for(
        MeshFormat.GLB,
        triangles=9000,
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


@pytest.fixture
def container() -> Container:
    """The container every inbound adapter is handed, built from the fakes."""
    fakes = build_fakes()
    spec_store: InMemorySpecStore = fakes["spec_store"]
    inspector: InMemoryMeshInspector = fakes["mesh_inspector"]
    spec_store.add(SPEC_PATH, an_asset())
    spec_store.set_project(ProjectConfig(name="Ronin", golden_rules=("Read at 25 m.",)))
    inspector.add(EXPORT, some_facts())
    return Container(
        spec_store=spec_store,
        mesh_inspector=inspector,
        blob_store=fakes["blob_store"],
    )


@pytest.mark.parametrize("use_case", USE_CASES)
def test_the_container_resolves_every_use_case(container: Container, use_case: str) -> None:
    """Every use case the change ships is reachable from the one composition root."""
    assert callable(getattr(container, use_case))


def test_it_validates_an_export_through_the_ports_it_was_given(container: Container) -> None:
    outcome = container.validate_export(EXPORT)
    assert isinstance(outcome, ValidationOutcome)
    assert outcome.asset_id == ASSET_ID
    assert outcome.spec_path == SPEC_PATH
    assert outcome.passed


def test_it_emits_a_preview_only_when_asked(container: Container) -> None:
    """Preview emission is opt-in and, either way, cannot move the verdict (D7)."""
    assert container.validate_export(EXPORT).preview is None
    assert container.validate_export(EXPORT, emit_preview=True).preview is not None


def test_it_lints_one_specification_and_a_whole_tree(container: Container) -> None:
    one = container.lint_specs([SPEC_PATH])
    everything = container.lint_project("")
    assert isinstance(one, LintReport)
    assert one.checked == (SPEC_PATH,)
    assert everything.checked == (SPEC_PATH,)


def test_it_compiles_an_asset_and_the_project_briefing(container: Container) -> None:
    compiled = container.compile_spec(SPEC_PATH)
    briefing = container.compile_project_briefing()
    assert isinstance(compiled, CompiledSpec)
    assert isinstance(briefing, CompiledBriefing)
    assert compiled.asset_id == ASSET_ID
    assert briefing.project == "Ronin"


def test_discovery_stays_in_the_port(container: Container) -> None:
    """The CLI asks the container; the upward walk (D9) is never re-implemented."""
    assert container.discover(EXPORT) == SPEC_PATH
    assert container.discover("docs/readme.md") is None


def test_the_blob_store_is_optional(container: Container) -> None:
    """A container with no blob store still validates: a preview is never the verdict."""
    without = Container(
        spec_store=container.spec_store,
        mesh_inspector=container.mesh_inspector,
    )
    outcome = without.validate_export(EXPORT, emit_preview=True)
    assert outcome.passed
    assert outcome.preview is None
