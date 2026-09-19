"""Group 9 — the HTTP surface, driven as a client drives it.

Every test here calls the real application: the versioned prefix, the pipeline,
the outcome mapping, the routers. The fakes underneath are the ones the command
line runs against in `tests/unit/test_mcp_tools.py` and the BDD suite, which is
the point — if this surface ever answered differently from the others, it would
be answering differently about the *same* objects.

What is deliberately **not** here: the cross-surface equivalence checks (group
11), which compare this surface's answer with the command line's and belong with
the other end-to-end drills, and the request endpoints (group 10).
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from http_world import (
    PROJECT,
    SCOUT,
    SCOUT_CONTENT,
    SCOUT_SPEC,
    STRANGER_TOKEN,
    TOKEN,
    UnreachableIndex,
    Wired,
    a_surface,
    automation,
    with_broken_index,
)

from cybercanon.adapters.inbound.http import outcomes, pagination, versioning, writes
from cybercanon.adapters.inbound.http.app import INTERFACE_PATH, build_app
from cybercanon.adapters.inbound.http.health import (
    DEPENDENCIES_FIELD,
    DOCUMENT_PLATFORM,
    IDENTITY_SERVICE,
    LANGUAGE_MODEL,
    READY,
    READY_PATH,
    STATUS_FIELD,
)
from cybercanon.adapters.inbound.http.surface import Dependency, permitted, subject_for
from cybercanon.domain.policy import HUMAN_ONLY, REQUIRES_PERSON, Operation

BASE = f"/{versioning.VERSION}/projects/{PROJECT}"

OTHER_ASSETS = {
    SCOUT: SCOUT_SPEC,
    "supply_crate": "props/supply_crate/asset.yaml",
    "mule_hauler": "vehicles/mule_hauler/asset.yaml",
}


@pytest.fixture
def wired() -> Wired:
    return a_surface()


def _digest(content: bytes = SCOUT_CONTENT) -> str:
    return hashlib.sha256(content).hexdigest()


def _edit(wired: Wired, **overrides: Any) -> dict[str, Any]:
    body = {
        "revision": wired.repository_host.head(PROJECT).value,
        "based_on": _digest(),
        "content": "id: mech_scout\nname: Scout\n",
    }
    return body | overrides


# --------------------------------------------------------------------------
# 9.1 — the surface is versioned, and never guesses
# --------------------------------------------------------------------------


def test_an_address_with_no_version_is_rejected_as_invalid(wired: Wired) -> None:
    """*"rejected as invalid rather than served by a guessed version"*."""
    response = wired.get(f"/projects/{PROJECT}/assets")

    assert response.status_code == outcomes.STATUSES[_invalid()]
    assert response.json()["error"]["id"] == versioning.UNVERSIONED_IDENTIFIER


def test_an_unknown_address_inside_a_served_version_is_not_found(wired: Wired) -> None:
    """The other half: a wrong resource is not the same mistake as a wrong version."""
    response = wired.get(f"/{versioning.VERSION}/nothing-like-this")

    assert response.status_code == 404
    assert response.json()["error"]["id"] == versioning.NOT_FOUND_IDENTIFIER


def test_every_response_names_the_version_that_produced_it(wired: Wired) -> None:
    assert wired.get(f"{BASE}/assets").json()["version"] == versioning.VERSION


def test_a_client_reading_only_the_fields_it_knows_keeps_working(wired: Wired) -> None:
    """Additive evolution, checked rather than promised.

    The same endpoint is served by two wirings — one that states a revision and
    one that has no working copy to state one from — and a client written
    against the smaller shape reads both. That is what *"the surface SHALL only
    add optional fields"* buys, and the test is the client.
    """
    with_freshness = wired.get(f"{BASE}/assets").json()
    without = a_surface_without_a_working_copy().get(f"{BASE}/assets").json()

    assert _a_client_reads(with_freshness) == _a_client_reads(without)
    assert set(with_freshness) > set(without)


def _a_client_reads(body: dict[str, Any]) -> list[str]:
    """A client that knows about `data.items` and nothing else."""
    return [item["asset"] for item in body["data"]["items"]]


def a_surface_without_a_working_copy() -> Wired:
    """A surface whose project has no repository host — the local wiring."""
    from dataclasses import replace

    from fastapi.testclient import TestClient

    wired = a_surface()
    hosted = replace(wired.surface.projects[PROJECT], repository_host=None)
    surface = replace(wired.surface, projects={PROJECT: hosted})
    return Wired(client=TestClient(build_app(surface=surface)), surface=surface, fakes=wired.fakes)


# --------------------------------------------------------------------------
# 9.5 — the read endpoints, each one use case deep
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/assets",
        f"/assets/{SCOUT}",
        f"/assets/{SCOUT}/briefing",
        f"/assets/{SCOUT}/locations",
        "/search?q=mech",
        "/briefing",
    ],
)
def test_every_read_endpoint_answers_from_the_shared_use_case(wired: Wired, path: str) -> None:
    response = wired.get(f"{BASE}{path}")

    assert response.status_code == 200
    assert response.json()["data"]


def test_a_specification_read_states_the_revision_and_its_staleness(wired: Wired) -> None:
    """`hosted-repository`: every read states what it was served from (D3)."""
    body = wired.get(f"{BASE}/assets/{SCOUT}").json()

    assert body["revision"] == wired.repository_host.head(PROJECT).value
    assert body["confirmed_at"]
    assert "may_be_stale" in body


def test_an_identifier_no_specification_declares_is_not_found(wired: Wired) -> None:
    response = wired.get(f"{BASE}/assets/no_such_asset")

    assert response.status_code == 404
    assert "no_such_asset" in response.text


def test_a_project_this_deployment_does_not_serve_is_not_found(wired: Wired) -> None:
    response = wired.get(f"/{versioning.VERSION}/projects/someone-elses-game/assets")

    assert response.status_code == 404


def test_an_address_survives_an_index_rebuild(wired: Wired) -> None:
    """*"the resource SHALL be reachable at the same address"* — no row in the URL."""
    address = f"{BASE}/assets/{SCOUT}"
    before = wired.get(address)
    container = wired.surface.projects[PROJECT].container

    wired.search_index.clear()
    container.rebuild_index("")
    after = wired.get(address)

    assert before.status_code == after.status_code == 200
    assert after.json()["data"]["asset"] == before.json()["data"]["asset"]


def test_a_lens_shapes_the_projection_and_carries_no_authority(wired: Wired) -> None:
    lensed = wired.get(f"{BASE}/assets/{SCOUT}?lens=modeling").json()["data"]

    assert lensed["lens"] == "modeling"
    assert lensed["full"]
    assert len(lensed["body"]) <= len(lensed["full"])


def test_an_unknown_lens_is_invalid(wired: Wired) -> None:
    response = wired.get(f"{BASE}/assets/{SCOUT}?lens=accounting")

    assert response.status_code == 400
    assert response.json()["error"]["id"] == "lens.unknown"


# --------------------------------------------------------------------------
# 9.2, 9.3 — one mapping, one shape, and a refusal is never an internal error
# --------------------------------------------------------------------------


def test_two_endpoints_producing_not_found_agree_on_status_and_shape(wired: Wired) -> None:
    from_asset = wired.get(f"{BASE}/assets/no_such_asset")
    from_project = wired.get(f"/{versioning.VERSION}/projects/no-such-project/assets")

    assert from_asset.status_code == from_project.status_code
    assert (
        set(from_asset.json()["error"])
        == set(from_project.json()["error"])
        == {
            "id",
            "message",
            "subject",
        }
    )
    assert {"version", "correlation_id", "error"} <= set(from_asset.json())
    assert {"version", "correlation_id", "error"} <= set(from_project.json())


def test_an_error_body_carries_an_identifier_a_message_and_a_subject(wired: Wired) -> None:
    error = wired.get(f"{BASE}/assets/no_such_asset").json()["error"]

    assert error["id"] == "asset.unknown"
    assert error["message"]
    assert error["subject"] == "no_such_asset"


def test_a_caller_who_may_not_read_the_project_is_refused_not_broken(wired: Wired) -> None:
    """A domain refusal, reported as a refusal, with the sentence the domain wrote."""
    response = wired.get(f"{BASE}/assets", token=STRANGER_TOKEN)

    assert response.status_code == 403
    assert response.status_code != outcomes.INTERNAL_STATUS
    assert "may not read project" in response.json()["error"]["message"]


def test_a_request_with_no_credential_is_never_served_anonymously(wired: Wired) -> None:
    response = wired.get(f"{BASE}/assets", token="")

    assert response.status_code == 401
    assert response.json()["error"]["id"] == "auth.credential_missing"


# --------------------------------------------------------------------------
# 9.4 — an unexpected failure describes nothing
# --------------------------------------------------------------------------


def test_an_unexpected_dependency_failure_is_generic_and_correlated(wired: Wired) -> None:
    broken = with_broken_index(wired)

    response = broken.client.get(f"{BASE}/assets", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == outcomes.INTERNAL_STATUS
    assert response.json()["error"]["id"] == outcomes.INTERNAL_IDENTIFIER
    assert response.json()["correlation_id"]
    assert UnreachableIndex.detail not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


# --------------------------------------------------------------------------
# 9.6 — paging, over the real listing endpoint
# --------------------------------------------------------------------------


def test_following_continuation_tokens_returns_each_asset_exactly_once() -> None:
    wired = a_surface(assets=OTHER_ASSETS)
    seen: list[str] = []
    token: str | None = None

    for _ in range(len(OTHER_ASSETS) + 1):
        query = "?page_size=1" + (f"&page={token}" if token else "")
        body = wired.get(f"{BASE}/assets{query}").json()["data"]
        seen.extend(item["asset"] for item in body["items"])
        token = body["next_token"]
        if token is None:
            break

    assert token is None
    assert sorted(seen) == sorted(OTHER_ASSETS)
    assert len(seen) == len(set(seen))


def test_an_oversized_page_request_is_bounded(wired: Wired) -> None:
    body = wired.get(f"{BASE}/assets?page_size={pagination.MAX_PAGE_SIZE * 5}").json()["data"]

    assert body["page_size"] == pagination.MAX_PAGE_SIZE


def test_a_continuation_token_grants_nothing() -> None:
    """Presented by somebody who may not read the project, it is still refused."""
    wired = a_surface(assets=OTHER_ASSETS)
    token = wired.get(f"{BASE}/assets?page_size=1").json()["data"]["next_token"]

    refused = wired.get(f"{BASE}/assets?page_size=1&page={token}", token=STRANGER_TOKEN)

    assert token
    assert refused.status_code == 403


def test_a_token_this_surface_did_not_issue_is_refused(wired: Wired) -> None:
    response = wired.get(f"{BASE}/assets?page=not-ours")

    assert response.status_code == 400
    assert response.json()["error"]["id"] == pagination.TOKEN_IDENTIFIER


# --------------------------------------------------------------------------
# 9.7 — a write declares the revision it was based on
# --------------------------------------------------------------------------


def _spec_path() -> str:
    return f"{BASE}/assets/{SCOUT}/spec"


def test_a_clean_edit_becomes_exactly_one_attributed_commit(wired: Wired) -> None:
    response = wired.put(_spec_path(), json=_edit(wired))

    (commit,) = wired.repository_host.commits(PROJECT)
    assert response.status_code == 200
    assert commit.author.email == "rafa@cyberdyne.com"
    assert response.json()["data"]["paths"] == [SCOUT_SPEC]


def test_an_edit_that_omits_its_revision_is_rejected_as_invalid(wired: Wired) -> None:
    body = _edit(wired)
    body.pop("revision")

    response = wired.put(_spec_path(), json=body)

    assert response.status_code == 400
    assert response.json()["error"]["id"] == writes.REVISION_MISSING
    assert wired.repository_host.commits(PROJECT) == ()


def test_a_stale_edit_is_refused_with_the_current_revision_and_changes_nothing(
    wired: Wired,
) -> None:
    """D5: the precondition is the file's content, and it moved under this edit."""
    composed = _edit(wired)
    wired.repository_host.push_to_remote(PROJECT, SCOUT_SPEC, b"id: mech_scout\nby: someone else\n")
    wired.repository_host.fetch(PROJECT)
    wired.spec_store.snapshot(wired.repository_host.head(PROJECT).value)

    response = wired.put(_spec_path(), json=composed)

    assert response.status_code == 409
    assert response.json()["error"]["id"] == "edit.conflict"
    assert response.json()["revision"] == wired.repository_host.head(PROJECT).value
    assert wired.repository_host.remote_files(PROJECT)[SCOUT_SPEC] != composed["content"].encode()


