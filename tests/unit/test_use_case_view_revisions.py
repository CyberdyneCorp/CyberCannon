"""Groups 4, 5 and 6 — revision history, the carry-or-orphan rule and freshness.

Every read below goes through the repository and nothing else. The blob store is
emptied in the middle of this module on purpose: *"No revision SHALL be
retrievable only from the mirror"* is the kind of claim that is only worth
anything when something has actually taken the mirror away.
"""

from __future__ import annotations

import pytest

from cybercanon.application.results import Invalid, NotFound
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.ingest_views import annotations_on
from cybercanon.application.use_cases.view_revisions import (
    PresentedView,
    Reanchoring,
    anchor_state_for,
    list_reanchorings,
    reanchor_annotation,
    reanchor_path,
    resolve_anchors,
)
from cybercanon.domain.annotations import AnchorState, AnnotationState
from cybercanon.domain.revisions import ContentHash
from views_world import PROJECT, RAFA, SCOUT, SCOUT_DIR, SCOUT_SPEC, a_world, with_asset

pytestmark = pytest.mark.unit

FRONT = f"{SCOUT_DIR}/concept/front.png"


def an_asset_with_annotations(count: int = 4, authored_against: str = "") -> bytes:
    """An `asset.yaml` carrying `count` pins on the `front` view."""
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


def three_revisions(world):
    """One view uploaded and then replaced twice — the shape most tests need."""
    for seed in (1, 2, 3):
        ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=seed)),)))
    return ran(world.revisions())


# --------------------------------------------------------------------------
# 4.1 — listing
# --------------------------------------------------------------------------


def test_three_revisions_are_listed_newest_first_with_exactly_one_current() -> None:
    world = with_asset()

    view = three_revisions(world)

    assert len(view.revisions) == 3
    assert [entry.is_current for entry in view.revisions] == [True, False, False]
    assert view.current is not None


def test_every_entry_carries_an_identifier_a_person_a_time_and_a_hash() -> None:
    world = with_asset()

    view = three_revisions(world)

    for entry in view.revisions:
        assert entry.revision
        assert entry.author == str(RAFA)
        assert entry.at is not None
        assert entry.content_hash is not None
        assert entry.dimensions == "1024x768"


def test_revision_identifiers_are_stable_across_two_listings() -> None:
    world = with_asset()
    three_revisions(world)

    first = [entry.revision for entry in ran(world.revisions()).revisions]
    second = [entry.revision for entry in ran(world.revisions()).revisions]

    assert first == second


def test_listing_a_view_that_was_never_uploaded_is_a_named_not_found() -> None:
    world = with_asset()

    refusal = refused(world.revisions(slot="side"))

    assert isinstance(refusal, NotFound)
    assert "side" in refusal.message


def test_a_slot_name_that_is_not_one_is_refused_as_invalid() -> None:
    world = with_asset()

    assert isinstance(refused(world.revisions(slot="Front View!")), Invalid)


# --------------------------------------------------------------------------
# 4.2 — retrieving one
# --------------------------------------------------------------------------


def test_a_superseded_revision_is_returned_and_labelled_historical() -> None:
    world = with_asset()
    view = three_revisions(world)
    superseded = view.revisions[1]

    retrieved = ran(world.retrieve(superseded.revision))

    assert retrieved.historical
    assert not retrieved.is_current
    assert superseded.revision in retrieved.label
    assert ContentHash.of(retrieved.content) == superseded.content_hash


def test_the_current_revision_is_returned_as_current() -> None:
    world = with_asset()
    view = three_revisions(world)

    retrieved = ran(world.retrieve(view.revisions[0].revision))

    assert retrieved.is_current
    assert retrieved.label == "current"


def test_an_unknown_revision_identifier_is_named_rather_than_substituted() -> None:
    """*"never the current revision as a fallback"* — the whole of the clause."""
    world = with_asset()
    view = three_revisions(world)

    refusal = refused(world.retrieve("no-such-revision"))

    assert isinstance(refusal, NotFound)
    assert "no-such-revision" in refusal.message
    assert view.revisions[0].revision not in refusal.message


# --------------------------------------------------------------------------
# 4.3 — comparing two
# --------------------------------------------------------------------------


