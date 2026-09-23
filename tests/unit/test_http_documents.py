"""Task 7.1 — link, unlink, list, create-and-link over the existing HTTP surface.

Five addresses, and the two properties that are only true on the wire:

* **the token that reaches the platform is the browser's**, captured from the
  fake platform's request log — D2 asserted against a request rather than
  against a signature;
* **the reference travels and the body never does**: the specification file the
  write produced is read back and compared against the document's prose.

The refusals are here too, because a surface that offered link-writing to an
automated caller would be the one place G4's durable-authorship row could be
bypassed, and the degradation is here because *"reports itself unavailable and
names the reason"* is a shape of response, not a state of the code.
"""

from __future__ import annotations

from typing import Any

import pytest
from http_world import (
    AUTOMATION_TOKEN,
    DOCUMENT_WORKSPACE,
    PROJECT,
    SCOUT,
    SCOUT_SPEC,
    TOKEN,
    Wired,
    a_surface,
)

from cybercanon.adapters.inbound.http import versioning
from cybercanon.application.ports.document_platform import UnavailabilityReason
from cybercanon.application.testing.document_platform import InMemoryDocumentPlatform
from cybercanon.domain.documents import PLACEMENT_GUIDANCE, DocumentState

pytestmark = pytest.mark.unit

BASE = f"/{versioning.VERSION}/projects/{PROJECT}/assets/{SCOUT}/documents"

RAFA = "auth|rafa"
ANA = "auth|ana"

RATIONALE = "d_rationale"
SECRET = "d_secret"

PROSE = (
    "The scout mech looks scavenged because the faction cannot manufacture "
    "armour plate; every panel it wears was taken off something else."
)


@pytest.fixture
def wired() -> Wired:
    """A deployment with a platform configured, holding two documents."""
    world = a_surface(documents=True)
    platform = _platform(world)
    platform.add_actor(TOKEN, RAFA)
    platform.add_document(
        DOCUMENT_WORKSPACE,
        RATIONALE,
        "mech_scout — design rationale",
        summary=PROSE,
        body=PROSE,
        readers=(RAFA,),
    )
    platform.add_document(DOCUMENT_WORKSPACE, SECRET, "unreleased faction", readers=(ANA,))
    platform.permit_creation(RAFA, DOCUMENT_WORKSPACE)
    return world


def _platform(wired: Wired) -> InMemoryDocumentPlatform:
    platform = wired.fakes["document_platform"]
    assert isinstance(platform, InMemoryDocumentPlatform)
    return platform


def _address(document: str) -> str:
    return f"https://documents.invalid/w/{DOCUMENT_WORKSPACE}/d/{document}"


def _link(wired: Wired, document: str = RATIONALE, token: str = TOKEN, **extra: Any) -> Any:
    response = wired.put(
        f"{BASE}/{document}",
        token=token,
        json={"workspace": DOCUMENT_WORKSPACE, "url": _address(document), **extra},
    )
    _advance(wired)
    return response


def _listed(wired: Wired, token: str = TOKEN) -> dict[str, Any]:
    response = wired.get(BASE, token=token)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _advance(wired: Wired) -> None:
    """Re-read the repository into the in-memory store, and snapshot the revision.

    `GitSpecStore` gets both for free; the fake is told, which is what keeps the
    suite from passing over a store that never saw the write.
    """
    host = wired.repository_host
    head = host.head(PROJECT)
    content = host.read(PROJECT, SCOUT_SPEC, head)
    if content is not None:
        wired.spec_store.add(SCOUT_SPEC, wired.spec_store.parse_document(SCOUT_SPEC, content).asset)
    wired.spec_store.snapshot(head.value)


def _linked(wired: Wired) -> tuple[str, ...]:
    """The references the specification file now holds, as the store reads them."""
    return tuple(ref.document_id for ref in wired.spec_store.load(SCOUT_SPEC).asset.documents)


def _committed(wired: Wired) -> str:
    """The bytes the last commit put in the specification file."""
    host = wired.repository_host
    return (host.read(PROJECT, SCOUT_SPEC, host.head(PROJECT)) or b"").decode()


