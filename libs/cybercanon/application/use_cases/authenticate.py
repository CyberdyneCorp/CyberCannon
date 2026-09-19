"""Who is acting **on the networked surface** — and the scoping that keeps it apart.

:mod:`cybercanon.application.use_cases.resolve_actor` answers the same question
for the *local process*: a laptop off the VPN, a pre-commit hook, the MCP server
an agent client spawned. Its chain ends in a local unauthenticated actor,
deliberately, because a validator that needed a token would become the enemy the
day auth is down.

This module answers it for a request that arrived over a network, where that
ending is exactly wrong. `auth-integration` is explicit:

> *"a request presents no credential ... it SHALL be refused ... and SHALL NOT
> be served as an anonymous or default actor."*

So the two resolutions are two functions rather than one function with a flag.
A flag is a thing a caller gets wrong once and nobody notices; two entry points
with no shared default cannot be confused, and
:func:`~cybercanon.application.use_cases.resolve_actor.local_actor` is not
reachable from anything here.

Three things this does, and nothing else:

* **refuse a request with no credential** — as unauthenticated, naming what is
  missing rather than serving somebody;
* **hand the credential to the verification adapter and keep the actor** — the
  token itself never travels further than the adapter, which is D12 and is why
  the whole authorization suite runs with no identity service present;
* **ignore anything the caller claimed about themselves** —
  :func:`~cybercanon.application.use_cases.resolve_actor.strip_identity_claims`
  is the same filter the MCP surface uses, applied here so a body-supplied actor
  and a path-supplied tenant are dropped *and named* rather than tolerated.

Authorization is not here. It is
:func:`~cybercanon.domain.policy.decide`, over the actor this produced, and this
module holds no opinion about what that actor may do.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.identity_provider import (
    Credential,
    IdentityProvider,
    ResolvedIdentity,
)
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.resolve_actor import strip_identity_claims
from cybercanon.domain.identity import Actor

NO_CREDENTIAL = (
    "this surface serves no anonymous actor: present a credential issued by the "
    "configured identity service"
)
"""What a caller with no credential is told. It names no actor, because there is none."""


class CredentialMissing(OperationFailed):
    """Nothing was presented. Unauthenticated, and never a default actor.

    Distinct from
    :class:`~cybercanon.application.ports.identity_provider.CredentialRejected`
    because the two lead a caller to different actions — sign in, versus your
    credential is not acceptable — and because the second requires a credential
    to have been read at all.
    """

    kind = FailureKind.UNAUTHENTICATED
    identifier = "auth.credential_missing"

    def __init__(self, subject: str = "this request") -> None:
        super().__init__(NO_CREDENTIAL, subject)


class NotAutomation(OperationFailed):
    """A service credential was expected and a person's credential arrived.

    Background work is *"recorded as automation rather than as any person"*, so
    a person's credential reaching the background path is refused rather than
    quietly recorded as automation — which would attribute somebody's action to
    nobody — and equally rather than recorded as them, which would attribute an
    unattended job to a person who was asleep.
    """

    kind = FailureKind.FORBIDDEN
    identifier = "auth.not_automation"

    def __init__(self, subject: str) -> None:
        super().__init__(
            f"{subject} resolved to a person; background work authenticates with a "
            "service credential and is recorded as automation",
            subject,
        )


@dataclass(frozen=True)
class Authenticated:
    """The actor a verified credential produced, and the claims the caller sent.

    `ignored` names the identity-claiming parameters that were dropped. It is
    reported rather than discarded because *"the supplied value SHALL have no
    effect"* is only observable if somebody says so — silence there reads as
    acceptance, and a client would keep sending it.
    """

    actor: Actor
    git_emails: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()

    @property
    def subject(self) -> str:
        """The stable identifier this request is evaluated as."""
        return self.actor.subject

    @property
    def is_automation(self) -> bool:
        return self.actor.is_automation


@as_result
def authenticate(
    presented: Credential | None,
    *,
    identity_provider: IdentityProvider,
    claimed: Mapping[str, Any] | None = None,
) -> Authenticated:
    """The actor this request is evaluated as, or a refusal — never an anonymous one.

    `claimed` is whatever the caller supplied alongside the credential — a
    request body, a path's parameters. It is accepted only so that it can be
    *stripped*: nothing in it reaches the actor, and the names that tried are
    returned so a surface can say they had no effect.
    """
    if presented is None:
        raise CredentialMissing()
    identity = identity_provider.resolve(presented)
    return _authenticated(identity, claimed)


@as_result
def authenticate_background(
    presented: Credential | None,
    *,
    identity_provider: IdentityProvider,
    claimed: Mapping[str, Any] | None = None,
) -> Authenticated:
    """The same, for work with no live human caller, and it must be automation.

    The service credential resolves to an actor the adapter marked as
    automation; anything else is refused here rather than at the adapter, so the
    rule holds for every identity provider this is ever wired to.
    """
    if presented is None:
        raise CredentialMissing("this scheduled run")
    identity = identity_provider.resolve(presented)
    if not identity.actor.is_automation:
        raise NotAutomation(identity.actor.subject)
    return _authenticated(identity, claimed)


def _authenticated(identity: ResolvedIdentity, claimed: Mapping[str, Any] | None) -> Authenticated:
    """One shape for both paths: the resolved actor, and what the caller claimed."""
    _, ignored = strip_identity_claims(claimed or {})
    return Authenticated(actor=identity.actor, git_emails=identity.git_emails, ignored=ignored)


__all__ = [
    "NO_CREDENTIAL",
    "Authenticated",
    "CredentialMissing",
    "NotAutomation",
    "authenticate",
    "authenticate_background",
]
