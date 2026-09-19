"""Step definitions for `http-api` — the networked surface, as a client drives it.

Groups 1 and 2 answered the three scenarios that need no surface at all; group 9
built the surface and answers the rest of this capability except the three
cross-surface equivalence checks (group 11) and the role-based refusal, whose
only endpoint is a request decision (group 10).

The three that never needed a surface:

* **health does not require identity** — group 1 builds the readiness signal,
  and its whole content is that it asks nothing of anything. The scenario is
  answered by serving it with no identity service anywhere;
* **a service credential cannot promote** — decided by domain policy (D13), not
  by a router. That is the point of putting the human-only registry in the core:
  the refusal holds for every surface that ever calls the operation, including
  the ones that do not exist yet;
* **human-only actions are enumerated** — the registry is
  :data:`cybercanon.domain.policy.HUMAN_ONLY`, an explicit literal, and the
  scenario asks for exactly that: an enumeration rather than an absence.

Everything else below drives the **real application** — the versioned prefix,
the pipeline, the one outcome-to-status mapping, the routers — over the same
in-memory fakes the unit suite uses. Nothing here reaches a disk, a database or
an identity service, which is what keeps a surface suite fast enough that people
keep running it.

The fixture is built here rather than imported from `tests/unit/` on purpose: a
step module that depended on another layer's helper would only import cleanly
while both layers were being collected, and `just test-bdd` collects one.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from hashlib import sha256
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client, FastMCP
from pytest_bdd import given, scenario, then, when
from typer.testing import CliRunner

from cybercanon.adapters.inbound.cli.app import build_app as build_cli
from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.health import (
    DEPENDENCIES_FIELD,
    DOCUMENT_PLATFORM,
    LANGUAGE_MODEL,
    READY,
    READY_PATH,
    STATUS_FIELD,
)
from cybercanon.adapters.inbound.http.outcomes import INTERNAL_IDENTIFIER, INTERNAL_STATUS
from cybercanon.adapters.inbound.http.pagination import MAX_PAGE_SIZE
from cybercanon.adapters.inbound.http.surface import Dependency, HostedProject, Surface
from cybercanon.adapters.inbound.http.versioning import UNVERSIONED_IDENTIFIER, VERSION
from cybercanon.adapters.inbound.http.writes import REVISION_MISSING
from cybercanon.adapters.inbound.mcp.tools import build_server
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.idempotency import InMemoryIdempotencyStore
from cybercanon.domain.actors import ActorBinding, ActorMapping
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.identity import Actor, ActorId, Role, automation_actor
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.policy import (
    HUMAN_ONLY,
    MUTATING,
    REQUIRES_PERSON,
    Operation,
    Subject,
    decide,
    declares_human_only,
    requires_person,
)

PROJECT = "cyberdyne-game"


@pytest.fixture
def surface() -> dict[str, Any]:
    """What this scenario asked the surface, and what it answered."""
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario("../features/add-web-backend/http-api.feature", "Health does not require identity")
def test_health_does_not_require_identity() -> None: ...


@scenario("../features/add-web-backend/http-api.feature", "Service credential cannot promote")
def test_service_credential_cannot_promote() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Human-only actions are enumerated, not incidental",
)
def test_human_only_actions_are_enumerated_not_incidental() -> None: ...


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


@given("the identity service is unreachable")
def _no_identity_service(surface: dict[str, Any]) -> None:
    """Unreachable is the ordinary case here: the app is built without one."""
    surface["client"] = TestClient(build_app())


@when("the health report is requested")
def _health_is_requested(surface: dict[str, Any]) -> None:
    surface["response"] = surface["client"].get(READY_PATH)


@then("it SHALL succeed")
def _it_succeeded(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == 200
    assert response.json()["status"] == READY


# --------------------------------------------------------------------------
# Human-only operations (D13)
# --------------------------------------------------------------------------


@given("a caller authenticated with a service credential holding every role")
def _automation_holding_every_role(surface: dict[str, Any]) -> None:
    surface["actor"] = automation_actor(projects=(PROJECT,), roles=tuple(Role))


@when("it attempts to promote an annotation to a durable rule")
def _it_attempts_promotion(surface: dict[str, Any]) -> None:
    surface["decision"] = decide(
        surface["actor"], Operation.PROMOTE_TO_RULE, Subject(project=PROJECT)
    )


@then("the attempt SHALL be refused as requiring a person")
def _refused_as_requiring_a_person(surface: dict[str, Any]) -> None:
    decision = surface["decision"]

    assert decision.refused
    assert REQUIRES_PERSON in decision.reason


@when("the set of operations refused to automated callers is inspected")
def _the_registry_is_inspected(surface: dict[str, Any]) -> None:
    surface["registry"] = HUMAN_ONLY


@then(
    "it SHALL be an explicit enumeration, so that adding an operation to the surface "
    "does not silently make it available to automation"
)
def _it_is_an_explicit_enumeration(surface: dict[str, Any]) -> None:
    registry = surface["registry"]

    assert registry
    assert registry <= MUTATING
    assert all(requires_person(operation) for operation in registry)
    assert all(declares_human_only(operation) for operation in MUTATING)


# --------------------------------------------------------------------------
# The wired surface — one project, in memory, nothing reachable
# --------------------------------------------------------------------------

SCOUT = "mech_scout"
SCOUT_SPEC = "characters/mech_scout/asset.yaml"
SCOUT_CONTENT = b"id: mech_scout\n"

ASSETS = {
    SCOUT: SCOUT_SPEC,
    "supply_crate": "props/supply_crate/asset.yaml",
    "mule_hauler": "vehicles/mule_hauler/asset.yaml",
}

TOKEN = "rafa-token"
READER_TOKEN = "ana-token"
STRANGER_TOKEN = "stranger-token"
RAFA_EMAIL = "rafa@cyberdyne.com"
ANA_EMAIL = "ana@cyberdyne.com"

SCOUT_EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
SCOUT_OBJECT = "SM_mech_scout_LOD0"

TRI_BUDGET = 12000
OVER_BUDGET = 19000

TERM = "mech"
"""A term the cascade matches in two assets **through different passes**.

