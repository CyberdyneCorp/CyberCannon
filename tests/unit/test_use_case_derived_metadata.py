"""Group 4 — generation, reuse, acceptance, rejection, and the sixth search pass.

Every test runs against `tests/derived_world.py`: a real repository host, the
adapter's own reader and comment-preserving writer over it, the in-memory index,
and a vision fake standing in for the model. So an accepted alias is asserted by
**parsing what landed in the repository**, not by reading back something the use
case returned.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cybercanon.application.errors import FailureKind
from cybercanon.application.ports.llm import Unavailability
from cybercanon.application.ports.search_index import IndexedAsset, MatchKind
from cybercanon.application.testing.llm import EVERY_REASON
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.domain.derived import GENERATED, SUGGESTION_NOTICE, SuggestionState
from cybercanon.domain.identity import AgentId, Role
from derived_world import (
    AN_AGENT,
    DESCRIPTION,
    FRONT,
    MOMENT,
    PROJECT,
    RAFA_ACTOR,
    RAFA_SUBJECT,
    SCOUT,
    SCOUT_SPEC,
    SIDE,
    a_derived_world,
    a_spec_with,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# 4.1 — one description per image, reused when the image has not changed (D5)
# --------------------------------------------------------------------------


def test_generation_produces_a_description_tags_and_suggested_aliases() -> None:
    world = a_derived_world()
    world.answering()

    described = ran(world.describe())

    (record,) = described.records
    assert record.description == DESCRIPTION
    assert record.tags == ("mech", "walker", "quadruped", "recon")
    assert record.suggested_aliases == ("mech", "walker", "quadruped", "recon")


def test_the_record_is_keyed_by_the_image_and_carries_its_provenance() -> None:
    world = a_derived_world()
    world.answering()

    (record,) = ran(world.describe()).records

    assert record.source_hash == world.source_hash(FRONT)
    assert record.source_path == FRONT
    assert record.generated_at == MOMENT
    assert record.model


def test_an_unchanged_image_is_reused_and_no_model_is_called() -> None:
    """D5's whole point: a repeated run over a project costs nothing."""
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    before = world.model_calls()

    again = ran(world.describe())

    assert [generation.reused for generation in again.generations] == [True]
    assert world.model_calls() == before


def test_a_changed_image_produces_a_new_record_rather_than_overwriting() -> None:
    world = a_derived_world()
    world.always_answering()
    first = ran(world.describe()).records[0].source_hash
    world.views.host.push_to_remote(PROJECT, FRONT, world.views.an_image(seed=99))
    world.views.host.fetch(PROJECT)

    second = ran(world.describe()).records[0].source_hash

    assert first != second
    assert {record.source_hash for record in world.records()} == {first, second}


def test_every_view_an_asset_holds_is_described() -> None:
    world = a_derived_world(views={FRONT: b"", SIDE: b""})
    world.always_answering()

    described = ran(world.describe())

    assert {record.source_path for record in described.records} == {FRONT, SIDE}


def test_one_slot_can_be_named() -> None:
    world = a_derived_world(views={FRONT: b"", SIDE: b""})
    world.always_answering()

    described = ran(world.describe(slot="side"))

    assert [record.source_path for record in described.records] == [SIDE]


def test_suggest_aliases_is_the_same_operation_seen_from_the_feature() -> None:
    world = a_derived_world()
    world.answering()

    suggested = ran(world.suggest())

    assert suggested.pending == ("mech", "walker", "quadruped", "recon")


def test_the_asset_s_own_terms_are_never_suggested() -> None:
    """`derived-metadata`: an asset declaring `mech` is never offered `mech`."""
    world = a_derived_world(spec=a_spec_with(("mech",)))
    world.answering(terms="mech, Scout Mech, mech_scout, walker")

    assert ran(world.describe()).pending == ("walker",)


# --------------------------------------------------------------------------
# 4.2 — images only. A mesh is not described, and nothing is rendered
# --------------------------------------------------------------------------


def test_an_asset_with_a_mesh_and_no_concept_view_has_no_describable_source() -> None:
    world = a_derived_world(views={})
    world.views.host.push_to_remote(
        PROJECT, "characters/mech_scout/exports/SM_mech_scout_LOD0.glb", b"glTF-bytes"
    )
    world.views.host.fetch(PROJECT)
    world.always_answering()

    refusal = refused(world.describe())

    assert refusal.identifier == "derived.no_describable_source"
    assert world.model_calls() == 0


def test_an_export_beside_a_view_is_never_sent_to_a_model() -> None:
    world = a_derived_world()
    world.views.host.push_to_remote(PROJECT, "characters/mech_scout/exports/a.glb", b"glTF")
    world.views.host.fetch(PROJECT)
    world.answering()

    ran(world.describe())

    assert set(world.vision.images) == {world.files()[FRONT]}


# --------------------------------------------------------------------------
# 4.3-4.4 — acceptance, attribution, partial acceptance and editing
# --------------------------------------------------------------------------


