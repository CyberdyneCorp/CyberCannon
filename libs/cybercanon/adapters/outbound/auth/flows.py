"""The three ways a credential is obtained, one per caller, none of them a password.

`auth-integration` names all three and names them separately, because they are
for different callers with different threat models:

* **the browser** — authorization code bound to a proof key
  (:class:`BrowserSignIn`). No client secret, because a secret delivered to a
  browser is public;
* **the terminal** — device authorization (:class:`DeviceAuthorization`), so a
  person approves a sign-in in a browser and never pastes a credential into a
  shell where it lands in history;
* **background work** — client credentials (:class:`ServiceCredentials`), which
  resolves to automation and is refused everything the project reserves to a
  person.

None of them takes a password, and that is structural: there is no parameter on
any of these classes through which one could be supplied. The surface's own
promise — *"no password SHALL be transmitted to or stored by the surface"* — is
therefore kept by the shape of the code rather than by a check somebody wrote.

Everything network-facing is one injected
:class:`~cybercanon.adapters.outbound.auth.oauth.OAuthTransport`, so the whole
of every flow is exercisable against an issuer that is a dictionary — which is
how the specified refusals get tested at all.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlencode

from cybercanon.adapters.outbound.auth.oauth import (
    ACCESS_DENIED,
    EXPIRED_TOKEN,
    HttpOAuthTransport,
    OAuthRefusal,
    OAuthTransport,
    OAuthUnreachable,
)
from cybercanon.adapters.outbound.auth.pkce import ProofKey
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.interactive_sign_in import (
    DeviceGrant,
    SignInFailed,
    SignInUnavailable,
)

DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
AUTHORIZATION_CODE_GRANT = "authorization_code"
CLIENT_CREDENTIALS_GRANT = "client_credentials"

DEFAULT_SCOPE = "openid profile email"

NO_TOKEN = "the issuer answered without a token"
TIMED_OUT = "the device authorization expired before it was approved"
WRONG_STATE = "the redirect did not carry the state this sign-in generated"

Sleep = Callable[[float], None]
Monotonic = Callable[[], float]


@dataclass(frozen=True)
class Endpoints:
    """Where the issuer's three relevant endpoints live."""

    token: str
    device_authorization: str = ""
    authorization: str = ""


def _transport(given: OAuthTransport | None) -> OAuthTransport:
    return given if given is not None else HttpOAuthTransport()


def _credential(document: Mapping[str, object]) -> Credential:
    """The access token out of a token response, or a named failure.

    An identity token is deliberately not accepted in its place: what this
    product presents to its own surface is the credential the issuer minted *for
    that audience*, and an `id_token` is minted for the client.
    """
    token = document.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise SignInFailed(NO_TOKEN)
    return Credential(token)


class DeviceAuthorization:
    """The terminal sign-in: show a code, wait for a browser, keep the credential.

    The wait is bounded by the grant's own lifetime and paced by the interval
    the issuer asked for, honouring `slow_down` by lengthening it. A poll loop
    that ignored either is the one that gets a client rate-limited and then
    blamed on the identity service.
    """

    def __init__(
        self,
        *,
        endpoints: Endpoints,
        client_id: str,
        scope: str = DEFAULT_SCOPE,
        audience: str = "",
        transport: OAuthTransport | None = None,
        sleep: Sleep = time.sleep,
        monotonic: Monotonic = time.monotonic,
    ) -> None:
        self._endpoints = endpoints
        self._client_id = client_id
        self._scope = scope
        self._audience = audience
        self._transport = _transport(transport)
        self._sleep = sleep
        self._monotonic = monotonic

    def begin(self) -> DeviceGrant:
        """Ask the issuer to start a grant and return what to show the person."""
        form = {"client_id": self._client_id, "scope": self._scope}
        if self._audience:
            form["audience"] = self._audience
        document = self._ask(self._endpoints.device_authorization, form)
        return DeviceGrant(
            verification_uri=str(
                document.get("verification_uri_complete") or document.get("verification_uri", "")
            ),
            user_code=str(document.get("user_code", "")),
            device_code=str(document.get("device_code", "")),
            expires_in_s=int(document.get("expires_in", 300)),
            interval_s=int(document.get("interval", 5)),
        )

    def redeem(self, grant: DeviceGrant) -> Credential:
        """Poll until the person approves, declines, or the grant expires."""
        deadline = self._monotonic() + grant.expires_in_s
        interval = float(grant.interval_s)
        while self._monotonic() < deadline:
            try:
                return _credential(self._ask(self._endpoints.token, self._redemption(grant)))
            except OAuthRefusal as refusal:
                interval = self._after(refusal, interval)
            self._sleep(interval)
        raise SignInFailed(TIMED_OUT)

    def _redemption(self, grant: DeviceGrant) -> dict[str, str]:
        return {
            "grant_type": DEVICE_CODE_GRANT,
            "device_code": grant.device_code,
            "client_id": self._client_id,
        }

    def _after(self, refusal: OAuthRefusal, interval: float) -> float:
        """A refusal is either *keep waiting*, or the end of this sign-in."""
        if not refusal.is_still_waiting:
            raise SignInFailed(_declined(refusal))
        return interval + 5.0 if refusal.code != "authorization_pending" else interval

    def _ask(self, url: str, form: Mapping[str, str]) -> Mapping[str, object]:
        if not url:
            raise SignInUnavailable("no device authorization endpoint is configured")
        try:
            return self._transport.post(url, form)
        except OAuthUnreachable as failure:
            raise SignInUnavailable(str(failure)) from failure


