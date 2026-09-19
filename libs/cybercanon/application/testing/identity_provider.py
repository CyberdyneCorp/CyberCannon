"""The in-memory `IdentityProvider` — credentials in a dict, outages on demand.

Identity is the one port whose *failures* carry as much specified behaviour as
its successes: `agent-identity` requires that reads survive an identity outage,
that an expired cached actor refuses role-requiring actions, and that a missing
credential degrades to a local actor rather than a refusal. None of that is
testable against a provider that always answers, so this fake makes the two
failure modes first-class — :meth:`fail_with` for a service that is down, and
simply not seeding a credential for one that rejects it.

It also models the D13 split: :meth:`add` takes `git_emails`, so a scenario can
seed a provider that describes a person's commit addresses and one that does
not, and assert that the mapping file is consulted in exactly the second case.
"""

from __future__ import annotations

from cybercanon.application.ports.identity_provider import (
    Credential,
    IdentityUnavailable,
    ResolvedIdentity,
)
from cybercanon.domain.identity import Actor


class InMemoryIdentityProvider:
    """Resolved identities keyed by the opaque credential that produces them."""

    def __init__(self) -> None:
        self._identities: dict[str, ResolvedIdentity] = {}
        self._failure: Exception | None = None
        self.resolutions = 0

    # -- seeding ---------------------------------------------------------

    def add(
        self, credential: Credential, actor: Actor, git_emails: tuple[str, ...] = ()
    ) -> ResolvedIdentity:
        """Register what this credential resolves to, with or without git emails."""
        identity = ResolvedIdentity(actor=actor, git_emails=git_emails)
        self._identities[credential.value] = identity
        return identity

    def fail_with(self, error: Exception | None) -> None:
        """Make every resolution raise — the identity outage the spec requires.

        ``None`` clears it, so one test can resolve an actor, take the service
        away and prove the read still succeeds from the cache.
        """
        self._failure = error

    # -- port ------------------------------------------------------------

    def resolve(self, credential: Credential) -> ResolvedIdentity:
        self.resolutions += 1
        if self._failure is not None:
            raise self._failure
        identity = self._identities.get(credential.value)
        if identity is None:
            raise IdentityUnavailable(str(credential), "unknown credential")
        return identity


__all__ = ["InMemoryIdentityProvider"]
