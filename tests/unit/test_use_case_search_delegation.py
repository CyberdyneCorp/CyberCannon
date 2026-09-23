"""Group 4 — the routing gate, the fan-out ordering, the budget and the two groups.

The arrangement is `tests/search_world.py`: the real in-memory index ranked by
the port's own cascade, the real in-memory document platform with its own
permissions beside it, and the real use case on top. Nothing here re-implements
a rule, so a test that passes here passes because the product does the thing.

Three of these assert an *absence*, and they are the ones worth reading twice:
no request goes out for an identifier-shaped query, no request goes out without
the asker's own credential, and no value in the response can order a semantic
result against an exact one.
"""

from __future__ import annotations

import time
from datetime import timedelta

import pytest

from cybercanon.application.ports.document_platform import (
    NO_CREDENTIAL,
    Credential,
    NullDocumentPlatform,
    UnavailabilityReason,
)
from cybercanon.application.ports.search_index import MatchKind
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.search_delegation import (
    APPROXIMATE_NOTICE,
    EXACT_LABEL,
    MINIMUM_PROSE_WORDS,
    NO_AUTHORITY,
    SEMANTIC_LABEL,
    UNAVAILABLE_SENTENCES,
    ExactResult,
    SemanticResult,
    is_identifier_shaped,
    is_prose,
    label_for,
    resolved_locally,
    search_assets_and_docs,
    should_delegate,
)
from cybercanon.domain.documents import PROVENANCE_ORDER, ResultProvenance
from documents_world import BRUNO_TOKEN, PRIVATE, RAFA_TOKEN, RATIONALE, RESEARCH, WORKSPACE
from search_world import (
    BOTH_QUERY,
    DRONE,
    HEAVY,
    IDENTIFIER_QUERY,
    PROSE_QUERY,
    SCOUT,
    UNKNOWN_QUERY,
    Searches,
    a_world,
    without_platform,
)
from views_world import PROJECT

pytestmark = pytest.mark.unit


@pytest.fixture
def searches() -> Searches:
    """Three indexed assets and three documents, two of them Rafa's to read."""
    return a_world()


# --------------------------------------------------------------------------
# 4.1 — the routing gate is a pure function of the query and the local results
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    ["mech_scout", "SCOUT", "drone_spotter", "characters/mech_scout", "v1.2", "a"],
)
def test_an_identifier_shaped_query_is_never_delegated(query: str) -> None:
    assert is_identifier_shaped(query)
    assert not should_delegate(query, ())


@pytest.mark.parametrize(
    "query",
    [
        PROSE_QUERY,
        "why does the scout read as a courier",
        "what did we decide about the pauldron",
    ],
)
def test_a_prose_query_with_no_exact_hit_is_delegated(query: str) -> None:
    assert is_prose(query)
    assert should_delegate(query, ())


def test_a_query_that_resolved_to_an_alias_is_not_delegated(searches: Searches) -> None:
    """Both halves of the requirement, and the local one comes first."""
    local = searches.index.search("recon mech", PROJECT)

    assert [hit.kind for hit in local] == [MatchKind.ALIAS]
    assert not should_delegate("recon mech", local)


def test_a_description_substring_is_not_the_query_having_resolved(searches: Searches) -> None:
    """The requirement names four passes, and the description pass is not one.

    A sentence that brushed against an asset's description is exactly the
    sentence worth also asking the document platform about — and if it were
    not, *"a query producing both exact and semantic results"* would be a
    scenario the gate could never produce.
    """
    local = searches.index.search(BOTH_QUERY, PROJECT)

    assert [hit.kind for hit in local] == [MatchKind.DESCRIPTION]
    assert not resolved_locally(local)
    assert should_delegate(BOTH_QUERY, local)


def test_two_words_are_a_name_somebody_typed_with_a_space_in_it() -> None:
    assert MINIMUM_PROSE_WORDS == 3
    assert not is_prose("scout mech")
    assert not should_delegate("scout mech", ())


def test_the_gate_is_pure(searches: Searches) -> None:
    """Asking it changes nothing — no index write, no request, no clock."""
    before = searches.index.misses(PROJECT)

    assert should_delegate(PROSE_QUERY, ()) is should_delegate(PROSE_QUERY, ())
    assert searches.requests == ()
    assert searches.index.misses(PROJECT) == before