def test_a_comparison_carries_every_field_the_specification_enumerates() -> None:
    world = with_asset()
    view = three_revisions(world)
    newer, older = view.revisions[0], view.revisions[1]

    comparison = ran(world.compare(older.revision, newer.revision))

    for side in (comparison.older, comparison.newer):
        assert side.revision and side.author and side.at
        assert side.dimensions == "1024x768"
        assert side.byte_size > 0
        assert side.content_hash.startswith("sha256:")


def test_the_older_revision_is_presented_first_whichever_order_it_was_asked_in() -> None:
    world = with_asset()
    view = three_revisions(world)
    newer, older = view.revisions[0].revision, view.revisions[1].revision

    forwards = ran(world.compare(older, newer))
    backwards = ran(world.compare(newer, older))

    assert forwards.older.revision == older == backwards.older.revision
    assert forwards.newer.revision == newer == backwards.newer.revision


def test_two_historical_revisions_compare_normally() -> None:
    world = with_asset()
    view = three_revisions(world)

    comparison = ran(world.compare(view.revisions[2].revision, view.revisions[1].revision))

    assert not comparison.older.is_current and not comparison.newer.is_current


def test_comparing_a_revision_with_itself_reports_them_identical() -> None:
    world = with_asset()
    view = three_revisions(world)
    only = view.revisions[0].revision

    comparison = ran(world.compare(only, only))

    assert comparison.identical
    assert comparison.older.revision == comparison.newer.revision


# --------------------------------------------------------------------------
# 4.4 — from the repository alone
# --------------------------------------------------------------------------


def test_listing_retrieving_and_comparing_survive_a_wiped_mirror() -> None:
    world = with_asset()
    view = three_revisions(world)
    world.blobs.empty()

    listed = ran(world.revisions())
    retrieved = ran(world.retrieve(view.revisions[1].revision))
    compared = ran(world.compare(view.revisions[2].revision, view.revisions[0].revision))

    assert len(listed.revisions) == 3
    assert retrieved.content
    assert compared.older.revision == view.revisions[2].revision


# --------------------------------------------------------------------------
# 4.5 — removal is a revision
# --------------------------------------------------------------------------


def test_removing_a_view_keeps_its_history_and_leaves_no_current_revision() -> None:
    world = with_asset()
    three_revisions(world)

    ran(world.remove())

    view = ran(world.revisions())
    assert view.is_removed
    assert view.current is None
    assert len([entry for entry in view.revisions if not entry.removed]) == 3
    assert ran(world.retrieve(view.revisions[1].revision)).content


def test_removing_a_view_that_is_not_there_is_a_named_not_found() -> None:
    world = with_asset()

    assert isinstance(refused(world.remove(slot="side")), NotFound)


# --------------------------------------------------------------------------
# 4.6 — truncated history
# --------------------------------------------------------------------------


def test_a_shallow_working_copy_lists_what_it_has_and_says_from_where() -> None:
    world = with_asset()
    view = three_revisions(world)
    world.host.truncate_history(PROJECT, view.revisions[2].revision)

    listed = ran(world.revisions())

    assert not listed.is_complete
    assert listed.truncated_before == view.revisions[2].revision
    assert len(listed.revisions) == 3


# --------------------------------------------------------------------------
# 5.1 to 5.5 — annotations across a replacement
# --------------------------------------------------------------------------


def a_world_with_pins(count: int = 4):
    """A project whose `mech_scout` carries `count` pins on an uploaded `front`."""
    world = a_world({SCOUT_SPEC: an_asset_with_annotations(count)})
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))
    view = ran(world.revisions())
    authored = view.revisions[0].revision
    world.host.push_to_remote(PROJECT, SCOUT_SPEC, an_asset_with_annotations(count, authored))
    world.host.fetch(PROJECT)
    return world, authored


def test_four_pins_are_all_carried_at_an_equal_aspect_ratio() -> None:
    world, authored = a_world_with_pins()

    outcome = ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=2)),)))

    assert (outcome.carried, outcome.orphaned) == (4, 0)
    view = ran(world.revisions())
    annotations = _annotations(world)
    assert all(
        resolved.anchor_state is AnchorState.CARRIED
        for resolved in resolve_anchors(annotations, view)
    )
    assert all(annotation.authored_against == authored for annotation in annotations)


