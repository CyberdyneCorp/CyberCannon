"""The identity provider the hosted service runs with, and what it reports (D8).

Two sentences of the specification meet here and neither is about verifying a
token. *"Readiness SHALL NOT depend on ... the identity provider"* and *"the
status surface SHALL name the identity provider as unreachable"* — so an outage
of CyberdyneAuth has to be **survivable** and **visible**, and those are
different mechanisms.

*Survivable* is :class:`~cybercanon.adapters.outbound.auth.keys.CachedKeySet`
and its window, and this module's contribution is that the window is
**configuration**: ``CANON_AUTH_KEY_CACHE_TTL_S``, defaulting to fifteen
minutes. D8 states the cost in so many words — *"verification keeps working,
new logins do not"*, and *"a bounded window where a key rotated during an
outage is not yet known, ending at the TTL"* — and a number that governs a
stated cost is a number a deployment gets to choose.

*Visible* is :class:`ObservedKeys`. It wraps the key source rather than reaching
into the cache, because the question `/status` asks is about the **last attempt
to retrieve** — which is exactly what a wrapper sees and what a cache hit
deliberately does not produce. Nothing here probes on demand: `/status` is
authenticated, so answering it has already driven the cache, and a status
surface that went and asked the identity service every time it was read would
be the second request per outage nobody wants.

The composition root calls :func:`identity_provider`; the readiness rule never
does. That asymmetry is the whole of D8.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cybercanon.adapters.outbound.auth.cyberdyne import CyberdyneAuth, Trust
from cybercanon.adapters.outbound.auth.keys import (
    CachedKeySet,
    Clock,
    JwksKeySource,
    KeySetPolicy,
    KeySource,
)
from cybercanon.adapters.wiring.configuration import IdentityConfig
from cybercanon.application.use_cases.service_health import (
    IDENTITY_SERVICE,
    ComponentStatus,
    available,
    unavailable,
)

VERIFYING = "the published signing keys were retrieved and are current"

NEVER_RETRIEVED = (
    "the published signing keys have not been retrieved yet; credentials will be "
    "verified once the first retrieval succeeds"
)


@dataclass
class ObservedKeys:
    """A key source that remembers how its last retrieval went.

    It answers :class:`~cybercanon.adapters.outbound.auth.keys.KeySource`, so
    the cache is unaware of it; what it adds is the one fact `/status` needs and
    a cache cannot give — whether the *issuer* answered the last time anybody
    asked it, as opposed to whether a cached key happened to satisfy a request.
    """

    source: KeySource
    attempts: int = 0
    failures: int = 0
    last_error: str = ""

    def fetch(self) -> Mapping[str, Any]:
        self.attempts += 1
        try:
            document = self.source.fetch()
        except Exception as failure:
            self.failures += 1
            self.last_error = f"{type(failure).__name__}: {failure}"
            raise
        self.last_error = ""
        return document

    @property
    def reachable(self) -> bool:
        """Whether the issuer answered the last time this process asked it."""
        return self.attempts > 0 and not self.last_error


@dataclass(frozen=True)
class WiredIdentity:
    """The provider the surface is given, and the source the status surface reads."""

    provider: CyberdyneAuth
    keys: CachedKeySet
    observed: ObservedKeys

    @property
    def status(self) -> ComponentStatus:
        return identity_status(self.observed)


def identity_provider(
    identity: IdentityConfig,
    *,
    source: KeySource | None = None,
    policy: KeySetPolicy | None = None,
    clock: Clock | None = None,
) -> WiredIdentity:
    """Build the verifier, with its key cache bounded by the configured TTL.

    `source`, `policy` and `clock` are parameters so that a suite can drive an
    issuer that stops answering, and a window that expires, without a socket and
    without waiting; a deployment passes none of them and gets the published key
    set over HTTP with the configured window.

    Nothing is retrieved here: construction opens no connection, because a boot
    that needed the identity service to be up would be the cascade this whole
    change exists to prevent.
    """
    observed = ObservedKeys(source or JwksKeySource(identity.key_set_url))
    keys = CachedKeySet(
        observed,
        policy=policy or KeySetPolicy(offline_window_s=identity.key_cache_ttl.total_seconds()),
        clock=clock,
    )
    provider = CyberdyneAuth(
        trust=Trust(issuer=identity.issuer, audience=identity.audience),
        keys=keys,
        group_roles=dict(identity.group_roles),
    )
    return WiredIdentity(provider=provider, keys=keys, observed=observed)


def identity_status(observed: ObservedKeys) -> ComponentStatus:
    """What `/status` says about the identity service. It never gates readiness.

    :data:`~cybercanon.application.use_cases.service_health.IDENTITY_SERVICE` is
    classified `OPTIONAL`, so this observation degrades a feature — signing in —
    and can never withhold traffic. That classification is the specification's,
    not this module's, and is why reporting an outage here is safe.
    """
    if observed.reachable:
        return available(IDENTITY_SERVICE, VERIFYING)
    if observed.attempts == 0:
        return available(IDENTITY_SERVICE, NEVER_RETRIEVED)
    return unavailable(IDENTITY_SERVICE, observed.last_error)


__all__ = [
    "NEVER_RETRIEVED",
    "VERIFYING",
    "ObservedKeys",
    "WiredIdentity",
    "identity_provider",
    "identity_status",
]
