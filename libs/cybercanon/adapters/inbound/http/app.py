"""The FastAPI application — the third inbound adapter, and the thinnest.

This is where the product's founding rule gets its hardest test. The pre-commit
validator an artist runs, the `validate_export` a Blender agent calls and the
"Validate" button in a browser are the **same use case**, and if this module
ever decides something the other two do not, the disagreement is visible to
artists and the trust the validator exists to create is gone. So the adapter is
shaped so that there is nothing here to disagree with, and three tests enforce
the shape rather than trusting it:

* `tests/tooling/test_http_adapter_is_a_translator.py` — no conditional on
  specification content, and no import of an outbound adapter, asserted over the
  syntax tree; and no route handler that catches an exception or writes a status
  code, which is D10's single-mapping rule made structural;
* the import-linter contract named for this package, which fails the build on
  the import a copy would need.

**What is assembled here, and in what order.** The application is built with no
ports at all by default, because readiness must not depend on a repository, an
index or an identity service being reachable — a process that refused to start
without a repository would turn one project's misconfiguration into a total
outage. Everything else is registered over the :class:`Surface` the composition
root hands in:

1. the generic-failure middleware, so that anything the domain did not express
   becomes a correlation identifier rather than a stack trace (task 9.4);
2. liveness and readiness, which reach for nothing;
3. the repository notification endpoint, when this deployment has a secret;
4. the versioned read and write surfaces;
5. the catch-all that refuses an address carrying no surface version — last,
   because it must only ever see what nothing else matched.

The generated interface description is FastAPI's own, produced from the routes
registered above and from nothing else (task 9.10): there is no hand-maintained
document to fall out of date, which is the only way *"produced from the
implemented endpoints"* is checkable rather than aspirational.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from cybercanon.adapters.inbound.http import health, outcomes, reads, versioning, webhooks, writes
from cybercanon.adapters.inbound.http.surface import Surface
from cybercanon.adapters.inbound.http.webhooks import RepositoryNotifications
from cybercanon.adapters.wiring.container import Container

TITLE = "CyberCanon"
SUMMARY = "The canon of a game project, over HTTP."

INTERFACE_PATH = "/openapi.json"
"""Where the generated interface description is published (task 9.10).

Outside the versioned prefix on purpose: it is how a client discovers which
versions are served, so it cannot itself live inside one of them.
"""

DESCRIPTION = """\
The HTTP surface over the same use cases the `canon` command line and the local
agent server call. It holds no validation, compilation or lookup logic of its
own: a verdict here is the verdict `canon validate` gives, because it is the
same function.

Every resource is addressed as `/{version}/projects/{project}/...` by the
identifier the specification already uses. Every failure carries a stable
identifier, a message and the subject at fault. Every listing pages with an
opaque continuation token that grants nothing.
"""


def build_app(
    container: Container | None = None,
    *,
    notifications: RepositoryNotifications | None = None,
    surface: Surface | None = None,
    **options: Any,
) -> FastAPI:
    """The application, optionally wired to a surface.

    `surface` is the wiring the versioned routers run over — the projects this
    deployment serves, the identity provider, the idempotency store and whatever
    the process can currently observe. It is optional for the same reason the
    container is: readiness must be answerable by a process that has been given
    nothing, and a factory that required a project would make that impossible to
    even express.

    `container` is kept as a parameter for the surfaces built before the
    versioned routers existed; a container with no project name of its own is
    served under its configured project by the composition root, never invented
    here.
    """
    wiring = surface or Surface()
    app = FastAPI(
        title=TITLE,
        summary=SUMMARY,
        description=DESCRIPTION,
        version=versioning.VERSION,
        openapi_url=INTERFACE_PATH,
        **options,
    )
    app.state.container = container
    app.state.surface = wiring
    outcomes.register(app, version=versioning.VERSION)
    health.register(app, wiring.observe)
    webhooks.register(app, notifications)
    reads.register(app, wiring)
    writes.register(app, wiring)
    versioning.register(app)
    return app


__all__ = ["DESCRIPTION", "INTERFACE_PATH", "SUMMARY", "TITLE", "build_app"]
