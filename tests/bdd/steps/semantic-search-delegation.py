"""Step definitions for `semantic-search-delegation` — routing, provenance, degradation.

The arrangement is `tests/search_world.py`, the same one
`tests/unit/test_use_case_search_delegation.py` runs against: the real
in-memory index ranked by the port's own cascade, the real in-memory document
platform with its own per-actor permissions beside it, and the real use case on
top. So a scenario here passes because the product routes, groups and degrades
the way it says it does, not because a step asserted about a value it built
itself.

Three scenarios assert an **absence** and they are the ones worth reading
twice: no request leaves for an identifier-shaped query, no request leaves
without the asker's own credential, and no value in a response can order a
semantic result against an exact one. Each is checked against what actually
reached the platform — :attr:`Searches.requests` — rather than against what the
code appears to send.
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from cybercanon.application.ports.document_platform import (
    DocumentPlatform,
    UnavailabilityReason,
)
from cybercanon.application.testing.document_platform import InMemoryDocumentPlatform
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.search_delegation import (
    APPROXIMATE_NOTICE,
    EXACT_LABEL,
    SEMANTIC_LABEL,
    UNAVAILABLE_SENTENCES,
    DelegatedSearch,
    ExactResult,
    SemanticResult,
)
from cybercanon.domain.documents import PROVENANCE_ORDER, ResultProvenance
from documents_world import BRUNO_SUBJECT, BRUNO_TOKEN, PRIVATE, RAFA_TOKEN
from search_world import (
    BIBLE_PROSE,
    BOTH_QUERY,
    HEAVY,
    IDENTIFIER_QUERY,
    PROSE_QUERY,
    SCOUT,
    Searches,
    a_world,
)

UNRELEASED = "w_unreleased"
"""A second workspace, so *"two people with access to different workspaces"* is
two workspaces rather than two permissions inside one."""

BUDGET_SECONDS = 0.05
"""The budget the slow-service scenario runs under. Small, and never slept through."""


@pytest.fixture
def searches() -> dict[str, Any]:
    """The world this scenario runs in, and whatever its steps produced."""
    return {"world": a_world()}


def _world(searches: dict[str, Any]) -> Searches:
    return searches["world"]


def _answer(searches: dict[str, Any]) -> DelegatedSearch:
    answer = searches.get("answer")
    assert answer is not None, "no search has been run by this scenario"
    return answer


def _run(searches: dict[str, Any], term: str, **options: Any) -> DelegatedSearch:
    answer = ran(_world(searches).run(term, **options))
    searches["answer"] = answer
    searches["term"] = term
    return answer


# --------------------------------------------------------------------------
# Rule: Exact lookup is always local and deterministic
# --------------------------------------------------------------------------


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Repeated query is stable",
)
def test_repeated_query_is_stable() -> None: ...


@given("a repository whose specifications have not changed")
def _unchanged(searches: dict[str, Any]) -> None:
    searches["before"] = tuple(entry.asset_id for entry in _world(searches).index.list_assets())


@when("the same query is run twice")
def _twice(searches: dict[str, Any]) -> None:
    searches["runs"] = [_run(searches, "mech").asset_ids for _ in range(2)]


@then("both runs SHALL return identical results in identical order")
def _identical(searches: dict[str, Any]) -> None:
    first, second = searches["runs"]

    assert first == second == (HEAVY, SCOUT)


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Exact lookup needs no remote service",
)
def test_exact_lookup_needs_no_remote_service() -> None: ...


@given("the document platform is unreachable")
def _platform_unreachable(searches: dict[str, Any]) -> None:
    _world(searches).unavailable(UnavailabilityReason.UNREACHABLE)


@when("an asset is searched by identifier, name, alias or tag")
def _by_every_exact_pass(searches: dict[str, Any]) -> None:
    searches["answers"] = {
        term: _run(searches, term).asset_ids
        for term in (SCOUT, "Scout Mech", "recon mech", "faction-logistics")
    }


@then("the result SHALL be returned normally")
def _returned_normally(searches: dict[str, Any]) -> None:
    assert searches["answers"] == dict.fromkeys(
        (SCOUT, "Scout Mech", "recon mech", "faction-logistics"), (SCOUT,)
    )


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Identifier query is never answered only semantically",
)
def test_identifier_query_is_never_answered_only_semantically() -> None: ...


@given("a query that exactly matches an asset identifier or alias")
def _exact_query(searches: dict[str, Any]) -> None:
    searches["term"] = IDENTIFIER_QUERY


@when("the search runs")
def _search_runs(searches: dict[str, Any]) -> None:
    """One query, or each of the several a scenario said *any query* about."""
    world = _world(searches)
    terms = searches.get("terms") or (searches.get("term", IDENTIFIER_QUERY),)
    answers = {term: ran(world.run(term)) for term in terms}
    searches["locals"] = {term: answer.local for term, answer in answers.items()}
    searches["answer"] = answers[terms[0]]
    searches["term"] = terms[0]


@then("that asset SHALL appear in the exact results")
def _asset_is_exact(searches: dict[str, Any]) -> None:
    answer = _answer(searches)

    assert SCOUT in answer.asset_ids
    assert SCOUT in {found.asset_id for found in answer.exact}


@then("it SHALL NOT be omitted in favour of a semantically retrieved result")
def _not_omitted(searches: dict[str, Any]) -> None:
    answer = _answer(searches)

    assert answer.exact
    assert answer.semantic.results == ()


# --------------------------------------------------------------------------
# Rule: Prose questions are delegated, and delegation is additive
# --------------------------------------------------------------------------


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Natural-language question reaches the document platform",
)
def test_natural_language_question_reaches_the_platform() -> None: ...


@given(parsers.re(r"""the query [`"'](?P<term>[^`"']+)[`"']$"""))
def _the_query(searches: dict[str, Any], term: str) -> None:
    searches["term"] = term


@when("the search runs with the document platform configured")
def _runs_configured(searches: dict[str, Any]) -> None:
    assert not isinstance(_world(searches).platform, type(None))
    _run(searches, searches["term"])


@then("the query SHALL be forwarded to the retrieval service")
def _forwarded(searches: dict[str, Any]) -> None:
    sent = _world(searches).searches

    assert [request.value("query") for request in sent] == [searches["term"]]


@then("any passages it returns SHALL be included in the response")
def _passages_included(searches: dict[str, Any]) -> None:
    answer = _answer(searches)

    assert len(answer.semantic.results) == 2
    assert all(found.text for found in answer.semantic.results)


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Local results are produced either way",
)
def test_local_results_are_produced_either_way() -> None: ...