def test_an_unmapped_person_is_refused_naming_the_missing_entry() -> None:
    """D8: no mapping, no write — and the refusal says where to add the line."""
    wired = a_surface(mapped=False)

    response = wired.put(_spec_path(), json=_edit(wired))

    assert response.status_code == 403
    assert ".canon/actors.yaml" in response.json()["error"]["message"]
    assert wired.repository_host.commits(PROJECT) == ()


def test_a_retried_write_with_the_same_key_creates_one_commit(wired: Wired) -> None:
    body = _edit(wired)

    first = wired.put(_spec_path(), key="k-1", json=body)
    replay = wired.put(_spec_path(), key="k-1", json=body)

    assert first.json()["data"] == replay.json()["data"]
    assert len(wired.repository_host.commits(PROJECT)) == 1


def test_a_reused_key_with_a_different_body_is_refused_as_conflicting(wired: Wired) -> None:
    wired.put(_spec_path(), key="k-2", json=_edit(wired))

    response = wired.put(_spec_path(), key="k-2", json=_edit(wired, content="something else\n"))

    assert response.status_code == 409
    assert response.json()["error"]["id"] == "idempotency.mismatch"
    assert len(wired.repository_host.commits(PROJECT)) == 1


# --------------------------------------------------------------------------
# 9.8 — the human-only registry, wired into the surface
# --------------------------------------------------------------------------


