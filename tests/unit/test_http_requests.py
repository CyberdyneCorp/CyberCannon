"""Tasks 10.1-10.6 — asset requests over HTTP, end to end through the real app.

Every test here drives the wired application: the versioned prefix, the
pipeline, the policy call, the use case, the in-memory repository host. What is
asserted is the six claims group 10 makes, and each one is a sentence somebody
wrote down:

* **10.1** a reader-only actor may raise, and a non-assignee without the
  responsible role is refused acceptance *naming the required role*;
* **10.2** one file per request (D7), one commit per transition, each authored
  by the acting person (D8);
* **10.3** the index-rebuild guarantee: drop the index, rebuild it, and every
  request is still there with the same state, assignee and attribution — which
  holds because the index was never asked in the first place;
* **10.4** a request whose commit did not land does not appear and its author is
  told it was not recorded;
* **10.5** unread items are derived and dismissal is per person (D9);
* **10.6** no request operation creates or changes durable specification
  content.

The seventh claim is the one the module docstring of
`adapters/inbound/http/requests.py` argues: an unmapped person may read
everything and raise nothing, because `asset-requests` and `hosted-repository`
disagree and the stricter reading is the one that keeps history attributable.
"""

from __future__ import annotations

from typing import Any

import pytest
from http_world import (
    ANA,
    AUTOMATION_TOKEN,
    PROJECT,
    RAFA,
    RAFA_EMAIL,
    READER_TOKEN,
    SCOUT,
    SCOUT_SPEC,
    Wired,
    a_surface,
    an_asset,
)

from cybercanon.adapters.inbound.http.requests import (
    UNKNOWN_DISCIPLINE,
    UNKNOWN_STATE,
)
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.application.use_cases.requests import REQUESTS_DIR, path_for
from cybercanon.domain.identity import Role
from cybercanon.domain.requests import RequestId

pytestmark = pytest.mark.unit

BASE = f"/{VERSION}/projects/{PROJECT}"
REQUESTS = f"{BASE}/requests"

WANTED = "a supply crate for the loading dock, one metre cubed"
REQUEST = "req-0001"


@pytest.fixture
def wired() -> Wired:
    """One project whose only asset is owned, for art, by the acting person."""
    built = a_surface()
    built.spec_store.add(SCOUT_SPEC, an_asset(SCOUT, owner_art=RAFA_EMAIL))
    return built


def a_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": REQUEST,
        "discipline": "modeling",
        "description": WANTED,
    }
    return body | overrides


def raise_one(wired: Wired, token: str = READER_TOKEN, **overrides: Any) -> Any:
    return wired.post(REQUESTS, token=token, json=a_body(**overrides))


def move(wired: Wired, state: str, token: str, request_id: str = REQUEST, **extra: Any) -> Any:
    return wired.post(
        f"{REQUESTS}/{request_id}/transitions", token=token, json={"state": state, **extra}
    )


# --------------------------------------------------------------------------
# 10.1 — who may raise, and who may decide
# --------------------------------------------------------------------------


def test_an_actor_with_only_read_access_may_raise_a_request(wired: Wired) -> None:
    """`asset-requests`: *"Any actor permitted to read a project ... SHALL"*."""
    response = raise_one(wired)

    assert response.status_code == 200
    assert response.json()["data"]["request"]["author"] == ANA
    assert response.json()["data"]["request"]["description"] == WANTED


def test_a_request_against_an_owned_asset_is_assigned_to_its_discipline_owner(
    wired: Wired,
) -> None:
    raised = raise_one(wired, asset=SCOUT)

    assert raised.json()["data"]["request"]["assignee"] == RAFA
    assert raised.json()["data"]["request"]["needs_owner"] is False


def test_a_request_for_an_asset_nobody_owns_is_unassigned_and_says_so(wired: Wired) -> None:
    """*"recorded as unassigned and reported as needing an owner"*."""
    raised = raise_one(wired)

    assert raised.json()["data"]["request"]["assignee"] is None
    assert raised.json()["data"]["request"]["needs_owner"] is True


def test_a_non_assignee_without_the_responsible_role_is_refused_acceptance(
    wired: Wired,
) -> None:
    """The refusal names what would be required, as `asset-requests` demands."""
    raise_one(wired, asset=SCOUT)

    refused = move(wired, "accepted", token=READER_TOKEN)

    assert refused.status_code == 403
    assert str(Role.ART_DIRECTOR) in refused.json()["error"]["message"]


def test_the_assignee_may_accept_the_request(wired: Wired) -> None:
    raise_one(wired, asset=SCOUT)

    accepted = move(wired, "accepted", token="rafa-token")

    assert accepted.status_code == 200
    assert accepted.json()["data"]["request"]["state"] == "accepted"


