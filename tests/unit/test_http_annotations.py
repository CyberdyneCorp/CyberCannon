"""Task 3.4 — the annotation surface over HTTP, end to end through the real app.

Every case here drives the **application**: the versioned prefix, the pipeline
that resolves the project and the credential, the domain's policy, the use case
and the single outcome mapping. Nothing is stubbed between the request and the
repository, which is what makes this a check on the adapter being a translator
rather than on a handler somebody wrote.

The structural half of 3.4 — no conditional on specification content, and no
import from an outbound adapter — is asserted over the syntax tree by
`tests/tooling/test_http_adapter_is_a_translator.py`, which walks every module
of this package. This is the behavioural half.
"""

from __future__ import annotations

from typing import Any

import pytest
from http_world import (
    PROJECT,
    READER_TOKEN,
    SCOUT,
    STRANGER_TOKEN,
    TOKEN,
    Wired,
    a_surface,
)

from cybercanon.adapters.inbound.http.versioning import VERSION

pytestmark = pytest.mark.unit

BASE = f"/{VERSION}/projects/{PROJECT}/assets/{SCOUT}/annotations"
TRIAGE = f"/{VERSION}/projects/{PROJECT}/triage"

SPEC_PATH = "characters/mech_scout/asset.yaml"

PIN = {"view": "front", "u": 0.25, "v": 0.4}
TEXT = "the pauldron reads as a backpack at 15 m"

OK = 200
BAD_REQUEST = 400
FORBIDDEN = 403
NOT_FOUND = 404


@pytest.fixture
def wired() -> Wired:
    """A deployment serving one project whose asset declares one view.

    The in-memory store is snapshotted per revision, so :func:`advance` is run
    after every write — the real `GitSpecStore` reaches any revision its
    repository holds, and the fake only reaches the ones it was told about.
    """
    built = a_surface()
    _declare_view(built)
    advance(built)
    return built


def _declare_view(wired: Wired) -> None:
    """Give the asset a `front` view, so an anchor naming it resolves."""
    from dataclasses import replace

    from cybercanon.domain.concept import Concept

    loaded = wired.spec_store.load(SPEC_PATH)
    wired.spec_store.add(loaded.path, replace(loaded.asset, concept=Concept(views=("front",))))


def advance(wired: Wired) -> None:
    """Re-read the repository into the in-memory store, and snapshot the revision.

    `GitSpecStore` gets both for free: it reads the file, so a commit is visible
    the moment it lands, and it can pin to any revision the repository holds.
    The fake is told, which keeps the two honest against each other rather than
    letting the suite pass over a store that never saw the write.
    """
    host = wired.repository_host
    head = host.head(PROJECT)
    content = host.read(PROJECT, SPEC_PATH, head)
    if content is not None:
        wired.spec_store.add(SPEC_PATH, wired.spec_store.parse_document(SPEC_PATH, content).asset)
    wired.spec_store.snapshot(head.value)


def create(wired: Wired, identifier: str = "an_1", token: str = TOKEN, **fields: Any) -> Any:
    body = {"id": identifier, "kind": "art-direction", "text": TEXT, "anchor": PIN} | fields
    response = wired.post(BASE, token=token, json=body)
    advance(wired)
    return response


def data(response: Any) -> dict[str, Any]:
    return response.json()["data"]


def identifier(response: Any) -> str:
    return str((response.json().get("error") or {}).get("id", ""))


# --------------------------------------------------------------------------
# Creating, replying, listing
# --------------------------------------------------------------------------


def test_creating_an_annotation_answers_the_recorded_thread(wired: Wired) -> None:
    response = create(wired)

    assert response.status_code == OK, response.text
    recorded = data(response)["annotation"]
    assert recorded["id"] == "an_1"
    assert recorded["kind"] == "art-direction"
    assert recorded["anchor"]["view"] == "front"
    assert recorded["state"] == "open"


def test_a_created_annotation_is_attributed_to_the_credential(wired: Wired) -> None:
    recorded = data(create(wired))["annotation"]

    assert recorded["author"] == "auth|rafa"
    assert recorded["attribution"] == "auth|rafa"


def test_the_listing_returns_what_was_written(wired: Wired) -> None:
    create(wired)

    listed = data(wired.get(BASE, token=TOKEN))

    assert [entry["id"] for entry in listed["annotations"]] == ["an_1"]
    assert listed["hidden"] == 0
    assert listed["view_names"] == ["front"]


