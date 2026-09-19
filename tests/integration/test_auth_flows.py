"""Tasks 8.6 and 8.8 — the three ways a credential is obtained, against a real issuer.

The device flow, the browser's authorization-code exchange and the service
credential, each run end to end over `canon_issuer.FakeIssuer`: it hands out
device codes, waits for an approval, binds an authorization code to the PKCE
challenge it was given and refuses an exchange whose verifier does not match,
and mints a client-credentials token that carries the grant claim the adapter
reads as automation.

The requirement these serve is mostly about what does *not* happen. No password
is transmitted, because there is no parameter anywhere in these classes that
could carry one. No client secret is embedded in the browser flow, because
:class:`~cybercanon.adapters.outbound.auth.flows.BrowserSignIn` has no
constructor argument for one. And an authorization code presented without its
proof does not become a credential — which is checked against an issuer that
really performs the comparison rather than against an assertion about intent.
"""

from __future__ import annotations

import inspect

import pytest

from canon_issuer import AUTHORIZE_PATH, DEVICE_CODE_PATH, TOKEN_PATH, FakeIssuer
from cybercanon.adapters.outbound.auth import pkce
from cybercanon.adapters.outbound.auth.flows import (
    BrowserSignIn,
    DeviceAuthorization,
    Endpoints,
    ServiceCredentials,
)
from cybercanon.adapters.outbound.auth.oauth import OAuthRefusal
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.interactive_sign_in import SignInFailed, SignInUnavailable

REDIRECT = "https://canon.cyberdynecorp.ai/signed-in"

PASSWORD_WORDS = frozenset({"password", "passphrase", "secret"})
"""Argument names a flow that asked a person for a secret would have."""


@pytest.fixture
def issuer() -> FakeIssuer:
    return FakeIssuer()


@pytest.fixture
def endpoints(issuer: FakeIssuer) -> Endpoints:
    return Endpoints(
        token=f"{issuer.issuer}{TOKEN_PATH}",
        device_authorization=f"{issuer.issuer}{DEVICE_CODE_PATH}",
        authorization=f"{issuer.issuer}{AUTHORIZE_PATH}",
    )


@pytest.fixture
def device(issuer: FakeIssuer, endpoints: Endpoints) -> DeviceAuthorization:
    return DeviceAuthorization(
        endpoints=endpoints,
        client_id=issuer.client_id,
        transport=issuer,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
    )


@pytest.fixture
def browser(issuer: FakeIssuer, endpoints: Endpoints) -> BrowserSignIn:
    return BrowserSignIn(
        endpoints=endpoints,
        client_id=issuer.client_id,
        redirect_uri=REDIRECT,
        transport=issuer,
    )


# --------------------------------------------------------------------------
# The terminal: device authorization
# --------------------------------------------------------------------------


def test_a_person_approves_in_a_browser_and_the_terminal_gets_a_credential(
    device: DeviceAuthorization, issuer: FakeIssuer
) -> None:
    grant = device.begin()
    issuer.approve(grant.user_code)

    credential = device.redeem(grant)

    assert isinstance(credential, Credential)
    assert credential.value


def test_the_grant_shows_the_person_an_address_and_a_code_and_nothing_else(
    device: DeviceAuthorization,
) -> None:
    """What is rendered is the two things the person acts on; the handle is not one."""
    grant = device.begin()

    assert grant.verification_uri.startswith("https://")
    assert grant.user_code
    assert grant.device_code not in repr(grant)


def test_a_declined_authorization_issues_nothing(
    device: DeviceAuthorization, issuer: FakeIssuer
) -> None:
    grant = device.begin()
    issuer.decline(grant.user_code)

    with pytest.raises(SignInFailed):
        device.redeem(grant)


def test_an_unapproved_authorization_expires_rather_than_hanging(
    issuer: FakeIssuer, endpoints: Endpoints
) -> None:
    """The person never answers: the wait is bounded by the grant's own lifetime."""
    elapsed = [0.0]

    def monotonic() -> float:
        return elapsed[0]

    def sleep(seconds: float) -> None:
        elapsed[0] += seconds

    flow = DeviceAuthorization(
        endpoints=endpoints,
        client_id=issuer.client_id,
        transport=issuer,
        sleep=sleep,
        monotonic=monotonic,
    )
    grant = flow.begin()

    with pytest.raises(SignInFailed):
        flow.redeem(grant)


def test_an_unreachable_issuer_is_unavailable_rather_than_a_refusal(
    device: DeviceAuthorization, issuer: FakeIssuer
) -> None:
    issuer.go_dark()

    with pytest.raises(SignInUnavailable):
        device.begin()


