"""One actor, one entitlement, every project-scoped endpoint — one verdict.

This is the test that was missing, and the bug it would have caught was in
production shape: a repository cloned as `ronin`, a `.canon/project.yaml`
declaring `name: Ronin`, and an actor entitled to the project reading the asset
list happily while the asset *page* refused them. Two endpoints, two different
answers to *which project is this*, and neither of them wrong on its own —
:func:`~cybercanon.adapters.inbound.http.routing.prepared_for` authorizes
against the address in the path, and
:func:`~cybercanon.application.use_cases.spec_lens.read_asset_spec` re-authorizes
inside the use case against whatever the working copy calls itself.

`http-api` settles which one is right: *"Every addressable resource SHALL be
identified by a project identifier ... and SHALL remain reachable at that
address for as long as the resource exists."* An entitlement that changed
because somebody edited a line in a file in the repository would be an address
that stopped working after a commit. So the address wins, and
:class:`~cybercanon.adapters.inbound.http.surface.HostedProject` pins the
container to it.

**The suite is written as an enumeration on purpose.** Every route the
application registers under `/projects/{project}` has to appear in
:data:`CALLS`, and :func:`test_every_project_scoped_route_is_exercised` fails
when one does not. A surface that grows a fifteenth project-scoped endpoint
cannot quietly grow a fifteenth opinion about entitlement with it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from http_world import (
    ANA,
    PROJECT,
    RAFA,
    SCOUT,
    STRANGER_TOKEN,
    TOKEN,
    Wired,
    a_surface,
    an_asset,
)

from cybercanon.adapters.inbound.http.surface import POLICY_REFUSED, UNKNOWN_PROJECT
from cybercanon.adapters.inbound.http.versioning import PREFIX, VERSION

pytestmark = pytest.mark.unit

DECLARED = "Ronin"
"""What the working copy calls itself — deliberately not the address it is served at."""

BASE = f"/{VERSION}/projects/{PROJECT}"
PROJECT_PREFIX = f"{PREFIX}/projects/{{project}}"

REQUEST = "req-0001"
ANNOTATION = "an-0001"
FORBIDDEN = 403

EDIT = {"revision": "abc123", "content": "id: mech_scout\n", "summary": "an edit"}
RAISED = {"id": REQUEST, "discipline": "modeling", "description": "a crate"}
UPLOAD = {"images": [{"slot": "front", "content": ""}]}
"""Enough of an upload to reach the authorization decision, and no more."""

PIN = {
    "id": ANNOTATION,
    "kind": "art-direction",
    "text": "the pauldron reads as a backpack",
    "anchor": {"view": "front", "u": 0.25, "v": 0.4},
}
REPLY = {"id": "re-0001", "text": "agreed"}
MOVED = {"anchor": {"view": "front", "u": 0.6, "v": 0.6}}
PROMOTION = {"rule": "the lens glow is always emissive", "destination": "concept.silhouette_rules"}
REANCHORED = {"anchor": {"part": "SM_MechScout_Pauldron_L"}}
"""Enough of each annotation write to reach its authorization decision."""


@dataclass(frozen=True)
class Call:
    """One project-scoped endpoint, and a request that reaches its authorization.

    The body only has to be good enough to get past parsing: what is being
    asserted is *which* refusal comes back, never that the operation succeeded.
    """

    method: str
    path: str
    body: dict[str, Any] | None = None

    @property
    def route(self) -> str:
        """The registered path this call exercises, with its parameters back in."""
        return (
            self.path.split("?")[0]
            .replace(f"/projects/{PROJECT}", "/projects/{project}")
            .replace(f"/assets/{SCOUT}", "/assets/{asset}")
            .replace(f"/{REQUEST}", "/{request_id}")
            .replace(f"/{ANNOTATION}", "/{annotation}")
            .replace("/views/front/revisions/r1", "/views/{slot}/revisions/{revision}")
            .replace("/views/front", "/views/{slot}")
        )


CALLS: tuple[Call, ...] = (
    Call("GET", f"{BASE}/assets"),
    Call("GET", f"{BASE}/assets/{SCOUT}"),
    Call("GET", f"{BASE}/assets/{SCOUT}/briefing"),
    Call("GET", f"{BASE}/assets/{SCOUT}/locations"),
    Call("PUT", f"{BASE}/assets/{SCOUT}/spec", EDIT),
    Call("GET", f"{BASE}/search?q=scout"),
    Call("GET", f"{BASE}/briefing"),
    Call("GET", f"{BASE}/validations?export=exports/mech_scout.glb"),
    Call("GET", f"{BASE}/requests"),
    Call("POST", f"{BASE}/requests", RAISED),
    Call("GET", f"{BASE}/requests/{REQUEST}"),
    Call("PUT", f"{BASE}/requests/{REQUEST}/assignee", {"assignee": ANA}),
    Call("POST", f"{BASE}/requests/{REQUEST}/transitions", {"state": "accepted"}),
    Call("GET", f"{BASE}/unread"),
    Call("POST", f"{BASE}/unread/{REQUEST}/dismissal", {}),
    Call("POST", f"{BASE}/assets/{SCOUT}/views", UPLOAD),
    Call("DELETE", f"{BASE}/assets/{SCOUT}/views/front"),
    Call("GET", f"{BASE}/assets/{SCOUT}/views/front/revisions"),
    Call("GET", f"{BASE}/assets/{SCOUT}/views/front/revisions/r1"),
    Call("GET", f"{BASE}/assets/{SCOUT}/views/front/comparison?first=r1&second=r2"),
    Call("GET", f"{BASE}/assets/{SCOUT}/views/front/token"),
    Call("GET", f"{BASE}/assets/{SCOUT}/annotations"),
    Call("POST", f"{BASE}/assets/{SCOUT}/annotations", PIN),
    Call("PATCH", f"{BASE}/assets/{SCOUT}/annotations/{ANNOTATION}", {"text": "reworded"}),
    Call("DELETE", f"{BASE}/assets/{SCOUT}/annotations/{ANNOTATION}"),
    Call("POST", f"{BASE}/assets/{SCOUT}/annotations/{ANNOTATION}/replies", REPLY),
    Call("POST", f"{BASE}/assets/{SCOUT}/annotations/{ANNOTATION}/anchor", MOVED),
    Call("POST", f"{BASE}/assets/{SCOUT}/annotations/{ANNOTATION}/resolution", {}),
    Call("DELETE", f"{BASE}/assets/{SCOUT}/annotations/{ANNOTATION}/resolution"),
    Call("POST", f"{BASE}/assets/{SCOUT}/annotations/{ANNOTATION}/promotion", PROMOTION),
    Call("POST", f"{BASE}/assets/{SCOUT}/annotations/{ANNOTATION}/reanchor", REANCHORED),
    Call("GET", f"{BASE}/assets/{SCOUT}/preview"),
    Call("GET", f"{BASE}/assets/{SCOUT}/preview/content"),
    Call("GET", f"{BASE}/assets/{SCOUT}/preview/resolutions"),
    Call("GET", f"{BASE}/triage"),
)
"""Every project-scoped endpoint, as one call each. Kept complete by a test."""


@pytest.fixture
def wired() -> Wired:
    """A deployment whose address and whose declared project name differ.

    This is the shape the review found in the repository under `examples/`, and
    it is the shape a studio produces without trying: git repositories are
    lowercase and hyphenated, and a project's own name is written by a person.
    """
    built = a_surface(declared=DECLARED)
    built.spec_store.add(f"characters/{SCOUT}/asset.yaml", an_asset(SCOUT, owner_art=RAFA))
    return built


def _issue(wired: Wired, call: Call, token: str) -> Any:
    if call.method == "GET":
        return wired.get(call.path, token=token)
    if call.method == "PUT":
        return wired.put(call.path, token=token, json=call.body)
    if call.method == "DELETE":
        return wired.delete(call.path, token=token)
    if call.method == "PATCH":
        return wired.patch(call.path, token=token, json=call.body)
    return wired.post(call.path, token=token, json=call.body)


def _identifier(response: Any) -> str:
    """The stable error identifier a refusal carries, or an empty string."""
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):  # pragma: no cover — a non-JSON body
        return ""
    return str((body.get("error") or {}).get("id", ""))


# --------------------------------------------------------------------------
# The two verdicts, each of which has to be unanimous
# --------------------------------------------------------------------------


@pytest.mark.parametrize("call", CALLS, ids=lambda call: f"{call.method} {call.route}")
def test_an_entitled_actor_is_refused_by_no_project_scoped_endpoint(
    wired: Wired, call: Call
) -> None:
    """One entitlement, fourteen endpoints, and not one of them may disagree.

    The assertion is deliberately about the *verdict* and not about success: a
    validation of an export that is not there is a not-found and a malformed
    edit is invalid, and both are fine. What may not happen is a refusal for
    lack of permission, or a not-found that says this deployment serves no such
    project — the two answers that mean *the endpoint disagreed about which
    project you are in*.
    """
    response = _issue(wired, call, TOKEN)

    assert response.status_code != FORBIDDEN, response.text
    assert _identifier(response) not in {POLICY_REFUSED, UNKNOWN_PROJECT}, response.text


@pytest.mark.parametrize("call", CALLS, ids=lambda call: f"{call.method} {call.route}")
def test_an_actor_entitled_elsewhere_is_refused_by_every_project_scoped_endpoint(
    wired: Wired, call: Call
) -> None:
    """The other direction, which is what stops the first one being satisfied by
    removing the check: an actor entitled to a different project is refused by
    all of them, with the one identifier the policy refusal carries."""
    response = _issue(wired, call, STRANGER_TOKEN)

    assert response.status_code == FORBIDDEN, response.text
    assert _identifier(response) == POLICY_REFUSED, response.text


def test_every_project_scoped_route_is_exercised(wired: Wired) -> None:
    """A new project-scoped endpoint fails this suite until it is listed.

    The enumeration is the point. A table somebody has to remember to extend is
    a table that stops being complete in the week somebody is busy, which is how
    the fifteenth endpoint acquires the fifteenth opinion. It reads the generated
    interface description rather than the route objects, because that document is
    produced from the implemented endpoints and from nothing else (task 9.10).
    """
    described = wired.client.app.openapi()["paths"]
    registered = {
        (method.upper(), path)
        for path, operations in described.items()
        for method in operations
        if path.startswith(PROJECT_PREFIX)
    }

    assert registered == {(call.method, call.route) for call in CALLS}


def test_the_address_and_not_the_declared_name_is_what_the_container_answers(
    wired: Wired,
) -> None:
    """The mechanism, asserted directly, so the reason the suite passes is visible."""
    hosted = wired.surface.projects[PROJECT]

    assert hosted.container.project_name == PROJECT
    assert hosted.container.project().name == DECLARED