@given("any query")
def _any_query(searches: dict[str, Any]) -> None:
    searches["terms"] = (IDENTIFIER_QUERY, PROSE_QUERY, BOTH_QUERY)


@then("the local index SHALL be consulted")
def _local_consulted(searches: dict[str, Any]) -> None:
    answers = searches["locals"]

    assert set(answers) == set(searches["terms"])
    assert all(answer.term == term for term, answer in answers.items())


@then("its results SHALL be present in the response")
def _local_present(searches: dict[str, Any]) -> None:
    answers = searches["locals"]

    assert answers[IDENTIFIER_QUERY].asset_ids == (SCOUT,)
    assert answers[BOTH_QUERY].asset_ids == (SCOUT,)
    assert answers[PROSE_QUERY].asset_ids == ()
    assert answers[PROSE_QUERY].recorded_as_miss


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Identifier-shaped query is not delegated",
)
def test_identifier_shaped_query_is_not_delegated() -> None: ...


@when("it matches an asset identifier in the local index")
def _matches_identifier(searches: dict[str, Any]) -> None:
    answer = _run(searches, searches["term"])

    assert answer.asset_ids == (SCOUT,)


@then("no query SHALL be forwarded to the retrieval service")
def _nothing_forwarded(searches: dict[str, Any]) -> None:
    assert _world(searches).requests == ()


# --------------------------------------------------------------------------
# Rule: Results are presented with provenance, exact first
# --------------------------------------------------------------------------


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Groups are labelled and ordered",
)
def test_groups_are_labelled_and_ordered() -> None: ...


@given("a query producing both exact and semantic results")
def _both_kinds(searches: dict[str, Any]) -> None:
    answer = _run(searches, BOTH_QUERY)

    assert answer.exact and answer.semantic.results


@when("the response is rendered")
def _rendered(searches: dict[str, Any]) -> None:
    searches["groups"] = _answer(searches).groups


@then("exact matches SHALL appear first under a label identifying them as exact")
def _exact_first(searches: dict[str, Any]) -> None:
    groups = searches["groups"]

    assert tuple(group.provenance for group in groups) == PROVENANCE_ORDER
    assert groups[0].provenance is ResultProvenance.EXACT
    assert EXACT_LABEL == "exact matches"
    assert groups[0].results == _answer(searches).exact


