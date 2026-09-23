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
AUDIENCE = "cybercanon"
CLIENT_ID = "cyb_Fixture0Client01"
"""**Invented**, and deliberately not the registered one.

The *shape* is copied from the registration — `cyb_` and sixteen characters —
because the shape is what the `roles` claim's prefix is made of and therefore
what an adapter has to split on. The *value* is this fixture's own, so that
nothing under `tests/` depends on a client existing on somebody's auth server.
The registered id is written down once, in `deploy/go-live.md`, where an
operator reads it.
"""

ANOTHER_CLIENT_ID = "cyb_Fixture0Other002"
"""A second registered client, for the roles this person holds somewhere else.

CyberdyneAuth puts **every** client's roles in one `roles` claim, so a token
minted for CyberCanon routinely carries entries that are nothing to do with
CyberCanon. A fixture that only ever minted our own prefix could not tell an
adapter that filters from an adapter that does not.
"""

ACCESS = "access"
"""`type` on a token issued for a person."""

SERVICE = "service"
"""`type` on a client-credentials token. Its `sub` is `client:<id>`.

The claims such a token carries were read off the live issuer and are exactly
these: `iss`, `sub`, `jti`, `type`, `client_id`, `scope`, `iat`, `exp`, and
`aud` when one was requested. **No `roles`, no `orgs`, no `org`** — a client
stands for no person, so there is no membership for it to hold and nothing for
the entitlement rule to read.

That last sentence used to be this module's one guess, minted and flagged as
such. It is now a recorded fact, and the fact matters more than the tidiness:
entitlement for automation cannot come from membership claims, because there are
none. It comes from the list of client ids the deployment was told
(`CANON_AUTH_SERVICE_CLIENTS`) and from nothing the token asserts.
"""

SERVICE_SUBJECT_PREFIX = "client:"

SCOPE = "email offline_access openid profile roles"
"""What a real sign-in comes back with — recorded because it is not `groups`."""

SERVICE_SCOPE = "canon:read canon:write"
"""What a client-credentials token's `scope` looks like. **Invented.**

The claim is a space-separated string on the real shape and nothing in this
repository reads it, so the value is this fixture's own: a suite that wrote a
production scope down would be recording somebody's configuration in a test.

It is here so that :meth:`FakeIssuer.mint_service` can carry every claim
team-cyberauth recorded, rather than only the ones the adapter happens to look
at — a fixture that mints less than the issuer sends is how a token from an
unexpected client became a case nobody could express.
"""

WORKER_CLIENT_ID = "cyb_Fixture0Worker01"
"""The service client *this* deployment runs its background work as. **Invented.**

The one client id a deployment would put on `CANON_AUTH_SERVICE_CLIENTS`. It is
deliberately not :data:`CLIENT_ID`: the client a person signs in through and the
client a worker authenticates as are two registrations, and an adapter that
conflated them would admit either wherever it meant one.
"""

OTHER_SERVICE_CLIENT_ID = "cyb_Fixture0Other003"
"""Another service client on the same issuer, and nothing to do with this one.

**Invented**, like every identifier here, and it stands for a real situation:
CyberdyneAuth lets a client-credentials client with no `allowed_audiences`
request *any* audience, so a service registered for something else entirely can
mint a token that names us and verifies perfectly. That token is not a forgery
and no signature, issuer or audience check will ever separate it from ours —
only a list of the clients this deployment accepts can.
"""

ORG_ID = "org_F1xture0Studio"
ORG_SHORT_NAME = "fixture-studio"
"""The organisation this fixture's deployment belongs to. **Invented.**

Every organisation identifier in this repository is one of these two, and
neither names a real organisation: a suite that hard-coded the studio's own org
id would pass or fail depending on a record in somebody else's database, and
would have to be edited by anybody standing the system up for a second studio.
The id is an opaque string with the issuer's shape and nothing more — the org
this deployment serves is *configuration*, read from the environment.
"""

OTHER_ORG_ID = "org_F1xture0Outside"
OTHER_ORG_SHORT_NAME = "fixture-outside"
"""Another organisation, for the person who belongs to one but not to ours."""


