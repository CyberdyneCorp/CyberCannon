"""Liveness and readiness — answerable with nothing else running (task 9.9).

**This capability owns neither signal.** `http-api` says so explicitly: the
surface *"SHALL expose the liveness and readiness signals specified by the
`deployment-operations` capability, which owns their shape and semantics; this
capability SHALL NOT define a separate or additional health surface."* So there
are two endpoints here and there will never be a third, and what they mean is
read from that capability rather than decided here.

What `http-api` does add is a constraint on readiness, stated negatively, which
is the useful direction: it *"SHALL NOT require a language model endpoint, the
identity service, the document platform, the rebuildable index, or any sibling
backend to be reachable, and SHALL separately describe the state of each
dependency it observes, so that a degraded dependency is visible without
withholding traffic."*

Those are two claims and this module keeps them apart:

* **the answer** does not depend on anything being reachable. Readiness reports
  the process, and the process is ready as soon as it is running;
* **the description** lists what the composition root observed, each dependency
  named with its state. Describing a dependency requires observing one, which is
  why :class:`~cybercanon.adapters.inbound.http.surface.Dependency` values are
  handed in rather than probed here — an inbound adapter that reached out to
  check a model endpoint would be an inbound adapter doing I/O against an
  outbound one.

**Which dependency may withhold traffic is not decided here.** `deployment-operations`
requires a lost working copy to report not-ready and a lost index not to; that is
its call to make, in its own change, over the same descriptions this already
produces.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from cybercanon.adapters.inbound.http.surface import Observe, observes_nothing

LIVE_PATH = "/health/live"
READY_PATH = "/health/ready"

ALIVE = "alive"
READY = "ready"

HEALTH_TAG = "health"

STATUS_FIELD = "status"
DEPENDENCIES_FIELD = "dependencies"

LANGUAGE_MODEL = "language_model"
DOCUMENT_PLATFORM = "document_platform"
IDENTITY_SERVICE = "identity_service"
SEARCH_INDEX = "search_index"
OBJECT_STORE = "object_store"
WORKING_COPY = "working_copy"
"""The names a dependency is described under, so two deployments agree on them.

Constants rather than free strings because the description is read by an
operator and by `deployment-operations`' status surface, and a name that drifted
between two releases would silently stop matching whatever reads it.
"""


def register(app: FastAPI, observe: Observe = observes_nothing) -> None:
    """Add the two signals. Liveness asks nothing; readiness asks nothing either."""

    @app.get(LIVE_PATH, tags=[HEALTH_TAG])
    def live() -> dict[str, str]:
        """Whether this process is running. It performs no input or output."""
        return {STATUS_FIELD: ALIVE}

    @app.get(READY_PATH, tags=[HEALTH_TAG])
    def ready() -> dict[str, Any]:
        """Whether this process can serve requests, and what it can currently see.

        It can, as soon as it is running. Every dependency this surface has is
        either optional or per project, and a process that withheld traffic
        because one project's remote was unreachable would take down the
        projects that are fine.
        """
        return {STATUS_FIELD: READY, DEPENDENCIES_FIELD: [described(one) for one in observe()]}


def described(dependency: Any) -> dict[str, str]:
    """One observation, as the three fields an operator reads."""
    return {
        "name": dependency.name,
        "state": dependency.state,
        "detail": dependency.detail,
    }


__all__ = [
    "ALIVE",
    "DEPENDENCIES_FIELD",
    "DOCUMENT_PLATFORM",
    "HEALTH_TAG",
    "IDENTITY_SERVICE",
    "LANGUAGE_MODEL",
    "LIVE_PATH",
    "OBJECT_STORE",
    "READY",
    "READY_PATH",
    "SEARCH_INDEX",
    "STATUS_FIELD",
    "WORKING_COPY",
    "described",
    "register",
]
