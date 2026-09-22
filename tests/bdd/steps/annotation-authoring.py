"""Step definitions for `annotation-authoring` — the first artist-facing writes.

Everything bound here runs against the in-memory repository host holding **real
`asset.yaml` bytes**, with the adapter's own comment-preserving reader and
writer over them and the real use cases on top. There is no index in the
arrangement at all, which is how *"no annotation is readable only from a derived
store"* is checked by what the code can reach rather than by what it happens to
call.

The arrangement is `tests/annotations_world.py`, shared with
`tests/unit/test_use_case_annotations.py`, so a scenario and a unit test
exercise one arrangement rather than two that drift.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from annotations_world import (
    ANA_ACTOR,
    BACK,
    FRONT,
    PROJECT,
    RAFA_ACTOR,
    RAFA_SUBJECT,
    SCOUT,
    SIDE,
    Threads,
    a_part_anchor,
    a_person,
    a_spec,
    a_world,
    an_anchor,
    with_asset,
)
from cybercanon.application.results import Ok
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.domain.annotations import AnnotationFilter, AnnotationKind, AnnotationState, Stroke
from cybercanon.domain.identity import AgentId, Role

SCOUT_SPEC = f"characters/{SCOUT}/asset.yaml"
TEXT = "the pauldron reads as a backpack at 15 m"
AGENT = AgentId("blender-agent")


@pytest.fixture
def threads() -> Threads:
    """A project whose `mech_scout` declares three views and holds no feedback."""
    return with_asset()


@pytest.fixture
def outcome() -> dict[str, Any]:
    """What this scenario did, and what came back."""
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Annotation created on a view",
)
def test_annotation_created_on_a_view() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Anchorless annotation refused",
)
def test_anchorless_annotation_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Anchor naming an absent subject refused",
)
def test_anchor_naming_an_absent_subject_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Unknown kind refused",
)
def test_unknown_kind_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Kind is machine-readable",
)
def test_kind_is_machine_readable() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "New annotation reaches the briefing",
)
def test_new_annotation_reaches_the_briefing() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "New annotation is awaiting triage",
)
def test_new_annotation_is_awaiting_triage() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Reply inherits the thread's anchor",
)
def test_reply_inherits_the_threads_anchor() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Thread order is stable",
)
def test_thread_order_is_stable() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Editing another person's annotation refused",
)
def test_editing_another_persons_annotation_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Deleting a thread with replies refused",
)
def test_deleting_a_thread_with_replies_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Deleting an untouched annotation succeeds",
)
def test_deleting_an_untouched_annotation_succeeds() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Text edit leaves the anchor untouched",
)
def test_text_edit_leaves_the_anchor_untouched() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Move is attributed and visible",
)
def test_move_is_attributed_and_visible() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Agent-originated annotation names both",
)
def test_agent_originated_annotation_names_both() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Submitted author field is ignored",
)
def test_submitted_author_field_is_ignored() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Unattributable contribution refused",
)
def test_unattributable_contribution_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Engineer raises art direction feedback",
)
def test_engineer_raises_art_direction_feedback() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Read-only person refused",
)
def test_read_only_person_refused() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Removed view orphans its annotations",
)
def test_removed_view_orphans_its_annotations() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Orphan can still be resolved",
)
def test_orphan_can_still_be_resolved() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Index rebuild loses nothing",
)
def test_index_rebuild_loses_nothing() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Annotation is visible in version control",
)
def test_annotation_is_visible_in_version_control() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Marks travel with the annotation",
)
def test_marks_travel_with_the_annotation() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Source image untouched",
)
def test_source_image_untouched() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "Same operations, same outcomes across media",
)
def test_same_operations_same_outcomes_across_media() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/annotation-authoring.feature",
    "A mixed list is uniform",
)
def test_a_mixed_list_is_uniform() -> None: ...


# --------------------------------------------------------------------------
# Given
# --------------------------------------------------------------------------


@given("an asset with a view named `front`")
def _an_asset_with_a_front_view(threads: Threads) -> None:
    assert FRONT in ran(threads.listed(AnnotationFilter.every())).views


@given("an asset with views `front` and `side`")
def _an_asset_with_two_views(threads: Threads) -> None:
    threads.replace_spec(a_spec(views=(FRONT, SIDE)))


@given("an asset with annotations of all three kinds")
def _annotations_of_all_three_kinds(threads: Threads) -> None:
    for index, kind in enumerate(AnnotationKind):
        ran(threads.create(f"an_{index}", kind=kind, text=f"{kind} feedback"))


@given("an open annotation anchored to part `SM_MechScout_Shoulder_L`")
def _an_annotation_on_a_part(threads: Threads) -> None:
    threads.parts = ("SM_MechScout_Shoulder_L",)
    ran(threads.create("an_1", anchor=a_part_anchor()))


@given("an annotation with three replies created in a known order")
def _three_replies(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1"))
    for index in range(3):
        ran(threads.reply("an_1", f"re_{index}", f"reply {index}"))
    outcome["order"] = ("re_0", "re_1", "re_2")


@given("an annotation authored by one person")
@given("an annotation anchored at a normalized coordinate within a view")
@given("an annotation with no replies")
@given("an open annotation")
def _one_annotation(threads: Threads) -> None:
    ran(threads.create("an_1"))


@given("an annotation that has at least one reply")
def _an_annotation_with_a_reply(threads: Threads) -> None:
    ran(threads.create("an_1"))
    ran(threads.reply("an_1", "re_1"))


@given("an automated caller acting on behalf of a person")
def _an_agent(outcome: dict[str, Any]) -> None:
    outcome["via"] = AGENT


@given("a credential resolving to one person")
def _a_credential(outcome: dict[str, Any]) -> None:
    outcome["actor"] = RAFA_ACTOR


@given("a person whose only role is engineering")
def _an_engineer(outcome: dict[str, Any]) -> None:
    outcome["actor"] = a_person(RAFA_SUBJECT, roles=(Role.ENGINEER,))


@given("a person with read access but not write access to the project")
def _a_reader(outcome: dict[str, Any]) -> None:
    outcome["mapped"] = False


@given("annotations anchored to a view named `back`")
def _annotations_on_the_back_view(threads: Threads) -> None:
    ran(threads.create("an_1", anchor=an_anchor(BACK)))
    ran(threads.create("an_2", anchor=an_anchor(BACK), text="the vents read as armour"))


@given("an orphaned annotation")
def _an_orphaned_annotation(threads: Threads) -> None:
    ran(threads.create("an_1", anchor=an_anchor(BACK)))
    threads.remove_view(BACK)


@given("an asset with open and replied-to annotations")
def _open_and_replied_to(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", strokes=(Stroke(((0.1, 0.1), (0.4, 0.4))),)))
    ran(threads.reply("an_1", "re_1"))
    ran(threads.create("an_2", text="the knee reads as a joint"))
    outcome["before"] = threads.annotations()


@given("an annotation carrying two freehand strokes")
def _two_strokes(threads: Threads) -> None:
    drawn = (Stroke(((0.1, 0.1), (0.2, 0.2))), Stroke(((0.5, 0.5), (0.6, 0.65))))
    ran(threads.create("an_1", strokes=drawn))


@given("a view image of an asset")
def _a_view_image(threads: Threads, outcome: dict[str, Any]) -> None:
    image = b"\x89PNG\r\n\x1a\nthe scout mech, front elevation"
    threads.host.push_to_remote(PROJECT, f"characters/{SCOUT}/concept/front.png", image)
    threads.host.fetch(PROJECT, confirmed_at=threads.clock())
    outcome["image"] = image


@given("one annotation with a 2D anchor and one with a 3D anchor, otherwise identical")
def _one_of_each_form(threads: Threads) -> None:
    threads.parts = ("SM_MechScout_Shoulder_L",)
    ran(threads.create("an_flat", text=TEXT))
    ran(threads.create("an_solid", text=TEXT, anchor=a_part_anchor()))


@given("an asset carrying annotations of both anchor forms")
def _both_forms(threads: Threads) -> None:
    threads.parts = ("SM_MechScout_Shoulder_L",)
    ran(threads.create("an_flat", kind=AnnotationKind.TECHNICAL, text="the pivot is off centre"))
    ran(
        threads.create(
            "an_solid",
            kind=AnnotationKind.TECHNICAL,
            text="the shoulder is over budget",
            anchor=a_part_anchor(),
        )
    )


# --------------------------------------------------------------------------
# When
# --------------------------------------------------------------------------


@when("an annotation is created against that view at a normalized coordinate")
@when("an annotation is created on an asset")
@when("an annotation is created on an asset of a project")
@when("an annotation is created through any surface")
def _create_an_annotation(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.create(
        "an_1",
        actor=outcome.get("actor", RAFA_ACTOR),
        via=outcome.get("via"),
        mapped=outcome.get("mapped", True),
    )


@when("an annotation is created with no anchor")
def _create_with_no_anchor(threads: Threads, outcome: dict[str, Any]) -> None:
    """The surface refuses this before the use case is reached.

    A draft has no way to carry *no* anchor — the field is not optional — so
    what is exercised is the shape the HTTP surface reads a body into, which is
    where an anchorless request actually arrives.
    """
    from cybercanon.adapters.inbound.http.annotations import _anchor

    outcome["result"] = _anchor(None)


@when("an annotation is created against a view named `three_quarter`")
def _create_against_an_absent_view(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.create("an_1", anchor=an_anchor("three_quarter"))


@when("an annotation is created with kind `nitpick`")
def _create_with_an_unknown_kind(outcome: dict[str, Any]) -> None:
    """A kind outside the set never becomes an `AnnotationKind`, so it never lands."""
    from cybercanon.application.use_cases.annotations import kind_of

    outcome["result"] = kind_of("nitpick")


@when("its annotations are listed filtered to `technical`")
def _list_filtered_to_technical(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["listing"] = ran(
        threads.listed(AnnotationFilter.of(kinds=(AnnotationKind.TECHNICAL,), states=()))
    )


@when("that asset's specification is compiled")
def _compile_the_specification(threads: Threads, outcome: dict[str, Any]) -> None:
    compiled = compile_spec(SCOUT_SPEC, spec_store=threads.spec_store)
    assert isinstance(compiled, Ok), compiled
    outcome["briefing"] = compiled.value.text


@when("a second person replies to it")
def _a_second_person_replies(threads: Threads) -> None:
    ran(threads.reply("an_1", "re_1", actor=ANA_ACTOR))


@when("the thread is read twice")
def _read_the_thread_twice(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["first"] = threads.annotation("an_1")
    outcome["second"] = threads.annotation("an_1")


@when("a different person attempts to edit its text")
def _another_person_edits(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.edit("an_1", "not what they said", actor=ANA_ACTOR)


@when("its author attempts to delete it")
@when("its author deletes it")
def _the_author_deletes_it(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.withdraw("an_1")


@when("its author edits only its text")
def _the_author_edits_the_text(threads: Threads) -> None:
    ran(threads.edit("an_1", "the pauldron is too round"))


@when("an author moves their annotation to a different coordinate in the same view")
def _the_author_moves_it(threads: Threads) -> None:
    ran(threads.create("an_1"))
    ran(threads.move("an_1", an_anchor(FRONT, 0.6, 0.6)))


@when("it creates an annotation")
def _the_agent_creates_an_annotation(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.create("an_1", via=AGENT)


@when("a creation request declares a different person as its author")
def _a_request_declaring_another_author(threads: Threads, outcome: dict[str, Any]) -> None:
    """The draft has no author member at all, which is how the rule stays true."""
    from cybercanon.application.use_cases.annotations import Draft

    outcome["draft_fields"] = set(Draft.__dataclass_fields__)
    outcome["result"] = threads.create("an_1", actor=RAFA_ACTOR)


@when("a creation request cannot be resolved to a person")
def _an_unattributable_request(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.create("an_1", mapped=False)


@when("they create an annotation of kind `art-direction`")
def _they_create_art_direction_feedback(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.create(
        "an_1", actor=outcome["actor"], kind=AnnotationKind.ART_DIRECTION
    )


@when("they attempt to create an annotation")
def _they_attempt_to_create(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.create("an_1", mapped=False)


@when("that view is removed from the asset")
def _remove_the_view(threads: Threads) -> None:
    threads.remove_view(BACK)


@when("it is resolved or promoted")
def _take_an_exit(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.resolve("an_1")


@when("every derived index is deleted and rebuilt from the repository")
def _rebuild_from_the_repository(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["rebuilt"] = a_world(threads.files()).annotations()


@when("the annotation is resolved")
def _resolve_the_annotation(threads: Threads) -> None:
    ran(threads.resolve("an_1"))


@when("freehand marks are drawn over it and saved")
def _draw_and_save_marks(threads: Threads) -> None:
    ran(threads.create("an_1", strokes=(Stroke(((0.1, 0.1), (0.3, 0.4))),)))


@when("the same sequence of reply, edit and filter operations is applied to each")
def _the_same_sequence(threads: Threads, outcome: dict[str, Any]) -> None:
    for identifier in ("an_flat", "an_solid"):
        ran(threads.reply(identifier, f"re_{identifier}", "agreed"))
        ran(threads.edit(identifier, "reworded", actor=RAFA_ACTOR))
    outcome["listing"] = ran(threads.listed(AnnotationFilter.every()))


@when("its annotations are listed filtered by kind and open state")
def _list_by_kind_and_state(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["listing"] = ran(
        threads.listed(
            AnnotationFilter.of(kinds=(AnnotationKind.TECHNICAL,), states=(AnnotationState.OPEN,))
        )
    )


# --------------------------------------------------------------------------
# Then
# --------------------------------------------------------------------------


@then("the annotation SHALL be recorded against the asset with that anchor")
def _recorded_with_that_anchor(threads: Threads, outcome: dict[str, Any]) -> None:
    recorded = ran(outcome["result"]).annotation
    assert recorded.target == an_anchor()


@then("it SHALL be retrievable among the asset's annotations")
def _retrievable(threads: Threads) -> None:
    assert threads.annotation("an_1") is not None


@then("the request SHALL be refused")
def _refused(outcome: dict[str, Any]) -> None:
    result = outcome["result"]
    assert result is None or refused(result)


@then("no annotation SHALL be recorded for the asset")
@then("no annotation SHALL be recorded")
def _nothing_recorded(threads: Threads) -> None:
    assert threads.annotations() == ()


@then("the request SHALL be refused naming `three_quarter` as absent")
def _refused_naming_the_view(outcome: dict[str, Any]) -> None:
    assert "three_quarter" in refused(outcome["result"]).message


@then("the system SHALL NOT attach the annotation to another view")
def _not_attached_elsewhere(threads: Threads) -> None:
    assert threads.annotations() == ()


@then("the request SHALL be refused naming `art-direction`, `technical` and `design`")
def _refused_naming_the_kinds(outcome: dict[str, Any]) -> None:
    from cybercanon.adapters.inbound.http.annotations import _kind_values

    assert outcome["result"] is None
    assert set(_kind_values()) == {"art-direction", "technical", "design"}


@then("only the `technical` annotations SHALL be returned")
def _only_technical(outcome: dict[str, Any]) -> None:
    listed = outcome["listing"].annotations
    assert listed
    assert all(entry.kind is AnnotationKind.TECHNICAL for entry in listed)


@then("the annotation SHALL appear among the asset's open issues")
def _appears_in_the_briefing(outcome: dict[str, Any]) -> None:
    assert TEXT in outcome["briefing"]


@then("it SHALL appear in that project's list of annotations awaiting triage")
def _appears_in_the_queue(threads: Threads) -> None:
    queue = ran(threads.queue())
    assert "an_1" in {entry.id for entry in queue.entries}


@then("the reply SHALL belong to that thread")
def _the_reply_belongs_to_the_thread(threads: Threads) -> None:
    thread = threads.annotation("an_1")
    assert thread is not None
    assert [reply.id for reply in thread.replies] == ["re_1"]


@then("the reply SHALL NOT be independently anchored or independently resolvable")
def _the_reply_has_no_anchor_of_its_own() -> None:
    from cybercanon.domain.annotations import Reply

    assert {"target", "kind", "state"}.isdisjoint(Reply.__dataclass_fields__)


@then("both readings SHALL present the replies in that same order")
def _the_order_is_stable(outcome: dict[str, Any]) -> None:
    first, second = outcome["first"], outcome["second"]
    assert [reply.id for reply in first.replies] == list(outcome["order"])
    assert [reply.id for reply in second.replies] == list(outcome["order"])


@then("the recorded text SHALL be unchanged")
def _the_text_is_unchanged(threads: Threads) -> None:
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.text == TEXT


@then("the request SHALL be refused stating that it may be resolved or promoted")
def _refused_naming_the_exits(outcome: dict[str, Any]) -> None:
    assert "resolve it or promote it" in refused(outcome["result"]).message


@then("the thread SHALL remain readable")
def _the_thread_remains(threads: Threads) -> None:
    assert threads.annotation("an_1") is not None


@then("it SHALL no longer appear among the asset's annotations")
def _gone_from_the_asset(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(outcome["result"])
    assert threads.annotation("an_1") is None


@then("it SHALL NOT appear in the compiled briefing")
def _gone_from_the_briefing(threads: Threads) -> None:
    compiled = compile_spec(SCOUT_SPEC, spec_store=threads.spec_store)
    assert isinstance(compiled, Ok), compiled
    assert TEXT not in compiled.value.text


@then("the anchor SHALL be unchanged")
def _the_anchor_is_unchanged(threads: Threads) -> None:
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.target == an_anchor()


@then("the annotation SHALL record that it was moved and by whom")
def _the_move_is_recorded(threads: Threads) -> None:
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.moved_by == RAFA_SUBJECT
    assert thread.moved_at


@then("the annotation SHALL name that person as responsible")
def _names_the_person(outcome: dict[str, Any]) -> None:
    assert ran(outcome["result"]).annotation.author == RAFA_SUBJECT


@then("it SHALL also name the agent that acted")
def _names_the_agent(outcome: dict[str, Any]) -> None:
    recorded = ran(outcome["result"]).annotation
    assert recorded.via == str(AGENT)
    assert recorded.attribution == f"{RAFA_SUBJECT}, via {AGENT}"


@then("the annotation SHALL be attributed to the person the credential resolves to")
def _attributed_to_the_credential(outcome: dict[str, Any]) -> None:
    assert {"author", "actor", "role", "via"}.isdisjoint(outcome["draft_fields"])
    assert ran(outcome["result"]).annotation.author == RAFA_SUBJECT


@then("it SHALL be refused")
def _it_is_refused(outcome: dict[str, Any]) -> None:
    assert refused(outcome["result"])


@then("the annotation SHALL be created normally")
def _created_normally(outcome: dict[str, Any]) -> None:
    assert ran(outcome["result"]).annotation.kind is AnnotationKind.ART_DIRECTION


@then("reading the asset's annotations SHALL still succeed for them")
def _reading_still_succeeds(threads: Threads) -> None:
    assert isinstance(threads.listed(AnnotationFilter.every(), mapped=False), Ok)


@then("those annotations SHALL be reported as orphaned")
def _reported_as_orphaned(threads: Threads) -> None:
    listing = ran(threads.listed(AnnotationFilter.every()))
    assert {entry.annotation.id for entry in listing.orphaned} == {"an_1", "an_2"}


@then("they SHALL NOT be displayed over any remaining view")
def _not_displayed(threads: Threads) -> None:
    assert ran(threads.listed(AnnotationFilter.every())).placeable == ()


@then("that exit SHALL be recorded normally")
def _the_exit_is_recorded(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(outcome["result"])
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.state is AnnotationState.RESOLVED


@then("every annotation, reply, author and anchor SHALL be identical to before")
def _identical_after_a_rebuild(outcome: dict[str, Any]) -> None:
    assert outcome["rebuilt"] == outcome["before"]


@then("the asset's specification file in the repository SHALL contain it")
def _the_file_contains_it(threads: Threads) -> None:
    assert TEXT in threads.spec_text()


@then("the change SHALL be attributable to the person responsible for it")
def _attributable(threads: Threads) -> None:
    from annotations_world import AUTHORS

    assert threads.commits()[-1].author == AUTHORS[RAFA_SUBJECT]


@then("the strokes SHALL no longer be presented over the view")
def _the_strokes_are_gone(threads: Threads) -> None:
    thread = threads.annotation("an_1")
    assert thread is not None
    assert thread.strokes == ()


@then("the stored view image SHALL be byte-identical to before")
def _the_image_is_untouched(threads: Threads, outcome: dict[str, Any]) -> None:
    path = f"characters/{SCOUT}/concept/front.png"
    assert threads.files()[path] == outcome["image"]


@then("the resulting state of both SHALL differ only in their anchors")
def _identical_but_for_the_anchor(outcome: dict[str, Any]) -> None:
    from dataclasses import replace

    flat, solid = (
        next(entry for entry in outcome["listing"].annotations if entry.id == identifier)
        for identifier in ("an_flat", "an_solid")
    )
    normalised = replace(
        flat,
        id=solid.id,
        target=solid.target,
        replies=solid.replies,
        created_at=solid.created_at,
        edited_at=solid.edited_at,
    )
    assert normalised == solid
    assert flat.target != solid.target


@then("both forms SHALL be returned by the same filter with the same fields present")
def _both_forms_uniform(outcome: dict[str, Any]) -> None:
    from cybercanon.adapters.inbound.http import payloads

    listed = outcome["listing"].annotations
    assert {entry.id for entry in listed} == {"an_flat", "an_solid"}
    rendered = [payloads.annotation(entry) for entry in listed]
    assert set(rendered[0]) == set(rendered[1])