def an_org(identifier: str, short_name: str, github_login: str | None = None) -> dict[str, Any]:
    """One entry of the `orgs` claim, in the shape CyberdyneAuth sends it.

    Three fields, and `github_login` is **nullable and null for the only
    organisation that exists today** — which is why it defaults to ``None``
    here. A reader that matched organisations on it would match nothing, or
    worse would match ``None`` against ``None``; the identifier is the field
    that is always there, and the fixture makes the other two look exactly as
    untrustworthy as they are.
    """
    return {"id": identifier, "short_name": short_name, "github_login": github_login}


def primary_org(entry: Mapping[str, Any]) -> dict[str, Any]:
    """One `orgs` entry as the **`org`** claim carries it: `id` and `short_name`.

    Two fields, not three. team-cyberauth read both claims off the live issuer
    and settled it: `github_login` rides on `orgs` entries and on nothing else,
    so an `org` claim carrying one is a shape the issuer never sends. A fixture
    that mints a key the issuer does not is precisely how this branch's first
    bug survived — every suite agreed with the adapter about a claim neither of
    them had ever seen — so the correction deletes a field rather than adding
    one.
    """
    return {"id": entry["id"], "short_name": entry["short_name"]}


HOME_ORG = an_org(ORG_ID, ORG_SHORT_NAME)
"""The deployment's own organisation — with a **null** `github_login`, as today."""

OTHER_ORG = an_org(OTHER_ORG_ID, OTHER_ORG_SHORT_NAME, "fixture-outside")
"""An organisation that is not ours, and that *does* carry a `github_login`.

So a reader keying on `github_login` would recognise the outsider and miss the
member, which is the exact inversion the real data makes available.
"""


class _AsIssued:
    """ "Whatever this kind of token normally carries" — not a value of its own.

    ``orgs`` has four meanings and only three of them are values: a list, the
    empty list, and no claim at all. The fourth is *leave it as this issuer
    would have issued it*, which differs between a person and a service, and it
    needs a spelling that is not ``None`` because ``None`` already means the
    legacy token with no claim.
    """


AS_ISSUED = _AsIssued()