@pytest.mark.parametrize("operation", [Operation.PROMOTE_TO_RULE, Operation.ACCEPT_SUGGESTED_ALIAS])
def test_a_service_credential_holding_every_role_is_refused_a_human_action(
    operation: Operation,
) -> None:
    """D13, reached the way a router reaches it — through one function, not a habit."""
    refusal = permitted(automation(), operation, subject_for(PROJECT))

    assert refusal is not None
    assert REQUIRES_PERSON in refusal.message


def test_the_surface_refuses_automated_authorship_of_specification_content(
    wired: Wired,
) -> None:
    """G4's last row, over the endpoint rather than over the policy function."""
    response = wired.put(_spec_path(), token="scheduler-token", json=_edit(wired))

    assert response.status_code == 403
    assert response.json()["error"]["id"] == writes.AUTHORSHIP_REFUSED
    assert wired.repository_host.commits(PROJECT) == ()


def test_the_registry_the_surface_consults_is_the_domain_one() -> None:
    """No second list: the surface has no opinion about which actions are human."""
    for operation in HUMAN_ONLY:
        assert permitted(automation(), operation, subject_for(PROJECT)) is not None


# --------------------------------------------------------------------------
# 9.9 — the health report describes what it observes
# --------------------------------------------------------------------------


def test_readiness_succeeds_while_every_optional_service_is_unreachable() -> None:
    """*"a degraded dependency is visible without withholding traffic"*."""
    wired = a_surface(
        dependencies=(
            Dependency(LANGUAGE_MODEL, available=False, detail="connection refused"),
            Dependency(DOCUMENT_PLATFORM, available=False, detail="connection refused"),
            Dependency(IDENTITY_SERVICE, available=False, detail="connection refused"),
        )
    )

    response = wired.client.get(READY_PATH)
    described = {one["name"]: one["state"] for one in response.json()[DEPENDENCIES_FIELD]}

    assert response.status_code == 200
    assert response.json()[STATUS_FIELD] == READY
    assert described == {
        LANGUAGE_MODEL: "unavailable",
        DOCUMENT_PLATFORM: "unavailable",
        IDENTITY_SERVICE: "unavailable",
    }