@then("semantic matches SHALL appear after, labelled as approximate")
def _semantic_after(searches: dict[str, Any]) -> None:
    groups = searches["groups"]
    answer = _answer(searches)

    assert groups[1].provenance is ResultProvenance.SEMANTIC
    assert groups[1].is_approximate
    assert "approximate" in SEMANTIC_LABEL
    assert answer.semantic.notice == APPROXIMATE_NOTICE


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Semantic results name their source",
)
def test_semantic_results_name_their_source() -> None: ...


@when("a semantically retrieved passage is presented")
def _one_passage(searches: dict[str, Any]) -> None:
    answer = _run(searches, PROSE_QUERY)
    searches["passage"] = answer.semantic.results[0]


@then("it SHALL name the document it came from")
def _names_document(searches: dict[str, Any]) -> None:
    passage = searches["passage"]

    assert passage.document_title
    assert passage.source == passage.document_title
    assert passage.document_id


@then("it SHALL be openable at the document platform")
def _openable(searches: dict[str, Any]) -> None:
    passage = searches["passage"]

    assert passage.is_openable
    assert passage.url.startswith("https://")
    assert passage.url.endswith(passage.document_id)


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "No combined score",
)
def test_no_combined_score() -> None: ...


@when("a response containing both kinds of result is inspected")
def _inspected(searches: dict[str, Any]) -> None:
    answer = _run(searches, BOTH_QUERY)

    assert answer.exact and answer.semantic.results


@then("no ordering value SHALL rank a semantic result against an exact one")
def _no_shared_ordering_value(searches: dict[str, Any]) -> None:
    """The comparison is unwritable: the two types share no field at all."""
    exact = set(ExactResult.__dataclass_fields__)
    semantic = set(SemanticResult.__dataclass_fields__)
    passage = _answer(searches).semantic.results[0]

    assert exact & semantic == set()
    assert not any(isinstance(getattr(passage, name), int | float) for name in semantic)
    assert not hasattr(_answer(searches), "ranked")


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "A semantic hit is not an asset record",
)
def test_a_semantic_hit_is_not_an_asset_record() -> None: ...


@given("a semantic result mentioning an asset by name")
def _mentions_an_asset(searches: dict[str, Any]) -> None:
    answer = _run(searches, PROSE_QUERY)
    passage = answer.semantic.results[0]

    assert SCOUT in passage.document_title or "scout" in passage.text.lower()


@when("the response is presented")
def _presented(searches: dict[str, Any]) -> None:
    searches["groups"] = _answer(searches).groups


@then("it SHALL NOT be presented as that asset's specification or location")
def _not_a_record(searches: dict[str, Any]) -> None:
    passage = _answer(searches).semantic.results[0]

    assert not hasattr(passage, "asset_id")
    assert not hasattr(passage, "spec_path")
    assert not hasattr(passage, "locations")


@then("the asset's own record SHALL be reachable only through the exact results")
def _record_only_exact(searches: dict[str, Any]) -> None:
    answer = _answer(searches)

    assert answer.asset_ids == answer.local.asset_ids
    assert answer.asset_ids == tuple(found.asset_id for found in answer.exact)


# --------------------------------------------------------------------------
# Rule: The asking person's authority is forwarded
# --------------------------------------------------------------------------


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Two people get different results",
)
def test_two_people_get_different_results() -> None: ...


@given("two people with access to different workspaces")
def _two_workspaces(searches: dict[str, Any]) -> None:
    """Bruno's document moves to a workspace of his own, and Rafa keeps his.

    The search is then run unscoped, so what each person receives is decided by
    the platform's own permissions rather than by the two queries differing.
    """
    world = _world(searches)
    platform = world.platform
    assert isinstance(platform, InMemoryDocumentPlatform)
    platform.delete(world.workspace, PRIVATE)
    platform.add_document(
        UNRELEASED,
        PRIVATE,
        "unreleased faction bible",
        summary=BIBLE_PROSE,
        body=BIBLE_PROSE,
        readers=(BRUNO_SUBJECT,),
    )
    world.workspace = ""


@when("each runs the same natural-language query")
def _each_runs(searches: dict[str, Any]) -> None:
    world = _world(searches)
    searches["by_person"] = {
        token: ran(world.run(PROSE_QUERY, token=token)) for token in (RAFA_TOKEN, BRUNO_TOKEN)
    }