PRO_MONTHLY = "pro:monthly"
"""One `entitlements` entry, in the shape CyberdyneAuth sends them.

`entitlements` is a list of **billing products**. It is not access, it has never
been access, and it does not name a project — the fixture mints `pro:monthly`
rather than a project name so that no test can accidentally read a subscription
as a permission. Project access is `orgs` plus `roles`.
"""

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

    def qualified(self, role: str) -> str:
        """A role key as CyberdyneAuth writes it: `<client id>:<role key>`.

        A value that already names a client is left alone, which is how a test
        mints the roles this person holds on **another** client alongside ours.
        """
        return role if ":" in role else f"{self.client_id}:{role}"

    def mint(
        self,
        subject: str = "auth|rafa",
        *,
        roles: Sequence[str] | None = (),
        entitlements: Sequence[str] = (),
        org: Mapping[str, Any] | None = None,
        orgs: Sequence[Mapping[str, Any]] | _AsIssued | None = AS_ISSUED,
        is_admin: bool = False,
        service: bool = False,
        kind: str | None = None,
        scope: str = SCOPE,
        audience: str | None = None,
        issuer: str | None = None,
        issued_at: int | None = None,
        lifetime_s: int = 3600,
        kid: str | None = None,
        key: jwk.RSAKey | None = None,
    ) -> Credential:
        """A signed credential, carrying **the claims CyberdyneAuth really emits**.

        This signature is the deliverable of `fix/real-token-shape` and it is
        deliberately narrower than what it replaced. It used to accept `groups`,
        `projects`, `tenant`, `git_emails`, `name` and `gty` — the six names
        `cybercanon.adapters.outbound.auth.claims` reads — and CyberdyneAuth
        emits **none of them**. Both halves of that conversation were written
        here, so the suites could agree with the adapter for ever without either
        one being right. What a real token verified against production carries
        is `roles` (every entry prefixed with the client id it belongs to),
        `type`, `org`, `orgs`, `entitlements`, `is_admin`, `scope` and `jti` —
        and no display name, no email and no commit addresses at all.

        Two callers, two shapes:

        * **a person** — `type` is `access`, `sub` is the person, and `roles`
          lists every client's roles, so a reader has to filter on its own
          prefix rather than take the claim as given;
        * **a service** — `type` is `service`, `sub` is `client:<id>`, and there
          is **no `roles` claim**, because a client-credentials token carries
          none. This is the *claim-light* service shape: it carries no
          `client_id` claim either, so a reader has to find the client in `sub`.
          :meth:`mint_service` is the recorded shape and the one a suite should
          reach for; `service=True` stays because a token naming its client only
          in `sub` is a real case and this is the only way to mint one.

        `roles=None` mints a person's token with the claim **absent**, which is
        what CyberdyneAuth does when IAM was unreachable. That is not "no
        roles": it is an unanswered question, and a reader must fail closed.
        `roles=()` is the answered version of the same question — this person
        holds nothing — and the two must not be spelled the same way.

        `orgs` has the same three-way spelling and for the same reason, because
        the entitlement rule fails closed on **both** shapes of absence:

        * ``orgs=(HOME_ORG,)`` — the default — is a person who belongs to the
          organisation this deployment serves;
        * ``orgs=()`` mints ``orgs: []``: asked and answered, belongs nowhere;
        * ``orgs=None`` mints **no `orgs` claim at all**, which is a token from
          before the claim existed. A legacy token is refused rather than
          treated as a member, because "the claim is missing" has never been a
          reason to let somebody in.

        `org` is the person's **primary** organisation and defaults to the first
        of `orgs`. It can be set independently, which is the whole point of its
        being here: a member of two organisations whose primary is the *other*
        one must still read, and a reader keying on `org` would lock them out.

        `entitlements` are **billing products** (`pro:monthly`). They are not
        access and they name no project.

        `kind` writes the `type` claim directly, and exists for the one shape
        neither caller above produces: a token whose `type` is something this
        adapter has never heard of. CyberdyneAuth mints other kinds — an id
        token is the obvious one — and a reader that treated an unrecognised
        `type` as a person would be guessing at the difference between a
        session and something that is not one. Nothing but a test should pass
        it, which is why it is last and why `service` remains the ordinary way
        to ask for the other legitimate shape.

        The rest are unchanged and still exist to make one scenario real:
        `audience` and `issuer` so a token minted for another service can be
        presented; `issued_at` and `lifetime_s` so one can be presented after it
        expires; `key` so one can be signed by something the issuer never
        published.
        """
        minted_at = self.now if issued_at is None else issued_at
        signer = key if key is not None else signing_key(kid or self.current)
        claims: dict[str, Any] = {
            "sub": _named(subject, service=service),
            "iss": self.issuer if issuer is None else issuer,
            "aud": self.audience if audience is None else audience,
            "iat": minted_at,
            "exp": minted_at + lifetime_s,
            "jti": secrets.token_urlsafe(16),
            "type": kind if kind is not None else (SERVICE if service else ACCESS),
            "scope": scope,
            "is_admin": is_admin,
            **self._held(roles, service=service),
            **_membership(org, orgs, service=service),
            **({"entitlements": list(entitlements)} if entitlements else {}),
        }
        header = {"alg": "RS256", "kid": signer.kid}
        return Credential(jwt.encode(header, claims, signer))

    def _held(self, roles: Sequence[str] | None, *, service: bool) -> dict[str, Any]:
        """The `roles` claim — or **no claim at all**, which is a different answer.

        A service token has never carried one, and a person's token loses it
        when IAM could not be reached. Both are the absent case and neither is
        an empty list.
        """
        if service or roles is None:
            return {}
        return {"roles": [self.qualified(role) for role in roles]}

    def mint_service(
        self,
        client_id: str,
        *,
        subject: str | None = None,
        named: bool = True,
        scope: str = SERVICE_SCOPE,
        audience: str | None = None,
        issuer: str | None = None,
        issued_at: int | None = None,
        lifetime_s: int = 3600,
        kid: str | None = None,
    ) -> Credential:
        """A client-credentials token **from the client named**, and nothing else.

        The claims are exactly the ones team-cyberauth read off the live issuer:
        `iss`, `sub` (`client:<client_id>`), `jti`, `type`, `client_id`, `scope`,
        `iat`, `exp`, and `aud` because this caller always requests one. There is
        **no `roles` claim, no `orgs` and no `org`** — a client stands for no
        person, so there is no membership for it to hold and nothing for the
        entitlement rule to read. Entitlement for automation is a list of client
        ids the deployment was told, and never anything the token asserts.

        It exists beside :meth:`mint` rather than inside it because of the claim
        :meth:`mint` cannot write: `client_id`, and with it the ability to mint a
        token from a client that is **not** the one this fixture stands for. Every
        service token these suites had minted was our own worker, so a token from
        a different client was a shape the fixtures could not express — which is
        the whole reason nobody checked what the adapter did with one.

        `audience` is the escape hatch that makes the danger reproducible: a
        client-credentials client with no `allowed_audiences` may request any
        audience it likes, so the default here is *our* audience. A token from a
        stranger that names us is the ordinary case, not the exotic one.

        `subject` and `named` exist for the shapes the **real** issuer never
        mints, which is exactly why a suite has to be able to mint them. `sub`
        and `client_id` always agree here because one authenticated client
        produced both; an adapter that read the two as interchangeable sources
        would never find that out from a fixture which could only write them the
        same. `subject` writes `sub` verbatim — a different client than the
        claim names, a `client:` with nothing after it, a padded id — and
        `named=False` drops the `client_id` claim, which is the claim-light
        shape :meth:`mint` produces with `service=True`.

        Nothing about them is a *forgery*: every one of these is signed by this
        issuer's real key and carries this issuer and this audience, because the
        question being asked is what the adapter does with a credential that
        verified.
        """
        minted_at = self.now if issued_at is None else issued_at
        signer = signing_key(kid or self.current)
        claims: dict[str, Any] = {
            "iss": self.issuer if issuer is None else issuer,
            "sub": f"{SERVICE_SUBJECT_PREFIX}{client_id}" if subject is None else subject,
            "aud": self.audience if audience is None else audience,
            "type": SERVICE,
            "scope": scope,
            "iat": minted_at,
            "exp": minted_at + lifetime_s,
            "jti": secrets.token_urlsafe(16),
            **({"client_id": client_id} if named else {}),
        }
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
            return self._issued(self.mint_service(form.get("client_id") or WORKER_CLIENT_ID))
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