def test_an_identifier_query_makes_no_request_at_all(searches: Searches) -> None:
    answer = ran(searches.run(IDENTIFIER_QUERY))

    assert answer.asset_ids == (SCOUT,)
    assert not answer.was_delegated
    assert searches.searches == ()


# --------------------------------------------------------------------------
# 4.2 — the local cascade runs to completion before the delegated call (D5)
# --------------------------------------------------------------------------


def test_the_local_half_is_complete_before_the_platform_is_asked(searches: Searches) -> None:
    """The miss is the evidence, and it is recorded by the local half.

    `search_assets` records a term that matched nothing *as part of answering*,
    so a platform that can already see the miss was called after the local
    cascade finished — which is the ordering D5 turns into a property.
    """
    seen: list[tuple[str, ...]] = []
    real = searches.platform.search

    def watching(query, credential, budget=timedelta(seconds=5), workspace=""):
        seen.append(tuple(miss.term for miss in searches.index.misses(PROJECT)))
        return real(query, credential, budget, workspace)

    searches.platform.search = watching  # type: ignore[method-assign]
    answer = ran(searches.run(PROSE_QUERY))

    assert seen == [(PROSE_QUERY,)]
    assert answer.recorded_as_miss


@pytest.mark.parametrize(
    "arrange",
    [
        lambda world: None,
        lambda world: world.unavailable(UnavailabilityReason.UNREACHABLE),
        lambda world: world.unconfigured(),
    ],
    ids=["answering", "unreachable", "unconfigured"],
)
def test_no_local_result_depends_on_the_remote_call(searches: Searches, arrange) -> None:
    expected = ran(a_world().run(IDENTIFIER_QUERY)).exact
    arrange(searches)

    assert ran(searches.run(IDENTIFIER_QUERY)).exact == expected


# --------------------------------------------------------------------------
# 4.3 — the time budget
# --------------------------------------------------------------------------


def test_a_platform_slower_than_the_budget_does_not_hold_the_response(
    searches: Searches,
) -> None:
    searches.budget = timedelta(milliseconds=50)
    searches.slow(30)

    started = time.monotonic()
    answer = ran(searches.run(PROSE_QUERY))
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert answer.semantic.reason is UnavailabilityReason.TIMED_OUT
    assert answer.semantic.results == ()


def test_a_platform_inside_the_budget_answers(searches: Searches) -> None:
    searches.budget = timedelta(seconds=5)
    searches.slow(1)

    answer = ran(searches.run(PROSE_QUERY))

    assert answer.semantic.is_available
    assert answer.semantic.results


# --------------------------------------------------------------------------
# 4.4 — degradation: five reasons, each distinguishable, local results intact
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        UnavailabilityReason.UNREACHABLE,
        UnavailabilityReason.REJECTED,
        UnavailabilityReason.TIMED_OUT,
        UnavailabilityReason.MALFORMED,
    ],
)
def test_every_failure_keeps_the_local_results_and_names_itself(
    searches: Searches, reason: UnavailabilityReason
) -> None:
    searches.unavailable(reason)

    answer = ran(searches.run(BOTH_QUERY))

    assert answer.asset_ids == (SCOUT,)
    assert answer.semantic.reason is reason
    assert answer.semantic.notice == UNAVAILABLE_SENTENCES[reason]


def test_an_unconfigured_deployment_says_unconfigured(searches: Searches) -> None:
    searches.unconfigured()

    answer = ran(searches.run(PROSE_QUERY))

    assert answer.semantic.reason is UnavailabilityReason.UNCONFIGURED
    assert answer.local.term == PROSE_QUERY


def test_the_five_reasons_are_all_distinguishable() -> None:
    sentences = {reason: UNAVAILABLE_SENTENCES[reason] for reason in UnavailabilityReason}

    assert len(set(sentences.values())) == len(UnavailabilityReason)
    assert set(UnavailabilityReason.values()) >= {
        "unconfigured",
        "unreachable",
        "rejected",
        "timed_out",
    }


def test_a_failure_never_fails_the_search_as_a_whole(searches: Searches) -> None:
    searches.unavailable(UnavailabilityReason.MALFORMED)

    result = searches.run(PROSE_QUERY)

    assert getattr(result, "value", None) is not None, getattr(result, "message", result)


