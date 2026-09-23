"""Group 3 — linking, listing, display, the per-actor cache and create-and-link.

The arrangement is `tests/documents_world.py`: a real repository host holding
real `asset.yaml` bytes, the adapter's own comment-preserving writer over them,
the in-memory document platform beside it and the real use cases on top. So
*"the resulting file diff contains the reference and no document body"* is
asserted against the file, not against a value object somebody built.
"""

from __future__ import annotations

import pytest

from cybercanon.application.ports.document_platform import (
    NO_CREDENTIAL,
    Credential,
    NullDocumentPlatform,
    PlatformUnavailable,
    UnavailabilityReason,
)
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.documents import (
    AVAILABLE_ACTIONS,
    CardCache,
    actions_for,
    default_title,
    where_to_write,
)
from cybercanon.domain.documents import (
    ContentPlacement,
    DocumentCard,
    DocumentRef,
    DocumentScope,
    DocumentState,
)
from documents_world import (
    BRUNO_ACTOR,
    GDD,
    PRIVATE,
    PROSE,
    RAFA_ACTOR,
    RAFA_SUBJECT,
    RATIONALE,
    RESEARCH,
    WORKSPACE,
    Documents,
    a_world,
    with_links,
    with_project_link,
    without_platform,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def documents() -> Documents:
    """A project whose `mech_scout` is hand-authored and links nothing yet."""
    return a_world()


# --------------------------------------------------------------------------
# 3.1, 3.2 — writing and removing a reference
# --------------------------------------------------------------------------


def test_a_link_is_written_into_the_specification_with_its_authorship(
    documents: Documents,
) -> None:
    recorded = ran(documents.link())

    text = documents.spec_text()
    assert recorded.scope is DocumentScope.ASSET
    assert "d_rationale" in text
    assert f"linked_by: {RAFA_SUBJECT}" in text
    assert "linked_at:" in text


def test_the_file_carries_the_reference_and_none_of_the_document_s_body(
    documents: Documents,
) -> None:
    """Task 3.1 and the `Only the reference is authored` scenario, on the file."""
    ran(documents.link())

    text = documents.spec_text()
    assert "courier" not in text
    assert "mech_scout — design rationale" not in text
    for sentence in PROSE.split(". "):
        assert sentence not in text


def test_linking_leaves_every_unrelated_line_of_a_hand_authored_file_untouched(
    documents: Documents,
) -> None:
    before = documents.spec_text()

    ran(documents.link())

    after = documents.spec_text()
    assert after.startswith(before), "the link is appended; nothing before it moves"
    assert "# renaming this is safe" in after
    assert "# engineering fixed these at the kick-off" in after


def test_unlinking_removes_the_reference_and_calls_the_platform_not_at_all(
    documents: Documents,
) -> None:
    """Task 3.2: *"the document SHALL NOT be modified or deleted."*"""
    ran(documents.link())
    calls_before = len(documents.platform.requests)

    ran(documents.unlink())

    assert "d_rationale" not in documents.spec_text()
    assert documents.platform.exists(WORKSPACE, RATIONALE)
    assert len(documents.platform.requests) == calls_before


def test_unlinking_something_that_is_not_linked_is_a_named_refusal(
    documents: Documents,
) -> None:
    outcome = documents.unlink("d_never_linked")

    assert refused(outcome).kind.value == "not_found"
    assert "d_never_linked" in refused(outcome).message


def test_a_person_with_no_mapped_git_identity_cannot_link(documents: Documents) -> None:
    outcome = documents.link(mapped=False)

    assert refused(outcome).kind.value == "forbidden"
    assert "d_rationale" not in documents.spec_text()


def test_linking_the_same_document_twice_writes_it_once(documents: Documents) -> None:
    ran(documents.link())

    ran(documents.link())

    assert documents.spec_text().count("id: d_rationale") == 1


# --------------------------------------------------------------------------
# 3.3, 3.4 — scope and deterministic listing
# --------------------------------------------------------------------------


def test_a_project_scoped_link_is_listed_beside_the_asset_s_own_and_distinguished() -> None:
    documents = with_links(with_project_link(), RATIONALE)

    listing = ran(documents.listed())

    assert [entry.ref.document_id for entry in listing.asset_links] == [RATIONALE]
    assert [entry.ref.document_id for entry in listing.project_links] == [GDD]
    assert [entry.scope for entry in listing.entries] == [
        DocumentScope.ASSET,
        DocumentScope.PROJECT,
    ]


def test_a_project_scoped_link_can_be_written_and_removed_through_the_use_case(
    documents: Documents,
) -> None:
    recorded = ran(documents.link(GDD, scope=DocumentScope.PROJECT))

    assert recorded.path == ".canon/project.yaml"
    assert GDD in documents.project_text()
    assert "golden_rules" in documents.project_text()

    ran(documents.unlink(GDD, scope=DocumentScope.PROJECT))
    assert GDD not in documents.project_text()


def test_two_listings_of_an_unchanged_specification_are_identical(
    documents: Documents,
) -> None:
    with_links(documents, RATIONALE, RESEARCH, PRIVATE)

    first, second = ran(documents.listed()), ran(documents.listed())

    assert [entry.ref for entry in first.entries] == [entry.ref for entry in second.entries]
    assert [entry.state for entry in first.entries] == [entry.state for entry in second.entries]


def test_a_listing_reads_as_documents_when_the_viewer_may_read_them(
    documents: Documents,
) -> None:
    with_links(documents, RATIONALE, RESEARCH)

    listing = ran(documents.listed())

    assert [entry.card.title for entry in listing.entries] == [
        "mech_scout — design rationale",
        "scout silhouette research",
    ]
    assert listing.entries[0].card.summary.startswith("The scout reads as a courier")
    assert listing.is_available


# --------------------------------------------------------------------------
# 3.5 — the per-(reference, actor) cache (D3)
# --------------------------------------------------------------------------


def test_a_second_actor_gets_a_cold_resolve_rather_than_the_first_actor_s_card(
    documents: Documents,
) -> None:
    """D3 in one test: a card Rafa resolved is never served to Bruno."""
    with_links(documents, PRIVATE)
    ran(documents.listed(actor=BRUNO_ACTOR))
    resolves = _resolves(documents)

    rafa = ran(documents.listed(actor=RAFA_ACTOR))

    assert _resolves(documents) > resolves, "Rafa's first view must be a cold resolve"
    assert rafa.entries[0].state is DocumentState.FORBIDDEN
    assert rafa.entries[0].card.discloses_nothing


def test_the_same_actor_viewing_twice_resolves_once(documents: Documents) -> None:
    with_links(documents, RATIONALE)
    ran(documents.listed())
    resolves = _resolves(documents)

    ran(documents.listed())

    assert _resolves(documents) == resolves


def test_the_cache_holds_nothing_durable_and_can_simply_be_dropped(
    documents: Documents,
) -> None:
    """Task 3.9: delete the resolved-card storage, and the links are unchanged."""
    with_links(documents, RATIONALE, RESEARCH)
    before = ran(documents.listed())

    documents.cache.clear()
    assert documents.cache.size == 0
    after = ran(documents.listed())

    assert [entry.ref for entry in before.entries] == [entry.ref for entry in after.entries]
    assert [entry.card.title for entry in after.entries] == [
        entry.card.title for entry in before.entries
    ]


def test_an_unreadable_card_is_never_cached(documents: Documents) -> None:
    """A forbidden answer is re-asked every time: permissions change, cards do not."""
    with_links(documents, PRIVATE)
    ran(documents.listed())
    resolves = _resolves(documents)

    ran(documents.listed())

    assert _resolves(documents) > resolves


def test_a_cache_entry_expires_and_the_card_is_asked_for_again(documents: Documents) -> None:
    with_links(documents, RATIONALE)
    ran(documents.listed())
    resolves = _resolves(documents)

    documents.age(10_000)
    ran(documents.listed())

    assert _resolves(documents) > resolves


# --------------------------------------------------------------------------
# 3.6 — the three states, distinguishable, and one broken link among others
# --------------------------------------------------------------------------


def test_an_unreachable_platform_leaves_every_link_listed_and_openable(
    documents: Documents,
) -> None:
    with_links(documents, RATIONALE, RESEARCH, GDD)
    documents.unavailable(UnavailabilityReason.UNREACHABLE)

    listing = ran(documents.listed())

    assert len(listing.entries) == 3
    assert {entry.state for entry in listing.entries} == {DocumentState.UNREACHABLE}
    assert all(entry.address.startswith("https://") for entry in listing.entries)
    assert listing.unavailable_reason is UnavailabilityReason.UNREACHABLE


def test_a_deleted_document_is_marked_missing_and_its_reference_stays(
    documents: Documents,
) -> None:
    with_links(documents, RATIONALE)
    documents.platform.delete(WORKSPACE, RATIONALE)

    listing = ran(documents.listed())

    assert listing.entries[0].state is DocumentState.MISSING
    assert "d_rationale" in documents.spec_text()


def test_a_forbidden_document_discloses_nothing_and_says_so(documents: Documents) -> None:
    with_links(documents, PRIVATE)

    entry = ran(documents.listed()).entries[0]

    assert entry.state is DocumentState.FORBIDDEN
    assert entry.card.discloses_nothing
    assert entry.card.display_title == entry.address


def test_the_three_states_are_distinguishable_in_one_listing(documents: Documents) -> None:
    with_links(documents, RATIONALE, PRIVATE, RESEARCH)
    documents.platform.delete(WORKSPACE, RESEARCH)

    states = {entry.ref.document_id: entry.state for entry in ran(documents.listed()).entries}

    assert states[RATIONALE] is DocumentState.READABLE
    assert states[PRIVATE] is DocumentState.FORBIDDEN
    assert states[RESEARCH] is DocumentState.MISSING


def test_one_broken_link_does_not_prevent_the_others_from_listing(
    documents: Documents,
) -> None:
    with_links(documents, PRIVATE, RATIONALE)

    listing = ran(documents.listed())

    assert listing.entries[0].state is DocumentState.FORBIDDEN
    assert listing.entries[1].card.title == "mech_scout — design rationale"


# --------------------------------------------------------------------------
# 3.7 — a rename at the source
# --------------------------------------------------------------------------


def test_a_rename_at_the_platform_is_shown_after_the_cache_lifetime(
    documents: Documents,
) -> None:
    with_links(documents, RATIONALE)
    assert ran(documents.listed()).entries[0].card.title == "mech_scout — design rationale"

    documents.platform.rename(WORKSPACE, RATIONALE, "mech_scout — why it reads as a courier")
    documents.age(10_000)

    title = ran(documents.listed()).entries[0].card.title
    assert title == "mech_scout — why it reads as a courier"
    assert "why it reads as a courier" not in documents.spec_text()


# --------------------------------------------------------------------------
# 3.8 — create and link, in that order (D8)
# --------------------------------------------------------------------------


def test_creating_a_document_for_an_asset_links_it_in_one_action(
    documents: Documents,
) -> None:
    recorded = ran(documents.create())

    assert recorded.created is not None
    assert recorded.created.title == default_title("mech_scout")
    assert recorded.created.document_id in documents.spec_text()
    assert f"linked_by: {RAFA_SUBJECT}" in documents.spec_text()


def test_a_created_document_is_pre_titled_from_the_asset_s_identity(
    documents: Documents,
) -> None:
    created = ran(documents.create()).created

    assert created is not None
    assert "mech_scout" in created.title


def test_a_refused_creation_leaves_the_specification_untouched(
    documents: Documents,
) -> None:
    before = documents.spec_text()

    outcome = documents.create(actor=BRUNO_ACTOR)

    assert refused(outcome).kind.value == "forbidden"
    assert documents.spec_text() == before


def test_a_link_that_cannot_be_written_names_the_created_document_and_its_address(
    documents: Documents,
) -> None:
    """D8's accepted cost, made survivable: the orphan is named, not lost."""
    documents.refuse_writes()

    outcome = documents.create()

    message = refused(outcome).message
    assert "was created at" in message
    assert "https://documents.invalid/" in message
    assert documents.platform.created, "the document really was created"


def test_creation_with_no_platform_configured_reports_itself_unavailable(
    documents: Documents,
) -> None:
    unconfigured = without_platform(documents)
    before = unconfigured.spec_text()

    outcome = unconfigured.create()

    refusal = refused(outcome)
    assert refusal.kind.value == "unavailable"
    assert "unconfigured" in refusal.message
    assert unconfigured.spec_text() == before


# --------------------------------------------------------------------------
# Degradation to absent (D4)
# --------------------------------------------------------------------------


def test_with_no_platform_configured_every_reference_is_still_listed_and_openable(
    documents: Documents,
) -> None:
    with_links(documents, RATIONALE, GDD)
    unconfigured = without_platform(documents)

    listing = ran(unconfigured.listed())

    assert [entry.ref.document_id for entry in listing.entries] == [RATIONALE, GDD]
    assert all(entry.address.startswith("https://") for entry in listing.entries)
    assert all(not entry.is_resolved for entry in listing.entries)
    assert listing.unavailable_reason is UnavailabilityReason.UNCONFIGURED


def test_the_null_platform_answers_every_method_the_same_way() -> None:
    """D4: one class, one reason, and no use case branching on configuration."""
    platform = NullDocumentPlatform()
    ref = DocumentRef(workspace="w", document_id="d", url="https://x.invalid/d")

    for call in (
        lambda: platform.resolve((ref,), NO_CREDENTIAL),
        lambda: platform.create("w", "t", NO_CREDENTIAL),
        lambda: platform.search("q", NO_CREDENTIAL),
        lambda: platform.revisions(ref, NO_CREDENTIAL),
    ):
        with pytest.raises(PlatformUnavailable) as failure:
            call()
        assert failure.value.reason is UnavailabilityReason.UNCONFIGURED


def test_a_caller_with_no_forwardable_credential_still_sees_its_links(
    documents: Documents,
) -> None:
    with_links(documents, RATIONALE)

    listing = ran(documents.listed(credentialed=False))

    assert [entry.ref.document_id for entry in listing.entries] == [RATIONALE]
    assert listing.unavailable_reason is UnavailabilityReason.REJECTED
    assert listing.entries[0].card.discloses_nothing


# --------------------------------------------------------------------------
# The version history, surfaced rather than reimplemented
# --------------------------------------------------------------------------


def test_a_linked_document_s_revisions_are_read_through_the_platform(
    documents: Documents,
) -> None:
    with_links(documents, RATIONALE)

    history = ran(documents.revisions())

    assert history.size == 2
    assert [revision.seq for revision in history.revisions] == [2, 1]
    assert history.revisions[0].label == "before retopo"
    assert "before retopo" not in documents.spec_text()


def test_a_document_the_viewer_may_not_read_has_no_listable_history(
    documents: Documents,
) -> None:
    with_links(documents, PRIVATE)

    history = ran(documents.revisions(PRIVATE))

    assert history.state is DocumentState.FORBIDDEN
    assert history.revisions == ()


def test_asking_for_the_history_of_something_that_is_not_linked_is_refused(
    documents: Documents,
) -> None:
    outcome = documents.revisions("d_not_linked")

    assert refused(outcome).kind.value == "not_found"


# --------------------------------------------------------------------------
# Editing happens elsewhere, and the guidance names both destinations
# --------------------------------------------------------------------------


def test_the_only_actions_offered_are_opening_and_unlinking(documents: Documents) -> None:
    with_links(documents, RATIONALE)

    entry = ran(documents.listed()).entries[0]

    assert actions_for(entry) == AVAILABLE_ACTIONS == ("open", "unlink")
    assert "edit" not in AVAILABLE_ACTIONS


def test_the_listing_carries_the_placement_guidance_naming_both_destinations(
    documents: Documents,
) -> None:
    listing = ran(documents.listed())

    assert "specification" in listing.guidance
    assert "linked document" in listing.guidance


def test_where_to_write_sends_a_budget_to_the_spec_and_a_rationale_to_the_document() -> None:
    assert where_to_write("the triangle budget is 12000") is ContentPlacement.SPECIFICATION
    assert (
        where_to_write("it reads as a courier because the faction is logistics")
        is ContentPlacement.DOCUMENT
    )


# --------------------------------------------------------------------------
# The cache itself
# --------------------------------------------------------------------------


def test_the_cache_is_keyed_by_reference_and_actor_together() -> None:
    from datetime import UTC, datetime

    cache = CardCache()
    ref = DocumentRef(workspace="w", document_id="d", url="https://x.invalid/d")
    now = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    cache.put(ref, "rafa", DocumentCard(ref=ref, title="a title"), now)

    assert cache.get(ref, "rafa", now) is not None
    assert cache.get(ref, "bruno", now) is None


def _resolves(documents: Documents) -> int:
    """How many times the platform has been asked to resolve anything."""
    return sum(1 for request in documents.platform.requests if request.operation == "resolve")


def test_a_credential_never_appears_in_a_repr() -> None:
    """A token in a traceback is a token in a log."""
    assert "s3cret" not in repr(Credential("s3cret"))
