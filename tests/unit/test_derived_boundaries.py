"""Group 5 — the boundary that makes generated content harmless (D4).

`derived-metadata` states the requirement as an *absence*, and
`add-mcp-read-server`'s D6 already established what happens to an absence
enforced by absence: it lasts until the first person who thinks a labelled
"generated description" section would be a nice touch. So this suite asserts it
four ways, and they fail in different directions:

* **structurally** — the parsed specification has no field able to hold derived
  content, and `compile_spec` has no dependency on the store that does;
* **byte for byte** — the same asset compiles identically with a full set of
  derived records in the index and with none;
* **through every lens** — all four, over an asset whose index rows are full of
  generated text;
* **through the core paths** — validation and compilation are identical with a
  model wired and with none, and a whole-project generation leaves the working
  tree clean.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime

import pytest

from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases import compile_spec as compile_module
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.spec_lens import Lens, project_lens
from cybercanon.domain.asset import Asset
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.derived import DerivedRecord, Provenance
from cybercanon.domain.design import Design
from cybercanon.domain.effective_spec import EffectiveSpec
from derived_world import DESCRIPTION, FRONT, PROJECT, SCOUT, SCOUT_SPEC, a_derived_world

pytestmark = pytest.mark.unit

DERIVED_NAMES = frozenset(
    {
        "derived",
        "derived_records",
        "suggested_aliases",
        "suggestions",
        "generated",
        "description",
        "tags",
    }
)
"""Names a derived member would arrive under on a parsed specification type."""

SPECIFICATION_TYPES = (Asset, Concept, Design, Constraints, EffectiveSpec)
"""Everything `compile_spec` reads. None of them can hold generated content."""

GENERATED_TEXT = "a light reconnaissance walker, machine-written"


def _records(world) -> None:
    """Fill the index with derived rows for this asset, of every kind there is."""
    world.answering(description=GENERATED_TEXT, terms="mech, walker, quadruped")
    ran(world.describe())


# --------------------------------------------------------------------------
# 5.1 — the compiler cannot express it (D4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("declared", SPECIFICATION_TYPES, ids=lambda kind: kind.__name__)
def test_no_parsed_specification_type_has_a_field_that_could_hold_derived_content(
    declared: type,
) -> None:
    """A filter could be bypassed by a later change; a type that cannot express it cannot."""
    names = {field.name for field in dataclass_fields(declared)}

    assert not names & DERIVED_NAMES


def test_compile_spec_has_no_dependency_on_the_store_derived_content_lives_in() -> None:
    """Derived rows are reachable only through `SearchIndex`, which this never imports."""
    tree = ast.parse(inspect.getsource(compile_module))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}

    assert not [name for name in imported if "search_index" in name or "derived" in name]
    assert "search_index" not in set(inspect.signature(compile_spec.raising).parameters)


# --------------------------------------------------------------------------
# 5.2 — byte-identical compiled output, with and without derived records
# --------------------------------------------------------------------------


def test_compiled_output_is_byte_identical_with_and_without_generated_metadata() -> None:
    world = a_derived_world()
    before = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store)).text

    _records(world)

    after = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store)).text
    assert after == before
    assert world.records()  # the records really are there


def test_no_generated_word_appears_in_a_compiled_briefing() -> None:
    world = a_derived_world()
    _records(world)

    compiled = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store)).text

    for generated in (GENERATED_TEXT, DESCRIPTION, "quadruped"):
        assert generated not in compiled


# --------------------------------------------------------------------------
# 5.3 — no lens exposes it, for each of the four
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lens", list(Lens), ids=str)
def test_no_lens_exposes_generated_content(lens: Lens) -> None:
    world = a_derived_world()
    _records(world)
    compiled = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store))

    lensed = project_lens(compiled, lens)

    for generated in (GENERATED_TEXT, "quadruped", "generated"):
        assert generated not in lensed.body
        assert generated not in lensed.full


# --------------------------------------------------------------------------
# 5.4 — the core paths are identical whether a model is there or not
# --------------------------------------------------------------------------


def test_compiling_is_identical_with_model_access_enabled_and_disabled() -> None:
    enabled = a_derived_world()
    _records(enabled)
    disabled = a_derived_world()

    first = ran(compile_spec(SCOUT_SPEC, spec_store=enabled.views.spec_store)).text
    second = ran(compile_spec(SCOUT_SPEC, spec_store=disabled.views.spec_store)).text

    assert first == second


def test_compiling_never_calls_a_model() -> None:
    world = a_derived_world()

    ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store))

    assert world.model_calls() == 0


# --------------------------------------------------------------------------
# 5.5 — generation leaves the working tree clean
# --------------------------------------------------------------------------


def test_generating_for_every_asset_leaves_the_working_tree_clean() -> None:
    """`derived-metadata`: metadata generated for every asset, nothing committed."""
    world = a_derived_world()
    before = dict(world.files())
    commits = len(world.views.commits())

    world.always_answering()
    ran(world.describe())

    assert world.files() == before
    assert len(world.views.commits()) == commits
    assert world.records()


def test_only_the_index_holds_what_generation_produced() -> None:
    world = a_derived_world()
    world.answering()

    ran(world.describe())

    assert SCOUT not in world.spec_text().replace("mech_scout", "")
    assert DESCRIPTION not in world.spec_text()
    assert world.index.derived(world.source_hash(FRONT), PROJECT) is not None


def test_a_derived_record_is_not_something_a_specification_could_carry() -> None:
    """The type cannot hold one, so there is no filter anybody could bypass."""
    record = DerivedRecord(
        provenance=Provenance(
            model="vision-v1", generated_at=datetime(2026, 9, 22, tzinfo=UTC), source_hash="a" * 64
        )
    )

    assert not [field for field in dataclass_fields(Asset) if field.name in DERIVED_NAMES]
    assert record.asset_id == ""