@then("each SHALL receive only passages from workspaces they may read")
def _scoped_to_the_person(searches: dict[str, Any]) -> None:
    world = _world(searches)
    by_person = searches["by_person"]
    rafa = by_person[RAFA_TOKEN].semantic.results
    bruno = by_person[BRUNO_TOKEN].semantic.results

    assert {found.workspace for found in rafa} == {"w_production"}
    assert {found.workspace for found in bruno} == {UNRELEASED}
    assert {found.document_id for found in rafa}.isdisjoint({found.document_id for found in bruno})
    assert [request.token for request in world.searches] == [RAFA_TOKEN, BRUNO_TOKEN]


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Service credential is never end-user authority",
)
def test_service_credential_is_never_end_user_authority() -> None: ...


@when("a delegated query is made on behalf of a person")
def _on_behalf(searches: dict[str, Any]) -> None:
    _run(searches, PROSE_QUERY, token=RAFA_TOKEN)


@then("the credential presented to the retrieval service SHALL be that person's")
def _that_persons_credential(searches: dict[str, Any]) -> None:
    assert [request.token for request in _world(searches).searches] == [RAFA_TOKEN]


@then("no query SHALL be made under a service credential on a person's behalf")
def _no_service_credential(searches: dict[str, Any]) -> None:
    """There is nowhere for one to be held, which is the structural half (D2)."""
    world = _world(searches)

    assert all(request.token == RAFA_TOKEN for request in world.requests)
    assert not any(
        "token" in str(name).lower() or "credential" in str(name).lower()
        for name in vars(world.platform)
    )


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "No forwardable credential means local only",
)
def test_no_forwardable_credential_means_local_only() -> None: ...


@given("a caller with no forwardable credential")
def _no_credential(searches: dict[str, Any]) -> None:
    searches["credentialed"] = False


@when("a natural-language query is run")
def _prose_query_runs(searches: dict[str, Any]) -> None:
    _run(searches, PROSE_QUERY, credentialed=searches.get("credentialed", True))


@then("only local results SHALL be returned")
def _local_only(searches: dict[str, Any]) -> None:
    answer = _answer(searches)

    assert answer.local.term == PROSE_QUERY
    assert answer.semantic.results == ()
    assert _world(searches).requests == ()


@then("the semantic portion SHALL be reported as unavailable for lack of authority")
def _unavailable_for_authority(searches: dict[str, Any]) -> None:
    group = _answer(searches).semantic

    assert group.reason is UnavailabilityReason.REJECTED
    assert "no credential was presented" in group.notice


# --------------------------------------------------------------------------
# Rule: No specification content is ingested into the document platform
# --------------------------------------------------------------------------


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Only the query is sent",
)
def test_only_the_query_is_sent() -> None: ...


@when("a natural-language query is delegated")
def _delegated(searches: dict[str, Any]) -> None:
    _run(searches, PROSE_QUERY)


@then("the transmitted payload SHALL contain the query text and routing scope")
def _query_and_scope(searches: dict[str, Any]) -> None:
    sent = _world(searches).searches[0]

    assert sent.value("query") == PROSE_QUERY
    assert sent.value("workspace") == _world(searches).workspace


@then("it SHALL contain no specification or annotation content")
def _no_repository_content(searches: dict[str, Any]) -> None:
    for sent in _world(searches).requests:
        assert set(dict(sent.payload)) <= {"query", "workspace"}


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "No indexing path exists",
)
def test_no_indexing_path_exists() -> None: ...


@when("the system's operations are enumerated")
def _enumerate_operations(searches: dict[str, Any]) -> None:
    searches["operations"] = {name for name in vars(DocumentPlatform) if not name.startswith("_")}
    searches["writes"] = set(InMemoryDocumentPlatform.WRITES)


@then("none SHALL push repository content into a document platform workspace")
def _no_push(searches: dict[str, Any]) -> None:
    assert searches["operations"] == {"resolve", "create", "search", "revisions"}
    assert searches["writes"] == {"create"}
    assert "body" not in DocumentPlatform.create.__annotations__
    assert set(DocumentPlatform.create.__annotations__) == {
        "workspace",
        "title",
        "credential",
        "return",
    }


# --------------------------------------------------------------------------
# Rule: Local search survives the retrieval service being unavailable
# --------------------------------------------------------------------------


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Unreachable service degrades the response, not the search",
)
def test_unreachable_service_degrades_the_response() -> None: ...


@given("the retrieval service is unreachable")
def _retrieval_unreachable(searches: dict[str, Any]) -> None:
    _world(searches).unavailable(UnavailabilityReason.UNREACHABLE)
    searches["term"] = BOTH_QUERY