def test_four_pins_are_all_orphaned_at_a_different_aspect_ratio() -> None:
    world, authored = a_world_with_pins()

    outcome = ran(
        world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),))
    )

    assert (outcome.carried, outcome.orphaned) == (0, 4)
    view = ran(world.revisions())
    resolved = resolve_anchors(_annotations(world), view)
    assert all(entry.anchor_state is AnchorState.ORPHANED for entry in resolved)
    assert all(entry.authored_against == authored for entry in resolved)


def test_the_outcome_states_how_many_were_carried_and_how_many_orphaned() -> None:
    world, _ = a_world_with_pins(3)

    outcome = ran(
        world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),))
    )

    assert outcome.carried + outcome.orphaned == 3
    assert outcome.views[0].orphaned == 3


def test_an_orphan_is_still_readable_against_the_revision_it_was_authored_on() -> None:
    world, authored = a_world_with_pins(1)
    ran(world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),)))

    (resolved,) = resolve_anchors(_annotations(world), ran(world.revisions()))

    assert resolved.is_orphaned
    assert resolved.authored_against == authored
    assert ran(world.retrieve(authored)).content
    assert resolved.annotation.target.u == pytest.approx(0.1)


def test_orphaning_is_not_an_exit() -> None:
    """Three open pins, orphaned, and still open — D7 in one assertion."""
    world, _ = a_world_with_pins(3)

    ran(world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),)))

    resolved = resolve_anchors(_annotations(world), ran(world.revisions()))
    assert all(entry.is_open for entry in resolved)
    assert all(entry.annotation.state is AnnotationState.OPEN for entry in resolved)
    assert all(entry.annotation.state is not AnnotationState.RESOLVED for entry in resolved)


def test_an_orphan_still_appears_among_the_open_annotations_of_the_asset() -> None:
    world, _ = a_world_with_pins(1)
    ran(world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),)))

    asset = world.spec_store.load(SCOUT_SPEC).asset

    assert len(asset.open_annotations) == 1


def test_a_pin_placed_against_no_revision_is_orphaned_rather_than_assumed_carried() -> None:
    """*Carried* is a claim, and a claim that cannot be checked is not made."""
    world = a_world({SCOUT_SPEC: an_asset_with_annotations(1)})
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))

    (resolved,) = resolve_anchors(_annotations(world), ran(world.revisions()))

    assert resolved.is_orphaned


# --------------------------------------------------------------------------
# 5.6 — re-anchoring is a human action
# --------------------------------------------------------------------------


def test_a_person_re_anchors_an_orphan_and_is_recorded() -> None:
    world, _ = a_world_with_pins(1)
    ran(world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),)))
    (annotation,) = _annotations(world)

    outcome = ran(
        reanchor_annotation(
            PROJECT,
            SCOUT,
            annotation,
            u=0.2,
            v=0.3,
            repository_host=world.host,
            spec_store=world.spec_store,
            author=RAFA,
            by="rafa",
            at="2026-09-22T12:00:00Z",
        )
    )

    assert outcome.annotation.anchor_state is AnchorState.CARRIED
    assert outcome.annotation.reanchored_by == "rafa"
    assert outcome.annotation.reanchored_at == "2026-09-22T12:00:00Z"
    assert outcome.annotation.text == annotation.text
    assert outcome.annotation.state is AnnotationState.OPEN
    assert reanchor_path(SCOUT, annotation.id) in world.files()


def test_a_recorded_re_anchoring_is_what_makes_the_orphan_carried_on_a_later_read() -> None:
    world, _ = a_world_with_pins(1)
    ran(world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),)))
    (annotation,) = _annotations(world)
    ran(
        reanchor_annotation(
            PROJECT,
            SCOUT,
            annotation,
            u=0.2,
            v=0.3,
            repository_host=world.host,
            spec_store=world.spec_store,
            author=RAFA,
            by="rafa",
            at="2026-09-22T12:00:00Z",
        )
    )

    records = ran(list_reanchorings(PROJECT, SCOUT, repository_host=world.host))
    (resolved,) = resolve_anchors(_annotations(world), ran(world.revisions()), records)

    assert resolved.anchor_state is AnchorState.CARRIED
    assert resolved.reanchored_by == "rafa"