def _declined(refusal: OAuthRefusal) -> str:
    if refusal.code == ACCESS_DENIED:
        return "the person declined the sign-in"
    if refusal.code == EXPIRED_TOKEN:
        return TIMED_OUT
    return refusal.description or refusal.code


@dataclass(frozen=True)
class AuthorizationRequest:
    """One browser sign-in in flight: where to send the person, and the proof.

    `proof` never leaves the application, and `state` is what makes a redirect
    arriving from somewhere else recognisable as not this sign-in.
    """

    url: str
    state: str
    proof: ProofKey = field(repr=False)


class BrowserSignIn:
    """The web application's sign-in: authorization code, bound to a proof key.

    The proof key is generated per sign-in by this object, which is what the
    requirement means by *"a proof key generated by that application"*. There is
    no constructor parameter for a client secret, so a deployment cannot supply
    one and a browser build cannot embed one.
    """

    def __init__(
        self,
        *,
        endpoints: Endpoints,
        client_id: str,
        redirect_uri: str,
        scope: str = DEFAULT_SCOPE,
        audience: str = "",
        transport: OAuthTransport | None = None,
    ) -> None:
        self._endpoints = endpoints
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._scope = scope
        self._audience = audience
        self._transport = _transport(transport)

    def begin(self) -> AuthorizationRequest:
        """The address to send the person to, carrying the challenge and state."""
        proof = ProofKey.generate()
        state = secrets.token_urlsafe(24)
        query = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": self._scope,
            "state": state,
            "code_challenge": proof.challenge,
            "code_challenge_method": proof.method,
        }
        if self._audience:
            query["audience"] = self._audience
        separator = "&" if "?" in self._endpoints.authorization else "?"
        url = f"{self._endpoints.authorization}{separator}{urlencode(query)}"
        return AuthorizationRequest(url=url, state=state, proof=proof)

    def redeem(self, request: AuthorizationRequest, code: str, state: str) -> Credential:
        """Exchange the code, presenting the verifier this sign-in generated.

        The verifier is not optional and there is no overload that omits it: an
        exchange without proof is a thing this client cannot express, and the
        issuer refuses it besides.
        """
        if not secrets.compare_digest(request.state, state):
            raise SignInFailed(WRONG_STATE)
        form = {
            "grant_type": AUTHORIZATION_CODE_GRANT,
            "code": code,
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "code_verifier": request.proof.verifier,
        }
        try:
            return _credential(self._transport.post(self._endpoints.token, form))
        except OAuthRefusal as refusal:
            raise SignInFailed(refusal.description or refusal.code) from refusal
        except OAuthUnreachable as failure:
            raise SignInUnavailable(str(failure)) from failure


class ServiceCredentials:
    """Background work's credential: client credentials, and no person anywhere.

    The credential it obtains carries the client-credentials grant, which is what
    :func:`~cybercanon.adapters.outbound.auth.claims.actor_from` reads to resolve
    it as automation. That link is the reason a scheduled run cannot be recorded
    as a person even if somebody configured it with a person's client.
    """

    def __init__(
        self,
        *,
        endpoints: Endpoints,
        client_id: str,
        client_secret: str,
        audience: str = "",
        transport: OAuthTransport | None = None,
    ) -> None:
        self._endpoints = endpoints
        self._client_id = client_id
        self._client_secret = client_secret
        self._audience = audience
        self._transport = _transport(transport)

    def obtain(self) -> Credential:
        """A service credential for this deployment. No person is involved."""
        form = {
            "grant_type": CLIENT_CREDENTIALS_GRANT,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if self._audience:
            form["audience"] = self._audience
        try:
            return _credential(self._transport.post(self._endpoints.token, form))
        except OAuthRefusal as refusal:
            raise SignInFailed(refusal.description or refusal.code) from refusal
        except OAuthUnreachable as failure:
            raise SignInUnavailable(str(failure)) from failure


__all__ = [
    "AUTHORIZATION_CODE_GRANT",
    "CLIENT_CREDENTIALS_GRANT",
    "DEFAULT_SCOPE",
    "DEVICE_CODE_GRANT",
    "NO_TOKEN",
    "TIMED_OUT",
    "WRONG_STATE",
    "AuthorizationRequest",
    "BrowserSignIn",
    "DeviceAuthorization",
    "Endpoints",
    "ServiceCredentials",
]
