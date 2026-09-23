"""Group 6 — the schema, the lint rule, and the two boundaries that must not blur.

The specification is strict about two things that are easy to lose now that a
rich document API is in reach, and both are asserted here rather than described:

* **a resolved title or summary is display-only cache.** It never reaches a
  specification file and never reaches the compiled briefing, so *"the two
  outputs SHALL be byte-identical"* whether the platform is reachable or not.
* **the `design` block is never generated from a document.** Linking, displaying
  and compiling an asset whose document describes a socket in prose leaves the
  block exactly as its author wrote it, and a budget stated in prose is not a
  constraint on an export.

The compilation and validation halves need no platform at all — which is the
point: neither function has a port in its signature that could reach one.
"""

from __future__ import annotations

import pytest

from cybercanon.adapters.outbound.git import schema, yaml_io
from cybercanon.application.ports.document_platform import UnavailabilityReason
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.spec_checks import RULE_MALFORMED_DOCUMENT_REF, check_document_reference
from documents_world import (
    PRIVATE,
    PROSE,
    RATIONALE,
    WORKSPACE,
    Documents,
    a_world,
    with_links,
    without_platform,
)
from views_world import SCOUT_SPEC

pytestmark = pytest.mark.unit

EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"

WELL_FORMED = f"""\
schema_version: 1
id: mech_scout
name: Scout Mech
documents:
  - workspace: {WORKSPACE}
    id: {RATIONALE}
    url: https://documents.invalid/w/{WORKSPACE}/d/{RATIONALE}
    linked_by: auth|rafa
"""

MALFORMED = f"""\
schema_version: 1
id: mech_scout
name: Scout Mech
documents:
  - workspace: {WORKSPACE}
    id: {RATIONALE}
    url: not-an-address
"""

VALIDATABLE = f"""\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
constraints:
  tri_budget: 12000
documents:
  - workspace: {WORKSPACE}
    id: {RATIONALE}
    url: https://documents.invalid/w/{WORKSPACE}/d/{RATIONALE}
"""
"""A specification whose declared budget is 12000 — and whose linked document
says *about forty thousand*. Only one of those two numbers is a constraint."""

LEGACY = """\
schema_version: 1
id: mech_scout
name: Scout Mech
links:
  source: art/mech_scout.blend
  design_doc: https://wiki.invalid/mech_scout
"""


def _parsed(text: str):
    data = yaml_io.load_mapping(text, subject=SCOUT_SPEC)
    parsed, warnings = schema.parse_asset_file(data)
    asset, more = schema.to_asset(parsed)
    return asset, (*warnings, *more)


def some_facts(triangles: int = 9000):
    return facts_for(
        MeshFormat.GLB,
        triangles=triangles,
        objects=(OBJECT,),
        transforms_applied=True,
        unit_scale=1.0,
        up_axis="Y",
        uv_sets=1,
        materials=("M_mech_scout",),
        empties=("SOCKET_muzzle_l",),
        clips=(),
        frame_rate=None,
        is_skinned=False,
        bone_count=0,
    )


# --------------------------------------------------------------------------
# 6.1 — the schema, alongside the plain URLs already stored in `links`
# --------------------------------------------------------------------------


def test_a_structured_reference_parses_into_the_asset() -> None:
    asset, warnings = _parsed(WELL_FORMED)

    assert [ref.document_id for ref in asset.documents] == [RATIONALE]
    assert asset.documents[0].linked_by == "auth|rafa"
    assert warnings == ()


def test_a_specification_written_before_this_change_parses_unchanged() -> None:
    """Additive and reversible: the plain URLs in `links` keep working untouched."""
    asset, warnings = _parsed(LEGACY)

    assert asset.documents == ()
    assert asset.links is not None
    assert asset.links.design_doc == "https://wiki.invalid/mech_scout"
    assert warnings == ()


def test_the_schema_has_no_field_that_could_hold_a_title_or_a_body() -> None:
    assert set(schema.DocumentFile.model_fields) == {
        "workspace",
        "id",
        "url",
        "linked_by",
        "linked_at",
    }


# --------------------------------------------------------------------------
# 6.2 — the lint rule names the offending reference
# --------------------------------------------------------------------------


def test_a_malformed_reference_is_reported_and_named() -> None:
    asset, warnings = _parsed(MALFORMED)

    assert asset.documents == ()
    assert [finding.rule_id for finding in warnings] == [RULE_MALFORMED_DOCUMENT_REF]
    assert RATIONALE in warnings[0].message
    assert "documents[0]" in warnings[0].subject


def test_one_broken_reference_does_not_deny_the_findings_beside_it() -> None:
    text = (
        MALFORMED
        + f"""\
  - workspace: {WORKSPACE}
    id: d_research
    url: https://documents.invalid/w/{WORKSPACE}/d/d_research
"""
    )

    asset, warnings = _parsed(text)

    assert [ref.document_id for ref in asset.documents] == ["d_research"]
    assert len(warnings) == 1


