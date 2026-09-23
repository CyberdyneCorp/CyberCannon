"""Task 8.3 (D8) — an identity outage costs new sessions, and says so.

D8 is one decision with two visible halves, and a deployment that got either
one wrong would look fine until CyberdyneAuth had an afternoon:

* *"The `IdentityProvider` adapter caches the signing keys with a TTL and
  continues verifying existing tokens while the provider is unreachable."* So a
  credential minted before the outage keeps working, and the window it keeps
  working for is **configured** — ``CANON_AUTH_KEY_CACHE_TTL_S`` — because D8
  states the cost of the number (*"a bounded window where a key rotated during
  an outage is not yet known"*) and a stated cost is a deployment's to choose.
* *"Readiness never consults it; `/status` reports it unreachable."* So the
  outage may not withhold a single request, and it may not be silent either.

The issuer here is `tools/canon_issuer`'s, which signs with real RSA keys and
can be told to stop answering, so *"unreachable"* is a source that raises rather
than a flag somebody set on the thing under test. What it never is, is a socket:
every rule in this module is a rule about a cache, and a cache is testable with
no network at all.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from canon_issuer import CLIENT_ID, ORG_ID, FakeIssuer
from cybercanon.adapters.inbound.http.health import DEGRADED_FIELD, READY, READY_PATH, STATUS_FIELD
from cybercanon.adapters.inbound.http.status import STATUS_PATH
from cybercanon.adapters.outbound.auth.keys import KeySetPolicy
from cybercanon.adapters.wiring.configuration import (
    AUTH_KEY_CACHE_TTL,
    DEFAULT_KEY_CACHE_TTL,
    IdentityConfig,
    load,
)
from cybercanon.adapters.wiring.identity import (
    NEVER_RETRIEVED,
    VERIFYING,
    identity_provider,
    identity_status,
)
from cybercanon.api.main import build_for
from cybercanon.application.ports.identity_provider import IdentityServiceUnavailable
from cybercanon.application.use_cases.service_health import (
    AVAILABLE,
    IDENTITY_SERVICE,
    UNAVAILABLE,
    Reliance,
)

pytestmark = pytest.mark.unit

COMPLETE = {
    "CANON_PROJECT": "ironwood",
    "CANON_REPOSITORY_URL": "git@github.com:cyberdynecorp/ironwood.git",
    "CANON_REPOSITORY_BRANCH": "canon",
    "CANON_REPOSITORY_CREDENTIAL": "a-deploy-key",
    "CANON_FETCH_INTERVAL_S": "300",
    "CANON_WEBHOOK_SECRET": "a-webhook-secret",
    "CANON_AUTH_ISSUER": "https://auth.cyberdynecorp.ai/",
    "CANON_AUTH_AUDIENCE": "cybercanon",
    "CANON_AUTH_CLIENT_ID": CLIENT_ID,
    "CANON_AUTH_ORG_ID": ORG_ID,
    "CANON_AUTH_KEY_SET_URL": "https://auth.cyberdynecorp.ai/.well-known/jwks.json",
    "CANON_AUTH_GROUP_ROLES": "art-leads=ART_DIRECTOR,artists=ARTIST",
    "CANON_DATABASE_URL": "postgresql://canon@db/canon",
    "CANON_OBJECT_STORE_URL": "https://minio.cyberdynecorp.ai",
    "CANON_LINK_EXPIRY_S": "120",
    "CANON_WRITE_BACK_TIMEOUT_S": "30",
    "CANON_DRAIN_WINDOW_S": "90",
}
"""A configured deployment, with nothing said about the key cache."""


@pytest.fixture
def issuer() -> FakeIssuer:
    """CyberdyneAuth, signing with real keys and able to stop answering."""
    return FakeIssuer(now=int(time.time()))


def _identity(issuer: FakeIssuer, ttl: timedelta = DEFAULT_KEY_CACHE_TTL) -> IdentityConfig:
    return IdentityConfig(
        issuer=issuer.issuer,
        audience=issuer.audience,
        key_set_url="https://auth.cyberdynecorp.ai/.well-known/jwks.json",
        group_roles={"art_director": "ART_DIRECTOR"},
        client_id=issuer.client_id,
        organisation=ORG_ID,
        key_cache_ttl=ttl,
    )


def _eager(window_s: float = 900.0) -> KeySetPolicy:
    """The configured window, with the anti-hammering cooldown out of the way."""
    return KeySetPolicy(offline_window_s=window_s, refresh_cooldown_s=0.0)


class _Ticking:
    """A clock a test moves, so a fifteen-minute window costs no seconds."""

    def __init__(self) -> None:
        self.at = 0.0

    def __call__(self) -> float:
        return self.at


# --------------------------------------------------------------------------
# The TTL is configuration
# --------------------------------------------------------------------------


def test_the_key_cache_window_defaults_when_nothing_is_configured() -> None:
    assert load(COMPLETE).identity.key_cache_ttl == DEFAULT_KEY_CACHE_TTL


def test_the_key_cache_window_is_read_from_the_environment() -> None:
    loaded = load({**COMPLETE, AUTH_KEY_CACHE_TTL: "60"})

    assert loaded.identity.key_cache_ttl == timedelta(seconds=60)


def test_a_malformed_key_cache_window_is_a_refused_boot() -> None:
    """Optional means absent is allowed, not that anything goes."""
    with pytest.raises(Exception, match=AUTH_KEY_CACHE_TTL):
        load({**COMPLETE, AUTH_KEY_CACHE_TTL: "a quarter of an hour"})


def test_the_configured_window_is_the_caches_window(issuer: FakeIssuer) -> None:
    wired = identity_provider(_identity(issuer, timedelta(minutes=5)), source=issuer)

    assert wired.keys.policy.offline_window_s == 300.0


# --------------------------------------------------------------------------
# The outage: existing credentials keep verifying
# --------------------------------------------------------------------------


def test_a_credential_minted_before_the_outage_still_verifies(issuer: FakeIssuer) -> None:
    """*"continues verifying existing tokens while the provider is unreachable"*."""
    wired = identity_provider(_identity(issuer), source=issuer)
    credential = issuer.mint("auth|rafa", roles=["art_director"])
    wired.provider.resolve(credential)
    retrievals = issuer.fetches

    issuer.go_dark()
    resolved = wired.provider.resolve(credential)

    assert resolved.actor.id.value == "auth|rafa"
    assert issuer.fetches == retrievals, "a cached key was re-retrieved during an outage"


def test_the_window_ends_and_the_refusal_names_the_identity_service(
    issuer: FakeIssuer,
) -> None:
    """*"a bounded window ... ending at the TTL"* — stated, and then executed."""
    clock = _Ticking()
    wired = identity_provider(_identity(issuer, timedelta(minutes=5)), source=issuer, clock=clock)
    credential = issuer.mint("auth|rafa", roles=["art_director"])
    wired.provider.resolve(credential)

    issuer.go_dark()
    clock.at = 301.0

    with pytest.raises(IdentityServiceUnavailable):
        wired.provider.resolve(credential)


def test_a_longer_window_keeps_verifying_where_a_shorter_one_would_not(
    issuer: FakeIssuer,
) -> None:
    """The number is the deployment's decision, so it has to make a difference."""
    clock = _Ticking()
    wired = identity_provider(_identity(issuer, timedelta(hours=1)), source=issuer, clock=clock)
    credential = issuer.mint("auth|rafa", roles=["art_director"])
    wired.provider.resolve(credential)

    issuer.go_dark()
    clock.at = 301.0

    assert wired.provider.resolve(credential).actor.id.value == "auth|rafa"


