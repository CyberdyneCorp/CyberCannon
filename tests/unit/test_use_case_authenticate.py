"""Task 8.5 — how a networked request becomes an actor, and what it refuses.

The scoping is the whole point of this module, and it is easy to get subtly
wrong in a way no single test catches. `auth-integration` says a networked
request with no credential *"SHALL be refused ... and SHALL NOT be served as an
anonymous or default actor"*, while `agent-identity` says a local process with
no credential resolves to a local unauthenticated actor so that reads work
offline. Both are correct, for different surfaces, and the failure mode is one
leaking into the other.

So these tests assert the refusal *and* the absence: `authenticate` produces no
local actor, and there is no argument through which one could be asked for.

Everything runs over the in-memory identity provider. The real adapter's
verification is `tests/integration/test_cyberdyne_auth.py`; what is checked here
is the layer above it, which must behave identically whichever provider is wired
in — including one that is not there at all.
"""

from __future__ import annotations

import inspect

import pytest

from cybercanon.application.ports.identity_provider import (
    Credential,
    CredentialRejected,
    IdentityServiceUnavailable,
)
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.authenticate import (
    authenticate,
    authenticate_background,
)
from cybercanon.domain.identity import Actor, ActorId, ActorKind, Role, automation_actor

PROJECT = "Ronin"
TOKEN = Credential("a-verified-credential")
SERVICE_TOKEN = Credential("a-service-credential")

RAFA = Actor(
    id=ActorId("auth|rafa"),
    display_name="Rafa",
    roles=(Role.ARTIST,),
    projects=(PROJECT,),
)


@pytest.fixture
def provider() -> InMemoryIdentityProvider:
    identities = InMemoryIdentityProvider()
    identities.add(TOKEN, RAFA)
    identities.add(SERVICE_TOKEN, automation_actor(projects=(PROJECT,)))
    return identities


# --------------------------------------------------------------------------
# A credential resolves; its absence is refused
# --------------------------------------------------------------------------


def test_a_verified_credential_is_evaluated_as_its_person(
    provider: InMemoryIdentityProvider,
) -> None:
    authenticated = ran(authenticate(TOKEN, identity_provider=provider))

    assert authenticated.actor == RAFA
    assert authenticated.subject == "auth|rafa"


def test_no_credential_is_refused_and_never_served_as_anybody(
    provider: InMemoryIdentityProvider,
) -> None:
    """The networked half of the scoping: there is no anonymous actor here."""
    refusal = refused(authenticate(None, identity_provider=provider))

    assert refusal.identifier == "auth.credential_missing"
    assert refusal.kind.value == "unauthenticated"
    assert "anonymous" in refusal.message
    assert provider.resolutions == 0


def test_the_local_actor_is_not_reachable_from_this_surface() -> None:
    """A parameter that could ask for one is the way the two surfaces merge."""
    parameters = inspect.signature(authenticate.raising).parameters

    assert set(parameters) == {"presented", "identity_provider", "claimed"}
    assert "project" not in parameters


def test_a_rejected_credential_is_unauthenticated(provider: InMemoryIdentityProvider) -> None:
    provider.fail_with(CredentialRejected("the signature does not verify"))

    refusal = refused(authenticate(TOKEN, identity_provider=provider))

    assert refusal.kind.value == "unauthenticated"


def test_an_unreachable_identity_service_is_unavailable_rather_than_a_refusal(
    provider: InMemoryIdentityProvider,
) -> None:
    """Different sentences, because they lead a person to different actions."""
    provider.fail_with(IdentityServiceUnavailable("the published key set"))

    refusal = refused(authenticate(TOKEN, identity_provider=provider))

    assert refusal.kind.value == "unavailable"
    assert "identity service" in refusal.message


# --------------------------------------------------------------------------
# Nothing the caller claims about themselves has any effect
# --------------------------------------------------------------------------


def test_a_body_supplied_actor_is_ignored_and_named(
    provider: InMemoryIdentityProvider,
) -> None:
    authenticated = ran(
        authenticate(
            TOKEN,
            identity_provider=provider,
            claimed={"actor": "auth|somebody-else", "roles": ["ART_DIRECTOR"], "lens": "art"},
        )
    )

    assert authenticated.actor == RAFA
    assert authenticated.actor.roles == (Role.ARTIST,)
    assert set(authenticated.ignored) == {"actor", "roles"}


def test_claiming_nothing_is_the_ordinary_case(provider: InMemoryIdentityProvider) -> None:
    assert ran(authenticate(TOKEN, identity_provider=provider)).ignored == ()


# --------------------------------------------------------------------------
# Background work: automation, and it cannot be a person
# --------------------------------------------------------------------------


def test_a_service_credential_authenticates_as_automation(
    provider: InMemoryIdentityProvider,
) -> None:
    authenticated = ran(authenticate_background(SERVICE_TOKEN, identity_provider=provider))

    assert authenticated.is_automation
    assert authenticated.actor.kind is ActorKind.AUTOMATION


def test_a_person_reaching_the_background_path_is_refused(
    provider: InMemoryIdentityProvider,
) -> None:
    """Neither recorded as nobody nor as somebody who was asleep."""
    refusal = refused(authenticate_background(TOKEN, identity_provider=provider))

    assert refusal.identifier == "auth.not_automation"
    assert refusal.kind.value == "forbidden"


def test_a_service_credential_supplying_a_person_is_still_automation(
    provider: InMemoryIdentityProvider,
) -> None:
    authenticated = ran(
        authenticate_background(
            SERVICE_TOKEN,
            identity_provider=provider,
            claimed={"actor": "auth|rafa", "on_behalf_of": "auth|rafa"},
        )
    )

    assert authenticated.is_automation
    assert "auth|rafa" not in authenticated.subject
    assert set(authenticated.ignored) == {"actor", "on_behalf_of"}


def test_background_work_with_no_credential_is_refused_too(
    provider: InMemoryIdentityProvider,
) -> None:
    refusal = refused(authenticate_background(None, identity_provider=provider))

    assert refusal.kind.value == "unauthenticated"
