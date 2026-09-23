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

The other half of this module is the **other** caller of the same identity
service: background work, which `auth-integration` requires to authenticate with
a service credential of its own. :func:`worker_credentials` builds the
client-credentials flow from `CANON_WORKER_CLIENT_ID` and its secret, and
:func:`background_identity` turns what it obtains into the subject a personless
pass is recorded as — degrading to `automation` whenever there is no client or
the issuer cannot be reached, because validation that stopped for want of an
identity service would be an outage turning into a backlog.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from cybercanon.adapters.outbound.auth.cyberdyne import CyberdyneAuth, Trust
from cybercanon.adapters.outbound.auth.discovery import EndpointDirectory, IssuerEndpoints
from cybercanon.adapters.outbound.auth.flows import ServiceCredentials
from cybercanon.adapters.outbound.auth.keys import (
    CachedKeySet,
    Clock,
    JwksKeySource,
    KeySetPolicy,
    KeySource,
)
from cybercanon.adapters.outbound.auth.oauth import OAuthTransport
from cybercanon.adapters.wiring.configuration import IdentityConfig, ServiceConfiguration
from cybercanon.application.ports.identity_provider import IdentityProvider
from cybercanon.application.use_cases.service_health import (
    IDENTITY_SERVICE,
    ComponentStatus,
    available,
    unavailable,
)
from cybercanon.domain.validation_outcome import AUTOMATION

type Attribution = Callable[[], str]
"""Who a personless pass is recorded as, asked once per pass and never cached wrong."""

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
    project: str = "",
    source: KeySource | None = None,
    policy: KeySetPolicy | None = None,
    clock: Clock | None = None,
) -> WiredIdentity:
    """Build the verifier, with its key cache bounded by the configured TTL.

    `project` is what this deployment serves and is the entitlement an admitted
    credential resolves with: a CyberdyneAuth token names no project, so the
    person is admitted by their `orgs` claim and their roles on this client and
    the *name* of what they may then read has to come from the configuration
    that already decides it (`CANON_PROJECT`). A verifier told no project
    entitles nobody to anything, which is the fail-closed direction.

    The trust carries one more list than it used to: the service clients whose
    background work this deployment admits. Nothing in a service credential says
    whose machine it is — `type: service` says only that it is a machine — so a
    deployment that lists none admits none, and its own worker is refused until
    `CANON_AUTH_SERVICE_CLIENTS` names it. That is the fail-closed direction and
    it is the same one `project` and `organisation` fail in.

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
        trust=Trust(
            issuer=identity.issuer,
            audience=identity.audience,
            client_id=identity.client_id,
            organisation=identity.organisation,
            service_clients=tuple(identity.service_clients),
        ),
        keys=keys,
        project=project,
        group_roles=dict(identity.group_roles),
    )
    return WiredIdentity(provider=provider, keys=keys, observed=observed)


def worker_credentials(
    configuration: ServiceConfiguration,
    *,
    endpoints: EndpointDirectory | None = None,
    transport: OAuthTransport | None = None,
) -> ServiceCredentials | None:
    """How background work obtains a credential of its own, when it has a client.

    `auth-integration`: *"Work performed with no live human caller SHALL
    authenticate with a service credential, SHALL resolve to an actor identified
    as automation, SHALL be recorded as automation rather than as any person, and
    SHALL be refused every operation the project reserves to a person."* The
    second half has always been true here — an unauthenticated background pass is
    attributed to
    :func:`~cybercanon.domain.identity.automation_actor` and refused every
    human-only operation — and the first half is this function: the credential
    comes from a **client-credentials exchange** against the issuer this
    deployment already trusts, minted for the worker's own client.

    ``None`` when `CANON_WORKER_CLIENT_ID` and `CANON_WORKER_CLIENT_SECRET` are
    not both set, which is a deployment whose background work presents no
    credential rather than a deployment that will not start: half a
    configuration behaves like the absence it is, exactly as the model settings
    do, instead of failing once per scheduled run.

    The token endpoint is **discovered**, never composed from the issuer: this
    product has already posted one grant into a 404 by appending a path it
    believed in. Nothing is retrieved at construction — :class:`IssuerEndpoints`
    reads the document the first time a credential is actually asked for.

    Obtaining a credential and being admitted with it are two settings, and a
    deployment can set one without the other. `CANON_AUTH_SERVICE_CLIENTS` has
    to list this same client id, or the credential this exchange obtains is
    refused by the verifier and :func:`background_identity` falls back to plain
    `automation` — a quiet degradation rather than an outage, and the reason the
    verifier's refusal names the variable.

    The secret reaches the exchange and nothing else. It is a
    :class:`~cybercanon.adapters.wiring.configuration.Secret` everywhere it is
    stored, so it cannot print itself into a log line, a refusal or a traceback,
    which is the treatment `CANON_REPOSITORY_CREDENTIAL` gets and for the same
    reason.
    """
    worker = configuration.worker
    if not worker.available:
        return None
    return ServiceCredentials(
        endpoints=endpoints or IssuerEndpoints(configuration.identity.issuer),
        client_id=worker.client_id,
        client_secret=worker.secret.value,
        audience=configuration.identity.audience,
        transport=transport,
    )


def background_identity(
    credentials: ServiceCredentials | None,
    *,
    provider: IdentityProvider | None,
    default: str = AUTOMATION,
) -> Attribution:
    """What background work is recorded as: whoever its own credential resolves to.

    This is the half of `auth-integration`'s background requirement that had no
    code behind it. *"Work performed with no live human caller SHALL
    authenticate with a service credential, SHALL resolve to an actor identified
    as automation"* — the second clause has always held, because a personless
    pass is attributed to automation by
    :mod:`cybercanon.application.use_cases.validation_worker`; the first one now
    does too, because the attribution is the subject of the credential the
    worker obtained for itself and had verified by the same adapter every other
    caller goes through.

    Three properties, and the third is the one worth arguing about:

    * it obtains **lazily**, at the first pass rather than at boot, so a
      deployment still starts while CyberdyneAuth is down — the cascade D8
      exists to prevent;
    * it caches only a **successful** answer, so an outage during the first pass
      is retried at the next one rather than remembered for the life of the
      process;
    * it **degrades to automation** on every failure. Background validation that
      stopped because an identity service was unreachable would be an outage
      turning into a growing backlog of unvalidated exports, and the worker was
      never able to do more than automation can: the resolution is refused
      unless the actor *is* automation
      (:func:`~cybercanon.application.use_cases.authenticate.authenticate_background`),
      so this can name a different subject and can never name a person.
    """
    remembered: list[str] = []

    def attributed_to() -> str:
        if remembered:
            return remembered[0]
        subject = _obtained(credentials, provider)
        if subject:
            remembered.append(subject)
        return subject or default

    return attributed_to


def _obtained(credentials: ServiceCredentials | None, provider: IdentityProvider | None) -> str:
    """The subject the worker's own credential resolves to, or nothing at all."""
    if credentials is None or provider is None:
        return ""
    try:
        resolved = provider.resolve(credentials.obtain())
    except Exception:  # an unreachable issuer must not stop background work
        return ""
    return resolved.actor.subject if resolved.actor.is_automation else ""


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
    "Attribution",
    "ObservedKeys",
    "WiredIdentity",
    "background_identity",
    "identity_provider",
    "identity_status",
    "worker_credentials",
]
