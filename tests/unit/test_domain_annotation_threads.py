"""Tasks 1.1 to 1.4, 1.8 and 1.9 — threads, filtering, marks and orphans, purely.

Everything here runs with no repository, no file and no DOM, which is the claim
`add-model-sheet-2d` makes about its own core: *"threads, filtering, triage,
status are written once and tested with no DOM and no GPU."* A rule that needed
a fixture to be exercised would be a rule the 3D viewer gets to re-decide.

The suite is parameterized over an **anchor factory** wherever the specification
says a behaviour is identical for both forms (D12). `add-viewer-3d` replaces the
stub factory with the real one and adds no cases; if it has to add one, the core
was not shared.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from cybercanon.domain.annotations import (
    MAX_STROKE_POINTS,
    NO_SUCH_PART,
    NO_SUCH_VIEW,
    Anchor,
    Anchor2D,
    Anchor3D,
    AnchorState,
    Annotation,
    AnnotationFilter,
    AnnotationKind,
    AnnotationState,
    Reply,
    Stroke,
    attributed,
    capped,
    marked_orphans,
    open_annotations,
    orphans,
    placeable,
    replaced,
    simplify,
    thread_of,
    without,
)

pytestmark = pytest.mark.unit

VIEW = "front"
PART = "SM_MechScout_Shoulder_L"

RAFA = "auth|rafa"
ANA = "auth|ana"


def a_2d_anchor() -> Anchor:
    return Anchor2D(view=VIEW, u=0.25, v=0.4)


def a_3d_anchor() -> Anchor:
    """The stub D12 asks for: a 3D anchor with no geometry behind it.

    `add-viewer-3d` replaces this with the real construction and every case
    below keeps passing, or the medium-agnostic claim was never true.
    """
    return Anchor3D(part=PART)


ANCHORS: tuple[Callable[[], Anchor], ...] = (a_2d_anchor, a_3d_anchor)
"""The two anchor factories every medium-agnostic case runs against (D12)."""

both_media = pytest.mark.parametrize("anchor", ANCHORS, ids=("2d", "3d"))


def an_annotation(
    identifier: str = "an_1",
    kind: AnnotationKind = AnnotationKind.ART_DIRECTION,
    *,
    anchor: Callable[[], Anchor] = a_2d_anchor,
    author: str = RAFA,
    state: AnnotationState = AnnotationState.OPEN,
    **fields: object,
) -> Annotation:
    return Annotation(
        id=identifier,
        author=author,
        kind=kind,
        text="the pauldron reads as a backpack at 15 m",
        target=anchor(),
        state=state,
        **fields,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------
# 1.1 — a 2D anchor validates itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize("u,v", [(-0.01, 0.5), (1.5, 0.5), (0.5, -2.0), (0.5, 1.000001)])
def test_a_coordinate_outside_the_normalized_range_is_refused(u: float, v: float) -> None:
    with pytest.raises(ValueError, match="normalized range"):
        Anchor2D(view=VIEW, u=u, v=v)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_coordinate_is_refused(value: float) -> None:
    """`nan` compares false against every bound, so a range check alone lets it through."""
    with pytest.raises(ValueError, match="finite"):
        Anchor2D(view=VIEW, u=value, v=0.5)


def test_an_anchor_with_no_view_is_refused() -> None:
    with pytest.raises(ValueError, match="names a view"):
        Anchor2D(view="", u=0.5, v=0.5)


@pytest.mark.parametrize("u,v", [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5)])
def test_the_edges_of_the_range_are_inside_it(u: float, v: float) -> None:
    """A limit that rejected its own value would be a limit nobody could state."""
    assert Anchor2D(view=VIEW, u=u, v=v).durable_key == VIEW


# --------------------------------------------------------------------------
# 1.2 — a reply carries no anchor, no kind and no state of its own
# --------------------------------------------------------------------------


@pytest.mark.parametrize("member", ["target", "anchor", "kind", "state"])
def test_a_reply_cannot_be_constructed_with_a_thread_wide_member(member: str) -> None:
    """A thread has one anchor and one exit; the type has nowhere to put a second."""
    with pytest.raises(TypeError):
        Reply(id="re_1", author=ANA, text="agreed", **{member: "anything"})  # type: ignore[arg-type]


def test_a_reply_has_no_field_for_an_anchor_a_kind_or_a_state() -> None:
    assert {"target", "kind", "state"}.isdisjoint(Reply.__dataclass_fields__)


@both_media
def test_a_thread_presents_its_replies_in_creation_order(anchor) -> None:
    thread = an_annotation(anchor=anchor)
    for index in (1, 2, 3):
        thread = thread.with_reply(Reply(id=f"re_{index}", author=ANA, text=str(index)))

    assert [reply.id for reply in thread.replies] == ["re_1", "re_2", "re_3"]
    assert [reply.id for reply in thread.replies] == [reply.id for reply in thread.replies]


@both_media
def test_a_reply_inherits_the_threads_anchor_and_exit(anchor) -> None:
    thread = an_annotation(anchor=anchor).with_reply(Reply(id="re_1", author=ANA, text="agreed"))

    assert thread.replies[0].id == "re_1"
    assert thread.durable_key == thread.target.durable_key
    assert thread.reply_count == 1


def test_an_edit_leaves_the_author_and_the_anchor_alone() -> None:
    """*"An edit SHALL NOT change the contribution's author or its attribution."*"""
    before = an_annotation(via="blender-agent")

    after = before.with_text("reworded", at="2026-09-22T10:00:00")

    assert after.author == before.author
    assert after.via == before.via
    assert after.target == before.target
    assert after.text == "reworded"


# --------------------------------------------------------------------------
# Attribution — the person, and the agent when one acted
# --------------------------------------------------------------------------


def test_a_person_acting_directly_is_named_alone() -> None:
    assert attributed(RAFA) == RAFA


def test_an_agent_is_named_beside_the_person_it_acted_for() -> None:
    assert attributed("rafa", "blender-agent") == "rafa, via blender-agent"
    assert an_annotation(via="blender-agent").attribution == f"{RAFA}, via blender-agent"


def test_a_reply_renders_its_attribution_the_same_way() -> None:
    """One renderer, because four phrasings is how surfaces start disagreeing."""
    assert Reply(id="re_1", author="ana", text="x", via="claude-code").attribution == (
        "ana, via claude-code"
    )


# --------------------------------------------------------------------------
# 1.4 — filtering, combined, and never a mutation
# --------------------------------------------------------------------------

A_FEW = (
    an_annotation("a1", AnnotationKind.ART_DIRECTION),
    an_annotation("a2", AnnotationKind.TECHNICAL),
    an_annotation("a3", AnnotationKind.DESIGN, state=AnnotationState.RESOLVED),
    an_annotation("a4", AnnotationKind.TECHNICAL, state=AnnotationState.PROMOTED),
)


def test_the_default_filter_shows_open_work_of_every_kind() -> None:
    """*"WHEN a model sheet is opened with no filter chosen THEN open annotations
    of every kind SHALL be presented."*"""
    shown = AnnotationFilter().apply(A_FEW)

    assert [entry.id for entry in shown] == ["a1", "a2"]


