"""Step definitions for `http-api` — what groups 1 and 2 of this change answer.

Three scenarios, and they are the three that do not need the surface itself:

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

Everything else this capability specifies — the versioned prefix, the single
outcome-to-status mapping, pagination, idempotency, revision preconditions, the
generated interface description, and the cross-surface equivalence checks — is
groups 9 and 11, and stays in `tests/bdd/pending.txt` until then.

**"Healthy while optional services are down" is deliberately still pending**,
even though the health endpoint exists: its second clause requires the report to
*describe those dependencies as unavailable*, and describing a dependency means
observing one. That is task 9.9.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, scenario, then, when

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.health import READY, READY_PATH
from cybercanon.domain.identity import Role, automation_actor
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