def test_replying_adds_one_contribution_to_the_thread(wired: Wired) -> None:
    create(wired)

    response = wired.post(f"{BASE}/an_1/replies", token=TOKEN, json={"id": "re_1", "text": "yes"})
    advance(wired)

    assert response.status_code == OK, response.text
    assert [reply["id"] for reply in data(response)["annotation"]["replies"]] == ["re_1"]


def test_a_reply_carries_no_anchor_of_its_own(wired: Wired) -> None:
    create(wired)
    wired.post(f"{BASE}/an_1/replies", token=TOKEN, json={"id": "re_1", "text": "yes"})
    advance(wired)

    reply = data(wired.get(BASE, token=TOKEN))["annotations"][0]["replies"][0]

    assert set(reply) == {"id", "author", "via", "attribution", "text", "at", "edited_at"}


# --------------------------------------------------------------------------
# What the surface refuses, and how
# --------------------------------------------------------------------------


def test_an_unknown_kind_is_refused_naming_the_allowed_values(wired: Wired) -> None:
    response = create(wired, kind="nitpick")

    assert response.status_code == BAD_REQUEST
    assert identifier(response) == "annotation.unknown_kind"
    assert "art-direction" in response.json()["error"]["message"]


def test_a_request_with_no_anchor_is_refused(wired: Wired) -> None:
    response = wired.post(BASE, token=TOKEN, json={"id": "an_1", "kind": "design", "text": TEXT})

    assert response.status_code == BAD_REQUEST
    assert identifier(response) == "annotation.malformed_anchor"


def test_a_request_carrying_both_anchor_forms_is_refused(wired: Wired) -> None:
    response = create(wired, anchor={"view": "front", "u": 0.1, "v": 0.1, "part": "SM_Arm"})

    assert response.status_code == BAD_REQUEST
    assert "names a view and a part" in response.json()["error"]["message"]


def test_an_anchor_naming_an_absent_view_is_refused_naming_it(wired: Wired) -> None:
    response = create(wired, anchor={"view": "three_quarter", "u": 0.1, "v": 0.1})

    assert response.status_code == NOT_FOUND
    assert "three_quarter" in response.json()["error"]["message"]


def test_a_coordinate_outside_the_image_is_refused(wired: Wired) -> None:
    response = create(wired, anchor={"view": "front", "u": 1.4, "v": 0.1})

    assert response.status_code == BAD_REQUEST
    assert identifier(response) == "annotation.malformed_anchor"


def test_an_actor_entitled_elsewhere_is_refused(wired: Wired) -> None:
    assert create(wired, token=STRANGER_TOKEN).status_code == FORBIDDEN


def test_a_body_that_is_not_json_is_refused_as_invalid(wired: Wired) -> None:
    response = wired.post(BASE, token=TOKEN, content=b"{not json")

    assert response.status_code == BAD_REQUEST
    assert identifier(response) == "annotation.unreadable_body"


# --------------------------------------------------------------------------
# The exits, and who may take them
# --------------------------------------------------------------------------


def test_resolving_marks_the_thread_resolved(wired: Wired) -> None:
    create(wired)

    response = wired.post(f"{BASE}/an_1/resolution", token=TOKEN, json={"conclusion": "fixed"})
    advance(wired)

    assert data(response)["annotation"]["state"] == "resolved"
    assert data(response)["annotation"]["closing_text"] == "fixed"


def test_reopening_returns_it_to_the_open_set(wired: Wired) -> None:
    create(wired)
    wired.post(f"{BASE}/an_1/resolution", token=TOKEN, json={})
    advance(wired)

    response = wired.delete(f"{BASE}/an_1/resolution", token=TOKEN)
    advance(wired)

    assert data(response)["annotation"]["state"] == "open"


def test_an_art_director_promotes_and_the_rule_lands(wired: Wired) -> None:
    create(wired)

    response = wired.post(
        f"{BASE}/an_1/promotion",
        token=TOKEN,
        json={
            "rule": "the lens glow is always emissive",
            "destination": "concept.silhouette_rules",
        },
    )
    advance(wired)

    assert response.status_code == OK, response.text
    assert data(response)["annotation"]["state"] == "promoted"


