"""Liveness and readiness — answerable with nothing else running.

`http-api` states the rule and states it negatively, which is the useful
direction: readiness *"SHALL NOT require a language model endpoint, the identity
service, the document platform, the rebuildable index, or any sibling backend to
be reachable"*. `project.md` says the same thing from the deployment side: a
health endpoint that needed a sibling would turn one dependency's outage into a
failed deploy.

So this module reaches for nothing. It reports that the process can serve
requests, and it answers the same way whether the identity service is down, the
language model is unconfigured and no repository has ever been cloned.

**What is deliberately not here yet.** `http-api` also requires readiness to
*"separately describe the state of each dependency it observes"*, and
`deployment-operations` owns the shape of the signals. Both are group 9 of this
change (task 9.9) and sprint S10's deployment work; describing a dependency
requires observing one, and this sprint's scope is the skeleton. The endpoint
below is the part task 1.1 asks for and nothing more, so that what arrives later
extends a working answer rather than replacing a guess.
"""

from __future__ import annotations

from fastapi import FastAPI

LIVE_PATH = "/health/live"
READY_PATH = "/health/ready"

ALIVE = "alive"
READY = "ready"

HEALTH_TAG = "health"


def register(app: FastAPI) -> None:
    """Add the two signals to an application. The only thing group 1 registers."""

    @app.get(LIVE_PATH, tags=[HEALTH_TAG])
    def live() -> dict[str, str]:
        """Whether this process is running. It asks nothing of anything else."""
        return {"status": ALIVE}

    @app.get(READY_PATH, tags=[HEALTH_TAG])
    def ready() -> dict[str, str]:
        """Whether this process can serve requests.

        It can, as soon as it is running. Every dependency this surface has is
        either optional or per project, and a process that withheld traffic
        because one project's remote was unreachable would take down the
        projects that are fine.
        """
        return {"status": READY}


__all__ = ["ALIVE", "HEALTH_TAG", "LIVE_PATH", "READY", "READY_PATH", "register"]
