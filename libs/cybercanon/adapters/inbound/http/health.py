"""Liveness and readiness — two endpoints, two different questions (D2).

**This capability owns neither signal.** `http-api` says so explicitly: the
surface *"SHALL expose the liveness and readiness signals specified by the
`deployment-operations` capability, which owns their shape and semantics; this
capability SHALL NOT define a separate or additional health surface."* So there
are two endpoints here and there will never be a third, and what they mean is
read from that capability rather than decided here.

D2 fixes the shape: `/healthz` returns a constant and touches nothing, `/readyz`
reports whether this process can serve its own requests, and the operational
detail — which project is at which revision, whether the index is stale — lives
on `/status`, which is authenticated and is a different module. Splitting
visibility from gating is structural rather than a matter of discipline:
whatever a single aggregated endpoint checks becomes a deploy blocker, and
somebody always adds the model gateway to it "for visibility".

Two claims, kept apart:

* **liveness** is answered without reading anything at all. Not the observations,
  not the configuration, not a dependency: a process that had to consult
  something to say it was running would be reporting that thing's health under
  the name of its own;
* **readiness** is
  :func:`~cybercanon.application.use_cases.service_health.describe_service_health`'s
  answer, and the classification behind it is that use case's. A lost working
  copy withholds traffic; a lost index does not, because git is the source of
  truth and *"answers derivable from the working copy alone SHALL continue to be
  served"*. That decision is in the application layer where it can be tested
  with nothing running, and this module renders it.

Observations are handed in rather than probed here, for the reason the layering
contract exists: an inbound adapter that reached out to check a model endpoint
would be an inbound adapter doing I/O against an outbound one.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import outcomes
from cybercanon.adapters.inbound.http.surface import Observe, observes_nothing
from cybercanon.application.results import Ok, Result, Unavailable
from cybercanon.application.use_cases.service_health import (
    DOCUMENT_PLATFORM,
    IDENTITY_SERVICE,
    LANGUAGE_MODEL,
    OBJECT_STORE,
    SEARCH_INDEX,
    WORKING_COPY,
    ComponentStatus,
    ServiceHealth,
    describe_service_health,
)

LIVE_PATH = "/healthz"
READY_PATH = "/readyz"
"""D2's names. The platform's liveness probe reads the first and its routing
gate reads the second, which is what makes "not ready" withhold traffic without
restarting anything.
"""

ALIVE = "alive"
READY = "ready"
NOT_READY = "not_ready"

HEALTH_TAG = "health"

STATUS_FIELD = "status"
DEPENDENCIES_FIELD = "dependencies"
DEGRADED_FIELD = "degraded"

NOT_READY_IDENTIFIER = "readiness.withheld"


def register(app: FastAPI, observe: Observe = observes_nothing, *, version: str = "") -> None:
    """Add the two signals. Liveness asks nothing; readiness asks only what is owned."""

    @app.get(LIVE_PATH, tags=[HEALTH_TAG])
    def live() -> dict[str, str]:
        """Whether this process is running. It performs no input or output.

        It does not call `observe`, which is the whole of *"the liveness signal
        SHALL NOT perform input or output against any dependency"*: there is
        nothing in this function that could.
        """
        return {STATUS_FIELD: ALIVE}

    @app.get(READY_PATH, tags=[HEALTH_TAG])
    def ready() -> JSONResponse:
        """Whether this process can serve requests, and what it can currently see.

        The answer carries no project, no revision and no configuration value:
        `/readyz` is open, so everything it says is said to anybody.
        """
        health = describe_service_health(observe())
        return outcomes.respond(readiness(health), version=version, extra=reported(health))


def readiness(health: ServiceHealth) -> Result[None]:
    """Ready, or the one refusal that names what is withholding traffic.

    An `Unavailable` rather than a status code written here: it travels through
    the same mapping every other outcome does (D10), so readiness cannot come to
    disagree with the rest of the surface about what 503 means.
    """
    if health.ready:
        return Ok(None)
    withheld = ", ".join(health.withholding)
    return Unavailable(
        identifier=NOT_READY_IDENTIFIER,
        message=f"this instance cannot serve requests: {withheld} is unavailable",
        subject=withheld,
    )


def reported(health: ServiceHealth) -> dict[str, object]:
    """The body both answers carry: the state, and what was observed."""
    return {
        STATUS_FIELD: READY if health.ready else NOT_READY,
        DEPENDENCIES_FIELD: [described(one) for one in health.components],
        DEGRADED_FIELD: list(health.degraded),
    }


def described(dependency: ComponentStatus) -> dict[str, str]:
    """One observation, as the fields an operator reads."""
    return {
        "name": dependency.name,
        "state": dependency.state,
        "detail": dependency.detail,
        "reliance": str(dependency.relied_on),
    }


__all__ = [
    "ALIVE",
    "DEGRADED_FIELD",
    "DEPENDENCIES_FIELD",
    "DOCUMENT_PLATFORM",
    "HEALTH_TAG",
    "IDENTITY_SERVICE",
    "LANGUAGE_MODEL",
    "LIVE_PATH",
    "NOT_READY",
    "NOT_READY_IDENTIFIER",
    "OBJECT_STORE",
    "READY",
    "READY_PATH",
    "SEARCH_INDEX",
    "STATUS_FIELD",
    "WORKING_COPY",
    "described",
    "readiness",
    "register",
    "reported",
]
