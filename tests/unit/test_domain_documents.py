"""Group 1 — the reference, the four states, provenance, and the placement rule.

Pure domain, so every test here runs with no platform, no network and no file.
The four assertions the specification actually rests on are the four that are
hardest to keep true by convention, and each is checked as a *property of a
type* rather than of a call site:

* a malformed reference cannot be constructed (1.1);
* a `FORBIDDEN` card carries no title and no summary **however it is built** (1.2);
* nothing orders a semantic result against an exact one (1.3);
* the placement rule classifies a budget and a rationale differently (1.4).
"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError

import pytest

from cybercanon.domain import documents as module
from cybercanon.domain.documents import (
    PLACEMENT_GUIDANCE,
    PROVENANCE_ORDER,
    SUMMARY_MAX_CHARS,
    ContentPlacement,
    DocumentCard,
    DocumentRef,
    DocumentRevision,
    DocumentScope,
    DocumentState,
    MalformedReference,
    ResultProvenance,
    constrains_or_is_checkable,
    find_document,
    grouped_by_provenance,
    linked_documents,
    newest_first,
    ordered_refs,
    placement_of,
    reference_problem,
    unresolved_card,
    without_document,
)

WORKSPACE = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
DOCUMENT = "9a8b7c6d5e4f30211203f4e5d6c7b8a9"
"""Identifiers shaped like the real platform's, and belonging to no instance.

