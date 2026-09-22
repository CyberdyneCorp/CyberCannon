"""Step definitions for `annotation-triage` — the two exits, and the pass over them.

This is the loop `openspec/project.md` calls the heart of the product: *"the one
that makes teams converge instead of just recording disagreements more neatly."*
So the scenarios that matter most here are the negative ones — a second exit
refused, a promotion that would invalidate the specification refused, a
briefing that does not grow — and every one of them runs against a real
`asset.yaml` in a real repository, because all three are claims about a file.

The arrangement is `tests/annotations_world.py`, shared with the unit suite and
with `annotation-authoring`'s steps.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from annotations_world import (
    ANA_ACTOR,
    AUTHORED,
    DIRECTOR,
    FRONT,
    OUTSIDER,
    PROJECT,
    RAFA_ACTOR,
    SCOUT,
    Threads,
    a_part_anchor,
    a_world,
    an_anchor,
    with_asset,
)
from cybercanon.application.results import Ok
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.domain.annotations import AnnotationKind, AnnotationState
from cybercanon.domain.identity import AgentId
from cybercanon.domain.triage import PromotionTarget

SCOUT_SPEC = f"characters/{SCOUT}/asset.yaml"
MULE_SPEC = "vehicles/mule/asset.yaml"
MULE = b"schema_version: 1\nid: mule\nname: Mule\nstatus: modeling\nconcept:\n  views: [front]\n"

EMISSIVE = "the lens glow is always emissive"
AGENT = AgentId("blender-agent")


@pytest.fixture
def threads() -> Threads:
    """A project whose `mech_scout` declares three views and holds no feedback."""
    return with_asset()


@pytest.fixture
def outcome() -> dict[str, Any]:
    return {}


def _briefing(threads: Threads, path: str = SCOUT_SPEC) -> str:
    compiled = compile_spec(path, spec_store=threads.spec_store)
    assert isinstance(compiled, Ok), compiled
    return compiled.value.text


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Only two exits are offered",
)
def test_only_two_exits_are_offered() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "A second exit is refused",
)
def test_a_second_exit_is_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Promotion lands the rule",
)
def test_promotion_lands_the_rule() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Promotion with no destination refused",
)
def test_promotion_with_no_destination_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Failed write leaves nothing half-done",
)
def test_failed_write_leaves_nothing_half_done() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Artist attempting promotion refused",
)
def test_artist_attempting_promotion_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Refusal does not remove other exits",
)
def test_refusal_does_not_remove_other_exits() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Art director's agent refused",
)
def test_art_directors_agent_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Promotion is absent from the agent surface",
)
def test_promotion_is_absent_from_the_agent_surface() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Promotion is visible in history",
)
def test_promotion_is_visible_in_history() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Index rebuild preserves the promotion",
)
def test_index_rebuild_preserves_the_promotion() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Invalid resulting constraint refused",
)
def test_invalid_resulting_constraint_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Resolved annotation leaves the briefing",
)
def test_resolved_annotation_leaves_the_briefing() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "An uninvolved person may not resolve",
)
def test_an_uninvolved_person_may_not_resolve() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Settling many issues does not inflate the briefing",
)
def test_settling_many_issues_does_not_inflate_the_briefing() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Promotion adds a rule, not a thread",
)
def test_promotion_adds_a_rule_not_a_thread() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Reopening a resolved issue",
)
def test_reopening_a_resolved_issue() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Reopening a promotion refused",
)
def test_reopening_a_promotion_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Repeated feedback rises",
)
def test_repeated_feedback_rises() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Queue is filterable for a pass",
)
def test_queue_is_filterable_for_a_pass() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Queue needs no derived store",
)
def test_queue_needs_no_derived_store() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Same exit, either medium",
)
def test_same_exit_either_medium() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-triage.feature",
    "Mixed queue is ordered by the same signals",
)
def test_mixed_queue_is_ordered_by_the_same_signals() -> None: ...


# --------------------------------------------------------------------------
# Given
# --------------------------------------------------------------------------


@given("an open annotation")
@given("an open annotation stating that the lens glow is always emissive")
def _an_open_annotation(threads: Threads) -> None:
    ran(threads.create("an_1", text=EMISSIVE))


@given("an annotation that has been resolved")
@given("a resolved annotation")
def _a_resolved_annotation(threads: Threads) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    ran(threads.resolve("an_1"))


@given("a promoted annotation")
def _a_promoted_annotation(threads: Threads) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    ran(threads.promote("an_1", EMISSIVE))


@given("a promotion whose write to the repository fails")
def _a_failing_promotion(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    outcome["before"] = threads.spec_text()
    threads.host.make_unreachable(PROJECT, "the remote is down")
    outcome["result"] = threads.promote("an_1", EMISSIVE)
    threads.host.make_reachable(PROJECT)
    threads.restore()


@given("an open annotation and a person whose roles do not include art director")
def _an_annotation_and_an_artist(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    outcome["actor"] = RAFA_ACTOR


@given("a person who was refused promotion")
def _a_refused_promoter(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    outcome["actor"] = RAFA_ACTOR
    assert refused(threads.promote("an_1", EMISSIVE, actor=RAFA_ACTOR))


@given("an automated caller acting on behalf of an art director")
def _a_directors_agent(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    outcome["before"] = threads.spec_text()
    outcome["via"] = AGENT


@given("a promoted annotation and a rule written by that promotion")
def _a_promotion_to_rebuild(threads: Threads) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    ran(threads.promote("an_1", EMISSIVE))


@given("a promotion that would set a triangle budget below the first LOD's count")
def _an_invalid_promotion(threads: Threads, outcome: dict[str, Any]) -> None:
    """`AUTHORED` declares `lods: [8000, 4000]`, so a budget of 4000 is below it."""
    threads.replace_spec(AUTHORED.encode())
    ran(threads.create("an_1", text="the mesh is too heavy"))
    outcome["before"] = threads.spec_text()
    outcome["rule"] = "tri_budget: 4000"


@given("an asset with one open and one just-resolved annotation")
def _one_open_one_resolved(threads: Threads) -> None:
    ran(threads.create("an_open", text="the pauldron reads as a backpack"))
    ran(threads.create("an_settled", text="the antenna is too short"))
    ran(threads.resolve("an_settled"))


@given(
    "a person who is neither the author, nor a discipline owner of the asset, nor an art director"
)
def _an_uninvolved_person(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    outcome["actor"] = OUTSIDER


@given("an asset whose briefing is compiled with no open annotations")
def _a_briefing_with_nothing_open(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["first"] = _briefing(threads)


@given("an annotation with six replies that is promoted")
def _a_promoted_thread(threads: Threads) -> None:
    ran(threads.create("an_1", text="the lens glow should always be emissive"))
    for index in range(6):
        ran(threads.reply("an_1", f"re_{index}", f"reply {index}", actor=ANA_ACTOR))
    ran(threads.promote("an_1", EMISSIVE))


@given("an asset with four open `art-direction` annotations and another with one")
def _four_and_one(threads: Threads) -> None:
    threads.host.push_to_remote(PROJECT, MULE_SPEC, MULE)
    threads.host.fetch(PROJECT, confirmed_at=threads.clock())
    for index in range(4):
        ran(threads.create(f"an_{index}", text=f"scout issue {index}"))
    ran(
        threads.create(
            "mu_1", asset_id="mule", text="the tailgate reads as a door", anchor=an_anchor(FRONT)
        )
    )


@given("a project with annotations of all three kinds")
def _all_three_kinds(threads: Threads) -> None:
    for index, kind in enumerate(AnnotationKind):
        ran(threads.create(f"an_{index}", kind=kind, text=f"{kind} feedback"))


@given("every derived index has been deleted")
def _no_index_at_all(threads: Threads) -> None:
    """There is no index in this arrangement to delete, which is the assertion.

    The queue is computed through `SpecStore` and nothing else, so a caller with
    no index reaches the same answer — *"the queue SHALL be derivable from the
    repository alone"* — and the way that is checked is that nothing here has
    one to lose.
    """
    ran(threads.create("an_1", text=EMISSIVE))


@given("one open annotation with a 2D anchor and one with a 3D anchor, of the same kind and age")
def _one_of_each_form(threads: Threads) -> None:
    threads.parts = ("SM_MechScout_Shoulder_L",)
    ran(threads.create("an_flat", text=EMISSIVE))
    ran(
        threads.create(
            "an_solid", text="the shoulder never breaks the silhouette", anchor=a_part_anchor()
        )
    )


@given("a project whose open annotations use both anchor forms")
def _a_mixed_project(threads: Threads) -> None:
    threads.parts = ("SM_MechScout_Shoulder_L",)
    for index in range(3):
        ran(threads.create(f"an_flat_{index}", text=f"flat issue {index}"))
    ran(threads.create("an_solid", text="the shoulder is over budget", anchor=a_part_anchor()))


# --------------------------------------------------------------------------
# When
# --------------------------------------------------------------------------


@when("the available exits for it are requested")
def _request_the_exits(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["exits"] = ran(threads.exits("an_1"))


@when("it is promoted without first being reopened")
def _promote_without_reopening(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.promote("an_1", EMISSIVE)


@when("an art director promotes it into `concept.silhouette_rules`")
def _a_director_promotes(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.promote(
        "an_1", EMISSIVE, PromotionTarget.SILHOUETTE_RULES, actor=DIRECTOR
    )


@when("a promotion is requested without naming a destination")
def _promote_with_no_destination(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    outcome["result"] = threads.promote("an_1", EMISSIVE, target=None)


@when("the asset is read afterwards")
def _read_the_asset(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["after"] = threads.spec_text()


@when("that person promotes it")
def _that_person_promotes(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.promote("an_1", EMISSIVE, actor=outcome["actor"])


@when("that person resolves the same annotation")
def _that_person_resolves(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.resolve("an_1", actor=outcome["actor"])


@when("it attempts to promote an annotation")
def _the_agent_promotes(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.promote("an_1", EMISSIVE, actor=DIRECTOR, via=outcome["via"])


@when("the operations available to an automated caller are enumerated")
def _enumerate_the_agent_surface(outcome: dict[str, Any]) -> None:
    from cybercanon.adapters.inbound.mcp.tools import TOOL_NAMES

    outcome["tools"] = tuple(TOOL_NAMES)


@when("an art director promotes an annotation")
def _the_director_promotes(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=EMISSIVE))
    outcome["result"] = ran(threads.promote("an_1", EMISSIVE, actor=DIRECTOR))


@when("every derived index is deleted and rebuilt from the repository")
def _rebuild_from_the_repository(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["rebuilt"] = a_world(threads.files())


@when("the promotion is submitted")
def _submit_the_promotion(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.promote("an_1", outcome["rule"], PromotionTarget.CONSTRAINTS)


@when("the asset's specification is compiled")
@when("the briefing is compiled")
def _compile_the_briefing(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["briefing"] = _briefing(threads)


@when("they attempt to resolve the annotation")
def _they_attempt_to_resolve(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.resolve("an_1", actor=outcome["actor"])


@when("twenty annotations are created and then all resolved")
def _twenty_settled(threads: Threads) -> None:
    for index in range(20):
        ran(threads.create(f"an_{index}", text=f"issue {index}"))
    for index in range(20):
        ran(threads.resolve(f"an_{index}"))


@when("the briefing is compiled again")
def _compile_again(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["second"] = _briefing(threads)


@when("a person with resolution rights reopens it")
def _reopen_it(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.reopen("an_1")


@when("reopening it is attempted")
def _attempt_to_reopen(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.reopen("an_1", actor=DIRECTOR)


@when("the project's triage queue is requested")
@when("the triage queue is requested")
def _request_the_queue(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["queue"] = ran(threads.queue())


@when("the queue is requested filtered to `art-direction`")
def _request_the_queue_filtered(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["queue"] = ran(threads.queue(kinds=(AnnotationKind.ART_DIRECTION,)))


@when("each is promoted by an art director into the same destination")
def _promote_both(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["flat"] = ran(
        threads.promote("an_flat", EMISSIVE, PromotionTarget.SILHOUETTE_RULES, actor=DIRECTOR)
    )
    outcome["solid"] = ran(
        threads.promote(
            "an_solid",
            "the shoulder never breaks the silhouette",
            PromotionTarget.SILHOUETTE_RULES,
            actor=DIRECTOR,
        )
    )


# --------------------------------------------------------------------------
# Then
# --------------------------------------------------------------------------


@then("exactly two SHALL be offered: promote and resolve")
def _exactly_two_exits(outcome: dict[str, Any]) -> None:
    assert [str(exit_) for exit_ in outcome["exits"]] == ["promote", "resolve"]


@then("the request SHALL be refused stating that the annotation is already resolved")
def _refused_as_already_resolved(outcome: dict[str, Any]) -> None:
    assert "already resolved" in refused(outcome["result"]).message


@then("that rule SHALL appear among the asset's durable rules")
def _the_rule_landed(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(outcome["result"])
    assert EMISSIVE in threads.spec_text()


@then("the annotation SHALL be marked promoted and SHALL NOT remain open")
def _the_annotation_is_retired(threads: Threads) -> None:
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.state is AnnotationState.PROMOTED
    assert not thread.is_open


@then("the request SHALL be refused naming the two valid destinations")
def _refused_naming_the_destinations(outcome: dict[str, Any]) -> None:
    message = refused(outcome["result"]).message
    assert "constraints" in message
    assert "concept.silhouette_rules" in message


@then("the annotation SHALL remain open")
@then("the annotation SHALL still be open")
def _the_annotation_is_still_open(threads: Threads) -> None:
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.is_open


@then("no partial rule SHALL appear in the asset's durable rules")
def _no_partial_rule(outcome: dict[str, Any]) -> None:
    assert outcome["after"] == outcome["before"]
    assert "silhouette_rules" not in outcome["after"]


@then("the request SHALL be refused naming the required role")
def _refused_naming_the_role(outcome: dict[str, Any]) -> None:
    assert "ART_DIRECTOR" in refused(outcome["result"]).message


@then("the resolution SHALL succeed")
def _the_resolution_succeeded(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(outcome["result"])
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.state is AnnotationState.RESOLVED


@then("the request SHALL be refused")
def _refused(outcome: dict[str, Any]) -> None:
    assert refused(outcome["result"])


@then("the asset's durable rules SHALL be unchanged")
def _the_rules_are_unchanged(threads: Threads, outcome: dict[str, Any]) -> None:
    assert threads.spec_text() == outcome["before"]


DURABLE_WRITES = (
    "promote",
    "set_constraint",
    "add_constraint",
    "write_constraint",
    "set_rule",
    "add_rule",
    "write_rule",
    "set_silhouette",
    "add_silhouette",
    "write_spec",
    "edit_spec",
    "set_spec",
    "update_spec",
)
"""The names an operation that writes a durable rule would plausibly be given.

