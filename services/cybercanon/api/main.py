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
from cybercanon.adapters.wiring.identity import WiredIdentity, identity_provider
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

    **Nothing built here reaches anything.** The identity provider is
    constructed with its key cache bounded by the configured TTL (D8) and
    retrieves nothing until a credential asks it to; the per-project working
    copy, the index and the blob mirror are attached to the surface by the
    deployment's own entry point once its volumes are mounted. A boot that
    needed a dependency to be up would be the cascade this change exists to
    prevent, so construction and reachability stay two different questions —
    which is also why :func:`observed` reports rather than probes.
    """
    logs.configure()
    identity = identity_provider(configuration.identity)
    surface = Surface(
        identity_provider=identity.provider,
        observe=lambda: observed(configuration, identity),
    )
    app = build_app(container=None, surface=surface)
    app.state.configuration = configuration
    app.state.identity = identity
    return app


def observed(
    configuration: ServiceConfiguration, identity: WiredIdentity | None = None
) -> Sequence[ComponentStatus]:
    """What this process can say about its dependencies, without going to ask.

    Two components answer from what this process already knows. The model's
    absence is a *configured* state rather than an unreachable one — a master
    switch that is off is a feature deliberately not deployed, and the status
    surface says so in the same vocabulary it would use for a gateway that
    stopped answering. The identity service's is the outcome of the last
    retrieval anybody drove (D8): unreachable is *reported*, never gated, so an
    outage of CyberdyneAuth costs new sign-ins and nothing else.

    Claiming anything about a component this process has not wired would be a
    health report that reports nothing, which is why the volumes' observations
    join this list where they are mounted rather than being guessed at here.
    """
    return _model(configuration) + _identity(identity)


def _model(configuration: ServiceConfiguration) -> tuple[ComponentStatus, ...]:
    model = configuration.model
    if model.available:
        return (available(LANGUAGE_MODEL, MODEL_CONFIGURED),)
    return (unavailable(LANGUAGE_MODEL, model.absence),)


def _identity(identity: WiredIdentity | None) -> tuple[ComponentStatus, ...]:
    return () if identity is None else (identity.status,)


def main(host: str = HOST, port: int = PORT) -> None:  # pragma: no cover — the server loop
    """Serve the API. The only place in this project that opens a port."""
    uvicorn.run(application(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover — exercised as a subprocess
    main()