# --------------------------------------------------------------------------
# The outage is visible, and it gates nothing
# --------------------------------------------------------------------------


def test_nothing_retrieved_yet_is_not_an_outage(issuer: FakeIssuer) -> None:
    """A service that has not been asked anything yet knows nothing, and says so."""
    wired = identity_provider(_identity(issuer), source=issuer)

    assert wired.status.state == AVAILABLE
    assert wired.status.detail == NEVER_RETRIEVED


def test_a_successful_retrieval_reports_the_service_available(issuer: FakeIssuer) -> None:
    wired = identity_provider(_identity(issuer), source=issuer)

    wired.provider.resolve(issuer.mint("auth|rafa", roles=["art_director"]))

    assert wired.status == identity_status(wired.observed)
    assert wired.status.detail == VERIFYING


def test_a_failed_retrieval_reports_the_service_unreachable(issuer: FakeIssuer) -> None:
    """The realistic sequence: a rotated key is what forces a retrieval.

    The cooldown is zeroed rather than waited out. It exists so that a stream of
    credentials naming unknown keys cannot be turned into a stream of requests
    at the issuer, which is a different rule from this one; leaving it in would
    make the scenario a test of how long this suite is willing to sleep.
    """
    wired = identity_provider(_identity(issuer), source=issuer, policy=_eager())
    old = issuer.mint("auth|rafa", roles=["art_director"])
    wired.provider.resolve(old)

    issuer.go_dark()
    issuer.rotate()
    with pytest.raises(IdentityServiceUnavailable):
        wired.provider.resolve(issuer.mint("auth|ana", roles=["art_director"]))

    assert wired.status.state == UNAVAILABLE
    assert wired.provider.resolve(old).actor.id.value == "auth|rafa", "the cached key held"