def test_a_kind_filter_returns_only_that_kind() -> None:
    shown = AnnotationFilter.of(kinds=(AnnotationKind.TECHNICAL,), states=()).apply(A_FEW)

    assert [entry.id for entry in shown] == ["a2", "a4"]


def test_the_two_filters_combine() -> None:
    wanted = AnnotationFilter.of(kinds=(AnnotationKind.TECHNICAL,), states=(AnnotationState.OPEN,))

    assert [entry.id for entry in wanted.apply(A_FEW)] == ["a2"]


def test_the_filter_reports_how_many_it_is_hiding() -> None:
    assert AnnotationFilter().hidden(A_FEW) == 2


def test_filtering_never_mutates_what_it_filters() -> None:
    before = tuple(A_FEW)

    AnnotationFilter.of(kinds=(AnnotationKind.DESIGN,)).apply(A_FEW)

    assert before == A_FEW
    assert all(first is second for first, second in zip(A_FEW, before, strict=True))


def test_every_filter_at_all_is_expressible_without_a_special_case() -> None:
    assert len(AnnotationFilter.every().apply(A_FEW)) == len(A_FEW)


def test_the_open_set_is_what_the_briefing_carries() -> None:
    assert [entry.id for entry in open_annotations(A_FEW)] == ["a1", "a2"]


# --------------------------------------------------------------------------
# 1.8 — a stroke is normalized polylines, capped by simplification
# --------------------------------------------------------------------------


@pytest.mark.parametrize("absent", ["width", "colour", "color", "layer", "z_order", "opacity"])
def test_a_stroke_has_no_brush_field_of_any_kind(absent: str) -> None:
    """D8: the stored shape is the guardrail, so the absence is the assertion."""
    assert absent not in Stroke.__dataclass_fields__


def test_a_stroke_point_outside_the_image_is_refused() -> None:
    with pytest.raises(ValueError, match="normalized range"):
        Stroke(((0.5, 0.5), (1.2, 0.5)))


def test_a_stroke_point_that_is_not_a_pair_is_refused() -> None:
    with pytest.raises(ValueError, match="pair"):
        Stroke(((0.5, 0.5, 0.5),))  # type: ignore[arg-type]


def test_simplification_keeps_the_ends_of_the_gesture() -> None:
    points = tuple((index / 200, 0.5) for index in range(200))

    thinned = simplify(points)

    assert thinned[0] == points[0]
    assert thinned[-1] == points[-1]


def test_a_scribble_over_the_cap_is_simplified_rather_than_truncated() -> None:
    """*"A stroke exceeding the cap is simplified rather than truncated at the end."*"""
    drawn = Stroke(tuple((index / 2000, 0.5 + (index % 7) / 100) for index in range(2000)))

    kept = capped([drawn])

    assert sum(stroke.length for stroke in kept) <= MAX_STROKE_POINTS
    assert kept[0].points[-1] == drawn.points[-1]
    assert kept[0].points[0] == drawn.points[0]


def test_a_tap_is_not_a_mark() -> None:
    assert capped([Stroke(((0.5, 0.5),))]) == ()


