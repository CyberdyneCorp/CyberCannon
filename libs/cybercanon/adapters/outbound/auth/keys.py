"""The issuer's published keys: cached, rotated, and bounded when it goes away.

Two requirements meet in this module and they pull in opposite directions.

*Rotation:* *"the issuer publishes a new signing key ... a credential signed by
that key SHALL be accepted without the service being restarted or
reconfigured."* So an unknown key identifier is a reason to go and look again,
not a reason to refuse.

*Outage:* *"the surface SHALL continue to verify credentials against the most
recently retrieved published keys for a bounded configured period ... Beyond
that period, or for a credential requiring a fresh exchange, requests SHALL be
refused with a message naming the identity service as unavailable."* So an
unreachable issuer is survivable for a while and then is not, and the refusal
when it stops being survivable says *which* thing is down.

:class:`CachedKeySet` is where those two become one policy, and the shape it
lands on is:

1. if the last successful retrieval is older than the offline window, retrieve
   again — and a failure here is :class:`IdentityServiceUnavailable`, whatever
   is in the cache, because the window is the whole guarantee;
2. if the credential's key is cached, verify against it;
3. otherwise retrieve again, subject to a cooldown — this is rotation;
4. if that retrieval fails, the credential *requires a fresh exchange* and the
   issuer is unreachable, so it is again an unavailability rather than a
   rejection. If it succeeds and the key is still unknown, the credential is
   signed by nothing this issuer publishes, and *that* is a rejection.

The cooldown exists so that a stream of credentials carrying garbage key
identifiers cannot be turned into a stream of requests at the issuer. It is
short, and it is measured from the last *attempt* rather than the last success,
because a failing issuer is exactly when hammering it is worst.

Nothing here reads a token. :class:`CachedKeySet` is handed a key identifier and
answers with a key or a named failure; what a credential is, and whether its
claims are acceptable, belongs to :mod:`cybercanon.adapters.outbound.auth.cyberdyne`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from joserfc import jwk
from joserfc.errors import JoseError

from cybercanon.application.ports.identity_provider import (
    CredentialRejected,
    IdentityServiceUnavailable,
)

Clock = Callable[[], float]
"""Monotonic-ish seconds. Injected so a window can be crossed without waiting."""

DEFAULT_OFFLINE_WINDOW_S = 900.0
"""How long cached keys keep verifying while the issuer is unreachable.

Fifteen minutes: long enough that a restart of the identity service is invisible
to everyone using the tool, short enough that a revoked key stops being honoured
inside a coffee break. It is configuration governing specified behaviour, which
is the design's own description of the numbers it declined to fix.
"""

DEFAULT_REFRESH_COOLDOWN_S = 10.0
"""The shortest gap between two retrievals. Rotation waits at most this long."""

UNKNOWN_KEY = "the credential names a key the issuer does not publish"
UNREACHABLE = "the published key set could not be retrieved"


class KeySource(Protocol):
    """Where the issuer's published key set comes from."""

    def fetch(self) -> Mapping[str, Any]:
        """The current key set document. Raises when the issuer is unreachable."""
        ...


class KeySetUnreachable(Exception):
    """A source could not retrieve the key set. Translated, never surfaced raw."""


@dataclass(frozen=True)
class KeySetPolicy:
    """How long cached keys last without the issuer, and how often to ask."""

    offline_window_s: float = DEFAULT_OFFLINE_WINDOW_S
    refresh_cooldown_s: float = DEFAULT_REFRESH_COOLDOWN_S