def test_the_check_is_a_pure_function_needing_no_platform() -> None:
    assert check_document_reference("documents[0]", WORKSPACE, RATIONALE, "https://x.invalid") == ()
    assert check_document_reference("documents[0]", "", RATIONALE, "https://x.invalid")


# --------------------------------------------------------------------------
# 6.3, 6.5 — compilation carries the link and never the document
# --------------------------------------------------------------------------


@pytest.fixture
def documents() -> Documents:
    return with_links(a_world(), RATIONALE, PRIVATE)


def _compiled(world: Documents) -> str:
    return ran(compile_spec(SCOUT_SPEC, spec_store=world.spec_store)).text


def test_a_compiled_specification_carries_the_link_as_its_bare_address(
    documents: Documents,
) -> None:
    compiled = _compiled(documents)

    assert f"https://documents.invalid/w/{WORKSPACE}/d/{RATIONALE}" in compiled
    assert "mech_scout — design rationale" not in compiled


def test_compiled_output_is_byte_identical_reachable_or_not(documents: Documents) -> None:
    """The scenario, and it is true because compilation has nothing to ask."""
    reachable = _compiled(documents)
    ran(documents.listed())  # resolve every card, so a leak would have something to leak

    documents.unavailable(UnavailabilityReason.UNREACHABLE)
    unreachable = _compiled(documents)

    assert reachable == unreachable
    assert _compiled(without_platform(documents)) == reachable


def test_no_prose_is_compiled_in_however_long_the_document_is(
    documents: Documents,
) -> None:
    """*"The compiled output SHALL grow by at most the link's own line."*"""
    without = _compiled(a_world())
    with_link = _compiled(documents)

    added = len(with_link) - len(without)
    assert added < 400, "a link costs a line, not a document"
    for sentence in PROSE.split(". "):
        assert sentence not in with_link


def test_compilation_succeeds_with_the_platform_unreachable(documents: Documents) -> None:
    documents.unavailable(UnavailabilityReason.UNREACHABLE)

    compiled = _compiled(documents)

    assert compiled.startswith("# mech_scout")
    assert f"/d/{RATIONALE}" in compiled


def test_linking_and_displaying_leave_the_design_block_exactly_as_authored() -> None:
    """Task 6.5 and the `No field is generated from a document` scenario."""
    world = a_world()
    before = world.asset().design

    with_links(world, RATIONALE)
    ran(world.listed())
    _compiled(world)

    after = world.asset().design
    assert after == before
    assert after is not None
    assert [socket.name for socket in after.sockets] == ["SOCKET_muzzle_l"]
    assert "courier" not in world.spec_text()


def test_a_resolved_title_reaches_neither_the_file_nor_the_briefing(
    documents: Documents,
) -> None:
    """Task 6.5's other half: the cache is display-only, in both artifacts."""
    listing = ran(documents.listed())
    title = listing.entries[0].card.title
    summary = listing.entries[0].card.summary

    assert title and summary
    for artifact in (documents.spec_text(), _compiled(documents)):
        assert title not in artifact
        assert summary not in artifact


# --------------------------------------------------------------------------
# 6.4 — validation never contacts the platform, and prose is not a constraint
# --------------------------------------------------------------------------


def _validated(triangles: int = 9000):
    """One export validated against a specification that carries document links.

    The store is the in-memory one rather than the repository-backed world,
    because validation discovers its governing specification by walking *upward*
    from the export — the walk that makes `canon validate exports/...glb` work.
    """
    store = InMemorySpecStore()
    asset, _ = _parsed(VALIDATABLE)
    store.add(SCOUT_SPEC, asset)
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, some_facts(triangles))
    return ran(validate_export(EXPORT, spec_store=store, mesh_inspector=inspector))


def test_validation_produces_identical_reports_reachable_or_not(
    documents: Documents,
) -> None:
    """Validation has no way to contact a platform, so the reports cannot differ."""
    reachable = _validated()
    documents.unavailable(UnavailabilityReason.UNREACHABLE)
    unreachable = _validated()

    assert reachable.report == unreachable.report
    assert reachable.passed


def test_a_budget_stated_in_a_document_is_not_a_constraint_on_an_export(
    documents: Documents,
) -> None:
    """The document says *about forty thousand*; the specification says 12000.

    An export of 11 000 triangles is inside the declared budget and above
    nothing the validator knows about, so it passes — and it would pass
    identically if the document said four.
    """
    outcome = _validated(triangles=11_000)

    assert outcome.passed
    assert outcome.report.violations == ()


def test_neither_compilation_nor_validation_can_reach_a_document_platform() -> None:
    """Structural: no parameter in either signature could hold one."""
    import inspect

    for function in (compile_spec.raising, validate_export.raising):
        parameters = set(inspect.signature(function).parameters)
        assert "document_platform" not in parameters
        assert "platform" not in parameters
        assert "credential" not in parameters