def test_an_unreachable_identity_service_never_withholds_traffic(issuer: FakeIssuer) -> None:
    """The classification is the specification's, and it is what makes this safe."""
    wired = identity_provider(_identity(issuer), source=issuer)
    issuer.go_dark()
    with pytest.raises(IdentityServiceUnavailable):
        wired.provider.resolve(issuer.mint("auth|rafa"))

    assert wired.status.relied_on is Reliance.OPTIONAL
    assert not wired.status.withholds
    assert wired.status.degrades


# --------------------------------------------------------------------------
# End to end over the deployable: the outage on `/status`, and `/readyz` ready
# --------------------------------------------------------------------------


def _environment(issuer: FakeIssuer) -> dict[str, str]:
    return {
        **COMPLETE,
        "CANON_AUTH_ISSUER": issuer.issuer,
        "CANON_AUTH_AUDIENCE": issuer.audience,
    }


def _served_by(monkeypatch: pytest.MonkeyPatch, issuer: FakeIssuer) -> None:
    """Point the deployable's key source at this issuer, and drop the cooldown.

    Two substitutions, and neither changes a rule: the published key set comes
    from an issuer in this process rather than over HTTP, and the gap between
    two retrievals is zero so that an outage is observable without waiting ten
    seconds for permission to notice it.
    """
    from cybercanon.adapters.wiring import identity as wiring

    monkeypatch.setattr(
        wiring, "JwksKeySource", lambda *_arguments, **_keywords: issuer, raising=True
    )
    monkeypatch.setattr(
        wiring, "KeySetPolicy", lambda **keywords: KeySetPolicy(**keywords, refresh_cooldown_s=0.0)
    )


def test_the_status_surface_names_the_identity_service_unreachable(
    issuer: FakeIssuer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/status` is authenticated, so the credential that reads it is a cached one."""
    _served_by(monkeypatch, issuer)
    client = TestClient(build_for(load(_environment(issuer))))
    rafa = issuer.mint("auth|rafa", roles=["art_director"])
    client.get(STATUS_PATH, headers={"Authorization": f"Bearer {rafa.value}"})

    issuer.go_dark()
    issuer.rotate()
    client.get(STATUS_PATH, headers={"Authorization": f"Bearer {issuer.mint('auth|ana').value}"})
    response = client.get(STATUS_PATH, headers={"Authorization": f"Bearer {rafa.value}"})

    body = response.json()["data"]
    named = next(one for one in body["dependencies"] if one["name"] == IDENTITY_SERVICE)
    assert response.status_code == 200
    assert named["state"] == UNAVAILABLE
    assert IDENTITY_SERVICE in body[DEGRADED_FIELD]


def test_readiness_stays_ready_through_that_outage(
    issuer: FakeIssuer, monkeypatch: pytest.MonkeyPatch
) -> None:
    _served_by(monkeypatch, issuer)
    client = TestClient(build_for(load(_environment(issuer))))
    issuer.go_dark()

    response = client.get(READY_PATH)

    assert response.status_code == 200
    assert response.json()[STATUS_FIELD] == READY


def test_the_minted_credential_is_current(issuer: FakeIssuer) -> None:
    """The fixture mints against wall-clock time, so nothing here expires mid-run."""
    assert abs(issuer.now - datetime.now(UTC).timestamp()) < 60
