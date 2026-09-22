"""Cross-origin access: a configured list of origins, and never a wildcard.

`deploy/coolify.yaml` puts the API at `api.backend.coolify.cyberdynecorp.ai` and
the web application at `canon.backend.coolify.cyberdynecorp.ai`. Those are two
origins, so every request the application makes is one the browser will only
hand back to the page if this service says the page may have it. Without that
permission the application shows its unavailable state against a service that is
answering perfectly — which is the worst shape of outage, because `/readyz` is
green and nothing in the logs is an error.

Three decisions, and each of them narrows rather than widens:

* **Configured, never `*`.** The origins are read from `CANON_WEB_ORIGINS`
  (:func:`~cybercanon.adapters.wiring.configuration.origins` refuses a
  wildcard), so pre-production and production permit different applications and
  a deployment nobody told about a browser permits none. A wildcard would also
  be useless here: this surface authenticates with a bearer credential, and the
  browser refuses to send credentials to a wildcard origin at all.
* **An unconfigured deployment sends no permission.** An empty list registers no
  middleware, so a service reached only by `canon` and the agent surface is
  unchanged — a preflight is answered by the router, which has no handler for it,
  rather than by a permissive default.
* **The methods and headers are this surface's own.** The two headers a caller
  may send are the ones
  :mod:`~cybercanon.adapters.inbound.http.surface` reads — `Authorization` and
  `Idempotency-Key` — plus `Content-Type` for a body. Listing them is what makes
  a fourth header a deliberate addition rather than something that arrived.

This is deliberately *not* a spec requirement: no capability in
`openspec/changes/*/specs` mentions cross-origin access. It is a property of the
deployment topology `deployment-operations` fixes, and it is here because the
first browser to load the application discovers it otherwise.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "OPTIONS")
"""Every method this surface serves. A method absent here is not preflighted."""

REQUEST_HEADERS: tuple[str, ...] = ("Authorization", "Idempotency-Key", "Content-Type")
"""The headers a browser may send: the credential, the write's key, and a body's type."""

RESPONSE_HEADERS: tuple[str, ...] = ("Content-Type",)
"""What a page may read back. The envelope is the body; nothing is in a header."""

PREFLIGHT_MAX_AGE_S = 600
"""How long a browser may cache one preflight. Ten minutes, so a changed
configuration takes effect inside a coffee break rather than inside a session."""


def register(app: FastAPI, origins: Sequence[str] = ()) -> None:
    """Permit these origins, or register nothing at all.

    Called by :func:`~cybercanon.adapters.inbound.http.app.build_app` with what
    the composition root read. The empty case returns without touching the
    application, which is what keeps *"a deployment that was not told about a
    browser grants nothing"* structural rather than a value somebody could set
    to `*`.
    """
    permitted = tuple(dict.fromkeys(origin for origin in origins if origin))
    if not permitted:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(permitted),
        allow_credentials=True,
        allow_methods=list(METHODS),
        allow_headers=list(REQUEST_HEADERS),
        expose_headers=list(RESPONSE_HEADERS),
        max_age=PREFLIGHT_MAX_AGE_S,
    )


__all__ = [
    "METHODS",
    "PREFLIGHT_MAX_AGE_S",
    "REQUEST_HEADERS",
    "RESPONSE_HEADERS",
    "register",
]
