"""Step definitions for `auth-integration` — the half that is domain policy.

This capability is mostly group 8's: verifying a credential against the issuer's
published keys, tolerating key rotation, the device flow, the offline window.
None of that exists yet and none of it is bound here.

What *is* answerable now is the part `auth-integration` insists must be
answerable without any of it — and that insistence is the whole reason these
four scenarios can be bound a sprint early:

> *"Authorization decisions and recorded actions SHALL be expressed in terms of
> a resolved actor carrying a stable identifier and a set of domain roles ... so
> that authorization behaviour can be exercised with no identity service
> present."*

So: a decision produced from a constructed actor alone, a decision that is the
same whether the actor was resolved from a credential or built by hand, a
cross-tenant address refused by policy, and a recorded action that carries a
subject and no claim vocabulary. If any of these needed an adapter, the
requirement they come from would already be broken.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.domain.authorization import WRONG_TENANT
from cybercanon.domain.identity import Actor, ActorId, Attribution, Role
from cybercanon.domain.policy import Operation, Subject, decide
from cybercanon.domain.requests import Discipline, EventKind, RequestId, raise_request
from cybercanon.domain.tenancy import ProjectRef, Tenant

PROJECT = "cyberdyne-game"
CYBERDYNE = Tenant("cyberdyne")
IRONWOOD = Tenant("ironwood-studios")

SUBJECT = "auth|rafa"
RAFA = ActorId(SUBJECT)
TOKEN = Credential("an-opaque-credential")

GROUP = "art-leads"
CLAIM = "https://auth.cyberdynecorp.ai/groups"

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


@pytest.fixture
def identity() -> dict[str, Any]:
    """What this scenario resolved, and what the policy said about it."""
    return {}


def a_person(*roles: Role, tenant: Tenant | None = None) -> Actor:
    return Actor(id=RAFA, display_name="Rafa", roles=roles, projects=(PROJECT,), tenant=tenant)


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Path-supplied tenant cannot widen access",
)
def test_path_supplied_tenant_cannot_widen_access() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Authorization tested without an identity service",
)
def test_authorization_tested_without_an_identity_service() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "No claim vocabulary in recorded actions",
)
def test_no_claim_vocabulary_in_recorded_actions() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Identical decision for identical actors",
)
def test_identical_decision_for_identical_actors() -> None: ...


# --------------------------------------------------------------------------
# Tenancy comes from the credential, and a path cannot widen it
# --------------------------------------------------------------------------


@given("a credential whose claims grant access to one tenant")
def _a_credential_for_one_tenant(identity: dict[str, Any]) -> None:
    provider = InMemoryIdentityProvider()
    provider.add(TOKEN, a_person(Role.ARTIST, tenant=CYBERDYNE))
    identity["actor"] = provider.resolve(TOKEN).actor


@when("a request addresses a project belonging to another tenant")
def _a_project_in_another_tenant(identity: dict[str, Any]) -> None:
    elsewhere = Subject(project=ProjectRef(PROJECT, tenant=IRONWOOD))
    identity["decision"] = decide(identity["actor"], Operation.READ_PROJECT, elsewhere)


@then("the request SHALL be refused")
def _the_request_was_refused(identity: dict[str, Any]) -> None:
    decision = identity["decision"]

    assert decision.refused
    assert WRONG_TENANT in decision.reason


# --------------------------------------------------------------------------
# The decision needs nothing but the actor
# --------------------------------------------------------------------------


@given("no identity service is configured or reachable")
def _no_identity_service(identity: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Proving "needs nothing external" requires a connection to fail the test."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("an authorization decision opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    identity["actor"] = a_person(Role.ART_DIRECTOR)


@when("an authorization decision is evaluated for a constructed actor")
def _a_decision_for_a_constructed_actor(identity: dict[str, Any]) -> None:
    identity["decisions"] = {
        operation: decide(identity["actor"], operation, Subject(project=PROJECT))
        for operation in Operation
    }


@then("the decision SHALL be produced from that actor's identifier and roles alone")
def _from_the_actor_alone(identity: dict[str, Any]) -> None:
    decisions = identity["decisions"]

    assert set(decisions) == set(Operation)
    assert decisions[Operation.READ_PROJECT].allowed
    assert decisions[Operation.PROMOTE_TO_RULE].allowed


@given(
    "two actors with the same roles, one resolved from a verified credential and one "
    "constructed directly"
)
def _two_actors_one_shape(identity: dict[str, Any]) -> None:
    provider = InMemoryIdentityProvider()
    provider.add(TOKEN, a_person(Role.ARTIST))
    identity["resolved"] = provider.resolve(TOKEN).actor
    identity["constructed"] = a_person(Role.ARTIST)


@when("the same operation is evaluated for each")
def _the_same_operation_for_each(identity: dict[str, Any]) -> None:
    subject = Subject(project=PROJECT)
    identity["pairs"] = {
        operation: (
            decide(identity["resolved"], operation, subject),
            decide(identity["constructed"], operation, subject),
        )
        for operation in Operation
    }


@then("both SHALL receive the same decision")
def _the_decisions_agree(identity: dict[str, Any]) -> None:
    for operation, (resolved, constructed) in identity["pairs"].items():
        assert resolved == constructed, operation


# --------------------------------------------------------------------------
# A record names a subject, and no group
# --------------------------------------------------------------------------


@when("an action is recorded")
def _an_action_is_recorded(identity: dict[str, Any]) -> None:
    """Two records the product actually writes: an attribution and a request event."""
    identity["attribution"] = Attribution(actor=RAFA)
    identity["request"] = raise_request(
        RequestId("req-0001"),
        author=RAFA,
        discipline=Discipline.MODELING,
        description="a supply crate for the loading dock",
        at=NOON,
    )


@then("the record SHALL identify the actor by its stable identifier")
def _identified_by_subject(identity: dict[str, Any]) -> None:
    (raised,) = identity["request"].history

    assert identity["attribution"].responsible == RAFA
    assert raised.kind is EventKind.RAISED
    assert raised.actor == RAFA
    assert str(raised.actor) == SUBJECT


@then("SHALL NOT contain claim or group names from the identity service")
def _no_claim_vocabulary(identity: dict[str, Any]) -> None:
    written = f"{identity['attribution']!r} {identity['request']!r}"

    assert GROUP not in written
    assert CLAIM not in written
    assert "Credential" not in written
    assert str(TOKEN.value) not in written
