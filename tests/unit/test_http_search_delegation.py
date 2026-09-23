"""Task 7.1 — the combined search over the existing HTTP surface.

One address, `GET /{version}/projects/{project}/search`, and the system decides
where the query goes: the person types a question into one box and never picks
a search engine. The page carries the exact group in the local cascade's order;
the approximate group travels beside it, labelled, with the reason when it is
not there.

Two properties are asserted against the wire rather than against a use case:

* **the token that reaches the platform is the one the browser presented**, not
  the deployment's — captured from the fake platform's request log;
* **a request with no bearer credential gets local results**, and no request
  leaves for the platform at all. The alternative — asking under the service's
  own identity — is what the specification forbids in so many words.
"""

from __future__ import annotations

from typing import Any

import pytest
from http_world import DOCUMENT_WORKSPACE, PROJECT, SCOUT, TOKEN, Wired, a_surface

from cybercanon.adapters.inbound.http import versioning
from cybercanon.application.ports.document_platform import UnavailabilityReason
from cybercanon.application.testing.document_platform import InMemoryDocumentPlatform
from cybercanon.application.use_cases.search_delegation import (
    APPROXIMATE_NOTICE,
    EXACT_LABEL,
    NO_AUTHORITY,
    SEMANTIC_LABEL,
    UNAVAILABLE_SENTENCES,
)

pytestmark = pytest.mark.unit

BASE = f"/{versioning.VERSION}/projects/{PROJECT}"

RATIONALE = "d_rationale"
PROSE = (
    "The scout mech looks scavenged because the faction cannot manufacture armour "
    "plate; every panel it wears was taken off something else."
)
PROSE_QUERY = "why does the scout mech look scavenged"

RAFA = "auth|rafa"


@pytest.fixture
def wired() -> Wired:
    """A deployment with a document platform configured, holding one document."""
    world = a_surface(documents=True)
    platform = world.fakes["document_platform"]
    assert isinstance(platform, InMemoryDocumentPlatform)
    platform.add_actor(TOKEN, RAFA)
    platform.add_document(
        DOCUMENT_WORKSPACE,
        RATIONALE,
        "mech_scout — design rationale",
        summary=PROSE,
        body=PROSE,
        readers=(RAFA,),
    )
    return world


def _body(wired: Wired, query: str, token: str = TOKEN) -> dict[str, Any]:
    response = wired.get(f"{BASE}/search?q={query.replace(' ', '+')}", token=token)

    assert response.status_code == 200, response.text
    return response.json()


def _platform(wired: Wired) -> InMemoryDocumentPlatform:
    return wired.fakes["document_platform"]


# --------------------------------------------------------------------------
# The two groups, on one address
# --------------------------------------------------------------------------


def test_an_identifier_query_is_answered_locally_and_asks_nothing(wired: Wired) -> None:
    body = _body(wired, SCOUT)

    assert [item["asset"] for item in body["data"]["items"]] == [SCOUT]
    assert body["semantic"]["results"] == []
    assert body["semantic"]["delegated"] is False
    assert _platform(wired).requests == []


def test_a_prose_query_carries_the_approximate_group_beside_the_page(wired: Wired) -> None:
    body = _body(wired, PROSE_QUERY)
    semantic = body["semantic"]

    assert body["data"]["items"] == []
    assert semantic["delegated"] is True
    assert semantic["available"] is True
    assert semantic["label"] == SEMANTIC_LABEL
    assert semantic["approximate"] is True
    assert semantic["notice"] == APPROXIMATE_NOTICE
    assert body["exact_label"] == EXACT_LABEL


def test_every_result_says_where_it_came_from(wired: Wired) -> None:
    body = _body(wired, PROSE_QUERY)
    passage = body["semantic"]["results"][0]

    assert passage["provenance"] == "semantic"
    assert passage["document"] == RATIONALE
    assert passage["title"] == "mech_scout — design rationale"
    assert passage["url"].endswith(RATIONALE)
    assert "asset" not in passage


def test_an_exact_result_carries_its_provenance_too(wired: Wired) -> None:
    item = _body(wired, SCOUT)["data"]["items"][0]

    assert item["provenance"] == "exact"
    assert item["matched"] == "exact_id"


def test_a_client_that_reads_only_the_page_keeps_working(wired: Wired) -> None:
    """The envelope is an open map: the semantic group is an added field."""
    body = _body(wired, SCOUT)

    assert [item["asset"] for item in body["data"]["items"]] == [SCOUT]
    assert body["version"] == versioning.VERSION


# --------------------------------------------------------------------------
# Whose authority the delegated call carries (D2)
# --------------------------------------------------------------------------


def test_the_token_that_reaches_the_platform_is_the_callers(wired: Wired) -> None:
    _body(wired, PROSE_QUERY)

    assert [sent.token for sent in _platform(wired).requests] == [TOKEN]


def test_a_request_with_no_credential_never_reaches_the_document_platform() -> None:
    """Over HTTP the pipeline refuses first, and that is `auth-integration`'s rule.

    *"A request without a credential receives local-only search results"* is the
    use case's behaviour and it is reached from the un-authenticated surfaces —
    the command line and the agent server, where the local actor has no token to
    forward. This surface serves no anonymous actor at all, so the request is
    refused before any use case runs. Either way the property that matters here
    holds: **nothing is asked of the document platform on nobody's behalf.**
    """
    world = a_surface(documents=True)
    response = world.client.get(f"{BASE}/search?q={PROSE_QUERY.replace(' ', '+')}")

    assert response.status_code == 401
    assert _platform(world).requests == []


def test_the_payload_that_goes_out_is_the_query_and_the_scope(wired: Wired) -> None:
    _body(wired, PROSE_QUERY)
    sent = _platform(wired).requests[0]

    assert dict(sent.payload) == {"query": PROSE_QUERY, "workspace": DOCUMENT_WORKSPACE}


# --------------------------------------------------------------------------
# Degradation over the wire
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
def test_an_unavailable_platform_is_a_degraded_answer_not_a_failed_one(
    wired: Wired, reason: UnavailabilityReason
) -> None:
    _platform(wired).fail_with(reason)

    body = _body(wired, PROSE_QUERY)

    assert body["semantic"]["available"] is False
    assert body["semantic"]["reason"] == reason.value
    assert body["semantic"]["notice"] == UNAVAILABLE_SENTENCES[reason]
    assert "error" not in body


def test_a_deployment_with_no_document_platform_answers_exactly_as_before() -> None:
    """*"every other capability works and linked-document features report
    themselves unavailable."*"""
    plain = a_surface()
    configured = a_surface(documents=True)

    without = plain.get(f"{BASE}/search?q={SCOUT}").json()
    with_one = configured.get(f"{BASE}/search?q={SCOUT}").json()

    prose = plain.get(f"{BASE}/search?q={PROSE_QUERY.replace(' ', '+')}").json()

    assert without["data"] == with_one["data"]
    assert without["semantic"]["reason"] is None, "nothing was asked, so nothing failed"
    assert prose["semantic"]["reason"] == UnavailabilityReason.UNCONFIGURED.value
    assert prose["semantic"]["notice"] == (UNAVAILABLE_SENTENCES[UnavailabilityReason.UNCONFIGURED])


def test_an_unconfigured_deployment_still_reports_the_reason_for_a_prose_query() -> None:
    body = a_surface().get(f"{BASE}/search?q={PROSE_QUERY.replace(' ', '+')}").json()

    assert body["semantic"]["available"] is False
    assert body["semantic"]["reason"] == "unconfigured"
    assert NO_AUTHORITY not in body["semantic"]["notice"]