# --------------------------------------------------------------------------
# 4.5 — provenance: two labelled groups, exact first, never merged (D6)
# --------------------------------------------------------------------------


def test_a_response_with_both_kinds_groups_them_exact_first(searches: Searches) -> None:
    answer = ran(searches.run(BOTH_QUERY))

    assert answer.exact and answer.semantic.results
    assert tuple(group.provenance for group in answer.groups) == PROVENANCE_ORDER
    assert answer.groups[0].results == answer.exact
    assert answer.groups[1].results == answer.semantic.results


def test_both_groups_are_present_even_when_one_is_empty(searches: Searches) -> None:
    groups = ran(searches.run(IDENTIFIER_QUERY)).groups

    assert len(groups) == 2
    assert groups[0].provenance is ResultProvenance.EXACT
    assert groups[1].provenance is ResultProvenance.SEMANTIC
    assert groups[1].size == 0


def test_the_groups_are_labelled_and_the_semantic_one_admits_it_guesses(
    searches: Searches,
) -> None:
    answer = ran(searches.run(PROSE_QUERY))

    assert label_for(ResultProvenance.EXACT) == EXACT_LABEL
    assert label_for(ResultProvenance.SEMANTIC) == SEMANTIC_LABEL
    assert answer.semantic.is_approximate
    assert answer.semantic.notice == APPROXIMATE_NOTICE
    assert "approximate" in SEMANTIC_LABEL


def test_every_result_carries_its_provenance(searches: Searches) -> None:
    exact = ran(searches.run(IDENTIFIER_QUERY)).exact
    semantic = ran(searches.run(PROSE_QUERY)).semantic.results

    assert {found.provenance for found in exact} == {ResultProvenance.EXACT}
    assert {found.provenance for found in semantic} == {ResultProvenance.SEMANTIC}


def test_each_semantic_result_names_its_document_and_is_openable(searches: Searches) -> None:
    answer = ran(searches.run(PROSE_QUERY))

    assert {found.document_id for found in answer.semantic.results} == {RATIONALE, RESEARCH}
    for found in answer.semantic.results:
        assert found.source == found.document_title
        assert found.is_openable
        assert found.url.endswith(found.document_id)


def test_no_ordering_value_ranks_a_semantic_result_against_an_exact_one() -> None:
    """There is no shared score, so the comparison is unwritable rather than unwritten."""
    exact = set(ExactResult.__dataclass_fields__)
    semantic = set(SemanticResult.__dataclass_fields__)

    assert exact & semantic == set()
    assert not any(
        name in semantic for name in ("score", "rank", "relevance", "matched", "position")
    )
    assert all(
        not isinstance(getattr(SemanticResult("w", "d", "t", "u", "x"), name), int | float)
        for name in semantic
    )


# --------------------------------------------------------------------------
# 4.6 — a semantic hit is not an asset record
# --------------------------------------------------------------------------


def test_a_passage_naming_an_asset_is_not_that_assets_record(searches: Searches) -> None:
    answer = ran(searches.run(PROSE_QUERY))
    passage = answer.semantic.results[0]

    assert SCOUT in passage.text or SCOUT in passage.document_title
    assert not hasattr(passage, "asset_id")
    assert answer.asset_ids == ()
    assert answer.exact == ()


def test_the_assets_own_record_is_reachable_only_through_the_exact_results(
    searches: Searches,
) -> None:
    answer = ran(searches.run("mech"))

    assert answer.asset_ids == (HEAVY, SCOUT)
    assert set(answer.asset_ids) == {found.asset_id for found in answer.exact}
    assert DRONE not in answer.asset_ids


# --------------------------------------------------------------------------
# 4.7 — misses are recorded locally, and they stay there
# --------------------------------------------------------------------------


def test_a_query_with_semantic_results_and_no_exact_ones_is_still_a_miss(
    searches: Searches,
) -> None:
    answer = ran(searches.run(PROSE_QUERY))

    assert len(answer.semantic.results) == 2
    assert answer.exact == ()
    assert answer.recorded_as_miss
    assert searches.misses == (PROSE_QUERY,)


