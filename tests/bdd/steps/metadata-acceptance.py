"""Step definitions for `metadata-acceptance` — the bridge from proposal to canon.

Every scenario here is about a **file**, so the arrangement is the one that has
a real one: `tests/derived_world.py` stands a repository host, the adapter's own
comment-preserving round trip over it, and reads back by parsing what actually
landed. An assertion about *"the difference SHALL show only the added alias"*
against something a use case returned would be an assertion about a return
value, and the requirement is about the artist's file.

Three of these scenarios assert an absence and they are the ones the product's
credibility rests on: no specification changes without a person, the written
alias carries no marker of where it came from, and a write that cannot complete
leaves the file byte-identical with the suggestion still pending.
"""

from __future__ import annotations

import difflib
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.errors import FailureKind
from cybercanon.application.ports.search_index import IndexedAsset, MatchKind
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.domain.derived import GENERATED
from derived_world import FRONT, PROJECT, RAFA_SUBJECT, SCOUT, a_derived_world, a_spec_with

DESCRIPTION = "A light reconnaissance walker with a narrow silhouette."
FOUR_TERMS = "mech, walker, quadruped, recon"

MARKERS = (GENERATED, "suggested", "derived", "llm", "vision", "proposed", "machine")
"""Words a marker of model origin would be spelled with. None may reach the file."""


@pytest.fixture
def acceptance() -> dict[str, Any]:
    """The world this scenario runs in, and whatever its steps produced."""
    return {"world": a_derived_world()}


def _world(acceptance: dict[str, Any]):
    return acceptance["world"]


def _suggested(acceptance: dict[str, Any], terms: str = FOUR_TERMS) -> tuple[str, ...]:
    """Generate once, and hand back what is now waiting for a person."""
    world = _world(acceptance)
    world.answering(DESCRIPTION, terms)
    described = ran(world.describe())
    acceptance["described"] = described
    acceptance["before"] = world.spec_text()
    return described.pending


def _changed_lines(before: str, after: str) -> tuple[str, ...]:
    return tuple(
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )


# --------------------------------------------------------------------------
# Rule: Acceptance is a human action
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Nothing is accepted without a person",
)
def test_nothing_is_accepted_without_a_person() -> None: ...


@given("generated suggestions for many assets")
def _suggestions_for_many_assets(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)
    world.always_answering(DESCRIPTION, FOUR_TERMS)
    ran(world.describe())
    acceptance["files"] = dict(world.files())
    acceptance["commits"] = len(world.views.commits())

    assert world.records()


@when("no person acts on them")
def _nobody_acts(acceptance: dict[str, Any]) -> None:
    """Time passes and the suggestions are read. Nothing accepts them."""
    acceptance["listed"] = ran(_world(acceptance).listed())


@then("no specification file SHALL change")
def _no_specification_changed(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    assert acceptance["listed"].pending
    assert world.files() == acceptance["files"]
    assert len(world.views.commits()) == acceptance["commits"]


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Acceptance requires an identified actor",
)
def test_acceptance_requires_an_identified_actor() -> None: ...


@when("acceptance is attempted with no resolvable person")
def _no_resolvable_person(acceptance: dict[str, Any]) -> None:
    _suggested(acceptance)
    acceptance["refusal"] = refused(_world(acceptance).accept("walker", actor=None))


@then("it SHALL be refused")
def _it_is_refused(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    assert acceptance["refusal"].kind is FailureKind.UNAUTHENTICATED
    assert world.aliases() == ()
    assert world.spec_text() == acceptance["before"]


# --------------------------------------------------------------------------
# Rule: Accepted content becomes ordinary authored content
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Accepted alias is a normal alias",
)
def test_accepted_alias_is_a_normal_alias() -> None: ...


@when("a suggested alias is accepted")
def _a_suggestion_is_accepted(acceptance: dict[str, Any]) -> None:
    _suggested(acceptance)
    acceptance["accepted"] = ran(_world(acceptance).accept("walker"))


