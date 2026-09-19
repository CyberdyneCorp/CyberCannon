"""`/status` — the operational detail, authenticated, and never a gate (D2).

Two questions actually get asked about a deployment of this shape, and both are
about freshness rather than about health: *is the index stale?* and *when did
the working copy last fetch?* `deployment-operations` requires both to be
answerable *"without a shell session inside a container"*, which is what this
endpoint is for.

It is deliberately the opposite of `/readyz` in every respect:

* **it is authenticated**, because it names projects, and `/healthz` and
  `/readyz` stay open precisely because they name nothing. A caller sees the
  projects it is entitled to read and no others — the same
  :func:`~cybercanon.domain.policy.decide` every read goes through, over the
  same actor;
* **it gates nothing.** A component reported unavailable here has already been
  classified by
  :mod:`~cybercanon.application.use_cases.service_health`; the model gateway
  being down appears as a degraded feature and is invisible to the platform's
  routing decision;
* **it describes, and computes nothing of its own.** The five facts per project
  are
  :func:`~cybercanon.application.use_cases.deployment_status.describe_project`'s,
  rendered here and decided there.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import health, outcomes
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.application.results import Ok, Result
from cybercanon.application.use_cases.deployment_status import (
    FetchAttempt,
    IndexFreshness,
    ProjectReport,
    WorkingCopyStatus,
    describe_project,
)
from cybercanon.application.use_cases.service_health import describe_service_health
from cybercanon.domain.policy import Operation

STATUS_PATH = "/status"
"""Unversioned on purpose: it describes the deployment, not the surface."""

PROJECTS_FIELD = "projects"


def register(app: FastAPI, surface: wiring.Surface, *, version: str = "") -> None:
    """Mount the operational surface. One endpoint, one use case per project."""

    @app.get(STATUS_PATH, tags=[health.HEALTH_TAG])
    async def read_status(request: Request) -> JSONResponse:
        """What this instance can see, and where each project's copy and index are."""
        return outcomes.respond(reported(surface, request), version=version)


def reported(surface: wiring.Surface, request: Request) -> Result[dict[str, Any]]:
    """The report, or the refusal that says why this caller cannot have it."""
    actor = wiring.acting(surface, request)
    if not isinstance(actor, Ok):
        return actor
    health_of = describe_service_health(surface.observe())
    return Ok(
        {
            **health.reported(health_of),
            PROJECTS_FIELD: [
                rendered(
                    describe_project(
                        name, repository_host=hosted.repository_host, journal=surface.journal
                    )
                )
                for name, hosted in sorted(surface.projects.items())
                if wiring.permitted(
                    actor.value.actor, Operation.READ_PROJECT, wiring.subject_for(name)
                )
                is None
            ],
        }
    )


def rendered(report: ProjectReport) -> dict[str, Any]:
    """One project's five facts, as the fields an operator reads."""
    return {
        "project": report.project,
        "working_copy": working_copy(report.working_copy),
        "index": index(report.index),
    }


def working_copy(copy: WorkingCopyStatus) -> dict[str, Any]:
    """Where the copy is, when it was last confirmed, and what the last try did."""
    return {
        "state": str(copy.state),
        "revision": copy.revision,
        "last_fetch_at": moment(copy.last_fetch_at),
        "last_attempt": attempt(copy.attempt),
        "reason": copy.reason,
    }


def attempt(latest: FetchAttempt | None) -> dict[str, Any] | None:
    """The most recent fetch attempt, separately from the last successful one."""
    if latest is None:
        return None
    return {
        "at": moment(latest.at),
        "outcome": latest.outcome,
        "reason": latest.reason,
    }


def index(freshness: IndexFreshness) -> dict[str, Any]:
    """Both revisions, always — "stale" with nothing to compare is unactionable."""
    return {
        "indexed_revision": freshness.indexed_revision,
        "working_copy_revision": freshness.working_copy_revision,
        "in_sync": freshness.in_sync,
        "rebuilding": freshness.rebuilding,
    }


def moment(when: datetime | None) -> str | None:
    return None if when is None else when.isoformat()


__all__ = [
    "PROJECTS_FIELD",
    "STATUS_PATH",
    "attempt",
    "index",
    "moment",
    "register",
    "rendered",
    "reported",
    "working_copy",
]
