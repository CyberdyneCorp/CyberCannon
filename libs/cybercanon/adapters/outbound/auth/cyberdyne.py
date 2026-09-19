"""CyberdyneAuth — the first real `IdentityProvider`, and the only place a token exists.

D12, as code: *"the auth adapter verifies the signature against a cached key
set, checks issuer, audience and validity, then maps configured groups to
`Role`s and the subject to an `ActorId`, producing an `Actor` with a
`Tenant`."* Four steps, three modules — the keys are
:mod:`cybercanon.adapters.outbound.auth.keys`, the translation is
:mod:`cybercanon.adapters.outbound.auth.claims`, and this is the seam that runs
them in order and decides what each failure means.

What leaves this class is a
:class:`~cybercanon.application.ports.identity_provider.ResolvedIdentity`: an
actor and, when the issuer describes them, the person's commit addresses.
Nothing else — no claim name, no group name, no issuer, no token, and in
particular **no decision**. The adapter cannot grant, cannot deny and has no
method that takes an operation, which is what makes *"identical decision for
identical actors"* a property of the type rather than of a test.

Two kinds of failure, and the distinction is the whole of the offline
requirement:

* :class:`~cybercanon.application.ports.identity_provider.CredentialRejected` —
  the credential was read and is not acceptable. One sentence for every reason,
  because the specification forbids telling the caller whether it was the
  signature or the audience; the discriminating detail rides on `reason`, for
  the log.
* :class:`~cybercanon.application.ports.identity_provider.IdentityServiceUnavailable`
  — the answer needed the issuer and the issuer is not there. It names the
  identity service, because that is the sentence the specification asks for and
  because it sends a person somewhere useful.

Both are :class:`~cybercanon.application.ports.identity_provider.IdentityUnavailable`,
so the local resolution chain still degrades past either exactly as it always
did: the command line does not acquire a new failure mode by this adapter
existing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import GuestProtocol, Key

from cybercanon.adapters.outbound.auth.claims import (
    DEFAULT_CLAIMS,
    ClaimNames,
    ClaimsIncomplete,
    actor_from,
    git_emails_from,
)
from cybercanon.adapters.outbound.auth.keys import CachedKeySet
from cybercanon.application.ports.identity_provider import (
    PRESENTED_CREDENTIAL,
    Credential,
    CredentialRejected,
    IdentityUnavailable,
    ResolvedIdentity,
)

ALGORITHMS: tuple[str, ...] = ("RS256", "RS384", "RS512", "ES256", "ES384")
"""The signature algorithms accepted. An allow-list, because `none` exists.

Asymmetric only, and stated rather than inferred from the credential: a verifier
that trusts the token's own `alg` header is the oldest hole in this protocol.
"""

UNREADABLE = "the credential is not a well-formed signed token"
BAD_SIGNATURE = "the signature does not verify against the issuer's published keys"
BAD_CLAIMS = "a required claim is absent, wrong or outside its validity period"
NO_SUBJECT = "the credential carries no subject"

PRESENTED = PRESENTED_CREDENTIAL
"""What a refusal is *about*. Never the credential itself, which never prints."""

Now = Callable[[], datetime]


def system_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Trust:
    """What the service will accept: one issuer, one audience.

    Both are required rather than optional. An audience nobody checks is how a
    token minted for another service becomes a session here, and the
    specification asks for the check by name.
    """

    issuer: str
    audience: str

    def __post_init__(self) -> None:
        if not self.issuer.strip():
            raise ValueError("an issuer is required: an unverified issuer trusts everyone")
        if not self.audience.strip():
            raise ValueError("an audience is required: a token minted elsewhere is not a session")


@dataclass
class CyberdyneAuth:
    """Verifies a CyberdyneAuth credential and resolves the actor behind it.

    `group_roles` is the configured mapping and is read, never interpreted: this
    class names no group, which is what makes adding one a configuration change.
    `claims` says which claim carries what — the credential's shape, fixed by
    the issuer rather than by a studio.
    """

    trust: Trust
    keys: CachedKeySet
    group_roles: Mapping[str, str] = field(default_factory=dict)
    claims: ClaimNames = DEFAULT_CLAIMS
    now: Now = system_now
    leeway_s: int = 30

    def resolve(self, credential: Credential) -> ResolvedIdentity:
        """The actor this credential belongs to, or a named refusal.

        Order matters and is the specified order: signature first, then issuer,
        audience and validity, then translation. Checking claims before the
        signature would be reading an attacker's assertions as facts.
        """
        token = self._verified(credential)
        self._acceptable(token.claims)
        return self._resolved(token.claims)

    # -- the four steps --------------------------------------------------

    def _verified(self, credential: Credential) -> jwt.Token:
        """Signature, against the key the credential names (rotation included)."""
        try:
            return jwt.decode(credential.value, self._key_for, algorithms=list(ALGORITHMS))
        except IdentityUnavailable:
            raise
        except JoseError as failure:
            raise CredentialRejected(BAD_SIGNATURE) from failure
        except (ValueError, TypeError, UnicodeDecodeError) as failure:
            raise CredentialRejected(UNREADABLE) from failure

    def _key_for(self, guest: GuestProtocol) -> Key:
        """Resolve the signing key from the credential's own header.

        The header is untrusted at this point, and that is fine: the only thing
        read from it is *which published key to check against*, and a header
        naming a key the issuer does not publish fails the check rather than
        choosing one.
        """
        return self.keys.key_for(guest.headers().get("kid"))

    def _acceptable(self, claims: Mapping[str, Any]) -> None:
        """Issuer, audience and validity period, against the configured trust."""
        registry = jwt.JWTClaimsRegistry(
            now=int(self.now().timestamp()),
            leeway=self.leeway_s,
            iss={"essential": True, "value": self.trust.issuer},
            aud={"essential": True, "value": self.trust.audience},
            exp={"essential": True},
        )
        try:
            registry.validate(dict(claims))
        except JoseError as failure:
            raise CredentialRejected(BAD_CLAIMS) from failure

    def _resolved(self, claims: Mapping[str, Any]) -> ResolvedIdentity:
        """Claims to actor. The last line at which a claim name exists."""
        try:
            actor = actor_from(claims, group_roles=self.group_roles, names=self.claims)
        except (ClaimsIncomplete, ValueError) as failure:
            raise CredentialRejected(NO_SUBJECT) from failure
        return ResolvedIdentity(actor=actor, git_emails=git_emails_from(claims, self.claims))


__all__ = [
    "ALGORITHMS",
    "BAD_CLAIMS",
    "BAD_SIGNATURE",
    "NO_SUBJECT",
    "PRESENTED",
    "UNREADABLE",
    "CyberdyneAuth",
    "Now",
    "Trust",
    "system_now",
]
