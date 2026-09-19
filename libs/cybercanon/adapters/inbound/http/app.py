"""The FastAPI application — the third inbound adapter, and the thinnest.

This is where the product's founding rule gets its hardest test. The pre-commit
validator an artist runs, the `validate_export` a Blender agent calls and the
"Validate" button in a browser are the **same use case**, and if this module
ever decides something the other two do not, the disagreement is visible to
artists and the trust the validator exists to create is gone. So the adapter is
shaped so that there is nothing here to disagree with, and two tests enforce the
shape rather than trusting it:

* `tests/tooling/test_http_adapter_is_a_translator.py` — no conditional on
  specification content, and no import of an outbound adapter, asserted over the
  syntax tree;
* the import-linter contract named for this package, which fails the build on
  the import a copy would need.

**Group 1 builds the skeleton and the health endpoint, and nothing else.** The
versioned surface, the outcome-to-status mapping, pagination, idempotency and
every read endpoint are group 9 of this change. What is here is what task 1.1
asks for: a service that a clean checkout can serve with **no database, no
identity service and no repository configured**, because that is the property
`http-api` requires of readiness and the one a deployment depends on — *"a
degraded dependency is visible without withholding traffic"*.

The application is therefore built with no ports at all by default. A container
arrives later, through :func:`build_app`, and its absence is not an error: a
process that refused to start without a repository would turn one project's
misconfiguration into a total outage.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from cybercanon.adapters.inbound.http import health
from cybercanon.adapters.wiring.container import Container

TITLE = "CyberCanon"
SUMMARY = "The canon of a game project, over HTTP."

DESCRIPTION = """\
The HTTP surface over the same use cases the `canon` command line and the local
agent server call. It holds no validation, compilation or lookup logic of its
own: a verdict here is the verdict `canon validate` gives, because it is the
same function.
"""


def build_app(container: Container | None = None, **options: Any) -> FastAPI:
    """The application, optionally wired to a container.

    The container is a parameter and it is optional, for two different reasons.
    A parameter, because that is what makes the surface exercisable against
    in-memory fakes with no repository on disk — the same decision the command
    line and the agent server made. Optional, because readiness must not depend
    on a repository, an index or an identity service being reachable, and a
    factory that required one would make that impossible to even express.
    """
    app = FastAPI(title=TITLE, summary=SUMMARY, description=DESCRIPTION, **options)
    app.state.container = container
    health.register(app)
    return app


__all__ = ["DESCRIPTION", "SUMMARY", "TITLE", "build_app"]
