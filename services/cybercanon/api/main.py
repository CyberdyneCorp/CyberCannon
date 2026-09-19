"""The API deployable — read the configuration, build the app, serve it.

D11 again, one layer over: the composition root builds the adapters, the inbound
HTTP adapter translates requests, and this module is only the process entry
point. It is the one place that knows an environment and a port exist.

**Two things happen here and they happen in this order, deliberately.**

1. :func:`load` reads the configuration and refuses to start when a required
   variable is missing, naming all of them at once (task 1.4). A deployment that
   is misconfigured should fail at boot, loudly and completely, rather than at
   the first request that needed the variable nobody set.
2. :func:`~cybercanon.adapters.inbound.http.app.build_app` builds the
   application, which needs nothing reachable. *Unset configuration* and *an
   unreachable dependency* are different conditions with opposite handling: the
   first stops the process, the second must not stop a single request that does
   not need it, because `http-api` requires readiness to survive the identity
   service, the index and every sibling being down.

:func:`application` exists for the process manager that imports an app object
rather than calling a function, and takes the same path.
"""

from __future__ import annotations

from collections.abc import Mapping

import uvicorn
from fastapi import FastAPI

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.wiring.configuration import ServiceConfiguration, load

HOST = "0.0.0.0"
PORT = 8000


def application(environment: Mapping[str, str] | None = None) -> FastAPI:
    """The configured application, or a refusal naming everything that is missing."""
    return build_for(load(environment))


def build_for(configuration: ServiceConfiguration) -> FastAPI:
    """The application for an already-read configuration.

    Separate from :func:`application` so a test can hand in a configuration it
    built rather than one it had to put in the environment first, and so the
    boot-time refusal and the wiring are two things that can fail apart.

    **It builds no adapters yet, and that is this sprint's boundary rather than
    an omission.** The hosted working copy, the PostgreSQL index, the blob
    mirror and the identity adapter are groups 5 to 8 of this change; until they
    exist there is nothing to construct from the repository URL, the database
    URL or the issuer. The configuration is attached to the application so that
    those groups wire from the value this function already read and validated,
    rather than each reaching into the environment for itself.
    """
    app = build_app(container=None)
    app.state.configuration = configuration
    return app


def main(host: str = HOST, port: int = PORT) -> None:  # pragma: no cover — the server loop
    """Serve the API. The only place in this project that opens a port."""
    uvicorn.run(application(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    main()
