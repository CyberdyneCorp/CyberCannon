"""Tasks 4.8 and 5.4 — reading, listing, searching, validating and compiling never ask a model.

`derived-metadata` requires generation to be *"explicitly requested by a person
or by a maintenance operation"*, and `llm-integration` requires specification
validation, compilation, lookup and search to *"produce identical results
whether model access is configured or not"*. Both are absences, so both are
asserted the way `tests/unit/test_ingestion_never_calls_a_model.py` asserts its
own: structurally over the syntax tree, **and** behaviourally with both model
ports wired to something that fails on any access at all.

The behavioural half is the one that survives a refactor: a call added through a
route the syntax tree cannot see still fails, on the spot, naming the port.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases import (
    compile_spec,
    index_assets,
    lookup_assets,
    spec_lens,
    validate_export,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.status import Status

pytestmark = pytest.mark.unit

PROJECT = "Ronin"
ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

MODEL_NAMES = frozenset(
    {
        "LLMPort",
        "VisionPort",
        "llm",
        "vision",
        "complete",
        "ModelAnswer",
        "OpenAICompatibleModels",
        "chat_body",
    }
)
"""Every name a model call would arrive under. Checked as names, not as strings."""

CORE_MODULES = (compile_spec, lookup_assets, spec_lens, validate_export, index_assets)
"""The five modules the specification names as core paths. All of them, not one file."""


class RaisesOnAnything:
    """A port that fails on any access at all — a model wired and unusable.

    Deliberately not a recording mock: a mock that was never called proves the
    same thing only if somebody remembers to assert it, and this cannot be used
    at all without the test failing on the spot.
    """

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"a core path reached a model port: {name}")


def an_asset() -> Asset:
    return Asset(
        id=AssetId(ASSET_ID),
        name="Scout Mech",
        status=Status.MODELING,
        aliases=("scout",),
        constraints=Constraints(tri_budget=12000),
    )


def a_container(**ports: Any) -> Container:
    fakes = build_fakes()
    store, index = fakes["spec_store"], fakes["search_index"]
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SPEC_PATH, an_asset())
    index.upsert(index_assets.entry_for(store.load(SPEC_PATH), ProjectConfig(name=PROJECT)))
    return Container(
        spec_store=store,
        mesh_inspector=fakes["mesh_inspector"],
        blob_store=fakes["blob_store"],
        search_index=index,
        **ports,
    )


def _named(source: str) -> set[str]:
    """Every identifier, attribute and imported name in one module."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return {part for name in found for part in name.split(".")}


# --------------------------------------------------------------------------
# The structural half
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module", CORE_MODULES, ids=lambda module: module.__name__)
def test_no_core_module_names_a_model_port(module: Any) -> None:
    offences = _named(Path(module.__file__).read_text(encoding="utf-8")) & MODEL_NAMES

    assert not offences, (
        f"{module.__name__} names {sorted(offences)}. Validation, compilation, "
        "lookup and search SHALL produce identical results whether model access "
        "is configured or not, and SHALL never block on a model call."
    )


def test_the_guard_is_over_something_that_could_fail() -> None:
    """A guard over nothing passes for the wrong reason."""
    staged = "from cybercanon.application.ports.llm import LLMPort\n\ndef read(llm: LLMPort): ...\n"

    assert _named(staged) & MODEL_NAMES == {"llm", "LLMPort"}


# --------------------------------------------------------------------------
# The behavioural half — a model wired to explode, and five operations run
# --------------------------------------------------------------------------


def test_read_list_search_validate_and_compile_make_no_model_call() -> None:
    """The scenario in one test: an asset with no derived record, five reads."""
    container = a_container(llm=RaisesOnAnything(), vision=RaisesOnAnything())

    assert ran(container.asset_spec(ASSET_ID)).asset_id == ASSET_ID
    assert ran(container.list_assets()).asset_ids == (ASSET_ID,)
    assert ran(container.search_assets("scout")).asset_ids == (ASSET_ID,)
    assert ran(container.where_is(ASSET_ID)).asset_id == ASSET_ID
    assert ran(container.compile_spec(SPEC_PATH)).asset_id == ASSET_ID


def test_a_search_that_matches_nothing_does_not_reach_for_a_model_either() -> None:
    """The place a helpful implementation would reach for one: an empty answer."""
    container = a_container(llm=RaisesOnAnything(), vision=RaisesOnAnything())

    answer = ran(container.search_assets("nothing-matches-this"))

    assert answer.is_empty and answer.recorded_as_miss


def test_compiling_is_byte_identical_with_a_model_wired_and_with_none() -> None:
    with_model = a_container(llm=RaisesOnAnything(), vision=RaisesOnAnything())
    without = a_container()

    assert ran(with_model.compile_spec(SPEC_PATH)).text == ran(without.compile_spec(SPEC_PATH)).text


def test_validation_produces_identical_reports_with_a_model_and_without() -> None:
    """*"the reports SHALL be identical"* — and they cannot differ, having no way to."""
    first = _validated(llm=RaisesOnAnything(), vision=RaisesOnAnything())
    second = _validated()

    assert first.report == second.report
    assert first.passed == second.passed


def _validated(**ports: Any):
    """One export validated through a whole container, with whatever ports it was given."""
    fakes = build_fakes()
    store, inspector = fakes["spec_store"], fakes["mesh_inspector"]
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SPEC_PATH, an_asset())
    inspector.add(EXPORT, _facts())
    container = Container(
        spec_store=store,
        mesh_inspector=inspector,
        blob_store=fakes["blob_store"],
        search_index=fakes["search_index"],
        **ports,
    )
    return ran(container.validate_export(EXPORT))


def _facts():
    """A mesh that passes everything the specification declares."""
    return facts_for(
        MeshFormat.GLB,
        triangles=9000,
        objects=("SM_mech_scout",),
        transforms_applied=True,
        unit_scale=1.0,
        up_axis="Y",
        uv_sets=1,
        materials=("M_mech_scout",),
        empties=(),
        clips=(),
        frame_rate=None,
        is_skinned=False,
    )


def test_the_default_container_has_a_model_that_is_simply_unavailable() -> None:
    """No `None` to check: *"degrades to absent"* is one wiring decision."""
    container = a_container()

    assert not container.llm.complete("anything")
    assert not container.vision.describe(b"\x89PNG", "anything")
