"""The browser's question, and the only two answers this surface gives.

`deploy/coolify.yaml` puts the API at `api.backend.coolify.cyberdynecorp.ai` and
the web application at `canon.backend.coolify.cyberdynecorp.ai`. Those are two
origins, so the browser will not hand the application a response from the API
unless the API says that page may have it — and a deployment that never says so
shows the application's unavailable state against a service whose `/readyz` is
green. That is the worst kind of outage to debug, which is why it is a suite.

Two answers, and no third:

* **a configured origin** is permitted, credentials included, for the methods
  and the two request headers this surface actually reads;
* **anything else** — a different host, a different scheme, a different port, or
  a deployment configured with no origins at all — is not answered at all. The
  browser then refuses the response, which is the correct outcome and not a
  failure of this service.

There is no wildcard and there is no way to configure one:
:func:`~cybercanon.adapters.wiring.configuration.origins` refuses `*` as a
malformed value, so a deployment cannot reach the permissive case by accident.
"""

from __future__ import annotations

import pytest
from http_world import PROJECT, TOKEN, a_surface

from cybercanon.adapters.inbound.http import cors
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.adapters.wiring.configuration import (
    WEB_ORIGINS,
    ConfigurationInvalid,
    origins,
)

pytestmark = pytest.mark.unit

APPLICATION = "https://canon.backend.coolify.cyberdynecorp.ai"
STAGING = "https://canon.pre.coolify.cyberdynecorp.ai"
STRANGER = "https://canon.example.invalid"

ASSETS = f"/{VERSION}/projects/{PROJECT}/assets"

ALLOW_ORIGIN = "access-control-allow-origin"
ALLOW_CREDENTIALS = "access-control-allow-credentials"
ALLOW_HEADERS = "access-control-allow-headers"
ALLOW_METHODS = "access-control-allow-methods"


def _bearer(origin: str) -> dict[str, str]:
    """The credential and the origin: what the application's own request carries."""
    return {"Authorization": f"Bearer {TOKEN}", "Origin": origin}


def _preflight(origin: str = APPLICATION, method: str = "GET") -> dict[str, str]:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "authorization",
    }


# --------------------------------------------------------------------------
# The configured origin
# --------------------------------------------------------------------------


def test_a_preflight_from_the_configured_web_origin_is_permitted() -> None:
    """The browser asks first, and this is the answer that lets the page proceed."""
    wired = a_surface(origins=(APPLICATION,))

    answered = wired.client.options(ASSETS, headers=_preflight())

    assert answered.status_code == 200, answered.text
    assert answered.headers[ALLOW_ORIGIN] == APPLICATION
    assert answered.headers[ALLOW_CREDENTIALS] == "true"
    assert "authorization" in answered.headers[ALLOW_HEADERS].lower()
    assert "GET" in answered.headers[ALLOW_METHODS]


def test_the_real_request_carries_the_permission_back() -> None:
    """A preflight nobody follows up on proves nothing; this is the request itself."""
    wired = a_surface(origins=(APPLICATION,))

    answered = wired.client.get(ASSETS, headers=_bearer(APPLICATION))

    assert answered.status_code == 200, answered.text
    assert answered.headers[ALLOW_ORIGIN] == APPLICATION


def test_several_environments_are_configured_as_several_origins() -> None:
    """Pre-production and production are two applications, not one wildcard."""
    wired = a_surface(origins=(APPLICATION, STAGING))

    for origin in (APPLICATION, STAGING):
        answered = wired.client.options(ASSETS, headers=_preflight(origin))

        assert answered.headers[ALLOW_ORIGIN] == origin


# --------------------------------------------------------------------------
# Everything else
# --------------------------------------------------------------------------


def test_a_preflight_from_an_unconfigured_origin_is_not_permitted() -> None:
    """The refusal is the *absence* of permission, which is what a browser reads."""
    wired = a_surface(origins=(APPLICATION,))

    answered = wired.client.options(ASSETS, headers=_preflight(STRANGER))

    assert ALLOW_ORIGIN not in answered.headers, answered.headers


def test_a_deployment_with_no_configured_origin_permits_none() -> None:
    """A service reached only by `canon` and the agent surface grants nothing."""
    wired = a_surface()

    answered = wired.client.options(ASSETS, headers=_preflight())

    assert ALLOW_ORIGIN not in answered.headers, answered.headers


def test_an_answer_to_a_permitted_origin_never_names_another_one() -> None:
    """The header echoes the asking origin, so one deployment cannot leak the list."""
    wired = a_surface(origins=(APPLICATION, STAGING))

    answered = wired.client.get(ASSETS, headers=_bearer(STAGING))

    assert answered.headers[ALLOW_ORIGIN] == STAGING
    assert APPLICATION not in answered.headers[ALLOW_ORIGIN]


# --------------------------------------------------------------------------
# The configuration itself
# --------------------------------------------------------------------------


def test_a_wildcard_origin_is_a_refused_configuration() -> None:
    """`*` cannot carry credentials and is the same in every environment."""
    with pytest.raises(ValueError):
        origins("*")


def test_a_list_is_read_in_order_and_de_duplicated() -> None:
    assert origins(f" {APPLICATION} , {STAGING},{APPLICATION} ") == (APPLICATION, STAGING)


def test_an_origin_without_a_scheme_is_refused() -> None:
    with pytest.raises((ValueError, ConfigurationInvalid)):
        origins("canon.backend.coolify.cyberdynecorp.ai")


def test_the_setting_is_optional_and_named_for_the_web_application() -> None:
    """Absent is a service nobody pointed a browser at, not a broken deployment."""
    assert WEB_ORIGINS == "CANON_WEB_ORIGINS"


def test_only_the_headers_this_surface_reads_are_permitted() -> None:
    """A fourth request header is a deliberate addition, not one that arrived."""
    assert cors.REQUEST_HEADERS == ("Authorization", "Idempotency-Key", "Content-Type")