@then("it SHALL appear in the specification's aliases exactly as a hand-written alias would")
def _appears_as_an_ordinary_alias(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    assert world.aliases() == ("walker",)
    assert "walker" in world.spec_text()


@then("the file SHALL contain no marker distinguishing it")
def _no_marker_in_the_file(acceptance: dict[str, Any]) -> None:
    written = _world(acceptance).spec_text().lower()

    assert not [marker for marker in MARKERS if marker in written]


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Accepted alias ranks as an alias",
)
def test_accepted_alias_ranks_as_an_alias() -> None: ...


@when("a previously suggested alias has been accepted")
def _previously_suggested_then_accepted(acceptance: dict[str, Any]) -> None:
    from cybercanon.application.ports.spec_store import ProjectConfig
    from cybercanon.application.use_cases.index_assets import entry_for

    world = _world(acceptance)
    world.index.upsert(IndexedAsset(asset_id=SCOUT, name="Scout Mech", project=PROJECT))
    _suggested(acceptance)
    acceptance["as_suggestion"] = world.index.search("walker", PROJECT)
    ran(world.accept("walker"))
    world.index.upsert(
        entry_for(
            world.views.spec_store.load("characters/mech_scout/asset.yaml"),
            ProjectConfig(name=PROJECT),
        )
    )


@then("search SHALL rank it as an accepted alias")
def _ranks_as_an_accepted_alias(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)
    (before,) = acceptance["as_suggestion"]

    (hit,) = world.index.search("walker", PROJECT)

    assert before.kind is MatchKind.SUGGESTED_ALIAS
    assert hit.kind is MatchKind.ALIAS
    assert not hit.is_suggestion


# --------------------------------------------------------------------------
# Rule: Acceptance is attributed to the accepting person
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Accepting person recorded",
)
def test_accepting_person_recorded() -> None: ...


@when("a person accepts a suggestion")
def _a_person_accepts(acceptance: dict[str, Any]) -> None:
    _suggested(acceptance)
    acceptance["accepted"] = ran(_world(acceptance).accept("walker"))


@then("the acceptance record SHALL identify that person and the time")
def _the_record_names_the_person(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    (decision,) = [entry for entry in world.index.decisions(project=PROJECT) if entry.accepted]

    assert decision.actor == RAFA_SUBJECT
    assert decision.at == world.moment
    assert acceptance["accepted"].actor == RAFA_SUBJECT


# --------------------------------------------------------------------------
# Rule: Partial acceptance
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Subset accepted",
)
def test_subset_accepted() -> None: ...


@given("four suggested aliases")
def _four_suggested(acceptance: dict[str, Any]) -> None:
    acceptance["pending"] = _suggested(acceptance)

    assert len(acceptance["pending"]) == 4


@when("a person accepts two of them")
def _accepts_two(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)
    acceptance["commits_before"] = len(world.views.commits())
    acceptance["taken"] = (acceptance["pending"][1], acceptance["pending"][3])
    for value in acceptance["taken"]:
        ran(world.accept(value))


@then("exactly those two SHALL be written to the specification")
def _exactly_those_two(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    untouched = set(acceptance["pending"]) - set(acceptance["taken"])

    assert world.aliases() == acceptance["taken"]
    assert not untouched & set(world.aliases())
    assert len(world.views.commits()) == acceptance["commits_before"] + 2


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Edited before acceptance",
)
def test_edited_before_acceptance() -> None: ...


@when("a person edits a suggested value and accepts the edited form")
def _edits_then_accepts(acceptance: dict[str, Any]) -> None:
    _suggested(acceptance)
    acceptance["accepted"] = ran(_world(acceptance).accept("walker", written="Strider Walker"))


@then("the edited value SHALL be written")
def _the_edited_value_is_written(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    assert world.aliases() == ("strider_walker",)
    assert "walker" not in world.aliases()


@then("the acceptance SHALL be attributed to that person")
def _the_edit_is_attributed(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    (decision,) = [entry for entry in world.index.decisions(project=PROJECT) if entry.accepted]

    assert decision.actor == RAFA_SUBJECT
    assert decision.value == "walker"
    assert decision.recorded == "strider_walker"


# --------------------------------------------------------------------------
# Rule: Rejection is recorded and suppresses re-suggestion
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Rejected suggestion does not return",
)
def test_rejected_suggestion_does_not_return() -> None: ...


@given("a suggestion rejected for an image")
def _a_rejected_suggestion(acceptance: dict[str, Any]) -> None:
    _suggested(acceptance)
    ran(_world(acceptance).reject("walker"))


@when("suggestions for that unchanged image are presented again")
def _presented_again(acceptance: dict[str, Any]) -> None:
    acceptance["again"] = ran(_world(acceptance).describe())


@then("the rejected value SHALL NOT appear")
def _the_rejected_value_is_gone(acceptance: dict[str, Any]) -> None:
    again = acceptance["again"]

    assert "walker" not in again.pending
    assert "mech" in again.pending
    assert again.records[0].source_hash == _world(acceptance).source_hash(FRONT)


# --------------------------------------------------------------------------
# Rule: Writes preserve the file a human wrote
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Only the intended change appears",
)
def test_only_the_intended_change_appears() -> None: ...