def test_acceptance_writes_the_alias_and_records_who_accepted_it() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    accepted = ran(world.accept("walker"))

    assert world.aliases() == ("walker",)
    assert accepted.actor == RAFA_SUBJECT
    (decision,) = [entry for entry in world.index.decisions(project=PROJECT) if entry.accepted]
    assert decision.actor == RAFA_SUBJECT and decision.at == MOMENT


def test_acceptance_with_no_resolvable_person_is_refused() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    refusal = refused(world.accept("walker", actor=None))

    assert refusal.kind is FailureKind.UNAUTHENTICATED
    assert world.aliases() == ()


def test_acceptance_by_a_person_with_no_git_identity_is_refused_naming_the_entry() -> None:
    world = a_derived_world(mapped=False)
    world.answering()
    ran(world.describe())

    refusal = refused(world.accept("walker", author=None))

    assert refusal.kind is FailureKind.FORBIDDEN
    assert "actors" in refusal.message
    assert world.aliases() == ()


def test_accepting_two_of_four_writes_exactly_those_two() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    ran(world.accept("walker"))
    ran(world.accept("recon"))

    assert world.aliases() == ("walker", "recon")


def test_an_edited_value_is_what_gets_written_and_it_is_still_theirs() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    accepted = ran(world.accept("walker", written="Strider Walker"))

    assert accepted.written == "strider_walker"
    assert world.aliases() == ("strider_walker",)
    (decision,) = [entry for entry in world.index.decisions(project=PROJECT) if entry.accepted]
    assert decision.value == "walker" and decision.recorded == "strider_walker"
    assert decision.actor == RAFA_SUBJECT


def test_a_rejected_value_cannot_then_be_accepted() -> None:
    """The two exits are exclusive: a refused term is refused for that image."""
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    ran(world.reject("walker"))

    refusal = refused(world.accept("walker"))

    assert refusal.identifier == "suggestion.not_found"
    assert world.aliases() == ()


def test_a_value_nothing_proposed_is_refused_rather_than_written() -> None:
    """Acceptance is of a suggestion, not a free-text field with extra steps."""
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    refusal = refused(world.accept("something_nobody_suggested"))

    assert refusal.identifier == "suggestion.not_found"
    assert world.aliases() == ()


def test_an_edit_that_normalises_to_nothing_is_refused() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    refusal = refused(world.accept("walker", written="!!!"))

    assert refusal.identifier == "suggestion.unusable_value"
    assert world.aliases() == ()


def test_accepting_the_same_value_twice_writes_one_commit() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    ran(world.accept("walker"))
    before = len(world.views.commits())

    again = ran(world.accept("walker"))

    assert not again.committed
    assert len(world.views.commits()) == before


def test_a_write_that_cannot_complete_leaves_the_suggestion_pending() -> None:
    """Task 6.2's second half: nothing changed, and the action can be retried."""
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    before = world.spec_text()
    world.views.host.reject_next_pushes(PROJECT, times=9)

    refusal = refused(world.accept("walker"))

    assert refusal.kind is FailureKind.CONFLICT
    assert world.spec_text() == before
    assert world.index.decisions(project=PROJECT) == ()
    assert "walker" in ran(world.listed()).pending

    world.views.host.reject_next_pushes(PROJECT, times=0)
    assert ran(world.accept("walker")).committed
    assert world.aliases() == ("walker",)


# --------------------------------------------------------------------------
# 3.5 / 4.3 — an automated caller may never accept, for any role
# --------------------------------------------------------------------------


def test_an_automated_caller_is_refused_although_it_holds_every_role() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    refusal = refused(world.accept("walker", actor=AN_AGENT))

    assert refusal.kind is FailureKind.FORBIDDEN
    assert "requires a person" in refusal.message
    assert world.aliases() == ()


@pytest.mark.parametrize("role", list(Role), ids=str)
def test_an_automated_caller_is_refused_for_every_role_one_at_a_time(role: Role) -> None:
    """Task 3.5, literally: each role on its own, and the answer is still no."""
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    automation = replace(AN_AGENT, roles=(role,))

    refusal = refused(world.accept("walker", actor=automation))

    assert refusal.kind is FailureKind.FORBIDDEN
    assert "requires a person" in refusal.message
    assert world.aliases() == ()


def test_a_person_acting_through_an_agent_is_refused_too() -> None:
    """The instrument is named and the answer is still no (`project.md`)."""
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    refusal = refused(world.accept("walker", via=AgentId("blender-agent")))

    assert refusal.kind is FailureKind.FORBIDDEN
    assert world.aliases() == ()


# --------------------------------------------------------------------------
# 4.5 — rejection, and that it survives regeneration (D6)
# --------------------------------------------------------------------------


def test_a_rejected_suggestion_is_not_presented_again() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    ran(world.reject("walker"))

    assert "walker" not in ran(world.listed()).pending


def test_a_rejection_survives_regenerating_the_same_unchanged_image() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    ran(world.reject("walker"))

    again = ran(world.describe())

    assert "walker" not in again.pending
    assert "mech" in again.pending


def test_rejection_writes_nothing_to_the_specification() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    before = world.spec_text()

    ran(world.reject("walker"))

    assert world.spec_text() == before