def test_a_promotion_from_a_person_who_is_not_a_director_is_refused(wired: Wired) -> None:
    """*"Hiding an action SHALL NOT be the only enforcement."*"""
    create(wired)

    response = wired.post(
        f"{BASE}/an_1/promotion",
        token=READER_TOKEN,
        json={"rule": "a rule", "destination": "constraints"},
    )

    assert response.status_code == FORBIDDEN
    assert "ART_DIRECTOR" in response.json()["error"]["message"]
    advance(wired)
    assert data(wired.get(BASE, token=TOKEN))["annotations"][0]["state"] == "open"


def test_a_promotion_with_no_destination_is_refused_naming_both(wired: Wired) -> None:
    create(wired)

    response = wired.post(f"{BASE}/an_1/promotion", token=TOKEN, json={"rule": "a rule"})

    assert response.status_code == BAD_REQUEST
    assert "concept.silhouette_rules" in response.json()["error"]["message"]


def test_the_exits_offered_are_exactly_two(wired: Wired) -> None:
    create(wired)

    listed = data(wired.get(BASE, token=TOKEN))["annotations"][0]

    assert listed["exits"] == ["promote", "resolve"]


# --------------------------------------------------------------------------
# Editing, withdrawing and moving one's own
# --------------------------------------------------------------------------


def test_editing_ones_own_annotation_rewords_it(wired: Wired) -> None:
    create(wired)

    response = wired.patch(f"{BASE}/an_1", token=TOKEN, json={"text": "the pauldron is too round"})
    advance(wired)

    assert data(response)["annotation"]["text"] == "the pauldron is too round"


def test_editing_another_persons_annotation_is_refused(wired: Wired) -> None:
    create(wired)

    response = wired.patch(f"{BASE}/an_1", token=READER_TOKEN, json={"text": "not theirs"})

    assert response.status_code == FORBIDDEN


def test_withdrawing_an_untouched_annotation_removes_it(wired: Wired) -> None:
    create(wired)

    wired.delete(f"{BASE}/an_1", token=TOKEN)
    advance(wired)

    assert data(wired.get(BASE, token=TOKEN))["annotations"] == []


def test_moving_an_annotation_records_that_it_moved(wired: Wired) -> None:
    create(wired)

    response = wired.post(
        f"{BASE}/an_1/anchor", token=TOKEN, json={"anchor": {"view": "front", "u": 0.6, "v": 0.6}}
    )
    advance(wired)

    moved = data(response)["annotation"]
    assert moved["anchor"]["u"] == 0.6
    assert moved["moved_by"] == "auth|rafa"


# --------------------------------------------------------------------------
# Filtering and the triage queue
# --------------------------------------------------------------------------


def test_the_listing_filters_by_kind_and_reports_the_hidden_count(wired: Wired) -> None:
    create(wired, "an_1", kind="art-direction")
    create(wired, "an_2", kind="technical", text="the pivot is off centre")

    listed = data(wired.get(f"{BASE}?kind=technical", token=TOKEN))

    assert [entry["id"] for entry in listed["annotations"]] == ["an_2"]
    assert listed["hidden"] == 1


def test_an_unknown_kind_in_the_filter_is_refused(wired: Wired) -> None:
    response = wired.get(f"{BASE}?kind=nitpick", token=TOKEN)

    assert response.status_code == BAD_REQUEST
    assert identifier(response) == "annotation.unknown_kind"


def test_the_triage_queue_reports_the_projects_open_annotations(wired: Wired) -> None:
    create(wired, "an_1")
    create(wired, "an_2", text="the knee reads as a joint")

    queue = data(wired.get(TRIAGE, token=TOKEN))

    assert {entry["annotation"]["id"] for entry in queue["entries"]} == {"an_1", "an_2"}
    assert queue["entries"][0]["same_kind_on_asset"] == 2


def test_the_triage_queue_filters_by_kind(wired: Wired) -> None:
    create(wired, "an_1", kind="art-direction")
    create(wired, "an_2", kind="design", text="it should telegraph the charge")

    queue = data(wired.get(f"{TRIAGE}?kind=design", token=TOKEN))

    assert [entry["annotation"]["id"] for entry in queue["entries"]] == ["an_2"]


def test_a_settled_annotation_leaves_the_queue(wired: Wired) -> None:
    create(wired)
    wired.post(f"{BASE}/an_1/resolution", token=TOKEN, json={})
    advance(wired)

    assert data(wired.get(TRIAGE, token=TOKEN))["entries"] == []
