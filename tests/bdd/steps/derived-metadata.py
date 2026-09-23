"""Step definitions for `derived-metadata` — proposals, keyed by the image they saw.

The arrangement is `tests/derived_world.py`, the same one
`tests/unit/test_use_case_derived_metadata.py` runs against: a real repository
host, the adapter's own reader and comment-preserving writer over it, the
in-memory index, and a vision fake standing in for the model. So a scenario here
passes because the product keys, reuses, ranks and refuses the way it says it
does, and never because a step asserted about a value it built itself.

Five scenarios assert an **absence**, and they are the ones worth reading twice:
the working tree stays clean, the compiled briefing is byte-identical, no lens
carries a generated word, a mesh is never rendered, and a read makes no model
call. Each is checked against what actually happened — the files in the
repository, the compiled text, the recorded calls — rather than against what the
code appears to do.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.ports.search_index import IndexedAsset, MatchKind
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.spec_lens import Lens, project_lens
from cybercanon.domain.derived import GENERATED, SUGGESTION_NOTICE, is_normalised
from derived_world import FRONT, PROJECT, SCOUT, SCOUT_SPEC, a_derived_world, a_spec_with

DESCRIPTION = "A light reconnaissance walker with a narrow silhouette."
TERMS = "mech, walker, quadruped, recon"

HEAVY = "mech_heavy"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

GENERATED_WORDS = ("quadruped", "reconnaissance", "silhouette.", GENERATED)
"""Words that would mean generated content escaped into an authored artifact."""


@pytest.fixture
def derived() -> dict[str, Any]:
    """The world this scenario runs in, and whatever its steps produced."""
    return {"world": a_derived_world()}


def _world(derived: dict[str, Any]):
    return derived["world"]


def _generate(derived: dict[str, Any], **options: Any):
    described = ran(_world(derived).describe(**options))
    derived["described"] = described
    return described


# --------------------------------------------------------------------------
# Rule: Generated content is a proposal, never authored content
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Specification file untouched by generation",
)
def test_specification_file_untouched_by_generation() -> None: ...


@given("a clean repository working tree")
def _a_clean_tree(derived: dict[str, Any]) -> None:
    world = _world(derived)
    derived["files"] = dict(world.files())
    derived["commits"] = len(world.views.commits())


@when("metadata is generated for every asset in the project")
def _generated_for_every_asset(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.always_answering()
    _generate(derived)


@then("the working tree SHALL remain clean")
def _the_tree_is_clean(derived: dict[str, Any]) -> None:
    world = _world(derived)

    assert world.files() == derived["files"]
    assert len(world.views.commits()) == derived["commits"]
    assert world.records()  # generation really did happen


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Generated content is labelled",
)
def test_generated_content_is_labelled() -> None: ...


@when("generated metadata is presented anywhere")
def _presented_anywhere(derived: dict[str, Any]) -> None:
    _world(derived).answering(DESCRIPTION, TERMS)
    _generate(derived)


@then("it SHALL be identified as generated and not attributed to a person")
def _labelled_and_unattributed(derived: dict[str, Any]) -> None:
    described = derived["described"]

    assert described.suggestions
    assert all(entry.label == GENERATED for entry in described.suggestions)
    assert all(entry.actor == "" for entry in described.suggestions)
    assert all(record.label == GENERATED for record in described.records)


# --------------------------------------------------------------------------
# Rule: Generated content never enters the compiled specification
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Compiled output identical with and without generation",
)
def test_compiled_output_identical_with_and_without_generation() -> None: ...


@given("an asset with generated metadata present in the index")
def _an_asset_with_generated_metadata(derived: dict[str, Any]) -> None:
    world = _world(derived)
    derived["without"] = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store)).text
    world.answering(DESCRIPTION, TERMS)
    _generate(derived)


@when("its specification is compiled")
def _its_specification_is_compiled(derived: dict[str, Any]) -> None:
    world = _world(derived)
    derived["with"] = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store)).text


@then(
    "the output SHALL be byte-identical to compiling the same asset with no generated "
    "metadata present"
)
def _compiled_byte_identical(derived: dict[str, Any]) -> None:
    assert _world(derived).records()
    assert derived["with"] == derived["without"]
    assert not [word for word in GENERATED_WORDS if word in derived["with"]]


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Lensed read excludes generated content",
)
def test_lensed_read_excludes_generated_content() -> None: ...


@when("an asset is read under any lens")
def _read_under_any_lens(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.answering(DESCRIPTION, TERMS)
    _generate(derived)
    compiled = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store))
    derived["lensed"] = {lens: project_lens(compiled, lens) for lens in Lens}


@then("no generated description, tag or alias SHALL appear")
def _no_generated_content_in_a_lens(derived: dict[str, Any]) -> None:
    assert _world(derived).records()
    for lens, lensed in derived["lensed"].items():
        for word in GENERATED_WORDS:
            assert word not in lensed.body, lens
            assert word not in lensed.full, lens


# --------------------------------------------------------------------------
# Rule: Generation targets images only
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Mesh is not described",
)
def test_mesh_is_not_described() -> None: ...


@given("an asset with an exported mesh and no concept view")
def _a_mesh_and_no_view(derived: dict[str, Any]) -> None:
    world = a_derived_world(views={})
    world.views.host.push_to_remote(PROJECT, EXPORT, b"glTF-bytes")
    world.views.host.fetch(PROJECT)
    world.always_answering()
    derived["world"] = world


@when("metadata generation is requested")
def _generation_requested(derived: dict[str, Any]) -> None:
    derived["refusal"] = refused(_world(derived).describe())


@then("the system SHALL report that there is no describable source")
def _no_describable_source(derived: dict[str, Any]) -> None:
    refusal = derived["refusal"]

    assert refusal.identifier == "derived.no_describable_source"
    assert "no concept view to describe" in refusal.message


@then("SHALL NOT render or describe the mesh")
def _the_mesh_is_untouched(derived: dict[str, Any]) -> None:
    world = _world(derived)

    assert world.model_calls() == 0
    assert world.records() == ()
    assert world.files()[EXPORT] == b"glTF-bytes"


# --------------------------------------------------------------------------
# Rule: Derived rows are keyed by source content
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Unchanged image is not regenerated",
)
def test_unchanged_image_is_not_regenerated() -> None: ...


@given("a derived record for an image")
def _a_derived_record(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.always_answering()
    _generate(derived)
    derived["first"] = derived["described"].records[0].source_hash
    derived["calls"] = world.model_calls()


@when("generation is requested again for the same unchanged image")
def _requested_again(derived: dict[str, Any]) -> None:
    derived["again"] = _generate(derived)


@then("the existing record SHALL be reused and no model call SHALL be made")
def _reused_with_no_model_call(derived: dict[str, Any]) -> None:
    world = _world(derived)

    assert [generation.reused for generation in derived["again"].generations] == [True]
    assert world.model_calls() == derived["calls"]
    assert derived["again"].records[0].source_hash == derived["first"]


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Changed image produces a new record",
)
def test_changed_image_produces_a_new_record() -> None: ...


@when("the image is replaced with different content and generation is requested")
def _image_replaced(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.views.host.push_to_remote(PROJECT, FRONT, world.views.an_image(seed=99))
    world.views.host.fetch(PROJECT)
    derived["again"] = _generate(derived)


@then("a new record SHALL be created keyed by the new content hash")
def _a_new_record(derived: dict[str, Any]) -> None:
    world = _world(derived)
    second = derived["again"].records[0].source_hash

    assert second == world.source_hash(FRONT)
    assert second != derived["first"]
    assert {record.source_hash for record in world.records()} == {derived["first"], second}


# --------------------------------------------------------------------------
# Rule: Provenance is recorded
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Provenance retrievable",
)
def test_provenance_retrievable() -> None: ...


@when("a derived record is presented")
def _a_record_presented(derived: dict[str, Any]) -> None:
    _world(derived).answering(DESCRIPTION, TERMS)
    _generate(derived)


@then("its model identifier, generation time and source content hash SHALL be available")
def _provenance_available(derived: dict[str, Any]) -> None:
    (record,) = derived["described"].records
    provenance = record.provenance

    assert provenance.model
    assert provenance.generated_at
    assert provenance.source_hash == _world(derived).source_hash(FRONT)
    for part in (provenance.model, provenance.short):
        assert part in provenance.described


# --------------------------------------------------------------------------
# Rule: Suggested aliases are the primary output
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Existing aliases are not re-suggested",
)
def test_existing_aliases_are_not_re_suggested() -> None: ...


@given("an asset already declaring the alias `mech`")
def _already_declaring_mech(derived: dict[str, Any]) -> None:
    derived["world"] = a_derived_world(spec=a_spec_with(("mech",)))


@when("aliases are suggested for it")
def _aliases_suggested(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.answering(DESCRIPTION, "Mech, MECH, walker, recon")
    derived["described"] = ran(world.suggest())


@then("`mech` SHALL NOT appear among the suggestions")
def _mech_is_not_suggested(derived: dict[str, Any]) -> None:
    described = derived["described"]

    assert "mech" not in described.pending
    assert described.pending == ("walker", "recon")


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Suggestions are search-usable",
)
def test_suggestions_are_search_usable() -> None: ...


@when("aliases are suggested")
def _aliases_are_suggested(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.answering(DESCRIPTION, "Scout Walker, RECON drone, quadruped ")
    derived["described"] = ran(world.suggest())


@then("each SHALL be in the same normalised form that a specification's aliases take")
def _each_is_normalised(derived: dict[str, Any]) -> None:
    pending = derived["described"].pending

    assert pending
    assert all(is_normalised(value) for value in pending)
    assert "scout_walker" in pending


# --------------------------------------------------------------------------
# Rule: Suggested aliases do not affect ranked search until accepted
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Accepted alias outranks a suggestion",
)
def test_accepted_alias_outranks_a_suggestion() -> None: ...


@given(
    "one asset with an accepted alias matching a term and another with only a suggested "
    "alias matching it"
)
def _one_accepted_one_suggested(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.index.upsert(
        IndexedAsset(asset_id=HEAVY, name="Heavy Hauler", project=PROJECT, aliases=("walker",))
    )
    world.index.upsert(IndexedAsset(asset_id=SCOUT, name="Scout Mech", project=PROJECT))
    world.answering(DESCRIPTION, "walker, recon")
    _generate(derived)


@when("that term is searched")
def _that_term_is_searched(derived: dict[str, Any]) -> None:
    derived["hits"] = _world(derived).index.search("walker", PROJECT)


@then("the asset with the accepted alias SHALL rank first")
def _the_accepted_one_ranks_first(derived: dict[str, Any]) -> None:
    hits = derived["hits"]

    assert [hit.asset_id for hit in hits] == [HEAVY, SCOUT]
    assert hits[0].kind is MatchKind.ALIAS
    assert hits[1].kind is MatchKind.SUGGESTED_ALIAS


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Suggestion match is disclosed",
)
def test_suggestion_match_is_disclosed() -> None: ...


@when("a result is produced only by a suggested alias")
def _produced_only_by_a_suggestion(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.index.upsert(IndexedAsset(asset_id=SCOUT, name="Scout Mech", project=PROJECT))
    world.answering(DESCRIPTION, "quadruped")
    _generate(derived)
    derived["hits"] = world.index.search("quadruped", PROJECT)


@then("the result SHALL indicate that the match came from an unaccepted suggestion")
def _the_match_is_disclosed(derived: dict[str, Any]) -> None:
    (hit,) = derived["hits"]

    assert hit.is_suggestion
    assert SUGGESTION_NOTICE in hit.notice
    assert "quadruped" in hit.notice


# --------------------------------------------------------------------------
# Rule: Derived content is disposable
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Derived records deleted",
)
def test_derived_records_deleted() -> None: ...


@given("a project with derived records and accepted aliases")
def _records_and_accepted_aliases(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.index.upsert(IndexedAsset(asset_id=SCOUT, name="Scout Mech", project=PROJECT))
    world.answering(DESCRIPTION, TERMS)
    _generate(derived)
    ran(world.accept("walker"))
    world.index.upsert(
        IndexedAsset(asset_id=SCOUT, name="Scout Mech", project=PROJECT, aliases=("walker",))
    )
    assert world.records()


@when("all derived records are deleted")
def _all_records_deleted(derived: dict[str, Any]) -> None:
    _world(derived).index.clear_derived(PROJECT)


@then("accepted aliases SHALL remain in their specification files")
def _accepted_aliases_remain(derived: dict[str, Any]) -> None:
    world = _world(derived)

    assert world.records() == ()
    assert world.aliases() == ("walker",)
    assert "walker" in world.spec_text()


@then("search SHALL continue to work")
def _search_still_works(derived: dict[str, Any]) -> None:
    world = _world(derived)

    (hit,) = world.index.search("walker", PROJECT)

    assert hit.asset_id == SCOUT
    assert hit.kind is MatchKind.ALIAS
    assert world.index.search("quadruped", PROJECT) == ()


# --------------------------------------------------------------------------
# Rule: Generation is explicitly requested, never automatic on read
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Reads never generate",
)
def test_reads_never_generate() -> None: ...


@given("an asset with no derived record")
def _no_derived_record(derived: dict[str, Any]) -> None:
    world = _world(derived)
    world.index.upsert(IndexedAsset(asset_id=SCOUT, name="Scout Mech", project=PROJECT))

    assert world.records() == ()


@when("it is read, listed, searched, validated and compiled")
def _five_reads(derived: dict[str, Any]) -> None:
    world = _world(derived)
    derived["reads"] = (
        ran(world.listed()),
        world.index.list_assets(PROJECT),
        world.index.search("scout", PROJECT),
        ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store)),
        world.views.spec_store.load(SCOUT_SPEC),
    )


@then("no model call SHALL be made")
def _no_model_call(derived: dict[str, Any]) -> None:
    world = _world(derived)

    assert derived["reads"]
    assert world.model_calls() == 0
    assert world.records() == ()


# --------------------------------------------------------------------------
# Rule: Automated callers cannot trigger generation into the canon
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/derived-metadata.feature",
    "Agent cannot accept a suggestion",
)
def test_agent_cannot_accept_a_suggestion() -> None: ...


@when("an automated caller attempts to accept a suggested alias")
def _an_agent_accepts(derived: dict[str, Any]) -> None:
    from derived_world import AN_AGENT

    world = _world(derived)
    world.answering(DESCRIPTION, TERMS)
    _generate(derived)
    derived["before"] = world.spec_text()
    derived["refusal"] = refused(world.accept("walker", actor=AN_AGENT))


@then("the attempt SHALL be refused regardless of the roles it acts under")
def _refused_whatever_its_roles(derived: dict[str, Any]) -> None:
    from cybercanon.domain.identity import Role
    from derived_world import AN_AGENT

    world = _world(derived)

    assert AN_AGENT.roles == tuple(Role)
    assert "requires a person" in derived["refusal"].message
    assert world.aliases() == ()
    assert world.spec_text() == derived["before"]