`mech_scout` matches on its name prefix and `supply_crate` on an alias, so the
two surfaces have to agree about the *ranking* and not merely about the set — a
surface that sorted its own results alphabetically would put the crate first and
fail this.
"""

ALIASES = {"supply_crate": ("mech",)}

BASE = f"/{VERSION}/projects/{PROJECT}"

CONFIGURED_VALUE = "postgresql://canon:hunter2@db.internal:5432/canon"


class UnreachableIndex:
    """An index whose every call raises something the domain never expressed."""

    def __getattr__(self, name: str) -> Any:
        def fails(*arguments: Any, **keywords: Any) -> Any:
            raise RuntimeError(f"could not reach {CONFIGURED_VALUE}")

        return fails


def a_person(
    subject: str,
    name: str,
    project: str = PROJECT,
    roles: tuple[Role, ...] = (Role.ART_DIRECTOR,),
) -> Actor:
    return Actor(id=ActorId(subject), display_name=name, roles=roles, projects=(project,))


def an_asset(asset_id: str) -> Asset:
    return Asset(
        id=AssetId(asset_id),
        name=asset_id.replace("_", " ").title(),
        aliases=ALIASES.get(asset_id, ()),
        owner_art=RAFA_EMAIL,
        constraints=Constraints(tri_budget=TRI_BUDGET, naming="SM_{asset}_LOD{n}"),
    )


def over_budget_facts(triangles: int = OVER_BUDGET):
    """An export that fails the one rule every surface must agree about."""
    return facts_for(
        MeshFormat.GLB,
        triangles=triangles,
        objects=(SCOUT_OBJECT,),
        transforms_applied=True,
        unit_scale=1.0,
        up_axis="Y",
        uv_sets=1,
        materials=("M_mech_scout",),
        empties=(),
        clips=(),
        frame_rate=None,
        is_skinned=False,
        bone_count=0,
    )


def a_wired_surface(*, dependencies: tuple[Dependency, ...] = ()) -> dict[str, Any]:
    """One project, its working copy, its index and two people who may or may not read it."""
    fakes = build_fakes()
    spec_store, index, host = fakes["spec_store"], fakes["search_index"], fakes["repository_host"]
    spec_store.set_project(ProjectConfig(name=PROJECT))
    for asset_id, spec_path in ASSETS.items():
        spec_store.add(spec_path, an_asset(asset_id))
        index.upsert(
            IndexedAsset(
                asset_id=asset_id,
                name=asset_id.replace("_", " ").title(),
                aliases=ALIASES.get(asset_id, ()),
                spec_path=spec_path,
                project=PROJECT,
            )
        )
    spec_store.set_actor_mapping(
        ActorMapping(
            bindings=(
                ActorBinding(subject="auth|rafa", display_name="Rafa", emails=(RAFA_EMAIL,)),
                ActorBinding(subject="auth|ana", display_name="Ana", emails=(ANA_EMAIL,)),
            )
        )
    )
    host.add_project(PROJECT, {SCOUT_SPEC: SCOUT_CONTENT})
    host.clone(PROJECT)
    spec_store.snapshot(host.head(PROJECT).value)

    provider = fakes["identity_provider"]
    fakes["mesh_inspector"].add(SCOUT_EXPORT, over_budget_facts())

    provider.add(Credential(TOKEN), a_person("auth|rafa", "Rafa"))
    provider.add(Credential(READER_TOKEN), a_person("auth|ana", "Ana", roles=()))
    provider.add(Credential(STRANGER_TOKEN), a_person("auth|sam", "Sam", "another-game"))

    container = Container(
        spec_store=spec_store,
        mesh_inspector=fakes["mesh_inspector"],
        blob_store=fakes["blob_store"],
        search_index=index,
    )
    wiring = Surface(
        projects={PROJECT: HostedProject(name=PROJECT, container=container, repository_host=host)},
        identity_provider=provider,
        idempotency=InMemoryIdempotencyStore(),
        dismissals=fakes["dismissals"],
        notifier=fakes["notifier"],
        observe=lambda: dependencies,
    )
    return {
        "client": TestClient(build_app(surface=wiring)),
        "wiring": wiring,
        "fakes": fakes,
        "container": container,
        "host": host,
        "index": index,
    }


def _headers(token: str = TOKEN, key: str = "") -> dict[str, str]:
    bearer = {"Authorization": f"Bearer {token}"} if token else {}
    return bearer | ({"Idempotency-Key": key} if key else {})


def _get(surface: dict[str, Any], path: str, token: str = TOKEN) -> Any:
    return surface["client"].get(path, headers=_headers(token))


def _an_edit(surface: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body = {
        "revision": surface["host"].head(PROJECT).value,
        "based_on": sha256(SCOUT_CONTENT).hexdigest(),
        "content": "id: mech_scout\nname: Scout\n",
    }
    return body | overrides


def _put(surface: dict[str, Any], body: dict[str, Any], key: str = "") -> Any:
    return surface["client"].put(
        f"{BASE}/assets/{SCOUT}/spec", json=body, headers=_headers(key=key)
    )


# --------------------------------------------------------------------------
# Scenarios group 9 answers
# --------------------------------------------------------------------------


@scenario("../features/add-web-backend/http-api.feature", "Validation agrees across surfaces")
def test_validation_agrees_across_surfaces() -> None: ...


@scenario("../features/add-web-backend/http-api.feature", "Compilation agrees across surfaces")
def test_compilation_agrees_across_surfaces() -> None: ...


@scenario("../features/add-web-backend/http-api.feature", "Lookup agrees across surfaces")
def test_lookup_agrees_across_surfaces() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature", "A domain refusal is not an internal error"
)
def test_a_domain_refusal_is_not_an_internal_error() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Address survives an index rebuild",
)
def test_address_survives_an_index_rebuild() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Unknown identifier is not found",
)
def test_unknown_identifier_is_not_found() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "The same outcome maps identically everywhere",
)
def test_the_same_outcome_maps_identically_everywhere() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Error bodies are machine-readable and specific",
)
def test_error_bodies_are_machine_readable_and_specific() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Correlated generic failure",
)
def test_correlated_generic_failure() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Full traversal returns each result once",
)
def test_full_traversal_returns_each_result_once() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Oversized page request is bounded",
)
def test_oversized_page_request_is_bounded() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "A continuation token grants nothing",
)
def test_a_continuation_token_grants_nothing() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Replay returns the original outcome",
)
def test_replay_returns_the_original_outcome() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Reused key with different content is refused",
)
def test_reused_key_with_different_content_is_refused() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "A retried write creates one commit",
)
def test_a_retried_write_creates_one_commit() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Stale write is refused",
)
def test_stale_write_is_refused() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Missing revision is refused",
)
def test_missing_revision_is_refused() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Unknown optional field is tolerated",
)
def test_unknown_optional_field_is_tolerated() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Unversioned request is rejected",
)
def test_unversioned_request_is_rejected() -> None: ...


@scenario(
    "../features/add-web-backend/http-api.feature",
    "Healthy while optional services are down",
)
def test_healthy_while_optional_services_are_down() -> None: ...


# --------------------------------------------------------------------------
# Addressing
# --------------------------------------------------------------------------


@given("a resource reachable at a given address")
def _a_reachable_address(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["address"] = f"{BASE}/assets/{SCOUT}"
    surface["before"] = _get(surface, surface["address"])

    assert surface["before"].status_code == 200


@when("the index is dropped and rebuilt from the repository")
def _the_index_is_rebuilt(surface: dict[str, Any]) -> None:
    surface["index"].clear()
    surface["container"].rebuild_index("")


@then("the resource SHALL be reachable at the same address")
def _reachable_at_the_same_address(surface: dict[str, Any]) -> None:
    after = _get(surface, surface["address"])

    assert after.status_code == 200
    assert after.json()["data"]["asset"] == surface["before"].json()["data"]["asset"]


@when("a resource is requested with an identifier no specification declares")
def _an_unknown_identifier_is_requested(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["response"] = _get(surface, f"{BASE}/assets/no_such_asset")


@then("the response SHALL report that it does not exist")
def _it_does_not_exist(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == 404
    assert response.json()["error"]["subject"] == "no_such_asset"


# --------------------------------------------------------------------------
# One mapping, one shape
# --------------------------------------------------------------------------


@given("two different endpoints that can both produce a not-found outcome")
def _two_endpoints_that_can_both_be_not_found(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["addresses"] = (
        f"{BASE}/assets/no_such_asset",
        f"/{VERSION}/projects/no-such-project/assets",
    )


@when("each produces it")
def _each_produces_it(surface: dict[str, Any]) -> None:
    surface["responses"] = [_get(surface, address) for address in surface["addresses"]]


@then("both SHALL return the same status class and the same error shape")
def _the_same_status_and_shape(surface: dict[str, Any]) -> None:
    first, second = surface["responses"]

    assert first.status_code == second.status_code == 404
    assert set(first.json()["error"]) == set(second.json()["error"])
    assert {"version", "correlation_id", "error"} <= set(first.json())
    assert {"version", "correlation_id", "error"} <= set(second.json())


@when("any request fails")
def _any_request_fails(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["response"] = _get(surface, f"{BASE}/assets/no_such_asset")


@then(
    "the response body SHALL carry a stable machine-readable error identifier, a "
    "human-readable message, and the subject at fault where one exists"
)
def _a_machine_readable_error_body(surface: dict[str, Any]) -> None:
    error = surface["response"].json()["error"]

    assert set(error) == {"id", "message", "subject"}
    assert error["id"] == "asset.unknown"
    assert error["message"].strip()
    assert error["subject"] == "no_such_asset"


# --------------------------------------------------------------------------
# Unexpected failures
# --------------------------------------------------------------------------


@given("an outbound dependency raises an unexpected error")
def _an_outbound_dependency_raises(surface: dict[str, Any]) -> None:
    built = a_wired_surface()
    hosted = built["wiring"].projects[PROJECT]
    broken = replace(hosted, container=replace(hosted.container, search_index=UnreachableIndex()))
    wiring = replace(built["wiring"], projects={PROJECT: broken})
    surface.update(built | {"wiring": wiring, "client": TestClient(build_app(surface=wiring))})


@when("a request encounters it")
def _a_request_encounters_it(surface: dict[str, Any]) -> None:
    surface["response"] = _get(surface, f"{BASE}/assets")


@then("the response SHALL report a generic failure with a correlation identifier")
def _a_generic_failure_with_a_correlation_identifier(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == INTERNAL_STATUS
    assert response.json()["error"]["id"] == INTERNAL_IDENTIFIER
    assert response.json()["correlation_id"]


@then("SHALL NOT contain a stack trace or any configuration value")
def _no_stack_trace_and_no_configuration(surface: dict[str, Any]) -> None:
    body = surface["response"].text

    assert "Traceback" not in body
    assert "RuntimeError" not in body
    assert CONFIGURED_VALUE not in body


# --------------------------------------------------------------------------
# Paging
# --------------------------------------------------------------------------


@given(
    "a listing of results larger than one page and a data set that does not change during traversal"
)
def _a_listing_larger_than_one_page(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["page_size"] = 1

    assert len(ASSETS) > surface["page_size"]


@when("the caller follows continuation tokens to exhaustion")
def _following_tokens_to_exhaustion(surface: dict[str, Any]) -> None:
    seen: list[str] = []
    token: str | None = None
    for _ in range(len(ASSETS) + 1):
        query = f"?page_size={surface['page_size']}" + (f"&page={token}" if token else "")
        body = _get(surface, f"{BASE}/assets{query}").json()["data"]
        seen.extend(item["asset"] for item in body["items"])
        token = body["next_token"]
        if token is None:
            break
    surface["seen"] = seen
    surface["token"] = token


@then("every result SHALL appear exactly once")
def _every_result_exactly_once(surface: dict[str, Any]) -> None:
    seen = surface["seen"]

    assert surface["token"] is None
    assert sorted(seen) == sorted(ASSETS)
    assert len(seen) == len(set(seen))


@when("a caller requests a page larger than the maximum")
def _a_page_larger_than_the_maximum(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["response"] = _get(surface, f"{BASE}/assets?page_size={MAX_PAGE_SIZE * 5}")


@then("the response SHALL return at most the maximum page size")
def _at_most_the_maximum(surface: dict[str, Any]) -> None:
    body = surface["response"].json()["data"]

    assert body["page_size"] == MAX_PAGE_SIZE
    assert len(body["items"]) <= MAX_PAGE_SIZE


@given("a continuation token issued to an actor permitted to read a project")
def _a_token_issued_to_a_permitted_actor(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["token"] = _get(surface, f"{BASE}/assets?page_size=1").json()["data"]["next_token"]

    assert surface["token"]


@when("it is presented by an actor not permitted to read that project")
def _presented_by_an_unpermitted_actor(surface: dict[str, Any]) -> None:
    surface["response"] = _get(
        surface, f"{BASE}/assets?page_size=1&page={surface['token']}", token=STRANGER_TOKEN
    )


@then("the request SHALL be refused")
def _the_request_was_refused(surface: dict[str, Any]) -> None:
    assert surface["response"].status_code == 403


# --------------------------------------------------------------------------
# Idempotency (D11)
# --------------------------------------------------------------------------


@given("a state-changing request that succeeded with a given idempotency key")
def _a_write_that_succeeded_under_a_key(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["body"] = _an_edit(surface)
    surface["first"] = _put(surface, surface["body"], key="replayed")

    assert surface["first"].status_code == 200


@when("the identical request is sent again with the same key")
def _the_identical_request_again(surface: dict[str, Any]) -> None:
    surface["second"] = _put(surface, surface["body"], key="replayed")


@then("the response SHALL describe the original outcome")
def _the_original_outcome(surface: dict[str, Any]) -> None:
    assert surface["second"].status_code == surface["first"].status_code
    assert surface["second"].json()["data"] == surface["first"].json()["data"]


@then("no second change SHALL be applied")
def _no_second_change(surface: dict[str, Any]) -> None:
    assert len(surface["host"].commits(PROJECT)) == 1


@given("an idempotency key already used for one request body")
def _a_key_already_used(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["body"] = _an_edit(surface)
    _put(surface, surface["body"], key="reused")


@when("a different request body is sent with that key")
def _a_different_body_with_that_key(surface: dict[str, Any]) -> None:
    surface["response"] = _put(surface, _an_edit(surface, content="something else\n"), key="reused")


@then("the request SHALL be refused as conflicting")
def _refused_as_conflicting(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == 409
    assert response.json()["error"]["id"] == "idempotency.mismatch"


@given("a write that was applied but whose response was lost in transit")
def _a_write_whose_response_was_lost(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["body"] = _an_edit(surface)
    _put(surface, surface["body"], key="lost-response")

    assert len(surface["host"].commits(PROJECT)) == 1


@when("the caller retries it with the same idempotency key")
def _the_caller_retries_it(surface: dict[str, Any]) -> None:
    surface["response"] = _put(surface, surface["body"], key="lost-response")


@then("the repository SHALL contain exactly one commit for that edit")
def _exactly_one_commit_for_that_edit(surface: dict[str, Any]) -> None:
    (commit,) = surface["host"].commits(PROJECT)

    assert surface["response"].status_code == 200
    assert commit.paths == (SCOUT_SPEC,)


# --------------------------------------------------------------------------
# The revision a write was based on
# --------------------------------------------------------------------------


@given("a caller composed an edit against a revision that has since changed")
def _an_edit_composed_against_a_changed_revision(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["body"] = _an_edit(surface)
    surface["host"].push_to_remote(PROJECT, SCOUT_SPEC, b"id: mech_scout\nby: someone else\n")
    surface["host"].fetch(PROJECT)
    surface["fakes"]["spec_store"].snapshot(surface["host"].head(PROJECT).value)


@when("the edit is submitted")
def _the_edit_is_submitted(surface: dict[str, Any]) -> None:
    surface["response"] = _put(surface, surface["body"])


@then("it SHALL be refused as conflicting")
def _the_edit_was_refused_as_conflicting(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == 409
    assert response.json()["error"]["id"] == "edit.conflict"


@then("the response SHALL name the current revision")
def _the_current_revision_is_named(surface: dict[str, Any]) -> None:
    assert surface["response"].json()["revision"] == surface["host"].head(PROJECT).value


@then("the stored content SHALL be unchanged")
def _the_stored_content_is_unchanged(surface: dict[str, Any]) -> None:
    stored = surface["host"].remote_files(PROJECT)[SCOUT_SPEC]

    assert stored != surface["body"]["content"].encode("utf-8")
    assert surface["host"].commits(PROJECT) == ()


@when("a specification-modifying request omits the revision it was based on")
def _a_write_with_no_revision(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    body = _an_edit(surface)
    body.pop("revision")
    surface["response"] = _put(surface, body)


@then("it SHALL be rejected as invalid")
def _rejected_as_invalid(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == 400
    assert response.json()["error"]["id"] == REVISION_MISSING
    assert surface["host"].commits(PROJECT) == ()


# --------------------------------------------------------------------------
# Versioning
# --------------------------------------------------------------------------


@given("a client written against the current version")
def _a_client_against_the_current_version(surface: dict[str, Any]) -> None:
    """A client that reads `data.items` and ignores everything else."""
    surface.update(a_wired_surface())
    surface["read"] = lambda body: [item["asset"] for item in body["data"]["items"]]
    surface["baseline"] = surface["read"](_get(surface, f"{BASE}/assets").json())


@when("the surface adds an optional response field")
def _an_optional_field_is_added(surface: dict[str, Any]) -> None:
    """The envelope is open, so an added field is the ordinary case, not an event.

    Modelled by serving the same endpoint from a wiring that states a revision
    and one that has none: the second is the shape a client was written
    against, the first is that shape plus optional fields.
    """
    hosted = replace(surface["wiring"].projects[PROJECT], repository_host=None)
    smaller = replace(surface["wiring"], projects={PROJECT: hosted})
    client = TestClient(build_app(surface=smaller))
    surface["narrower"] = client.get(f"{BASE}/assets", headers=_headers()).json()
    surface["wider"] = _get(surface, f"{BASE}/assets").json()


@then("the client's requests SHALL continue to succeed")
def _the_client_still_succeeds(surface: dict[str, Any]) -> None:
    read = surface["read"]

    assert read(surface["wider"]) == read(surface["narrower"]) == surface["baseline"]
    assert set(surface["wider"]) > set(surface["narrower"])


@when("a request is made without an identifiable surface version")
def _a_request_with_no_version(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())
    surface["response"] = _get(surface, f"/projects/{PROJECT}/assets")


@then("it SHALL be rejected as invalid rather than served by a guessed version")
def _rejected_rather_than_guessed(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == 400
    assert response.json()["error"]["id"] == UNVERSIONED_IDENTIFIER
    assert VERSION in response.json()["error"]["message"]


# --------------------------------------------------------------------------
# Health, with dependencies to describe (task 9.9)
# --------------------------------------------------------------------------


@given("the language model endpoint and the document platform are unreachable")
def _optional_services_are_down(surface: dict[str, Any]) -> None:
    surface.update(
        a_wired_surface(
            dependencies=(
                Dependency(LANGUAGE_MODEL, available=False, detail="connection refused"),
                Dependency(DOCUMENT_PLATFORM, available=False, detail="connection refused"),
            )
        )
    )


@then("it SHALL report the process as able to serve requests")
def _able_to_serve_requests(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == 200
    assert response.json()[STATUS_FIELD] == READY


@then("SHALL describe those dependencies as unavailable")
def _those_dependencies_are_described(surface: dict[str, Any]) -> None:
    described = {
        one["name"]: one["state"] for one in surface["response"].json()[DEPENDENCIES_FIELD]
    }

    assert described == {LANGUAGE_MODEL: "unavailable", DOCUMENT_PLATFORM: "unavailable"}


# --------------------------------------------------------------------------
# One core, three surfaces — the claim the whole change rests on
# --------------------------------------------------------------------------
#
# Each of these drives two *real* surfaces over one container and compares the
# answers. They would fail the day any surface grew logic of its own, which is
# the only reason they are worth running: the agreement is not asserted by
# reading both implementations, it is asserted by executing both.


@given("an export that fails its triangle budget")
def _an_export_over_its_budget(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())


@when("it is validated over HTTP and again from the command line")
def _validated_on_both_surfaces(surface: dict[str, Any]) -> None:
    surface["http"] = _get(surface, f"{BASE}/validations?export={SCOUT_EXPORT}").json()["data"]
    surface["cli"] = _cli(surface, "validate", "--json", SCOUT_EXPORT)["results"][0]


@then("both SHALL report the same violations with the same severities and the same overall outcome")
def _the_same_verdict_on_both(surface: dict[str, Any]) -> None:
    over_http, over_cli = surface["http"], surface["cli"]

    assert over_http["violations"] == over_cli["violations"]
    assert over_http["passed"] is over_cli["passed"] is False
    assert over_http["outcome"] == over_cli["outcome"]
    assert over_http["not_evaluated"] == over_cli["not_evaluated"]
    assert {one["severity"] for one in over_http["violations"]}


@given("an asset whose specification compiles to a briefing")
def _an_asset_that_compiles(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())


@when(
    "the briefing is requested over HTTP and produced from the command line at the same "
    "repository revision"
)
def _compiled_on_both_surfaces(surface: dict[str, Any]) -> None:
    surface["revision"] = surface["host"].head(PROJECT).value
    surface["http"] = _get(surface, f"{BASE}/assets/{SCOUT}/briefing").json()["data"]
    surface["cli"] = _cli(surface, "compile", "--stdout", "--json", SCOUT_SPEC)


@then("both SHALL be identical")
def _byte_identical_briefings(surface: dict[str, Any]) -> None:
    over_http, over_cli = surface["http"], surface["cli"]

    assert over_http["text"] == over_cli["text"]
    assert over_http["text"].encode("utf-8") == over_cli["text"].encode("utf-8")
    assert over_http["asset"] == over_cli["asset"]
    assert surface["host"].head(PROJECT).value == surface["revision"]


@given("a query matching several assets")
def _a_query_matching_several(surface: dict[str, Any]) -> None:
    surface.update(a_wired_surface())


@when("it is issued over HTTP and through the agent surface at the same repository revision")
def _searched_on_both_surfaces(surface: dict[str, Any]) -> None:
    surface["revision"] = surface["host"].head(PROJECT).value
    page = _get(surface, f"{BASE}/search?q={TERM}&page_size={MAX_PAGE_SIZE}").json()["data"]
    surface["http"] = [item["asset"] for item in page["items"]]
    surface["agent"] = _agent_search(surface, TERM)


@then("both SHALL return the same assets in the same order")
def _the_same_assets_in_the_same_order(surface: dict[str, Any]) -> None:
    assert surface["http"] == surface["agent"]
    assert len(surface["http"]) > 1
    assert surface["host"].head(PROJECT).value == surface["revision"]


@given("an operation the domain refuses because the actor lacks the required role")
def _an_operation_the_domain_refuses(surface: dict[str, Any]) -> None:
    """Deciding a request: G4 reserves it to the assignee or the art director."""
    surface.update(a_wired_surface())
    raised = surface["client"].post(
        f"{BASE}/requests",
        headers=_headers(READER_TOKEN),
        json={"id": "req-0001", "discipline": "modeling", "description": "a crate", "asset": SCOUT},
    )

    assert raised.status_code == 200


@when("it is requested over HTTP")
def _requested_over_http(surface: dict[str, Any]) -> None:
    surface["response"] = surface["client"].post(
        f"{BASE}/requests/req-0001/transitions",
        headers=_headers(READER_TOKEN),
        json={"state": "accepted"},
    )


@then("the response SHALL report a refusal naming the required role")
def _a_refusal_naming_the_role(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code == 403
    assert str(Role.ART_DIRECTOR) in response.json()["error"]["message"]


@then("SHALL NOT report an internal failure")
def _not_an_internal_failure(surface: dict[str, Any]) -> None:
    response = surface["response"]

    assert response.status_code != INTERNAL_STATUS
    assert response.json()["error"]["id"] != INTERNAL_IDENTIFIER


def _cli(surface: dict[str, Any], *arguments: str) -> dict[str, Any]:
    """The same operation through the command line, over the same container."""
    result = CliRunner().invoke(build_cli(surface["container"]), list(arguments))

    assert result.exit_code in (0, 1), result.output
    return json.loads(result.stdout)


def _agent_search(surface: dict[str, Any], term: str) -> list[str]:
    """The agent surface's answer, read back out of the table it renders.

    Parsing the rendering rather than calling the use case is the point: what is
    compared is what an agent actually receives, so a server that re-ordered
    results on the way out would fail this and not the one below it.
    """
    server = build_server(surface["container"])
    return _identifiers(_call(server, "search_assets", {"term": term}))


def _call(server: FastMCP, tool: str, arguments: dict[str, Any]) -> str:
    async def _run() -> str:
        async with Client(server) as client:
            answered = await client.call_tool(tool, arguments)
            return "\n".join(block.text for block in answered.content)

    return asyncio.run(_run())


def _identifiers(table: str) -> list[str]:
    """The first column of a rendered table, minus its header and its rule."""
    rows = [line for line in table.splitlines() if line.startswith("|")]
    cells = [row.strip("|").split("|")[0].strip() for row in rows]
    return [cell for cell in cells if cell not in {"asset", ""} and not set(cell) <= {"-", ":"}]
