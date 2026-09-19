"""A CyberdyneAuth that runs in the test process — the counterpart, not a mock.

The verification adapter's whole job is to be right about credentials it did not
mint, so the thing it is tested against has to actually mint them: sign real
tokens with real RSA keys, publish a real key set, rotate it, refuse an
authorization code whose proof does not match, and stop answering when it is
told to be unreachable. A mock that returned `True` from `verify` would agree
with whatever the adapter happened to do, which is the failure the port
conformance suites exist to catch one level down.

So :class:`FakeIssuer` is small but not fake in the load-bearing places:

* **the keys are real** and the signatures are checked by `joserfc` against the
  published JWKS, so *"unverifiable signature is refused"* is a real signature
  that really does not verify;
* **rotation is real** — :meth:`FakeIssuer.rotate` publishes a new key and mints
  with it, and the adapter only accepts the result if it re-retrieves the key
  set;
* **the PKCE check is real** — the token endpoint compares the verifier against
  the challenge it was given, so an exchange with no proof fails at the issuer
  rather than at an assertion;
* **being unreachable is real enough** — :meth:`FakeIssuer.go_dark` makes every
  endpoint raise, which is what the bounded offline window is measured against.

It lives in `tools/` beside the other test-support packages because three layers
need it: the port conformance suite, the integration suite, and the BDD steps
for `auth-integration`.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

from joserfc import jwk, jwt

from cybercanon.adapters.outbound.auth import pkce
from cybercanon.adapters.outbound.auth.oauth import (
    ACCESS_DENIED,
    AUTHORIZATION_PENDING,
    INVALID_GRANT,
    OAuthUnreachable,
    read,
)
from cybercanon.application.ports.identity_provider import Credential

ISSUER = "https://auth.cyberdynecorp.ai"
AUDIENCE = "https://api.cybercanon.cyberdynecorp.ai"
CLIENT_ID = "cybercanon-cli"

DEVICE_CODE_PATH = "/oauth/device/code"
TOKEN_PATH = "/oauth/token"
AUTHORIZE_PATH = "/authorize"

EPOCH = 1_789_000_000
"""A fixed 'now' in seconds, so a token's validity is decided by the test."""

_KEYS: dict[str, jwk.RSAKey] = {}


def signing_key(kid: str) -> jwk.RSAKey:
    """An RSA key for this identifier, generated once per process.

    Generation is the slowest thing in these suites by an order of magnitude and
    the keys carry no state, so they are cached by identifier. A test that wants
    a *different* key with the same identifier — the way a signature stops
    verifying — asks for one under another name and relabels it.
    """
    if kid not in _KEYS:
        _KEYS[kid] = jwk.RSAKey.generate_key(2048, parameters={"kid": kid})
    return _KEYS[kid]


def impostor_key(kid: str) -> jwk.RSAKey:
    """A key carrying a published identifier that the issuer never published.

    What an attacker has: the right `kid` in the header and the wrong private
    key underneath. The signature must fail to verify, and the refusal must not
    say which of the two things was wrong.
    """
    key = signing_key(f"impostor-{kid}")
    return jwk.RSAKey.import_key(key.as_dict(private=True) | {"kid": kid})


@dataclass
class DeviceState:
    """One device authorization in flight, and whether the person has answered."""

    user_code: str
    subject: str
    approved: bool = False
    declined: bool = False


@dataclass
class CodeState:
    """One authorization code, and the challenge it is bound to."""

    challenge: str
    method: str
    subject: str