# --------------------------------------------------------------------------
# Linking — a reference, and never a body
# --------------------------------------------------------------------------


def test_linking_records_the_reference_attributed_to_the_caller(wired: Wired) -> None:
    response = _link(wired)

    assert response.status_code in (200, 201), response.text
    recorded = response.json()["data"]
    assert recorded["reference"]["document"] == RATIONALE
    assert recorded["reference"]["workspace"] == DOCUMENT_WORKSPACE
    assert recorded["reference"]["linked_by"] == RAFA
    assert recorded["scope"] == "asset"
    assert recorded["path"] == SCOUT_SPEC


def test_the_written_specification_carries_the_reference_and_no_prose(wired: Wired) -> None:
    _link(wired)

    assert _linked(wired) == (RATIONALE,)
    assert "scavenged" not in _committed(wired)
    assert PROSE not in _committed(wired)


def test_linking_asks_the_platform_nothing(wired: Wired) -> None:
    _link(wired)

    assert _platform(wired).requests == []


def test_a_malformed_reference_is_refused_naming_it(wired: Wired) -> None:
    response = wired.put(
        f"{BASE}/{RATIONALE}",
        json={"workspace": DOCUMENT_WORKSPACE, "url": "not-an-address"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["subject"] == RATIONALE


def test_an_unknown_scope_is_refused_naming_both(wired: Wired) -> None:
    response = _link(wired, scope="somewhere")

    assert response.status_code == 400, response.text
    message = response.json()["error"]["message"]
    assert "asset" in message and "project" in message


def test_an_automated_caller_may_not_author_a_link(wired: Wired) -> None:
    response = _link(wired, token=AUTOMATION_TOKEN)

    assert response.status_code == 403, response.text
    assert _linked(wired) == ()


# --------------------------------------------------------------------------
# Listing — scope, state, and what a forbidden link discloses
# --------------------------------------------------------------------------


def test_a_listed_link_reads_as_a_document(wired: Wired) -> None:
    _link(wired)

    entry = _listed(wired)["links"][0]
    assert entry["title"] == "mech_scout — design rationale"
    assert entry["summary"].startswith("The scout mech")
    assert entry["state"] == str(DocumentState.READABLE)
    assert entry["scope"] == "asset"
    assert entry["resolved"] is True


def test_the_only_actions_offered_are_opening_and_unlinking(wired: Wired) -> None:
    _link(wired)

    assert _listed(wired)["links"][0]["actions"] == ["open", "unlink"]


def test_a_forbidden_link_discloses_nothing_and_stays_openable(wired: Wired) -> None:
    _link(wired, SECRET)

    entry = _listed(wired)["links"][0]
    assert entry["state"] == str(DocumentState.FORBIDDEN)
    assert entry["title"] == ""
    assert entry["summary"] == ""
    assert entry["url"] == _address(SECRET)
    assert entry["display_title"] == _address(SECRET)


def test_one_broken_link_does_not_break_the_list(wired: Wired) -> None:
    _link(wired)
    _link(wired, SECRET)

    states = {entry["document"]: entry["state"] for entry in _listed(wired)["links"]}
    assert states == {
        RATIONALE: str(DocumentState.READABLE),
        SECRET: str(DocumentState.FORBIDDEN),
    }


def test_the_listing_carries_the_placement_guidance(wired: Wired) -> None:
    """Task 7.3 — the sentence naming both destinations travels with the list."""
    listing = _listed(wired)

    assert listing["guidance"] == PLACEMENT_GUIDANCE
    assert "specification" in listing["guidance"]
    assert "document" in listing["guidance"]


def test_ordering_is_deterministic(wired: Wired) -> None:
    _link(wired)
    _link(wired, SECRET)

    first = [entry["document"] for entry in _listed(wired)["links"]]
    second = [entry["document"] for entry in _listed(wired)["links"]]
    assert first == second == [RATIONALE, SECRET]


def test_the_platform_is_asked_under_the_caller_s_own_token(wired: Wired) -> None:
    _link(wired)
    _listed(wired)

    assert {request.token for request in _platform(wired).requests} == {TOKEN}


def test_a_request_with_no_credential_still_lists_the_references(wired: Wired) -> None:
    _link(wired)
    _platform(wired).requests.clear()

    listing = _listed(wired)
    assert [entry["document"] for entry in listing["links"]] == [RATIONALE]


# --------------------------------------------------------------------------
# Revisions — the platform's history, read and not copied
# --------------------------------------------------------------------------


def test_the_revision_history_is_the_platform_s_own(wired: Wired) -> None:
    _link(wired)
    _platform(wired).add_revision(DOCUMENT_WORKSPACE, RATIONALE, label="second pass")

    response = wired.get(f"{BASE}/{RATIONALE}/revisions")
    assert response.status_code == 200, response.text
    history = response.json()["data"]
    assert history["readable"] is True
    assert [entry["label"] for entry in history["revisions"]] == ["second pass", "created"]
    assert all("body" not in entry for entry in history["revisions"])


def test_a_forbidden_document_answers_with_its_state_and_no_history(wired: Wired) -> None:
    _link(wired, SECRET)

    history = wired.get(f"{BASE}/{SECRET}/revisions").json()["data"]
    assert history["state"] == str(DocumentState.FORBIDDEN)
    assert history["revisions"] == []


def test_history_for_a_document_that_is_not_linked_is_not_found(wired: Wired) -> None:
    response = wired.get(f"{BASE}/d_nothing/revisions")

    assert response.status_code == 404, response.text


# --------------------------------------------------------------------------
# Creating — one action, and D8's two failures
# --------------------------------------------------------------------------


def test_creating_produces_a_pre_titled_document_and_links_it(wired: Wired) -> None:
    response = wired.post(BASE, json={})

    assert response.status_code in (200, 201), response.text
    recorded = response.json()["data"]
    _advance(wired)
    assert SCOUT in recorded["created"]["title"]
    assert recorded["reference"]["document"] == recorded["created"]["document"]
    assert _linked(wired) == (recorded["created"]["document"],)


def test_a_refused_creation_leaves_the_specification_unchanged(wired: Wired) -> None:
    before = _committed(wired)
    response = wired.post(BASE, json={}, token="ana-token")

    assert response.status_code >= 400, response.text
    assert _committed(wired) == before
    assert _linked(wired) == ()


def test_an_automated_caller_may_not_create_a_document(wired: Wired) -> None:
    response = wired.post(BASE, json={}, token=AUTOMATION_TOKEN)

    assert response.status_code == 403, response.text
    assert _platform(wired).created == ()


# --------------------------------------------------------------------------
# Unlinking — the reference goes, the document does not
# --------------------------------------------------------------------------


def test_unlinking_removes_the_reference_and_touches_no_document(wired: Wired) -> None:
    _link(wired)
    _platform(wired).requests.clear()

    response = wired.delete(f"{BASE}/{RATIONALE}")
    _advance(wired)
    assert response.status_code == 200, response.text
    assert _linked(wired) == ()
    assert _platform(wired).requests == []
    assert _platform(wired).exists(DOCUMENT_WORKSPACE, RATIONALE)


def test_unlinking_something_that_is_not_linked_is_not_found(wired: Wired) -> None:
    response = wired.delete(f"{BASE}/d_nothing")

    assert response.status_code == 404, response.text


# --------------------------------------------------------------------------
# Degradation — the whole integration absent
# --------------------------------------------------------------------------


def test_with_no_platform_configured_the_listing_says_why() -> None:
    world = a_surface()
    response = _link(world)
    assert response.status_code in (200, 201), response.text

    listing = _listed(world)
    assert listing["available"] is False
    assert listing["reason"] == str(UnavailabilityReason.UNCONFIGURED)
    entry = listing["links"][0]
    assert entry["resolved"] is False
    assert entry["url"] == _address(RATIONALE)
    assert entry["actions"] == ["open", "unlink"]


def test_with_no_platform_configured_creating_reports_unavailability() -> None:
    world = a_surface()
    before = _committed(world)

    response = world.post(BASE, json={})
    assert response.status_code == 503, response.text
    assert str(UnavailabilityReason.UNCONFIGURED) in response.text
    assert _committed(world) == before
    assert _linked(world) == ()