def test_an_automated_caller_is_refused_a_decision_however_many_roles_it_holds(
    wired: Wired,
) -> None:
    """D13: deciding a request is human-only, and the registry is checked first."""
    raise_one(wired, asset=SCOUT)

    refused = move(wired, "accepted", token=AUTOMATION_TOKEN)

    assert refused.status_code == 403
    assert "requires a person" in refused.json()["error"]["message"]


def test_an_unmapped_person_may_read_but_may_not_raise(wired: Wired) -> None:
    """The stricter reading of two specifications that disagree (D7, D8)."""
    unmapped = a_surface(mapped=False)

    assert unmapped.get(f"{BASE}/requests").status_code == 200

    refused = raise_one(unmapped)

    assert refused.status_code == 403
    assert "actors mapping" in refused.json()["error"]["message"]
    assert unmapped.repository_host.commits(PROJECT) == ()


def test_an_unknown_discipline_is_refused_as_invalid(wired: Wired) -> None:
    refused = raise_one(wired, discipline="marketing")

    assert refused.status_code == 400
    assert refused.json()["error"]["id"] == UNKNOWN_DISCIPLINE


def test_an_unknown_state_is_refused_as_invalid(wired: Wired) -> None:
    raise_one(wired, asset=SCOUT)

    refused = move(wired, "nearly-done", token="rafa-token")

    assert refused.status_code == 400
    assert refused.json()["error"]["id"] == UNKNOWN_STATE


def test_a_request_with_no_description_is_rejected(wired: Wired) -> None:
    refused = raise_one(wired, description="   ")

    assert refused.status_code == 400
    assert wired.repository_host.commits(PROJECT) == ()


# --------------------------------------------------------------------------
# 10.2 — one file per request, one commit per transition, each attributed
# --------------------------------------------------------------------------


def test_a_full_lifecycle_produces_one_commit_per_transition_authored_by_the_actor(
    wired: Wired,
) -> None:
    raise_one(wired, asset=SCOUT)
    move(wired, "accepted", token="rafa-token")
    move(wired, "fulfilled", token="rafa-token")

    commits = wired.repository_host.commits(PROJECT)

    assert [commit.paths for commit in commits] == [(path_for(RequestId(REQUEST)),)] * 3
    assert [commit.author.email for commit in commits] == [
        "ana@cyberdyne.com",
        RAFA_EMAIL,
        RAFA_EMAIL,
    ]


def test_every_transition_is_in_the_one_file_that_request_lives_in(wired: Wired) -> None:
    """D7: one file per request, with its state history in the file."""
    raise_one(wired, asset=SCOUT)
    move(wired, "accepted", token="rafa-token")

    stored = wired.repository_host.remote_files(PROJECT)
    written = {path for path in stored if path.startswith(REQUESTS_DIR)}

    assert written == {path_for(RequestId(REQUEST))}


def test_the_history_records_who_moved_it_and_when(wired: Wired) -> None:
    raise_one(wired, asset=SCOUT)
    move(wired, "accepted", token="rafa-token")

    read = wired.get(f"{REQUESTS}/{REQUEST}").json()["data"]
    last = read["history"][-1]

    assert last["actor"] == RAFA
    assert last["state"] == "accepted"
    assert last["at"]


def test_reassignment_is_attributed_and_moves_nothing_else(wired: Wired) -> None:
    raise_one(wired, asset=SCOUT)

    assigned = wired.put(f"{REQUESTS}/{REQUEST}/assignee", json={"assignee": ANA})

    assert assigned.status_code == 200
    assert assigned.json()["data"]["request"]["assignee"] == ANA
    assert assigned.json()["data"]["request"]["state"] == "open"


def test_a_declined_request_without_a_reason_is_refused(wired: Wired) -> None:
    raise_one(wired, asset=SCOUT)

    refused = move(wired, "declined", token="rafa-token")

    assert refused.status_code == 400
    assert len(wired.repository_host.commits(PROJECT)) == 1


def test_fulfilment_is_refused_until_the_asset_reaches_the_asked_for_status(
    wired: Wired,
) -> None:
    """The precondition reads the asset's position and never writes it."""
    raise_one(wired, asset=SCOUT, asked_for="validated")
    move(wired, "accepted", token="rafa-token")

    refused = move(wired, "fulfilled", token="rafa-token")

    assert refused.status_code == 409
    assert "validated" in refused.json()["error"]["message"]


def test_a_retried_raise_under_one_key_produces_one_commit(wired: Wired) -> None:
    body = a_body(asset=SCOUT)

    first = wired.post(REQUESTS, token=READER_TOKEN, key="retried", json=body)
    second = wired.post(REQUESTS, token=READER_TOKEN, key="retried", json=body)

    assert first.json()["data"] == second.json()["data"]
    assert len(wired.repository_host.commits(PROJECT)) == 1


# --------------------------------------------------------------------------
# 10.3 — the index-rebuild guarantee, for requests
# --------------------------------------------------------------------------