@dataclass
class FakeIssuer:
    """CyberdyneAuth, in process: signs, publishes, rotates, and can go away."""

    issuer: str = ISSUER
    audience: str = AUDIENCE
    client_id: str = CLIENT_ID
    now: int = EPOCH
    published: list[str] = field(default_factory=lambda: ["key-2026-a"])
    reachable: bool = True
    fetches: int = 0
    devices: dict[str, DeviceState] = field(default_factory=dict)
    codes: dict[str, CodeState] = field(default_factory=dict)

    # -- keys ------------------------------------------------------------

    @property
    def current(self) -> str:
        """The identifier of the key new credentials are signed with."""
        return self.published[-1]

    def rotate(self, kid: str = "key-2026-b") -> str:
        """Publish a new signing key and start using it, as an issuer does."""
        self.published.append(kid)
        return kid

    def jwks(self) -> dict[str, Any]:
        """The published key set — public halves only, exactly as served."""
        return {"keys": [signing_key(kid).as_dict(private=False) for kid in self.published]}

    def fetch(self) -> Mapping[str, Any]:
        """The :class:`~cybercanon.adapters.outbound.auth.keys.KeySource` side."""
        self._reachable()
        self.fetches += 1
        return self.jwks()

    def go_dark(self) -> None:
        """Stop answering. Every endpoint and the key set alike."""
        self.reachable = False

    def come_back(self) -> None:
        self.reachable = True

    # -- credentials -----------------------------------------------------

    def mint(
        self,
        subject: str = "auth|rafa",
        *,
        name: str = "",
        groups: Sequence[str] = (),
        projects: Sequence[str] = (),
        tenant: str = "",
        git_emails: Sequence[str] = (),
        grant: str = "",
        audience: str | None = None,
        issuer: str | None = None,
        issued_at: int | None = None,
        lifetime_s: int = 3600,
        kid: str | None = None,
        key: jwk.RSAKey | None = None,
    ) -> Credential:
        """A signed credential. Every argument exists to make one scenario real.

        `audience` and `issuer` are overridable so a token minted for another
        service can be presented; `issued_at` and `lifetime_s` so one can be
        presented after it expires; `key` so one can be signed by something the
        issuer does not publish.
        """
        minted_at = self.now if issued_at is None else issued_at
        signer = key if key is not None else signing_key(kid or self.current)
        claims: dict[str, Any] = {
            "sub": subject,
            "iss": self.issuer if issuer is None else issuer,
            "aud": self.audience if audience is None else audience,
            "iat": minted_at,
            "exp": minted_at + lifetime_s,
        }
        if name:
            claims["name"] = name
        if groups:
            claims["groups"] = list(groups)
        if projects:
            claims["projects"] = list(projects)
        if tenant:
            claims["tenant"] = tenant
        if git_emails:
            claims["git_emails"] = list(git_emails)
        if grant:
            claims["gty"] = grant
        header = {"alg": "RS256", "kid": signer.kid}
        return Credential(jwt.encode(header, claims, signer))

    # -- the OAuth endpoints ---------------------------------------------

    def authorize(self, url: str, *, subject: str = "auth|rafa") -> tuple[str, str]:
        """What the browser does at the authorization endpoint: a code and the state.

        The challenge is remembered against the code, which is the only reason
        the token endpoint can refuse an exchange that arrives without the
        matching verifier.
        """
        query = {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}
        code = secrets.token_urlsafe(16)
        self.codes[code] = CodeState(
            challenge=query.get("code_challenge", ""),
            method=query.get("code_challenge_method", ""),
            subject=subject,
        )
        return code, query.get("state", "")

    def approve(self, user_code: str) -> None:
        """The person confirms the code the terminal showed them."""
        for state in self.devices.values():
            if state.user_code == user_code:
                state.approved = True

    def decline(self, user_code: str) -> None:
        for state in self.devices.values():
            if state.user_code == user_code:
                state.declined = True

    def post(self, url: str, form: Mapping[str, str]) -> Mapping[str, Any]:
        """The :class:`~cybercanon.adapters.outbound.auth.oauth.OAuthTransport` side."""
        self._reachable()
        path = urlsplit(url).path
        if path == DEVICE_CODE_PATH:
            return read(self._device_grant())
        if path == TOKEN_PATH:
            return read(self._token(form))
        raise OAuthUnreachable(f"no endpoint at {path}")

    def _device_grant(self) -> Mapping[str, Any]:
        device_code = secrets.token_urlsafe(16)
        user_code = "WDJB-MJHT"
        self.devices[device_code] = DeviceState(user_code=user_code, subject="auth|rafa")
        return {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": f"{self.issuer}/activate",
            "expires_in": 300,
            "interval": 1,
        }

    def _token(self, form: Mapping[str, str]) -> Mapping[str, Any]:
        grant = form.get("grant_type", "")
        if grant.endswith("device_code"):
            return self._device_token(form)
        if grant == "authorization_code":
            return self._code_token(form)
        if grant == "client_credentials":
            return self._issued(
                self.mint(form.get("client_id", "cybercanon-worker"), grant="client-credentials")
            )
        return _error(INVALID_GRANT, f"unsupported grant {grant!r}")

    def _device_token(self, form: Mapping[str, str]) -> Mapping[str, Any]:
        state = self.devices.get(form.get("device_code", ""))
        if state is None:
            return _error(INVALID_GRANT, "no such device authorization")
        if state.declined:
            return _error(ACCESS_DENIED, "the person declined")
        if not state.approved:
            return _error(AUTHORIZATION_PENDING, "the person has not approved it yet")
        return self._issued(self.mint(state.subject))

    def _code_token(self, form: Mapping[str, str]) -> Mapping[str, Any]:
        state = self.codes.get(form.get("code", ""))
        if state is None:
            return _error(INVALID_GRANT, "no such authorization code")
        verifier = form.get("code_verifier", "")
        if not verifier or not pkce.verify(state.challenge, verifier, state.method):
            return _error(INVALID_GRANT, "the proof does not match the challenge")
        del self.codes[form["code"]]
        return self._issued(self.mint(state.subject))

    def _issued(self, credential: Credential) -> Mapping[str, Any]:
        return {"access_token": credential.value, "token_type": "Bearer", "expires_in": 3600}

    def _reachable(self) -> None:
        if not self.reachable:
            raise OAuthUnreachable("the identity service is not answering")


def _error(code: str, description: str) -> Mapping[str, Any]:
    return {"error": code, "error_description": description}


__all__ = [
    "AUDIENCE",
    "AUTHORIZE_PATH",
    "CLIENT_ID",
    "DEVICE_CODE_PATH",
    "EPOCH",
    "ISSUER",
    "TOKEN_PATH",
    "CodeState",
    "DeviceState",
    "FakeIssuer",
    "impostor_key",
    "signing_key",
]