def test_readiness_needs_no_credential_and_no_wiring() -> None:
    """The process answers before it has been given a project, an index or an issuer."""
    from fastapi.testclient import TestClient

    response = TestClient(build_app()).get(READY_PATH)

    assert response.status_code == 200
    assert response.json()[STATUS_FIELD] == READY
    assert response.json()[DEPENDENCIES_FIELD] == []


# --------------------------------------------------------------------------
# 9.10 — the interface description is generated, never maintained
# --------------------------------------------------------------------------


def test_the_published_interface_description_lists_the_implemented_endpoints(
    wired: Wired,
) -> None:
    published = wired.client.get(INTERFACE_PATH).json()
    registered = _published_routes(wired.client.app)

    assert published["paths"]
    assert set(published["paths"]) == registered
    assert published["info"]["version"] == versioning.VERSION


def test_an_endpoint_added_to_the_application_appears_in_the_description() -> None:
    """Produced from the routes: there is no hand-maintained document to update."""
    app = build_app()
    before = set(app.openapi()["paths"])

    @app.get("/v1/projects/{project}/an-addition")
    def an_addition(project: str) -> dict[str, str]:
        return {}

    app.openapi_schema = None
    after = set(app.openapi()["paths"])

    assert after - before == {"/v1/projects/{project}/an-addition"}


def _published_routes(app: Any) -> set[str]:
    """Every path the application actually registered, routers included.

    Walked rather than read off `app.routes`, because an included router is one
    entry there and several endpoints underneath it — and the claim being
    checked is about the endpoints.
    """
    found: set[str] = set()
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        pending.extend(getattr(route, "routes", ()))
        pending.extend(getattr(getattr(route, "original_router", None), "routes", ()))
        if getattr(route, "include_in_schema", False) and hasattr(route, "path"):
            found.add(route.path)
    return found


def _invalid():
    from cybercanon.application.errors import FailureKind

    return FailureKind.INVALID