def _named(subject: str, *, service: bool) -> str:
    """What `sub` says: the person, or `client:<id>` for a client-credentials token."""
    if service and not subject.startswith(SERVICE_SUBJECT_PREFIX):
        return f"{SERVICE_SUBJECT_PREFIX}{subject}"
    return subject


def _membership(
    org: Mapping[str, Any] | None,
    orgs: Sequence[Mapping[str, Any]] | _AsIssued | None,
    *,
    service: bool,
) -> dict[str, Any]:
    """The `orgs` and `org` claims — organisation membership, in the real shape.

    ``orgs=None`` omits the claim entirely: that is the legacy token, and a
    claim that is *absent* and a claim that is *empty* are two different answers
    a fixture has to be able to spell, because the rule refuses both and only a
    suite that can mint both knows that it refuses both.

    The two claims are **not the same object**. An `orgs` entry has three fields
    and `org` has two: the primary organisation goes through :func:`primary_org`,
    which drops `github_login`, because that is the shape team-cyberauth read
    off the live issuer.

    Left alone, a person belongs to this fixture's own organisation and a
    service belongs to none — a client-credentials token stands for no person,
    so there is nobody for it to be a member as, and the issuer sends it no
    `orgs` and no `org`.
    """
    if isinstance(orgs, _AsIssued):
        orgs = None if service else (HOME_ORG,)
    if orgs is None:
        return {"org": primary_org(org)} if org else {}
    first = org if org is not None else (orgs[0] if orgs else None)
    claims: dict[str, Any] = {"orgs": [dict(entry) for entry in orgs]}
    if first is not None:
        claims["org"] = primary_org(first)
    return claims


def _error(code: str, description: str) -> Mapping[str, Any]:
    return {"error": code, "error_description": description}


__all__ = [
    "ACCESS",
    "ANOTHER_CLIENT_ID",
    "AS_ISSUED",
    "AUDIENCE",
    "AUTHORIZE_PATH",
    "CLIENT_ID",
    "DEVICE_CODE_PATH",
    "EPOCH",
    "HOME_ORG",
    "ISSUER",
    "ORG_ID",
    "ORG_SHORT_NAME",
    "OTHER_ORG",
    "OTHER_ORG_ID",
    "OTHER_ORG_SHORT_NAME",
    "OTHER_SERVICE_CLIENT_ID",
    "PRO_MONTHLY",
    "SCOPE",
    "SERVICE",
    "SERVICE_SCOPE",
    "SERVICE_SUBJECT_PREFIX",
    "TOKEN_PATH",
    "WORKER_CLIENT_ID",
    "CodeState",
    "DeviceState",
    "FakeIssuer",
    "an_org",
    "impostor_key",
    "primary_org",
    "signing_key",
]