A test fixture naming a live workspace is a live workspace identifier that
outlives the test, so these are the right *shape* — thirty-two hexadecimal
characters — and nothing else.
"""
ADDRESS = f"https://documents.invalid/w/{WORKSPACE}/d/{DOCUMENT}"


def a_ref(document_id: str = DOCUMENT) -> DocumentRef:
    return DocumentRef(workspace=WORKSPACE, document_id=document_id, url=ADDRESS)


# --------------------------------------------------------------------------
# 1.1 — the reference
# --------------------------------------------------------------------------


def test_a_well_formed_reference_is_accepted_and_frozen() -> None:
    ref = a_ref()

    assert ref.key == (WORKSPACE, DOCUMENT)
    with pytest.raises(FrozenInstanceError):
        ref.url = "https://elsewhere.invalid"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("workspace", "document_id", "url"),
    [
        ("", DOCUMENT, ADDRESS),
        (WORKSPACE, "", ADDRESS),
        (WORKSPACE, DOCUMENT, ""),
        (WORKSPACE, DOCUMENT, "not-a-url"),
        (WORKSPACE, DOCUMENT, "ftp://documents.invalid/d/1"),
        ("two words", DOCUMENT, ADDRESS),
        (WORKSPACE, " padded", ADDRESS),
    ],
)
def test_a_malformed_reference_cannot_be_constructed(
    workspace: str, document_id: str, url: str
) -> None:
    """The constructor refuses, and the same judgement is available as a function.

    Both halves matter: the type cannot hold a broken value, and the *parser*
    needs to report one without raising, so the rule is a function the schema
    can ask before it builds anything.
    """
    assert reference_problem(workspace, document_id, url) is not None
    with pytest.raises(MalformedReference):
        DocumentRef(workspace=workspace, document_id=document_id, url=url)


def test_a_reference_carries_no_field_that_could_hold_a_title_or_a_body() -> None:
    """D1 and D9 as a shape: what is authored is a reference and its authorship."""
    assert set(DocumentRef.__dataclass_fields__) == {
        "workspace",
        "document_id",
        "url",
        "linked_by",
        "linked_at",
    }


def test_attribution_is_added_without_touching_the_identity() -> None:
    attributed = a_ref().attributed("rafa", "2026-09-22T10:00:00+00:00")

    assert attributed.key == (WORKSPACE, DOCUMENT)
    assert attributed.linked_by == "rafa"
    assert attributed.linked_at == "2026-09-22T10:00:00+00:00"


def test_reference_lists_keep_authored_order_and_drop_repeats() -> None:
    first, second = a_ref("d1"), a_ref("d2")

    assert ordered_refs((first, second, first)) == (first, second)
    assert without_document((first, second), "d1") == (second,)
    assert find_document((first, second), "d2") is second
    assert find_document((first, second), "d9") is None


# --------------------------------------------------------------------------
# 1.2 — the states and the card
# --------------------------------------------------------------------------


def test_the_state_set_is_closed_and_has_exactly_four_members() -> None:
    assert DocumentState.values() == ("readable", "unreachable", "missing", "forbidden")
    assert DocumentState.READABLE.is_resolved
    assert not any(
        state.is_resolved
        for state in (DocumentState.UNREACHABLE, DocumentState.MISSING, DocumentState.FORBIDDEN)
    )


def test_a_forbidden_card_discloses_nothing_however_it_is_constructed() -> None:
    """Task 1.2 in one assertion: the rule is the type's, not the caller's."""
    built = DocumentCard(
        ref=a_ref(),
        title="Scout mech rationale",
        summary="Why the pauldron reads as a backpack.",
        state=DocumentState.FORBIDDEN,
    )
    helper = unresolved_card(a_ref(), DocumentState.FORBIDDEN)

    for card in (built, helper):
        assert card.discloses_nothing
        assert card.title == ""
        assert card.summary == ""
        assert not card.is_resolved
        assert card.display_title == ADDRESS
        assert card.address == ADDRESS


def test_a_readable_card_shows_its_title_and_a_bounded_summary() -> None:
    card = DocumentCard(
        ref=a_ref(),
        title="Scout mech rationale",
        summary="word " * 500,
        state=DocumentState.READABLE,
        resolved_at="2026-09-22T10:00:00+00:00",
    )

    assert card.is_resolved
    assert card.display_title == "Scout mech rationale"
    assert len(card.summary) == SUMMARY_MAX_CHARS


def test_an_unresolved_card_is_still_openable_at_its_address() -> None:
    for state in (DocumentState.UNREACHABLE, DocumentState.MISSING):
        card = unresolved_card(a_ref(), state)
        assert card.state is state
        assert card.address == ADDRESS
        assert not card.is_resolved


def test_a_listing_puts_asset_links_first_and_names_every_scope() -> None:
    asset_ref, project_ref = a_ref("d_asset"), a_ref("d_project")

    entries = linked_documents((asset_ref,), (project_ref,), {})

    assert [entry.scope for entry in entries] == [DocumentScope.ASSET, DocumentScope.PROJECT]
    assert [entry.ref for entry in entries] == [asset_ref, project_ref]
    assert all(entry.state is DocumentState.UNREACHABLE for entry in entries)
    assert linked_documents((asset_ref,), (project_ref,), {}) == entries


# --------------------------------------------------------------------------
# 1.3 — provenance
# --------------------------------------------------------------------------


def test_exact_results_precede_semantic_ones_and_both_groups_are_always_present() -> None:
    groups = grouped_by_provenance(("mech_scout",), ("a passage",))

    assert [group.provenance for group in groups] == list(PROVENANCE_ORDER)
    assert groups[0].results == ("mech_scout",)
    assert not groups[0].is_approximate
    assert groups[1].is_approximate
    assert [group.size for group in grouped_by_provenance((), ())] == [0, 0]


def test_no_comparator_orders_a_semantic_result_against_an_exact_one() -> None:
    """Task 1.3: the comparison is *unwritable*, so it cannot drift back in (D6).

    Two halves. The enum defines no ordering, so `EXACT < SEMANTIC` raises; and
    nothing in the module carries a score, rank or weight that two results from
    different groups could be compared on.
    """
    with pytest.raises(TypeError):
        _ = ResultProvenance.EXACT < ResultProvenance.SEMANTIC  # type: ignore[operator]

    ordering = {"score", "rank", "weight", "relevance", "distance", "similarity"}
    for name, value in vars(module).items():
        fields = getattr(value, "__dataclass_fields__", None)
        if fields is None or name.startswith("_"):
            continue
        assert not set(fields) & ordering, f"{name} carries a value results could be sorted on"


def test_the_only_sort_in_the_module_is_within_one_document_history() -> None:
    """`newest_first` orders revisions of one document — never results of a search."""
    revisions = (DocumentRevision(id="a", seq=1), DocumentRevision(id="b", seq=3))

    assert [revision.id for revision in newest_first(revisions)] == ["b", "a"]
    assert DocumentRevision(id="c", seq=2).name == "revision 2"
    assert DocumentRevision(id="c", seq=2, label="before retopo").name == "before retopo"


# --------------------------------------------------------------------------
# 1.4 — the content-placement rule
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "the triangle budget is 12000",
        "LOD0 must stay under 12000 tris",
        "it carries a socket named SOCKET_muzzle_l",
        "the silhouette must read at 25 m",
        "textures are 2048 px",
        "the rig may use at most 64 bones",
    ],
)
def test_a_checkable_statement_belongs_in_the_specification(statement: str) -> None:
    assert placement_of(statement) is ContentPlacement.SPECIFICATION
    assert constrains_or_is_checkable(statement)


@pytest.mark.parametrize(
    "statement",
    [
        "the scout reads as a courier, not as a brawler, because the faction is logistics",
        "we tried a heavier chassis in February and it made the team read it as a tank",
        "the art director prefers the asymmetric antenna for storytelling reasons",
        "",
        "   ",
    ],
)
def test_rationale_belongs_in_the_document(statement: str) -> None:
    assert placement_of(statement) is ContentPlacement.DOCUMENT
    assert not constrains_or_is_checkable(statement)


def test_the_guidance_names_both_destinations() -> None:
    """*"The system SHALL state that ... belongs in the specification and ... the document."*"""
    assert "specification" in PLACEMENT_GUIDANCE
    assert "document" in PLACEMENT_GUIDANCE
    assert "constrains" in PLACEMENT_GUIDANCE
    assert "Rationale" in PLACEMENT_GUIDANCE


# --------------------------------------------------------------------------
# 1.5 — the one-way boundary
# --------------------------------------------------------------------------


def test_no_domain_signature_accepts_a_document_body() -> None:
    """Task 1.5 (domain half): nothing here has a parameter that could hold prose.

    `placement_of` takes a *statement a person is writing*, which is the
    opposite direction: it answers where to put something somebody typed, and
    returns a destination rather than content.
    """
    forbidden = {"body", "content", "blocks", "html", "markdown", "prose", "document_body"}
    for name, value in vars(module).items():
        if not inspect.isfunction(value) or name.startswith("_"):
            continue
        parameters = set(inspect.signature(value).parameters)
        assert not parameters & forbidden, f"{name} accepts {sorted(parameters & forbidden)}"
