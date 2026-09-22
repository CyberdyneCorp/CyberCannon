"""Step definitions for `view-versioning` — a view is a file, so git is the history.

Nothing here invents a versioning system. Listing, retrieving and comparing are
reads over
:meth:`~cybercanon.application.ports.repository_host.RepositoryHost.history`, and
the two interesting rules are the ones the specification states out loud: a
replacement never destroys, and an annotation anchored to a replaced view is
**carried or orphaned**, mechanically, with the outcome visible.

The mirror is deliberately emptied in one of these scenarios. *"No revision
SHALL be retrievable only from the mirror"* is worth nothing as a claim and
something as a drill.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.ingest_views import annotations_on
from cybercanon.application.use_cases.view_revisions import (
    list_reanchorings,
    reanchor_annotation,
    resolve_anchors,
)
from cybercanon.domain.annotations import AnchorState, AnnotationState
from views_world import PROJECT, RAFA, SCOUT, SCOUT_SPEC, Views, a_world, with_asset

REANCHORED_BY = "ana"
REANCHORED_AT = "2026-09-22T12:00:00Z"


def an_asset_with_annotations(count: int, authored_against: str = "") -> bytes:
    """An `asset.yaml` carrying `count` open pins on the `front` view."""
    pins = "".join(
        f"  - id: ann-{index}\n"
        f"    author: rafa\n"
        f"    kind: art-direction\n"
        f"    text: the pauldron reads as a backpack\n"
        f"    state: open\n"
        f"    authored_against: {authored_against}\n"
        f"    target:\n"
        f"      view: front\n"
        f"      u: 0.{index + 1}\n"
        f"      v: 0.5\n"
        for index in range(count)
    )
    return (
        "schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: concept\n"
        f"annotations:\n{pins}"
    ).encode()


@pytest.fixture
def views() -> Views:
    return with_asset()


@pytest.fixture
def history() -> dict[str, Any]:
    """What this scenario arranged, and what the reads answered."""
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Three uploads, three revisions",
)
def test_three_uploads_three_revisions() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Removing a view keeps its history",
)
def test_removing_a_view_keeps_its_history() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "An identical re-upload is not a revision",
)
def test_an_identical_re_upload_is_not_a_revision() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "A revision list is complete and ordered",
)
def test_a_revision_list_is_complete_and_ordered() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Revision identifiers are stable",
)
def test_revision_identifiers_are_stable() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "A removed view has no current revision",
)
def test_a_removed_view_has_no_current_revision() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "A historical revision is labelled",
)
def test_a_historical_revision_is_labelled() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Unknown revision identifier",
)
def test_unknown_revision_identifier() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Comparing a superseded revision with the current one",
)
def test_comparing_a_superseded_revision_with_the_current_one() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Argument order does not change the presentation",
)
def test_argument_order_does_not_change_the_presentation() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Comparing two historical revisions",
)
def test_comparing_two_historical_revisions() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Comparing a revision with itself",
)
def test_comparing_a_revision_with_itself() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "History survives a wiped mirror",
)
def test_history_survives_a_wiped_mirror() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Shallow working copy",
)
def test_shallow_working_copy() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Same aspect ratio carries the pins",
)
def test_same_aspect_ratio_carries_the_pins() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "A different aspect ratio orphans the pins",
)
def test_a_different_aspect_ratio_orphans_the_pins() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "The outcome is never silent",
)
def test_the_outcome_is_never_silent() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "An orphan can still be read against its own revision",
)
def test_an_orphan_can_still_be_read_against_its_own_revision() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Orphans still appear in the compiled briefing",
)
def test_orphans_still_appear_in_the_compiled_briefing() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Replacement resolves nothing",
)
def test_replacement_resolves_nothing() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "A person re-anchors an orphan",
)
def test_a_person_re_anchors_an_orphan() -> None: ...


@scenario(
    "../features/add-concept-ingestion/view-versioning.feature",
    "Nothing re-anchors itself",
)
def test_nothing_re_anchors_itself() -> None: ...


# --------------------------------------------------------------------------
# Replacing destroys nothing
# --------------------------------------------------------------------------


def _upload(views: Views, seed: int) -> None:
    ran(views.ingest(uploads=(views.upload(content=views.an_image(seed=seed)),)))


@given("a `front` view that has been uploaded and then replaced twice")
def _uploaded_and_replaced_twice(views: Views) -> None:
    for seed in (1, 2, 3):
        _upload(views, seed)


@when("its revisions are listed")
def _its_revisions_are_listed(views: Views, history: dict[str, Any]) -> None:
    history["listed"] = ran(views.revisions())


@then("three revisions SHALL be listed and each SHALL be retrievable")
def _three_and_each_retrievable(views: Views, history: dict[str, Any]) -> None:
    listed = history["listed"]
    assert len(listed.revisions) == 3
    for entry in listed.revisions:
        assert ran(views.retrieve(entry.revision)).content


@given("a view with two revisions")
def _a_view_with_two_revisions(views: Views, history: dict[str, Any]) -> None:
    for seed in (1, 2):
        _upload(views, seed)
    history["before"] = ran(views.revisions()).revisions


@when("the view is removed")
def _the_view_is_removed(views: Views, history: dict[str, Any]) -> None:
    history["removal"] = ran(views.remove())
    history["listed"] = ran(views.revisions())


@then("both earlier revisions SHALL still be retrievable")
def _both_still_retrievable(views: Views, history: dict[str, Any]) -> None:
    for entry in history["before"]:
        assert ran(views.retrieve(entry.revision)).content


@then("the view SHALL be reported as removed rather than as never having existed")
def _reported_as_removed(history: dict[str, Any]) -> None:
    listed = history["listed"]
    assert listed.is_removed
    assert listed.current is None
    assert len(listed.revisions) == 3


@given("a view whose current revision has a given content hash")
def _a_view_with_a_known_hash(views: Views, history: dict[str, Any]) -> None:
    history["content"] = views.an_image(seed=1)
    ran(views.ingest(uploads=(views.upload(content=history["content"]),)))
    history["commits"] = len(views.commits())


@when("a byte-identical image is uploaded to the same slot")
def _the_same_bytes_again(views: Views, history: dict[str, Any]) -> None:
    history["outcome"] = ran(views.ingest(uploads=(views.upload(content=history["content"]),)))


@then("no new revision SHALL be created")
def _no_new_revision(views: Views, history: dict[str, Any]) -> None:
    assert len(views.commits()) == history["commits"]
    assert len(ran(views.revisions()).revisions) == 1


@then("the result SHALL report the view as unchanged")
def _reported_unchanged(history: dict[str, Any]) -> None:
    outcome = history["outcome"]
    assert not outcome.committed
    assert outcome.unchanged == ("front",)


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


@given("a view with three revisions")
def _a_view_with_three_revisions(views: Views) -> None:
    for seed in (1, 2, 3):
        _upload(views, seed)


@then("three entries SHALL be returned newest first")
def _three_newest_first(views: Views, history: dict[str, Any]) -> None:
    listed = history["listed"]
    assert len(listed.revisions) == 3
    times = [entry.at for entry in listed.revisions]
    assert times == sorted(times, reverse=True)


@then("each SHALL carry an identifier, a person, a time and a content hash")
def _each_carries_four_things(history: dict[str, Any]) -> None:
    for entry in history["listed"].revisions:
        assert entry.revision
        assert entry.author == str(RAFA)
        assert entry.at is not None
        assert entry.content_hash is not None


@then("exactly one SHALL be marked current")
def _exactly_one_current(history: dict[str, Any]) -> None:
    assert sum(entry.is_current for entry in history["listed"].revisions) == 1


@when("the same view's revisions are listed twice with no intervening change")
def _listed_twice(views: Views, history: dict[str, Any]) -> None:
    for seed in (1, 2):
        _upload(views, seed)
    history["first"] = ran(views.revisions())
    history["second"] = ran(views.revisions())


@then("both listings SHALL report the same identifiers for the same revisions")
def _same_identifiers(history: dict[str, Any]) -> None:
    assert [entry.revision for entry in history["first"].revisions] == [
        entry.revision for entry in history["second"].revisions
    ]


@given("a view that has been removed")
def _a_removed_view(views: Views, history: dict[str, Any]) -> None:
    for seed in (1, 2):
        _upload(views, seed)
    history["before"] = ran(views.revisions()).revisions
    ran(views.remove())


@then("the earlier revisions SHALL be listed and none SHALL be marked current")
def _listed_with_none_current(history: dict[str, Any]) -> None:
    listed = history["listed"]
    assert not any(entry.is_current for entry in listed.revisions)
    assert {entry.revision for entry in history["before"]} <= {
        entry.revision for entry in listed.revisions
    }


# --------------------------------------------------------------------------
# Retrieving one
# --------------------------------------------------------------------------


@when("a superseded revision is retrieved by its identifier")
def _a_superseded_revision(views: Views, history: dict[str, Any]) -> None:
    for seed in (1, 2):
        _upload(views, seed)
    history["superseded"] = ran(views.revisions()).revisions[1]
    history["retrieved"] = ran(views.retrieve(history["superseded"].revision))


@then("its image SHALL be returned")
def _the_image_is_returned(history: dict[str, Any]) -> None:
    from cybercanon.domain.revisions import ContentHash

    retrieved = history["retrieved"]
    assert retrieved.content
    assert ContentHash.of(retrieved.content) == history["superseded"].content_hash


@then("it SHALL be labelled historical with its revision identifier")
def _labelled_historical(history: dict[str, Any]) -> None:
    retrieved = history["retrieved"]
    assert retrieved.historical
    assert retrieved.revision in retrieved.label


@when("a revision identifier that does not belong to the view is requested")
def _an_unknown_identifier(views: Views, history: dict[str, Any]) -> None:
    _upload(views, 1)
    history["current"] = ran(views.revisions()).revisions[0]
    history["refusal"] = refused(views.retrieve("no-such-revision"))


@then("an explicit not-found result naming the identifier SHALL be returned")
def _not_found_naming_it(history: dict[str, Any]) -> None:
    refusal = history["refusal"]
    assert "no-such-revision" in refusal.message
    assert refusal.identifier == "view.revision_not_found"


@then("the current revision SHALL NOT be returned in its place")
def _no_fallback_to_current(history: dict[str, Any]) -> None:
    assert history["current"].revision not in history["refusal"].message


# --------------------------------------------------------------------------
# Comparing
# --------------------------------------------------------------------------


def _two_revisions(views: Views, history: dict[str, Any]) -> None:
    for seed in (1, 2):
        _upload(views, seed)
    listed = ran(views.revisions()).revisions
    history["r2"], history["r1"] = listed[0].revision, listed[1].revision


@given("a view with revisions `r1` and `r2` where `r2` is current")
def _r1_and_r2(views: Views, history: dict[str, Any]) -> None:
    _two_revisions(views, history)


@when("the two are compared")
def _the_two_are_compared(views: Views, history: dict[str, Any]) -> None:
    history["comparison"] = ran(views.compare(history["r1"], history["r2"]))


@then(
    "both images SHALL be presented with their identifier, person, time, "
    "dimensions, byte size and content hash"
)
def _both_sides_are_complete(history: dict[str, Any]) -> None:
    comparison = history["comparison"]
    for side in (comparison.older, comparison.newer):
        assert side.revision and side.author and side.at
        assert side.dimensions == "1024x768"
        assert side.byte_size > 0
        assert side.content_hash.startswith("sha256:")


@given("revisions `r1` and `r2` of one view")
def _revisions_of_one_view(views: Views, history: dict[str, Any]) -> None:
    _two_revisions(views, history)


@when("they are compared as `r2, r1` and again as `r1, r2`")
def _compared_both_ways(views: Views, history: dict[str, Any]) -> None:
    history["backwards"] = ran(views.compare(history["r2"], history["r1"]))
    history["forwards"] = ran(views.compare(history["r1"], history["r2"]))


@then("both comparisons SHALL present `r1` as the older revision")
def _r1_is_older_both_times(history: dict[str, Any]) -> None:
    assert history["backwards"].older.revision == history["r1"]
    assert history["forwards"].older.revision == history["r1"]


@given("a view with three revisions of which the third is current")
def _three_with_the_third_current(views: Views, history: dict[str, Any]) -> None:
    for seed in (1, 2, 3):
        _upload(views, seed)
    listed = ran(views.revisions()).revisions
    history["third"], history["second"], history["first"] = (
        listed[0].revision,
        listed[1].revision,
        listed[2].revision,
    )


@when("the first and second are compared")
def _first_and_second_compared(views: Views, history: dict[str, Any]) -> None:
    history["comparison"] = ran(views.compare(history["first"], history["second"]))


@then("the comparison SHALL be produced normally")
def _produced_normally(history: dict[str, Any]) -> None:
    comparison = history["comparison"]
    assert comparison.older.revision == history["first"]
    assert comparison.newer.revision == history["second"]
    assert not comparison.older.is_current and not comparison.newer.is_current


@when("a revision is compared with itself")
def _compared_with_itself(views: Views, history: dict[str, Any]) -> None:
    _upload(views, 1)
    only = ran(views.revisions()).revisions[0].revision
    history["comparison"] = ran(views.compare(only, only))


@then("the result SHALL report the two as identical")
def _reported_identical(history: dict[str, Any]) -> None:
    comparison = history["comparison"]
    assert comparison.identical
    assert comparison.older.revision == comparison.newer.revision


# --------------------------------------------------------------------------
# From the repository alone
# --------------------------------------------------------------------------


@given("a view with three revisions and an emptied blob store")
def _three_revisions_no_mirror(views: Views, history: dict[str, Any]) -> None:
    for seed in (1, 2, 3):
        _upload(views, seed)
    history["superseded"] = ran(views.revisions()).revisions[1].revision
    views.blobs.empty()
    assert views.stored_keys() == ()


@when("its revisions are listed and a superseded one is retrieved")
def _listed_and_retrieved(views: Views, history: dict[str, Any]) -> None:
    history["listed"] = ran(views.revisions())
    history["retrieved"] = ran(views.retrieve(history["superseded"]))


@then("both SHALL succeed using the repository")
def _both_succeeded(views: Views, history: dict[str, Any]) -> None:
    assert len(history["listed"].revisions) == 3
    assert history["retrieved"].content
    assert views.stored_keys() == ()


# --------------------------------------------------------------------------
# Truncated history
# --------------------------------------------------------------------------


@given("a working copy whose history is truncated")
def _a_truncated_working_copy(views: Views, history: dict[str, Any]) -> None:
    for seed in (1, 2, 3):
        _upload(views, seed)
    history["oldest"] = ran(views.revisions()).revisions[-1].revision
    views.host.truncate_history(PROJECT, history["oldest"])


@when("a view's revisions are listed")
def _a_views_revisions_are_listed(views: Views, history: dict[str, Any]) -> None:
    history["listed"] = ran(views.revisions())


@then("the available revisions SHALL be listed")
def _available_revisions_listed(history: dict[str, Any]) -> None:
    assert history["listed"].revisions


@then("the result SHALL state that earlier revisions are unavailable and from which point")
def _states_the_truncation_point(history: dict[str, Any]) -> None:
    listed = history["listed"]
    assert not listed.is_complete
    assert listed.truncated_before == history["oldest"]


# --------------------------------------------------------------------------
# Annotations across a replacement
# --------------------------------------------------------------------------


def _pinned(count: int) -> tuple[Views, str]:
    """A project whose `front` view carries `count` pins authored against it."""
    views = a_world({SCOUT_SPEC: an_asset_with_annotations(count)})
    ran(views.ingest(uploads=(views.upload(content=views.an_image(seed=1)),)))
    authored = ran(views.revisions()).revisions[0].revision
    views.host.push_to_remote(PROJECT, SCOUT_SPEC, an_asset_with_annotations(count, authored))
    views.host.fetch(PROJECT)
    return views, authored


@given("a view with four annotations anchored to it")
def _four_pins(history: dict[str, Any]) -> None:
    history["views"], history["authored"] = _pinned(4)


@when("it is replaced by an image of the same aspect ratio")
def _replaced_at_the_same_ratio(history: dict[str, Any]) -> None:
    views = history["views"]
    same_shape = views.an_image(seed=2, width=2048, height=1536)
    history["outcome"] = ran(views.ingest(uploads=(views.upload(content=same_shape),)))
    history["resolved"] = _resolved(views)


@then("all four annotations SHALL be marked carried")
def _all_four_carried(history: dict[str, Any]) -> None:
    assert history["outcome"].carried == 4
    assert all(entry.anchor_state is AnchorState.CARRIED for entry in history["resolved"])


@then("each SHALL still name the revision it was authored against")
def _each_names_its_revision(history: dict[str, Any]) -> None:
    assert all(entry.authored_against == history["authored"] for entry in history["resolved"])


@when("it is replaced by an image of a different aspect ratio")
def _replaced_at_a_different_ratio(history: dict[str, Any]) -> None:
    views = history["views"]
    history["outcome"] = ran(
        views.ingest(uploads=(views.upload(content=views.an_image(width=768, height=768)),))
    )
    history["resolved"] = _resolved(views)


@then("all four annotations SHALL be marked orphaned")
def _all_four_orphaned(history: dict[str, Any]) -> None:
    assert history["outcome"].orphaned == 4
    assert all(entry.is_orphaned for entry in history["resolved"])


@then("none SHALL be displayed at a position on the new revision")
def _none_displayed_on_the_new_revision(history: dict[str, Any]) -> None:
    """An orphan is drawn against its authoring revision or not at all."""
    current = ran(history["views"].revisions()).current
    assert current is not None
    assert all(entry.authored_against != current.revision for entry in history["resolved"])


@when("a view carrying annotations is replaced")
def _a_view_with_pins_is_replaced(history: dict[str, Any]) -> None:
    history["views"], history["authored"] = _pinned(3)
    views = history["views"]
    history["outcome"] = ran(
        views.ingest(uploads=(views.upload(content=views.an_image(width=768, height=768)),))
    )


@then(
    "the result of the replacement SHALL state how many annotations were carried "
    "and how many were orphaned"
)
def _the_counts_are_stated(history: dict[str, Any]) -> None:
    outcome = history["outcome"]
    assert (outcome.carried, outcome.orphaned) == (0, 3)
    assert outcome.views[0].carried + outcome.views[0].orphaned == 3


@given("an orphaned annotation")
def _an_orphaned_annotation(history: dict[str, Any]) -> None:
    history["views"], history["authored"] = _pinned(1)
    views = history["views"]
    ran(views.ingest(uploads=(views.upload(content=views.an_image(width=768, height=768)),)))
    (history["orphan"],) = _resolved(views)
    assert history["orphan"].is_orphaned


@when("it is opened")
def _the_orphan_is_opened(history: dict[str, Any]) -> None:
    history["retrieved"] = ran(history["views"].retrieve(history["authored"]))


@then(
    "the revision it was authored against SHALL be retrievable and its position "
    "on that revision SHALL be shown"
)
def _readable_against_its_own_revision(history: dict[str, Any]) -> None:
    assert history["retrieved"].content
    assert history["retrieved"].revision == history["authored"]
    anchor = history["orphan"].annotation.target
    assert (anchor.view, anchor.u, anchor.v) == ("front", 0.1, 0.5)


# --------------------------------------------------------------------------
# Orphaning is not an exit
# --------------------------------------------------------------------------


@given("an asset with one orphaned open annotation")
def _an_asset_with_one_orphan(history: dict[str, Any]) -> None:
    _an_orphaned_annotation(history)


@when("its briefing is compiled")
def _the_briefing_is_compiled(history: dict[str, Any]) -> None:
    history["briefing"] = ran(compile_spec(SCOUT_SPEC, spec_store=history["views"].spec_store))


@then("that annotation SHALL appear among the open issues")
def _the_orphan_is_in_the_briefing(history: dict[str, Any]) -> None:
    compiled = history["briefing"]
    views = history["views"]

    assert "the pauldron reads as a backpack" in compiled.text
    assert views.spec_store.load(SCOUT_SPEC).asset.open_annotations
    assert history["orphan"].is_orphaned and history["orphan"].is_open


@given("a view with three open annotations")
def _three_open_annotations(history: dict[str, Any]) -> None:
    history["views"], history["authored"] = _pinned(3)


@when("it is replaced such that all three are orphaned")
def _replaced_orphaning_all_three(history: dict[str, Any]) -> None:
    views = history["views"]
    history["outcome"] = ran(
        views.ingest(uploads=(views.upload(content=views.an_image(width=768, height=768)),))
    )
    history["resolved"] = _resolved(views)


@then("all three SHALL still be open")
def _all_three_still_open(history: dict[str, Any]) -> None:
    assert len(history["resolved"]) == 3
    assert all(entry.is_open for entry in history["resolved"])


@then("none SHALL be recorded as promoted or resolved")
def _none_exited(history: dict[str, Any]) -> None:
    states = {entry.annotation.state for entry in history["resolved"]}
    assert states == {AnnotationState.OPEN}


# --------------------------------------------------------------------------
# Re-anchoring
# --------------------------------------------------------------------------


@when("a person re-anchors it to a position on the current revision")
def _a_person_re_anchors(history: dict[str, Any]) -> None:
    views = history["views"]
    history["before"] = history["orphan"].annotation
    history["reanchored"] = ran(
        reanchor_annotation(
            PROJECT,
            SCOUT,
            history["before"],
            u=0.2,
            v=0.3,
            repository_host=views.host,
            spec_store=views.spec_store,
            author=RAFA,
            by=REANCHORED_BY,
            at=REANCHORED_AT,
        )
    )


@then("it SHALL be marked carried against that revision")
def _carried_against_the_current_revision(history: dict[str, Any]) -> None:
    views = history["views"]
    records = ran(list_reanchorings(PROJECT, SCOUT, repository_host=views.host))
    (resolved,) = resolve_anchors(_annotations(views), ran(views.revisions()), records)

    assert resolved.anchor_state is AnchorState.CARRIED
    assert resolved.authored_against == history["reanchored"].record.revision


@then("the person and time of re-anchoring SHALL be recorded")
def _who_and_when_are_recorded(history: dict[str, Any]) -> None:
    record = history["reanchored"].record
    assert (record.by, record.at) == (REANCHORED_BY, REANCHORED_AT)
    assert history["reanchored"].annotation.reanchored_by == REANCHORED_BY
    assert history["reanchored"].annotation.reanchored_at == REANCHORED_AT


@then("its text and its open state SHALL be unchanged")
def _text_and_state_unchanged(history: dict[str, Any]) -> None:
    before, after = history["before"], history["reanchored"].annotation
    assert after.text == before.text
    assert after.state is before.state is AnnotationState.OPEN


@given("an orphaned annotation and a view that is replaced again")
def _an_orphan_and_a_second_replacement(history: dict[str, Any]) -> None:
    _an_orphaned_annotation(history)
    views = history["views"]
    ran(
        views.ingest(uploads=(views.upload(content=views.an_image(seed=9, width=768, height=768)),))
    )


@when("no person re-anchors it")
def _nobody_re_anchors(history: dict[str, Any]) -> None:
    views = history["views"]
    history["records"] = ran(list_reanchorings(PROJECT, SCOUT, repository_host=views.host))
    assert history["records"] == ()


@then("it SHALL still be orphaned")
def _still_orphaned(history: dict[str, Any]) -> None:
    views = history["views"]
    (resolved,) = resolve_anchors(_annotations(views), ran(views.revisions()), history["records"])
    assert resolved.is_orphaned


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------


def _annotations(views: Views):
    return annotations_on(views.spec_store.load(SCOUT_SPEC).asset.annotations, "front")


def _resolved(views: Views):
    return resolve_anchors(_annotations(views), ran(views.revisions()))