def test_nothing_re_anchors_itself_across_a_second_replacement() -> None:
    world, _ = a_world_with_pins(1)
    ran(world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),)))
    again = world.an_image(seed=5, width=768, height=768)
    ran(world.ingest(uploads=(world.upload(content=again),)))

    (resolved,) = resolve_anchors(_annotations(world), ran(world.revisions()))

    assert resolved.is_orphaned


def test_a_re_anchoring_document_round_trips() -> None:
    record = Reanchoring(
        annotation_id="ann-0",
        asset_id=SCOUT,
        slot="front",
        revision="rev-0003",
        u=0.2,
        v=0.3,
        by="rafa",
        at="2026-09-22T12:00:00Z",
    )

    assert Reanchoring.from_document(record.as_document()) == record
    assert Reanchoring.from_document(b"not json") is None
    assert Reanchoring.from_document(b"[]") is None


def test_re_anchoring_without_a_mapped_author_is_refused() -> None:
    world, _ = a_world_with_pins(1)
    (annotation,) = _annotations(world)

    refusal = refused(
        reanchor_annotation(
            PROJECT,
            SCOUT,
            annotation,
            u=0.2,
            v=0.3,
            repository_host=world.host,
            spec_store=world.spec_store,
            author=None,
            by="rafa",
            at="2026-09-22T12:00:00Z",
        )
    )

    assert ".canon/actors.yaml" in refusal.message


# --------------------------------------------------------------------------
# 6 — freshness (D8)
# --------------------------------------------------------------------------


def test_two_revisions_of_one_view_present_different_identities() -> None:
    world = with_asset()
    first = world.an_image(seed=1)
    ran(world.ingest(uploads=(world.upload(content=first),)))
    before = ran(world.token())
    second = world.an_image(seed=2)

    ran(world.ingest(uploads=(world.upload(content=second),)))
    after = ran(world.token())

    assert before.identity != after.identity
    assert after.content_hash == ContentHash.of(second)


def test_a_replaced_view_is_reported_superseded_and_never_current() -> None:
    world = with_asset()
    shown = ContentHash.of(world.an_image(seed=1))
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=2)),)))

    presented = PresentedView(shown=shown, token=ran(world.token()))

    assert presented.is_superseded
    assert not presented.is_current
    assert not presented.is_stale


def test_a_view_that_has_not_moved_is_current() -> None:
    world = with_asset()
    content = world.an_image(seed=1)
    ran(world.ingest(uploads=(world.upload(content=content),)))

    presented = PresentedView(shown=ContentHash.of(content), token=ran(world.token()))

    assert presented.is_current
    assert not presented.is_superseded


def test_a_token_that_could_not_be_read_marks_the_view_stale_and_never_current() -> None:
    presented = PresentedView(shown=ContentHash.of(b"whatever"), token=None)

    assert presented.is_stale
    assert not presented.is_current
    assert not presented.is_superseded


def test_a_removed_view_has_no_token_and_is_therefore_stale() -> None:
    world = with_asset()
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))
    shown = ran(world.token()).content_hash
    ran(world.remove())

    presented = PresentedView(shown=shown, token=ran(world.token()))

    assert presented.is_stale
    assert not presented.is_current


# --------------------------------------------------------------------------
# the anchor walk, on its own
# --------------------------------------------------------------------------


def test_a_crop_and_a_crop_back_does_not_count_as_never_having_moved() -> None:
    """The walk is per replacement, not end to end — which is the honest reading."""
    world = a_world({SCOUT_SPEC: an_asset_with_annotations(1)})
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))
    authored = ran(world.revisions()).revisions[0].revision
    world.host.push_to_remote(PROJECT, SCOUT_SPEC, an_asset_with_annotations(1, authored))
    world.host.fetch(PROJECT)
    ran(world.ingest(uploads=(world.upload(content=world.an_image(width=768, height=768)),)))
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=7)),)))

    (annotation,) = _annotations(world)
    resolved = anchor_state_for(annotation, ran(world.revisions()))

    assert resolved.anchor_state is AnchorState.ORPHANED


def _annotations(world):
    """The pins on `front`, as the repository currently records them."""
    return annotations_on(world.spec_store.load(SCOUT_SPEC).asset.annotations, "front")