def test_marks_disappear_with_the_annotation_that_carries_them() -> None:
    """*"Marks SHALL disappear with it when it is resolved, promoted or deleted."*"""
    drawn = an_annotation().with_strokes([Stroke(((0.1, 0.1), (0.2, 0.2)))])

    assert drawn.strokes
    assert drawn.resolved().strokes == ()
    assert drawn.promoted().strokes == ()


# --------------------------------------------------------------------------
# 1.9 — orphans, for both anchor forms
# --------------------------------------------------------------------------


def test_a_2d_anchor_naming_an_absent_view_is_an_orphan() -> None:
    found = orphans((an_annotation(anchor=a_2d_anchor),), views=("side", "back"))

    assert [entry.subject for entry in found] == [VIEW]
    assert found[0].reason == NO_SUCH_VIEW


def test_a_3d_anchor_naming_an_absent_part_is_an_orphan() -> None:
    found = orphans((an_annotation(anchor=a_3d_anchor),), parts=("SM_Other",))

    assert [entry.subject for entry in found] == [PART]
    assert found[0].reason == NO_SUCH_PART


@both_media
def test_an_unknown_subject_set_never_declares_an_orphan(anchor) -> None:
    """``None`` is *I do not know*, which is not the same as *it is gone*."""
    assert orphans((an_annotation(anchor=anchor),)) == ()


@both_media
def test_an_orphan_is_never_placed_over_anything(anchor) -> None:
    thread = an_annotation(anchor=anchor).orphaned_by()

    assert placeable((thread,), views=(VIEW,), parts=(PART,)) == ()


def test_an_orphan_stays_open_and_still_owes_an_exit() -> None:
    """`AnchorState` and `AnnotationState` are independent by construction."""
    marked = marked_orphans((an_annotation(),), views=())

    assert marked[0].anchor_state is AnchorState.ORPHANED
    assert marked[0].state is AnnotationState.OPEN
    assert marked[0].is_open


def test_nothing_re_anchors_an_orphan_on_its_own() -> None:
    """The system answers *the named subject is gone* and never *it is over there*."""
    marked = marked_orphans((an_annotation(),), views=("side",))

    assert marked[0].target == an_annotation().target


def test_a_person_moving_an_orphan_clears_it_and_is_recorded() -> None:
    moved = (
        an_annotation()
        .orphaned_by()
        .moved_to(Anchor2D(view="side", u=0.5, v=0.5), by=RAFA, at="2026-09-22T10:00:00")
    )

    assert moved.anchor_state is AnchorState.CARRIED
    assert moved.moved_by == RAFA
    assert moved.moved_at == "2026-09-22T10:00:00"
    assert moved.text == an_annotation().text


# --------------------------------------------------------------------------
# The list operations a write path composes with
# --------------------------------------------------------------------------


def test_replacing_an_annotation_keeps_its_position_in_the_file() -> None:
    """The order in `asset.yaml` is the order a reviewer reads the diff in."""
    listed = (an_annotation("a1"), an_annotation("a2"), an_annotation("a3"))

    after = replaced(listed, an_annotation("a2").with_text("reworded"))

    assert [entry.id for entry in after] == ["a1", "a2", "a3"]
    assert after[1].text == "reworded"


def test_withdrawing_removes_exactly_one() -> None:
    listed = (an_annotation("a1"), an_annotation("a2"))

    assert [entry.id for entry in without(listed, "a1")] == ["a2"]


def test_a_thread_is_found_by_its_identifier_or_not_at_all() -> None:
    listed = (an_annotation("a1"),)

    assert thread_of(listed, "a1") is not None
    assert thread_of(listed, "a2") is None


# --------------------------------------------------------------------------
# The edges of the stroke and reply types
# --------------------------------------------------------------------------


def test_a_non_finite_stroke_point_is_refused() -> None:
    """`nan` compares false against every bound, so a range check alone lets it through."""
    with pytest.raises(ValueError, match="non-finite"):
        Stroke(((0.5, 0.5), (float("nan"), 0.5)))


def test_a_stroke_that_returns_to_where_it_started_still_simplifies() -> None:
    """A closed loop makes the outer segment zero-length — a real pen draws these."""
    points = ((0.5, 0.5), (0.9, 0.9), (0.9, 0.5), (0.5, 0.5))

    thinned = simplify(points, tolerance=0.001)

    assert thinned[0] == thinned[-1] == (0.5, 0.5)
    assert (0.9, 0.9) in thinned


def test_a_reply_can_be_reworded_without_changing_who_said_it() -> None:
    before = Reply(id="re_1", author=ANA, text="agreed", at="2026-09-22T10:00:00")

    after = before.with_text("agreed, with one caveat", at="2026-09-22T11:00:00")

    assert after.author == before.author
    assert after.at == before.at
    assert after.text == "agreed, with one caveat"
    assert after.edited_at == "2026-09-22T11:00:00"


def test_an_annotation_says_which_exit_it_took() -> None:
    thread = an_annotation()

    assert not thread.is_resolved and not thread.is_promoted
    assert thread.resolved().is_resolved
    assert thread.promoted().is_promoted
