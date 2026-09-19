"""Tasks 2.2, 2.3 and 2.7 — the three endpoints, driven as a platform drives them.

D2 splits one word into three endpoints, and the split is the point:

* `/healthz` is the process saying it is running. It performs no input or output,
  which is checked by handing it an observer that raises on any access and
  asking it anyway;
* `/readyz` is the process saying it can serve its own requests. The model
  gateway and the identity provider being down leave it ready; a lost working
  copy does not; a lost index does not either, because git is the source of
  truth and the answers derivable from the working copy alone keep being served;
* `/status` is the operational detail, and it is the only one of the three that
  names a project — which is why it is the only one that is authenticated.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from http_world import (
    PROJECT,
    READER_TOKEN,
    STRANGER_TOKEN,
    TOKEN,
    a_surface,
    with_broken_index,
)

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.health import (
    ALIVE,
    DEGRADED_FIELD,
    DEPENDENCIES_FIELD,
    LIVE_PATH,
    NOT_READY,
    NOT_READY_IDENTIFIER,
    READY,
    READY_PATH,
    STATUS_FIELD,
)
from cybercanon.adapters.inbound.http.status import PROJECTS_FIELD, STATUS_PATH
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.application.use_cases.service_health import (
    IDENTITY_SERVICE,
    LANGUAGE_MODEL,
    SEARCH_INDEX,
    WORKING_COPY,
    available,
    unavailable,
)

OK = 200
UNAVAILABLE = 503
UNAUTHENTICATED = 401

SLOW = 1.0
"""What "within its normal response time" means for a handler that returns a dict."""


class Raising:
    """An observer that fails the way an unreachable dependency fails."""

    calls = 0

    def __call__(self) -> Any:
        Raising.calls += 1
        raise RuntimeError("every dependency of this service is unreachable")


# --------------------------------------------------------------------------
# 2.2 — liveness performs no input or output
# --------------------------------------------------------------------------


def test_liveness_answers_with_every_dependency_raising_on_access() -> None:
    wired = a_surface()
    client = TestClient(build_app(surface=_observing(wired, Raising())))

    started = time.monotonic()
    response = client.get(LIVE_PATH)

    assert response.status_code == OK
    assert response.json()[STATUS_FIELD] == ALIVE
    assert time.monotonic() - started < SLOW


def test_liveness_never_reaches_the_observer() -> None:
    """The mechanical half: the handler cannot have done I/O, because it asked nothing."""
    Raising.calls = 0
    wired = a_surface()
    client = TestClient(build_app(surface=_observing(wired, Raising())))

    response = client.get(LIVE_PATH)

    assert response.status_code == OK
    assert Raising.calls == 0


def test_liveness_names_no_project() -> None:
    wired = a_surface()

    assert PROJECT not in wired.client.get(LIVE_PATH).text


# --------------------------------------------------------------------------
# 2.3 — readiness depends only on what this service owns
# --------------------------------------------------------------------------


def test_readiness_is_ready_with_the_model_and_the_identity_provider_unreachable() -> None:
    wired = a_surface(
        dependencies=(
            available(WORKING_COPY),
            unavailable(LANGUAGE_MODEL, "connection refused"),
            unavailable(IDENTITY_SERVICE, "connection refused"),
        )
    )

    response = wired.client.get(READY_PATH)
    body = response.json()

    assert response.status_code == OK
    assert body[STATUS_FIELD] == READY
    assert sorted(body[DEGRADED_FIELD]) == sorted((LANGUAGE_MODEL, IDENTITY_SERVICE))


def test_readiness_is_ready_with_the_index_unreachable() -> None:
    """A lost index degrades search; git is still the source of truth."""
    wired = a_surface(dependencies=(available(WORKING_COPY), unavailable(SEARCH_INDEX, "down")))

    body = wired.client.get(READY_PATH).json()

    assert body[STATUS_FIELD] == READY
    assert body[DEGRADED_FIELD] == [SEARCH_INDEX]


def test_an_answer_derivable_from_the_working_copy_is_served_with_no_index() -> None:
    """The other half of the same requirement, asserted against a real read."""
    broken = with_broken_index(a_surface())

    response = broken.get(f"/{VERSION}/projects/{PROJECT}/briefing")

    assert response.status_code == OK


def test_readiness_is_withheld_when_the_working_copy_is_lost_and_names_it() -> None:
    wired = a_surface(dependencies=(unavailable(WORKING_COPY, "volume not mounted"),))

    response = wired.client.get(READY_PATH)
    body = response.json()

    assert response.status_code == UNAVAILABLE
    assert body[STATUS_FIELD] == NOT_READY
    assert body["error"]["id"] == NOT_READY_IDENTIFIER
    assert WORKING_COPY in body["error"]["message"]
    assert body["error"]["subject"] == WORKING_COPY


def test_readiness_describes_every_dependency_it_observed() -> None:
    wired = a_surface(
        dependencies=(available(WORKING_COPY), unavailable(LANGUAGE_MODEL, "connection refused"))
    )

    described = {
        one["name"]: one for one in wired.client.get(READY_PATH).json()[DEPENDENCIES_FIELD]
    }

    assert described[LANGUAGE_MODEL]["state"] == "unavailable"
    assert described[LANGUAGE_MODEL]["detail"] == "connection refused"
    assert described[LANGUAGE_MODEL]["reliance"] == "optional"
    assert described[WORKING_COPY]["reliance"] == "owned"


def test_readiness_names_no_project() -> None:
    wired = a_surface(dependencies=(available(WORKING_COPY),))

    assert PROJECT not in wired.client.get(READY_PATH).text


# --------------------------------------------------------------------------
# 2.7 — `/status` is authenticated; the other two are not
# --------------------------------------------------------------------------


def test_status_is_refused_without_a_credential() -> None:
    wired = a_surface()

    response = wired.client.get(STATUS_PATH)

    assert response.status_code == UNAUTHENTICATED
    assert PROJECT not in response.text


@pytest.mark.parametrize("path", (LIVE_PATH, READY_PATH))
def test_the_open_endpoints_need_no_credential(path: str) -> None:
    wired = a_surface(dependencies=(available(WORKING_COPY),))

    assert wired.client.get(path).status_code in (OK, UNAVAILABLE)


def test_status_reports_the_projects_this_caller_may_read() -> None:
    wired = a_surface()

    body = wired.get(STATUS_PATH, token=TOKEN).json()["data"]

    assert [one["project"] for one in body[PROJECTS_FIELD]] == [PROJECT]
    assert body[PROJECTS_FIELD][0]["working_copy"]["revision"]
    assert body[PROJECTS_FIELD][0]["index"]["in_sync"] is False


def test_status_names_no_project_the_caller_cannot_read() -> None:
    """A caller entitled to another project's canon sees none of this one."""
    wired = a_surface()

    body = wired.get(STATUS_PATH, token=STRANGER_TOKEN).json()["data"]

    assert body[PROJECTS_FIELD] == []


def test_status_reports_a_degraded_dependency_without_withholding_anything() -> None:
    wired = a_surface(
        dependencies=(available(WORKING_COPY), unavailable(LANGUAGE_MODEL, "connection refused"))
    )

    body = wired.get(STATUS_PATH, token=READER_TOKEN).json()["data"]

    assert body[STATUS_FIELD] == READY
    assert body[DEGRADED_FIELD] == [LANGUAGE_MODEL]


def _observing(wired: Any, observe: Any) -> Any:
    """The same surface, watching something that cannot be watched."""
    return replace(wired.surface, observe=observe)