# --------------------------------------------------------------------------
# The browser: authorization code, bound to a proof key
# --------------------------------------------------------------------------


def test_the_browser_sign_in_carries_a_challenge_and_never_a_secret(
    browser: BrowserSignIn,
) -> None:
    request = browser.begin()

    assert f"code_challenge_method={pkce.METHOD}" in request.url
    assert "client_secret" not in request.url
    assert request.proof.verifier not in request.url


def test_the_code_is_exchanged_when_the_proof_matches(
    browser: BrowserSignIn, issuer: FakeIssuer
) -> None:
    request = browser.begin()
    code, state = issuer.authorize(request.url)

    credential = browser.redeem(request, code, state)

    assert isinstance(credential, Credential)


def test_an_authorization_code_exchanged_without_the_proof_issues_nothing(
    browser: BrowserSignIn, issuer: FakeIssuer
) -> None:
    """The issuer really performs the comparison; there is nothing to issue without it."""
    request = browser.begin()
    code, _state = issuer.authorize(request.url)

    with pytest.raises(OAuthRefusal):
        issuer.post(
            f"{issuer.issuer}{TOKEN_PATH}",
            {"grant_type": "authorization_code", "code": code},
        )


def test_an_authorization_code_exchanged_with_the_wrong_proof_issues_nothing(
    browser: BrowserSignIn, issuer: FakeIssuer
) -> None:
    request = browser.begin()
    code, _state = issuer.authorize(request.url)
    somebody_elses = pkce.ProofKey.generate()

    with pytest.raises(OAuthRefusal):
        issuer.post(
            f"{issuer.issuer}{TOKEN_PATH}",
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": somebody_elses.verifier,
            },
        )


def test_a_redirect_carrying_another_state_is_refused(
    browser: BrowserSignIn, issuer: FakeIssuer
) -> None:
    request = browser.begin()
    code, _state = issuer.authorize(request.url)

    with pytest.raises(SignInFailed):
        browser.redeem(request, code, "a-state-this-sign-in-never-generated")


def test_a_proof_key_verifies_only_against_its_own_challenge() -> None:
    proof = pkce.ProofKey.generate()

    assert pkce.verify(proof.challenge, proof.verifier)
    assert not pkce.verify(proof.challenge, pkce.ProofKey.generate().verifier)
    assert not pkce.verify(proof.challenge, proof.verifier, method="plain")


def test_a_proof_key_never_prints_its_verifier() -> None:
    proof = pkce.ProofKey.generate()

    assert proof.verifier not in f"{proof!r} {proof}"


# --------------------------------------------------------------------------
# No flow accepts a password (the requirement's second clause)
# --------------------------------------------------------------------------


def _parameters(flow: type) -> set[str]:
    """Every argument name a flow accepts, constructor and operations alike."""
    operations = (name for name in ("begin", "redeem", "obtain") if hasattr(flow, name))
    members = (flow.__init__, *(getattr(flow, name) for name in operations))
    return {name for member in members for name in inspect.signature(member).parameters}


@pytest.mark.parametrize("flow", [DeviceAuthorization, BrowserSignIn], ids=lambda f: f.__name__)
def test_no_flow_a_person_uses_has_anywhere_to_put_a_secret(flow: type) -> None:
    """A shape with no slot for the wrong thing cannot be handed the wrong thing.

    Neither of the two flows a *person* goes through accepts a password, a
    passphrase or a client secret — which is both halves of the requirement at
    once: the surface never sees a password, and a browser-delivered application
    needs no confidential secret.
    """
    offered = {name for name in _parameters(flow) if any(w in name for w in PASSWORD_WORDS)}

    assert not offered


def test_only_the_unattended_flow_holds_a_secret_and_it_belongs_to_the_deployment() -> None:
    """`client_secret` exists exactly once, on the flow with no person in it."""
    assert "client_secret" in _parameters(ServiceCredentials)
    assert "client_secret" not in _parameters(BrowserSignIn)
    assert "client_secret" not in _parameters(DeviceAuthorization)


# --------------------------------------------------------------------------
# Background work: client credentials, recognised as automation
# --------------------------------------------------------------------------


def test_a_service_credential_is_obtained_with_no_person_involved(
    issuer: FakeIssuer, endpoints: Endpoints
) -> None:
    service = ServiceCredentials(
        endpoints=endpoints,
        client_id="cybercanon-worker",
        client_secret="the-deployment-secret",
        transport=issuer,
    )

    credential = service.obtain()

    assert isinstance(credential, Credential)
    assert credential.value