class CachedKeySet:
    """The issuer's keys, kept between requests and re-retrieved when they move.

    `retrievals` and `failures` are counted because two of the specified
    behaviours are about *not* going to the network — the cooldown, and a cached
    hit during an outage — and a behaviour about absence is only testable if the
    absence is observable.
    """

    def __init__(
        self,
        source: KeySource,
        *,
        policy: KeySetPolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._source = source
        self._policy = policy or KeySetPolicy()
        self._clock: Clock = clock or time.monotonic
        self._keys: jwk.KeySet | None = None
        self._retrieved_at: float | None = None
        self._attempted_at: float | None = None
        self.retrievals = 0
        self.failures = 0

    @property
    def policy(self) -> KeySetPolicy:
        return self._policy

    @property
    def retrieved_at(self) -> float | None:
        """When the key set was last retrieved successfully, if ever."""
        return self._retrieved_at

    def key_for(self, kid: str | None) -> jwk.Key:
        """The published key with this identifier, or a named failure.

        :class:`~cybercanon.application.ports.identity_provider.IdentityServiceUnavailable`
        when the issuer is unreachable and the answer depends on reaching it;
        :class:`~cybercanon.application.ports.identity_provider.CredentialRejected`
        when the issuer was reached and publishes no such key.
        """
        self._retire_if_beyond_window()
        found = self._cached(kid)
        if found is not None:
            return found
        self._rotate()
        found = self._cached(kid)
        if found is None:
            raise CredentialRejected(UNKNOWN_KEY)
        return found

    def refresh(self) -> None:
        """Retrieve the key set now, translating an unreachable issuer."""
        self._attempted_at = self._clock()
        try:
            document = self._source.fetch()
        except Exception as failure:  # any source failure is one unavailability
            self.failures += 1
            raise IdentityServiceUnavailable("the published key set", UNREACHABLE) from failure
        self._keys = jwk.KeySet.import_key_set(dict(document))
        self._retrieved_at = self._attempted_at
        self.retrievals += 1

    # -- the policy, one clause per method -------------------------------

    def _retire_if_beyond_window(self) -> None:
        """Clause 1: cached keys expire, and expiry is not survivable."""
        if self._retrieved_at is None:
            self.refresh()
            return
        if self._clock() - self._retrieved_at > self._policy.offline_window_s:
            self.refresh()

    def _rotate(self) -> None:
        """Clause 3 and 4: an unknown key is a reason to look again, once in a while."""
        if not self._may_attempt():
            raise CredentialRejected(UNKNOWN_KEY)
        self.refresh()

    def _may_attempt(self) -> bool:
        if self._attempted_at is None:
            return True
        return self._clock() - self._attempted_at >= self._policy.refresh_cooldown_s

    def _cached(self, kid: str | None) -> jwk.Key | None:
        """The cached key with this identifier, or ``None`` — never a failure.

        A key set with exactly one key answers a credential that names no `kid`,
        because a single-key issuer is a real and legal configuration. Two or
        more keys and no identifier is unanswerable, and unanswerable is
        ``None``: the caller decides whether that means rotate or refuse.
        """
        if self._keys is None:
            return None
        if kid:
            try:
                return self._keys.get_by_kid(kid)
            except JoseError:
                return None
            except ValueError:
                return None
        keys = self._keys.keys
        return keys[0] if len(keys) == 1 else None


class JwksKeySource:
    """The published key set, retrieved over HTTP from the configured address.

    The whole of the network in this adapter, deliberately: everything that
    decides anything runs against a :class:`KeySource`, so the rotation policy,
    the offline window and every verification rule are exercised with no socket
    and no server. What is left here is a request and a timeout.
    """

    def __init__(self, url: str, *, timeout_s: float = 5.0, client: Any | None = None) -> None:
        self.url = url
        self.timeout_s = timeout_s
        self._client = client

    def fetch(self) -> Mapping[str, Any]:
        import httpx

        client = self._client or httpx
        try:
            response = client.get(self.url, timeout=self.timeout_s)
            response.raise_for_status()
            document = response.json()
        except Exception as failure:
            raise KeySetUnreachable(f"{type(failure).__name__} retrieving the key set") from failure
        if not isinstance(document, Mapping) or "keys" not in document:
            raise KeySetUnreachable("the address did not answer with a key set")
        return document


__all__ = [
    "DEFAULT_OFFLINE_WINDOW_S",
    "DEFAULT_REFRESH_COOLDOWN_S",
    "UNKNOWN_KEY",
    "UNREACHABLE",
    "CachedKeySet",
    "Clock",
    "JwksKeySource",
    "KeySetPolicy",
    "KeySetUnreachable",
    "KeySource",
]
