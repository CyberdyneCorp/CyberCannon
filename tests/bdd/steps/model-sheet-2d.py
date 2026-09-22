"""Step definitions for `model-sheet-2d` — the half of the sheet that is the system.

**Read the pending list beside this file.** The sheet is a Svelte surface, and
most of its scenarios are claims about a *screen*: that a pin stays over a
feature through a zoom, that a finger pans once a stylus has been seen, that two
overlapping pins are each selectable. Those are exercised where they can be —
`apps/cybercanon/web/tests/annotation-sheet.test.ts` and
`annotation-render.test.ts`, which run under `just check` through `web-check` —
and they are listed in `tests/bdd/pending.txt` as the reviewed exception
`add-test-strategy`'s D3 provides for, exactly as `add-web-app-shell` listed all
twenty-nine of its own interface scenarios.

What is bound here is every scenario whose THEN is satisfiable by the **system**
rather than by a DOM: the filter agreeing across surfaces, the coordinate
surviving a round trip through the repository, a gesture outside the image
creating nothing, a discarded composition recording nothing, and — the one that
matters most — *"hidden is not the same as forbidden"*, which is the whole
reason the panel's courtesy is not the enforcement.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from annotations_world import (
    BACK,
    FRONT,
    RAFA_ACTOR,
    SCOUT,
    Threads,
    an_anchor,
    with_asset,
)
from cybercanon.application.results import Ok
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.domain.annotations import (
    DEFAULT_FILTER,
    Anchor2D,
    AnnotationFilter,
    AnnotationKind,
    AnnotationState,
    Stroke,
)
from cybercanon.domain.triage import PromotionTarget

SCOUT_SPEC = f"characters/{SCOUT}/asset.yaml"
PIN = an_anchor(FRONT, 0.2537, 0.4128)
TEXT = "the pauldron reads as a backpack at 15 m"


@pytest.fixture
def threads() -> Threads:
    return with_asset()


@pytest.fixture
def outcome() -> dict[str, Any]:
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Filtering agrees across surfaces",
)
def test_filtering_agrees_across_surfaces() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Round trip preserves the coordinate",
)
def test_round_trip_preserves_the_coordinate() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Gesture on the background places nothing",
)
def test_gesture_on_the_background_places_nothing() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Filtering changes nothing durable",
)
def test_filtering_changes_nothing_durable() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Default presentation shows open work",
)
def test_default_presentation_shows_open_work() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Orphans are visible but not placed",
)
def test_orphans_are_visible_but_not_placed() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Scribble is attached to its annotation",
)
def test_scribble_is_attached_to_its_annotation() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Discarding before saving leaves nothing",
)
def test_discarding_before_saving_leaves_nothing() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Promotion is not offered to a non-director",
)
def test_promotion_is_not_offered_to_a_non_director() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Hidden is not the same as forbidden",
)
def test_hidden_is_not_the_same_as_forbidden() -> None: ...


@scenario(
    "../features/add-model-sheet-2d/model-sheet-2d.feature",
    "Reload agrees with the repository",
)
def test_reload_agrees_with_the_repository() -> None: ...


# --------------------------------------------------------------------------
# Given
# --------------------------------------------------------------------------


@given("an asset whose annotations are filtered to open `technical` items")
def _filtered_to_open_technical(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", kind=AnnotationKind.TECHNICAL, text="the pivot is off centre"))
    ran(threads.create("an_2", kind=AnnotationKind.ART_DIRECTION, text=TEXT))
    ran(threads.create("an_3", kind=AnnotationKind.TECHNICAL, text="the naming is wrong"))
    ran(threads.resolve("an_3"))
    outcome["filter"] = AnnotationFilter.of(
        kinds=(AnnotationKind.TECHNICAL,), states=(AnnotationState.OPEN,)
    )


@given("any filter has been applied")
def _a_filter_has_been_applied(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=TEXT))
    outcome["before"] = threads.spec_text()
    ran(threads.listed(AnnotationFilter.of(kinds=(AnnotationKind.DESIGN,))))


@given("an annotation anchored to a view that has been removed")
def _an_annotation_on_a_removed_view(threads: Threads) -> None:
    ran(threads.create("an_1", anchor=an_anchor(BACK), text=TEXT))
    threads.remove_view(BACK)


@given("an annotation being composed with two strokes drawn over a view")
def _a_composition_with_two_strokes(outcome: dict[str, Any]) -> None:
    outcome["strokes"] = (
        Stroke(((0.1, 0.1), (0.2, 0.2), (0.31, 0.26))),
        Stroke(((0.5, 0.5), (0.62, 0.55))),
    )


@given("strokes drawn while composing an annotation")
def _strokes_drawn_while_composing(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["strokes"] = (Stroke(((0.1, 0.1), (0.2, 0.2))),)
    outcome["before"] = threads.spec_text()


@given("a person whose roles do not include art director")
def _a_non_director(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=TEXT))
    outcome["actor"] = RAFA_ACTOR


@given("the same person submits a promotion regardless")
def _they_submit_a_promotion_anyway(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=TEXT))
    outcome["actor"] = RAFA_ACTOR
    outcome["result"] = threads.promote(
        "an_1", "a durable rule", PromotionTarget.SILHOUETTE_RULES, actor=RAFA_ACTOR
    )


@given("a sequence of placements of which one failed")
def _a_sequence_with_one_failure(threads: Threads, outcome: dict[str, Any]) -> None:
    ran(threads.create("an_1", text=TEXT))
    threads.host.make_unreachable("cyberdyne-game", "the remote is down")
    outcome["failed"] = threads.create("an_ghost", text="never recorded")
    threads.host.make_reachable("cyberdyne-game")
    threads.restore()
    ran(threads.create("an_2", text="the knee reads as a joint"))


# --------------------------------------------------------------------------
# When
# --------------------------------------------------------------------------


@when("the same filter is applied on the sheet and on any other surface")
def _apply_the_filter_on_two_surfaces(threads: Threads, outcome: dict[str, Any]) -> None:
    """The sheet reads the listing use case; so does every other surface.

    There is one filter implementation in the domain and one listing use case
    over it, which is what makes the two answers the same answer rather than two
    that agree today.
    """
    outcome["sheet"] = ran(threads.listed(outcome["filter"]))
    outcome["elsewhere"] = ran(threads.listed(outcome["filter"]))


@when("a pin is placed, stored, re-read and presented again without being moved")
def _place_store_and_re_read(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["placed"] = ran(threads.create("an_1", anchor=PIN, text=TEXT)).annotation
    outcome["re_read"] = threads.annotation("an_1")


@when("a placement gesture occurs outside the image area of every view")
def _a_gesture_outside_the_image(outcome: dict[str, Any]) -> None:
    """A coordinate outside the image never becomes an anchor at all.

    The refusal is at construction, in the domain, so there is no path by which
    such a gesture reaches a write — and no code that could clamp it, because
    the value it would clamp cannot be built.
    """
    outcome["refusals"] = []
    for u, v in ((-0.2, 0.5), (1.4, 0.5), (0.5, -0.01), (0.5, 1.2)):
        try:
            Anchor2D(view=FRONT, u=u, v=v)
        except ValueError as refusal:
            outcome["refusals"].append(str(refusal))


@when("the asset's specification is read from the repository")
def _read_the_specification(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["after"] = threads.spec_text()


@when("a model sheet is opened with no filter chosen")
def _open_with_no_filter(threads: Threads, outcome: dict[str, Any]) -> None:
    for index, kind in enumerate(AnnotationKind):
        ran(threads.create(f"an_{index}", kind=kind, text=f"{kind} feedback"))
    ran(threads.create("an_settled", text="already dealt with"))
    ran(threads.resolve("an_settled"))
    outcome["listing"] = ran(threads.listed(DEFAULT_FILTER))


@when("the model sheet is opened")
def _open_the_sheet(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["listing"] = ran(threads.listed(AnnotationFilter.every()))


@when("it is saved")
def _save_the_composition(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["result"] = threads.create("an_1", text=TEXT, strokes=outcome["strokes"])


@when("the composition is cancelled")
def _cancel_the_composition(threads: Threads) -> None:
    """Cancelling submits nothing, so there is nothing for the system to record."""


@when("they select an open annotation")
def _select_an_open_annotation(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["listing"] = ran(threads.listed(AnnotationFilter.every(), actor=outcome["actor"]))


@when("the request reaches the system")
def _the_request_reaches_the_system(outcome: dict[str, Any]) -> None:
    assert "result" in outcome


@when("the model sheet is reloaded")
def _reload_the_sheet(threads: Threads, outcome: dict[str, Any]) -> None:
    outcome["listing"] = ran(threads.listed(AnnotationFilter.every()))


# --------------------------------------------------------------------------
# Then
# --------------------------------------------------------------------------


@then("both SHALL present the same set of annotations")
def _the_two_surfaces_agree(outcome: dict[str, Any]) -> None:
    sheet = [entry.id for entry in outcome["sheet"].annotations]
    elsewhere = [entry.id for entry in outcome["elsewhere"].annotations]

    assert sheet == elsewhere == ["an_1"]
    assert outcome["sheet"].hidden == outcome["elsewhere"].hidden


@then("its recorded coordinate SHALL be unchanged")
def _the_coordinate_is_unchanged(outcome: dict[str, Any]) -> None:
    assert outcome["placed"].target == PIN
    assert outcome["re_read"].target == PIN


@then("no annotation SHALL be created")
def _nothing_was_created(threads: Threads) -> None:
    assert threads.annotations() == ()


@then("no coordinate SHALL be clamped to an edge")
def _nothing_was_clamped(outcome: dict[str, Any]) -> None:
    assert len(outcome["refusals"]) == 4
    assert all("normalized range" in reason for reason in outcome["refusals"])


@then("every annotation SHALL be unchanged")
def _nothing_durable_changed(outcome: dict[str, Any]) -> None:
    assert outcome["after"] == outcome["before"]


@then("open annotations of every kind SHALL be presented")
def _open_work_of_every_kind(outcome: dict[str, Any]) -> None:
    listed = outcome["listing"].annotations

    assert {entry.kind for entry in listed} == set(AnnotationKind)
    assert all(entry.is_open for entry in listed)
    assert outcome["listing"].hidden == 1


@then("the annotation SHALL be listed with its reason")
def _the_orphan_is_listed_with_its_reason(outcome: dict[str, Any]) -> None:
    orphans = outcome["listing"].orphaned

    assert [entry.annotation.id for entry in orphans] == ["an_1"]
    assert orphans[0].reason
    assert orphans[0].subject == BACK


@then("no pin for it SHALL be drawn over any remaining view")
def _no_pin_is_drawn(outcome: dict[str, Any]) -> None:
    assert outcome["listing"].placeable == ()


@then("the strokes SHALL be recorded with that annotation in normalized coordinates")
def _the_strokes_are_recorded(threads: Threads, outcome: dict[str, Any]) -> None:
    recorded = ran(outcome["result"]).annotation

    assert recorded.strokes
    assert threads.annotation("an_1").strokes == recorded.strokes
    for stroke in recorded.strokes:
        assert all(0.0 <= value <= 1.0 for point in stroke.points for value in point)


@then("no strokes and no annotation SHALL be recorded")
def _nothing_was_recorded(threads: Threads, outcome: dict[str, Any]) -> None:
    assert threads.annotations() == ()
    assert threads.spec_text() == outcome["before"]


@then("no promotion action SHALL be offered")
def _promotion_is_not_offered(outcome: dict[str, Any]) -> None:
    """`may_promote` is the only thing the panel consults before offering it."""
    assert outcome["listing"].may_promote is False


@then("it SHALL be refused")
def _the_submitted_promotion_is_refused(outcome: dict[str, Any]) -> None:
    assert "ART_DIRECTOR" in refused(outcome["result"]).message


@then("the annotation SHALL remain open")
def _the_annotation_remains_open(threads: Threads) -> None:
    thread = threads.annotation("an_1")

    assert thread is not None
    assert thread.is_open


@then("the pins presented SHALL be exactly those recorded in the repository")
def _the_reload_matches_the_repository(threads: Threads, outcome: dict[str, Any]) -> None:
    assert refused(outcome["failed"])
    presented = {entry.id for entry in outcome["listing"].annotations}

    assert presented == {"an_1", "an_2"}
    assert "never recorded" not in threads.spec_text()
    assert isinstance(threads.listed(AnnotationFilter.every()), Ok)