def test_no_request_carrying_a_miss_leaves_the_machine(searches: Searches) -> None:
    ran(searches.run(PROSE_QUERY))

    assert searches.misses == (PROSE_QUERY,)
    for sent in searches.requests:
        assert "miss" not in dict(sent.payload)
        assert set(dict(sent.payload)) <= {"query", "workspace"}


def test_a_matched_query_is_not_recorded(searches: Searches) -> None:
    ran(searches.run(IDENTIFIER_QUERY))

    assert searches.misses == ()


# --------------------------------------------------------------------------
# 4.8 — determinism is untouched, platform or no platform
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arrange",
    [
        lambda world: None,
        lambda world: world.unconfigured(),
        lambda world: world.unavailable(UnavailabilityReason.UNREACHABLE),
    ],
    ids=["configured", "unconfigured", "unreachable"],
)
def test_the_same_query_returns_the_same_results_in_the_same_order(
    searches: Searches, arrange
) -> None:
    arrange(searches)

    runs = {ran(searches.run("mech")).asset_ids for _ in range(5)}

    assert runs == {(HEAVY, SCOUT)}


def test_exact_lookup_needs_no_remote_service(searches: Searches) -> None:
    searches.unavailable(UnavailabilityReason.UNREACHABLE)

    for query in (SCOUT, "Scout Mech", "recon mech", "faction-logistics"):
        assert ran(searches.run(query)).asset_ids == (SCOUT,), query


def test_an_exact_match_is_never_dropped_in_favour_of_a_semantic_one(
    searches: Searches,
) -> None:
    answer = ran(searches.run(IDENTIFIER_QUERY))

    assert SCOUT in answer.asset_ids
    assert answer.semantic.results == ()


# --------------------------------------------------------------------------
# The asking person's authority (D2)
# --------------------------------------------------------------------------


def test_the_credential_forwarded_is_the_callers_own(searches: Searches) -> None:
    ran(searches.run(PROSE_QUERY, token=RAFA_TOKEN))

    assert [sent.token for sent in searches.searches] == [RAFA_TOKEN]


def test_two_people_get_different_passages(searches: Searches) -> None:
    rafa = ran(searches.run(PROSE_QUERY, token=RAFA_TOKEN))
    bruno = ran(searches.run(PROSE_QUERY, token=BRUNO_TOKEN))

    assert {found.document_id for found in rafa.semantic.results} == {RATIONALE, RESEARCH}
    assert {found.document_id for found in bruno.semantic.results} == {PRIVATE}


def test_no_forwardable_credential_means_local_only(searches: Searches) -> None:
    answer = ran(searches.run(PROSE_QUERY, credentialed=False))

    assert answer.local.term == PROSE_QUERY
    assert answer.semantic.results == ()
    assert answer.semantic.reason is UnavailabilityReason.REJECTED
    assert answer.semantic.notice == NO_AUTHORITY


def test_no_query_is_made_under_a_service_credential_on_a_persons_behalf(
    searches: Searches,
) -> None:
    """Not *made and refused* — not made at all, which is the only honest reading."""
    ran(searches.run(PROSE_QUERY, credentialed=False))

    assert searches.requests == ()


def test_the_delegated_payload_carries_the_query_and_the_scope_and_nothing_else(
    searches: Searches,
) -> None:
    ran(searches.run(PROSE_QUERY))
    sent = searches.searches[0]

    assert dict(sent.payload) == {"query": PROSE_QUERY, "workspace": WORKSPACE}


# --------------------------------------------------------------------------
# Composition — the default is absence (D4)
# --------------------------------------------------------------------------


def test_with_no_platform_argument_the_null_one_is_used() -> None:
    answer = ran(
        search_assets_and_docs(
            PROSE_QUERY,
            search_index=a_world().index,
            credential=Credential("token-rafa"),
            project=PROJECT,
        )
    )

    assert answer.semantic.reason is UnavailabilityReason.UNCONFIGURED


def test_the_null_platform_is_what_an_unconfigured_deployment_holds() -> None:
    world = without_platform()

    assert isinstance(world.platform, NullDocumentPlatform)
    assert ran(world.run(UNKNOWN_QUERY, credentialed=False)).semantic.reason is (
        UnavailabilityReason.REJECTED
    )


def test_an_absent_credential_is_the_one_that_carries_nothing() -> None:
    assert not NO_CREDENTIAL.is_present
    assert "token" not in repr(Credential("s3cret"))