def test_an_automated_caller_may_not_reject_either() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())

    refusal = refused(world.reject("walker", actor=AN_AGENT))

    assert refusal.kind is FailureKind.FORBIDDEN


# --------------------------------------------------------------------------
# 4.6 — accepted content survives everything derived
# --------------------------------------------------------------------------


def test_an_accepted_alias_survives_the_image_being_replaced() -> None:
    world = a_derived_world()
    world.always_answering()
    ran(world.describe())
    ran(world.accept("walker"))

    world.views.host.push_to_remote(PROJECT, FRONT, world.views.an_image(seed=77))
    world.views.host.fetch(PROJECT)
    ran(world.describe())

    assert world.aliases() == ("walker",)


def test_an_accepted_alias_survives_every_derived_record_being_deleted() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    ran(world.accept("walker"))

    world.index.clear_derived(PROJECT)

    assert world.records() == ()
    assert world.aliases() == ("walker",)


# --------------------------------------------------------------------------
# 4.7 — the sixth cascade pass, disclosed (D9)
# --------------------------------------------------------------------------


def test_an_accepted_alias_outranks_a_suggestion() -> None:
    world = a_derived_world()
    world.index.upsert(IndexedAsset(asset_id="mech_heavy", name="Heavy", project=PROJECT))
    world.index.upsert(
        IndexedAsset(asset_id="mech_scout", name="Scout Mech", project=PROJECT, aliases=("walker",))
    )
    world.answering(terms="walker, recon")
    ran(world.describe(asset_id=SCOUT))
    world.index.upsert(IndexedAsset(asset_id="mech_heavy", name="Heavy", project=PROJECT))

    hits = world.index.search("walker", PROJECT)

    assert hits[0].asset_id == "mech_scout"
    assert hits[0].kind is MatchKind.ALIAS


def test_a_result_produced_only_by_a_suggestion_says_so() -> None:
    world = a_derived_world()
    world.index.upsert(IndexedAsset(asset_id=SCOUT, name="Scout Mech", project=PROJECT))
    world.answering(terms="quadruped")
    ran(world.describe())

    (hit,) = world.index.search("quadruped", PROJECT)

    assert hit.kind is MatchKind.SUGGESTED_ALIAS
    assert hit.is_suggestion
    assert SUGGESTION_NOTICE in hit.notice and "quadruped" in hit.notice


def test_a_rejected_suggestion_stops_rescuing_searches() -> None:
    world = a_derived_world()
    world.index.upsert(IndexedAsset(asset_id=SCOUT, name="Scout Mech", project=PROJECT))
    world.answering(terms="quadruped")
    ran(world.describe())
    ran(world.reject("quadruped"))

    assert world.index.search("quadruped", PROJECT) == ()


def test_the_suggestion_pass_is_the_last_one() -> None:
    assert MatchKind.SUGGESTED_ALIAS.pass_number == len(MatchKind) - 1


# --------------------------------------------------------------------------
# 4.8 / the degradation — every reason behaves the same way
# --------------------------------------------------------------------------


@pytest.mark.parametrize("reason", EVERY_REASON, ids=str)
def test_every_failure_degrades_to_the_same_observable_outcome(
    reason: Unavailability,
) -> None:
    """Ok, unavailable, the reason stated, and nothing else changed."""
    world = a_derived_world()
    world.refusing(reason)
    before = world.spec_text()

    described = ran(world.describe())

    assert not described.is_available
    assert str(reason) in described.reason
    assert described.records == ()
    assert world.spec_text() == before
    assert world.records() == ()


def test_an_unreadable_answer_is_malformed_rather_than_partly_accepted() -> None:
    world = a_derived_world()
    world.answering(terms="Here are some ideas: mech; walker")

    described = ran(world.describe())

    assert not described.is_available
    assert str(Unavailability.MALFORMED) in described.reason
    assert world.records() == ()


def test_listing_what_is_derived_never_calls_a_model() -> None:
    world = a_derived_world()

    listed = ran(world.listed())

    assert listed.generations == ()
    assert world.model_calls() == 0


# --------------------------------------------------------------------------
# Presentation — generated, and attributed to nobody
# --------------------------------------------------------------------------


def test_a_pending_suggestion_is_labelled_generated_and_never_attributed() -> None:
    world = a_derived_world()
    world.answering()

    described = ran(world.describe())

    assert all(entry.label == GENERATED for entry in described.suggestions)
    assert all(entry.actor == "" for entry in described.suggestions)


def test_an_accepted_suggestion_stops_being_labelled_generated() -> None:
    world = a_derived_world()
    world.answering()
    ran(world.describe())
    ran(world.accept("walker"))

    states = {entry.value: entry.state for entry in ran(world.listed()).suggestions}

    assert states["walker"] is SuggestionState.ACCEPTED
    assert states["mech"] is SuggestionState.PENDING


def test_an_unknown_asset_is_a_named_refusal() -> None:
    world = a_derived_world()

    assert refused(world.describe(asset_id="nobody")).identifier == "asset.not_found"
    assert SCOUT_SPEC in world.files()
    assert RAFA_ACTOR.subject == RAFA_SUBJECT