def test_requests_survive_the_index_being_dropped_and_rebuilt(wired: Wired) -> None:
    """Open, accepted and terminal, through a drop and a rebuild (D7)."""
    _three_requests(wired)
    before = wired.get(REQUESTS).json()["data"]["items"]

    wired.search_index.clear()
    wired.surface.projects[PROJECT].container.rebuild_index("")

    assert wired.get(REQUESTS).json()["data"]["items"] == before
    assert [(one["state"], one["assignee"]) for one in before] == [
        ("open", RAFA),
        ("accepted", RAFA),
        ("withdrawn", RAFA),
    ]


def test_a_listing_is_ordered_by_identifier_and_pages(wired: Wired) -> None:
    _three_requests(wired)

    page = wired.get(f"{REQUESTS}?page_size=2").json()["data"]

    assert [one["id"] for one in page["items"]] == ["req-0001", "req-0002"]
    assert page["next_token"]


# --------------------------------------------------------------------------
# 10.4 — a request that was not persisted did not happen
# --------------------------------------------------------------------------


def test_a_request_whose_commit_did_not_land_is_absent_and_its_author_is_told(
    wired: Wired,
) -> None:
    wired.repository_host.reject_next_pushes(PROJECT, times=9)

    refused = raise_one(wired)

    assert refused.status_code == 409
    assert refused.json()["error"]["message"]
    assert wired.get(REQUESTS).json()["data"]["items"] == []
    assert wired.get(f"{REQUESTS}/{REQUEST}").status_code == 404


# --------------------------------------------------------------------------
# 10.5 — unread items, derived, dismissed per person (D9)
# --------------------------------------------------------------------------


def test_the_assignee_sees_the_request_among_their_unread_items(wired: Wired) -> None:
    raise_one(wired, asset=SCOUT)

    unread = wired.get(f"{BASE}/unread").json()["data"]

    assert unread["count"] == 1
    assert [one["id"] for one in unread["items"]] == [REQUEST]


def test_one_persons_dismissal_leaves_the_item_unread_for_the_other(wired: Wired) -> None:
    raise_one(wired, asset=SCOUT)

    dismissed = wired.post(f"{BASE}/unread/{REQUEST}/dismissal")

    assert dismissed.status_code == 200
    assert wired.get(f"{BASE}/unread").json()["data"]["count"] == 0
    assert wired.get(f"{BASE}/unread", token=READER_TOKEN).json()["data"]["count"] == 1


def test_dismissing_something_that_does_not_exist_is_not_found(wired: Wired) -> None:
    assert wired.post(f"{BASE}/unread/req-9999/dismissal").status_code == 404


def test_an_unrelated_person_sees_no_unread_item(wired: Wired) -> None:
    """Only the assignee and the author, which is what D9 derives the query from."""
    raise_one(wired, asset=SCOUT)
    wired.put(f"{REQUESTS}/{REQUEST}/assignee", json={"assignee": "auth|nobody"})

    assert wired.get(f"{BASE}/unread").json()["data"]["count"] == 0
    assert wired.get(f"{BASE}/unread", token=READER_TOKEN).json()["data"]["count"] == 1


def test_a_failing_notifier_does_not_reverse_an_acceptance(wired: Wired) -> None:
    raise_one(wired, asset=SCOUT)
    wired.notifier.fail_with(ConnectionError("the notifier is down"))

    accepted = move(wired, "accepted", token="rafa-token")

    assert accepted.status_code == 200
    assert wired.get(f"{REQUESTS}/{REQUEST}").json()["data"]["state"] == "accepted"


# --------------------------------------------------------------------------
# 10.6 — a request is not a constraint
# --------------------------------------------------------------------------


def test_no_request_operation_changes_durable_specification_content(wired: Wired) -> None:
    before = dict(wired.repository_host.remote_files(PROJECT))

    raise_one(wired, asset=SCOUT)
    wired.put(f"{REQUESTS}/{REQUEST}/assignee", json={"assignee": RAFA})
    move(wired, "accepted", token="rafa-token")
    move(wired, "fulfilled", token="rafa-token")
    wired.post(f"{BASE}/unread/{REQUEST}/dismissal")

    after = wired.repository_host.remote_files(PROJECT)
    changed = {path for path, content in after.items() if before.get(path) != content}

    assert changed == {path_for(RequestId(REQUEST))}
    assert after[SCOUT_SPEC] == before[SCOUT_SPEC]
    assert {path for commit in wired.repository_host.commits(PROJECT) for path in commit.paths} == {
        path_for(RequestId(REQUEST))
    }


def _three_requests(wired: Wired) -> None:
    """One open, one accepted and one terminal — the three 10.3 asks for."""
    raise_one(wired, id="req-0001", asset=SCOUT)
    raise_one(wired, id="req-0002", asset=SCOUT)
    raise_one(wired, id="req-0003", asset=SCOUT)
    move(wired, "accepted", token="rafa-token", request_id="req-0002")
    move(wired, "withdrawn", token=READER_TOKEN, request_id="req-0003")
