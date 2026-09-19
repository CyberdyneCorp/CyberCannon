"""The API deployable — read the configuration, build the app, serve it.

D11 again, one layer over: the composition root builds the adapters, the inbound
HTTP adapter translates requests, and this module is only the process entry
point. It is the one place that knows an environment and a port exist.

**Three things happen here and they happen in this order, deliberately.**

1. :func:`load` reads the configuration and refuses to start when a required
   variable is missing or malformed, naming all of them at once with the shape
   each malformed one was expected to have (`deployment-operations`). A
   deployment that is misconfigured should fail at boot, loudly and completely,
   rather than at the first request that needed the variable nobody set.
2. :func:`observed` turns that configuration into what the process can already
   say about its dependencies. The language model is the case the specification
   singles out: *"the model-dependent features SHALL report themselves
   unavailable"* when the switch is off, and the service starts anyway.
3. :func:`~cybercanon.adapters.inbound.http.app.build_app` builds the
   application, which needs nothing reachable. *Unset configuration* and *an
   unreachable dependency* are different conditions with opposite handling: the
   first stops the process, the second must not stop a single request that does
   not need it, because readiness must survive the identity service, the index
   and every sibling being down.

:func:`application` exists for the process manager that imports an app object
rather than calling a function, and takes the same path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import uvicorn
from fastapi import FastAPI

from cybercanon.adapters.inbound.http import logs
from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.surface import Surface
from cybercanon.adapters.wiring.configuration import ServiceConfiguration, load
from cybercanon.application.use_cases.service_health import (
    LANGUAGE_MODEL,
    ComponentStatus,
    available,
    unavailable,
)

HOST = "0.0.0.0"
PORT = 8000

MODEL_CONFIGURED = "the configured endpoint is reachable from this deployment"


def application(environment: Mapping[str, str] | None = None) -> FastAPI:
    """The configured application, or a refusal naming everything that is wrong."""
    return build_for(load(environment))


def build_for(configuration: ServiceConfiguration) -> FastAPI:
    """The application for an already-read configuration.

    Separate from :func:`application` so a test can hand in a configuration it
    built rather than one it had to put in the environment first, and so the
    boot-time refusal and the wiring are two things that can fail apart.

    **It builds no outbound adapters yet, and that is this group's boundary
    rather than an omission.** The hosted working copy, the PostgreSQL index and
    the blob mirror are wired by groups 5 to 8 of `add-coolify-deployment`,
    which is also where their observations join :func:`observed`. What exists
    now is the seam: one function turning configuration into
    :class:`~cybercanon.application.use_cases.service_health.ComponentStatus`
    values, and a readiness signal that classifies them rather than probing
    anything itself.
    """
    logs.configure()
    app = build_app(container=None, surface=Surface(observe=lambda: observed(configuration)))
    app.state.configuration = configuration
    return app


def observed(configuration: ServiceConfiguration) -> Sequence[ComponentStatus]:
    """What this process can say about its dependencies from configuration alone.

    Only the model, for now, and only because its absence is a *configured*
    state rather than an unreachable one: a master switch that is off is a
    feature deliberately not deployed, and the status surface says so in the
    same vocabulary it would use for a gateway that stopped answering. Claiming
    anything about a component this process has not wired would be a health
    report that reports nothing.
    """
    model = configuration.model
    if model.available:
        return (available(LANGUAGE_MODEL, MODEL_CONFIGURED),)
    return (unavailable(LANGUAGE_MODEL, model.absence),)


def main(host: str = HOST, port: int = PORT) -> None:  # pragma: no cover — the server loop
    """Serve the API. The only place in this project that opens a port."""
    uvicorn.run(application(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    main()