@given("a specification containing comments and a specific key order")
def _a_hand_authored_specification(acceptance: dict[str, Any]) -> None:
    acceptance["world"] = a_derived_world(spec=a_spec_with(("mech",)))
    acceptance["pending"] = _suggested(acceptance, "walker, recon")


@when("an accepted alias is written into it")
def _an_accepted_alias_is_written(acceptance: dict[str, Any]) -> None:
    ran(_world(acceptance).accept("walker"))
    acceptance["after"] = _world(acceptance).spec_text()


@then("the difference SHALL show only the added alias")
def _only_the_added_alias(acceptance: dict[str, Any]) -> None:
    changed = _changed_lines(acceptance["before"], acceptance["after"])

    assert len(changed) == 2
    assert changed[0].startswith("-aliases:")
    assert changed[1] == "+aliases: [mech, walker]"


@then("comments and key order SHALL be unchanged")
def _comments_and_order_unchanged(acceptance: dict[str, Any]) -> None:
    after = acceptance["after"]

    assert "# The scout. Keep the silhouette readable at 32 px." in after
    assert "# art owns the concept" in after
    assert _keys(after) == _keys(acceptance["before"])


def _keys(text: str) -> list[str]:
    return [
        line.split(":", 1)[0]
        for line in text.splitlines()
        if line and not line[0].isspace() and not line.startswith("#") and ":" in line
    ]


# --------------------------------------------------------------------------
# Rule: Acceptance survives regeneration of its source
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Image replaced after acceptance",
)
def test_image_replaced_after_acceptance() -> None: ...


@given("an accepted alias derived from an image")
def _an_accepted_alias(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)
    world.always_answering(DESCRIPTION, FOUR_TERMS)
    ran(world.describe())
    ran(world.accept("walker"))
    acceptance["after"] = world.spec_text()

    assert world.aliases() == ("walker",)


@when("that image is replaced and metadata is regenerated")
def _replaced_and_regenerated(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)
    world.views.host.push_to_remote(PROJECT, FRONT, world.views.an_image(seed=77))
    world.views.host.fetch(PROJECT)
    acceptance["again"] = ran(world.describe())


@then("the accepted alias SHALL remain in the specification unchanged")
def _the_alias_remains(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    assert acceptance["again"].records[0].source_hash == world.source_hash(FRONT)
    assert world.aliases() == ("walker",)
    assert world.spec_text() == acceptance["after"]


# --------------------------------------------------------------------------
# Rule: A failed write leaves the specification untouched
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/metadata-acceptance.feature",
    "Interrupted write",
)
def test_interrupted_write() -> None: ...


@when("writing an accepted value fails partway")
def _the_write_fails(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)
    _suggested(acceptance)
    world.views.host.reject_next_pushes(PROJECT, times=9)
    acceptance["refusal"] = refused(world.accept("walker"))


@then("the specification file SHALL be unchanged")
def _the_file_is_unchanged(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    assert acceptance["refusal"].kind is FailureKind.CONFLICT
    assert world.spec_text() == acceptance["before"]
    assert world.aliases() == ()


@then("the suggestion SHALL still be pending")
def _the_suggestion_is_still_pending(acceptance: dict[str, Any]) -> None:
    world = _world(acceptance)

    assert world.index.decisions(project=PROJECT) == ()

    world.views.host.reject_next_pushes(PROJECT, times=0)
    assert "walker" in ran(world.listed()).pending
    assert ran(world.accept("walker")).committed