@then("the local results SHALL be returned")
def _locals_returned(searches: dict[str, Any]) -> None:
    answer = ran(_world(searches).run(BOTH_QUERY))
    searches["answer"] = answer

    assert answer.asset_ids == (SCOUT,)


@then("the response SHALL state that semantic results were unavailable and why")
def _states_why(searches: dict[str, Any]) -> None:
    group = _answer(searches).semantic

    assert not group.is_available
    assert group.reason is UnavailabilityReason.UNREACHABLE
    assert group.notice == UNAVAILABLE_SENTENCES[UnavailabilityReason.UNREACHABLE]


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Slow service does not hold the response",
)
def test_slow_service_does_not_hold_the_response() -> None: ...


@given("a retrieval service that does not answer within the configured time budget")
def _slow_service(searches: dict[str, Any]) -> None:
    world = _world(searches)
    world.budget = timedelta(seconds=BUDGET_SECONDS)
    world.slow(30)


@when("a query is run")
def _timed_run(searches: dict[str, Any]) -> None:
    started = time.monotonic()
    _run(searches, PROSE_QUERY)
    searches["elapsed"] = time.monotonic() - started


@then("the response SHALL be returned within that budget plus the local search time")
def _within_budget(searches: dict[str, Any]) -> None:
    assert searches["elapsed"] < BUDGET_SECONDS + 1.0


@then("the semantic portion SHALL be reported as unavailable")
def _semantic_unavailable(searches: dict[str, Any]) -> None:
    group = _answer(searches).semantic

    assert not group.is_available
    assert group.results == ()


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Reason is distinguishable",
)
def test_reason_is_distinguishable() -> None: ...


@when("semantic results are unavailable")
def _each_way_of_being_unavailable(searches: dict[str, Any]) -> None:
    searches["reasons"] = {}
    for reason in (
        UnavailabilityReason.UNREACHABLE,
        UnavailabilityReason.REJECTED,
        UnavailabilityReason.TIMED_OUT,
        UnavailabilityReason.MALFORMED,
    ):
        world = a_world()
        world.unavailable(reason)
        searches["reasons"][reason] = ran(world.run(PROSE_QUERY)).semantic
    unconfigured = a_world()
    unconfigured.unconfigured()
    searches["reasons"][UnavailabilityReason.UNCONFIGURED] = ran(
        unconfigured.run(PROSE_QUERY)
    ).semantic


@then(
    "the reported reason SHALL distinguish at least unconfigured, unreachable, "
    "rejected and timed out"
)
def _reasons_distinguish(searches: dict[str, Any]) -> None:
    reported = searches["reasons"]

    assert {reason: group.reason for reason, group in reported.items()} == {
        reason: reason for reason in reported
    }
    assert len({group.notice for group in reported.values()}) == len(reported)
    assert {str(reason) for reason in reported} >= {
        "unconfigured",
        "unreachable",
        "rejected",
        "timed_out",
    }


# --------------------------------------------------------------------------
# Rule: Unanswered queries are recorded locally
# --------------------------------------------------------------------------


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "A semantic hit does not hide an exact miss",
)
def test_a_semantic_hit_does_not_hide_an_exact_miss() -> None: ...


@given("a query with no exact results but two semantic results")
def _miss_with_passages(searches: dict[str, Any]) -> None:
    searches["term"] = PROSE_QUERY


@when("the search completes")
def _completes(searches: dict[str, Any]) -> None:
    answer = _run(searches, searches["term"])

    assert answer.exact == ()
    assert len(answer.semantic.results) == 2


@then("the query SHALL be recorded as a miss")
def _recorded_as_miss(searches: dict[str, Any]) -> None:
    assert _answer(searches).recorded_as_miss
    assert _world(searches).misses == (PROSE_QUERY,)


@scenario(
    "../features/add-cyberarche-integration/semantic-search-delegation.feature",
    "Misses stay local",
)
def test_misses_stay_local() -> None: ...


@when("a miss is recorded")
def _a_miss(searches: dict[str, Any]) -> None:
    _run(searches, PROSE_QUERY)

    assert _world(searches).misses == (PROSE_QUERY,)


@then("no request carrying it SHALL be made to any remote service")
def _miss_stays_here(searches: dict[str, Any]) -> None:
    for sent in _world(searches).requests:
        assert set(dict(sent.payload)) <= {"query", "workspace"}
        assert "miss" not in str(sent.payload).lower()