The same list `tests/unit/test_mcp_tools.py` enumerates, restated here rather
than imported: `tests/unit` is not an importable package from a step module,
and a step that reached into another suite's internals would couple two things
meant to fail independently. Both sides check the same claim against the same
advertised surface, so a divergence is visible immediately.
"""


@then("no operation that writes a durable rule SHALL be among them")
def _no_durable_write_is_advertised(outcome: dict[str, Any]) -> None:
    for tool in outcome["tools"]:
        assert all(f"_{stem}_" not in f"_{tool}_" for stem in DURABLE_WRITES), tool


@then("the repository history SHALL contain a change attributed to that person")
def _attributed_in_history(threads: Threads) -> None:
    from annotations_world import DANA

    assert threads.commits()[-1].author == DANA


@then("that change SHALL show the added rule and the retired annotation")
def _the_change_shows_both(threads: Threads) -> None:
    written = threads.spec_text()
    assert EMISSIVE in written
    assert "state: promoted" in written
    assert threads.commits()[-1].paths == (SCOUT_SPEC,)


@then("the rule SHALL still be present and the annotation SHALL still be retired")
def _the_promotion_survives(outcome: dict[str, Any]) -> None:
    rebuilt = outcome["rebuilt"]
    thread = rebuilt.annotation("an_1")
    assert thread is not None
    assert thread.state is AnnotationState.PROMOTED
    assert EMISSIVE in rebuilt.spec_text()


@then("it SHALL be refused reporting that violation")
def _refused_reporting_the_violation(outcome: dict[str, Any]) -> None:
    assert "lod" in refused(outcome["result"]).message.lower()


@then("the specification file SHALL be unchanged")
def _the_file_is_unchanged(threads: Threads, outcome: dict[str, Any]) -> None:
    assert threads.spec_text() == outcome["before"]


@then("the output SHALL contain the open annotation")
def _contains_the_open_one(outcome: dict[str, Any]) -> None:
    assert "the pauldron reads as a backpack" in outcome["briefing"]


@then("it SHALL NOT contain the resolved one")
def _omits_the_resolved_one(outcome: dict[str, Any]) -> None:
    assert "the antenna is too short" not in outcome["briefing"]


@then("the second output SHALL be identical to the first")
def _byte_identical(outcome: dict[str, Any]) -> None:
    assert outcome["second"] == outcome["first"]


@then("it SHALL contain the promoted rule")
def _contains_the_rule(outcome: dict[str, Any]) -> None:
    assert EMISSIVE in outcome["briefing"]


@then("it SHALL NOT contain the annotation's text or any of its replies")
def _omits_the_thread(outcome: dict[str, Any]) -> None:
    assert "should always be emissive" not in outcome["briefing"]
    assert "reply 0" not in outcome["briefing"]


@then("it SHALL be open again and appear in the triage queue")
def _open_again_and_queued(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(outcome["result"])
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.is_open
    assert "an_1" in {entry.id for entry in ran(threads.queue()).entries}


@then("the reopening SHALL be attributed to that person")
def _the_reopening_is_attributed(threads: Threads) -> None:
    from annotations_world import RAFA_SUBJECT

    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.closed_by == RAFA_SUBJECT


@then("the request SHALL be refused stating that its content is now a rule")
def _refused_as_now_a_rule(outcome: dict[str, Any]) -> None:
    assert "now a rule" in refused(outcome["result"]).message


@then("annotations from the asset with four SHALL be ordered above the single one")
def _recurring_feedback_rises(outcome: dict[str, Any]) -> None:
    entries = outcome["queue"].entries
    assert entries[0].asset == SCOUT
    assert entries[-1].asset == "mule"


@then("each entry SHALL report its same-kind counts, its reply count and its age")
def _each_entry_reports_its_signals(outcome: dict[str, Any]) -> None:
    for entry in outcome["queue"].entries:
        assert entry.same_kind_on_asset >= 1
        assert entry.same_kind_in_project >= 1
        assert entry.replies >= 0
        assert entry.age_seconds >= 0.0


@then("only `art-direction` annotations SHALL be returned")
def _only_art_direction(outcome: dict[str, Any]) -> None:
    entries = outcome["queue"].entries
    assert entries
    assert all(entry.kind is AnnotationKind.ART_DIRECTION for entry in entries)


@then("it SHALL be produced from the repository")
def _produced_from_the_repository(threads: Threads, outcome: dict[str, Any]) -> None:
    from cybercanon.application.use_cases.annotations import list_triage_queue

    assert "an_1" in {entry.id for entry in outcome["queue"].entries}
    assert "search_index" not in list_triage_queue.raising.__code__.co_varnames


@then("both SHALL produce a rule in that destination and be retired")
def _both_produced_a_rule(threads: Threads, outcome: dict[str, Any]) -> None:
    written = threads.spec_text()
    assert EMISSIVE in written
    assert "the shoulder never breaks the silhouette" in written
    for identifier in ("an_flat", "an_solid"):
        thread = threads.annotation(identifier)
        assert thread is not None
        assert thread.state is AnnotationState.PROMOTED


@then("neither outcome SHALL depend on the anchor form")
def _the_outcome_is_form_independent(outcome: dict[str, Any]) -> None:
    flat, solid = outcome["flat"].annotation, outcome["solid"].annotation
    assert flat.state is solid.state
    assert type(flat.target) is not type(solid.target)


@then("ordering SHALL be determined by the same counts and age for both forms")
def _the_queue_orders_both_forms_alike(outcome: dict[str, Any]) -> None:
    entries = outcome["queue"].entries
    forms = {type(entry.annotation.target).__name__ for entry in entries}
    assert len(forms) == 2
    ranks = [entry.rank for entry in entries]
    assert ranks == sorted(ranks)
