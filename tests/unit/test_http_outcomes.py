"""Tasks 9.2 to 9.4 — one mapping, one error shape, and one place exceptions stop.

The three claims this file checks are the three `http-api` makes about failure,
and each is checked in the way that would catch the drift it is about:

* **exhaustiveness** — every member of the outcome vocabulary has a status, and
  the assertion is written against :class:`FailureKind` itself rather than a
  list, so adding a kind fails here before it reaches a router;
* **sameness** — two different outcomes of the same kind produce the same status
  and the same body shape, because they go through one function;
* **silence** — an unexpected exception produces a correlation identifier and
  nothing else. Not the exception's message, not its type, not a path.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cybercanon.adapters.inbound.http import outcomes
from cybercanon.application.errors import FailureKind
from cybercanon.application.results import (
    REFUSALS,
    Conflict,
    Forbidden,
    Invalid,
    NotFound,
    Ok,
    Unauthenticated,
    Unavailable,
)

VERSION = "v1"

SECRET_PATH = "/srv/canon/working-copies/cyberdyne-game"
CONNECTION_STRING = "postgresql://canon:hunter2@db.internal:5432/canon"


def test_every_failure_kind_has_exactly_one_status() -> None:
    """D10's whole claim: *one test asserts every member of the union has a mapping*."""
    assert set(outcomes.STATUSES) == set(FailureKind)
    assert len(set(outcomes.STATUSES.values())) == len(FailureKind)


def test_every_member_of_the_result_union_maps_to_a_status() -> None:
    """The union, not the enum: the two are kept in step by `REFUSALS`."""
    for kind, member in REFUSALS.items():
        refusal = member(identifier=f"{kind}.example", message="because", subject="thing")

        assert outcomes.status_for(refusal) == outcomes.STATUSES[kind]


def test_a_successful_outcome_is_two_hundred() -> None:
    assert outcomes.status_for(Ok("anything")) == outcomes.OK_STATUS


@pytest.mark.parametrize(
    ("refusal", "status"),
    [
        (NotFound(identifier="asset.unknown", message="no such asset"), 404),
        (Forbidden(identifier="policy.refused", message="ART_DIRECTOR required"), 403),
        (Unauthenticated(identifier="auth.credential_missing", message="sign in"), 401),
        (Invalid(identifier="lens.unknown", message="no such lens"), 400),
        (Conflict(identifier="edit.conflict", message="it moved"), 409),
        (Unavailable(identifier="index.unavailable", message="still building"), 503),
    ],
)
def test_the_six_refusals_map_to_the_six_status_classes(refusal, status: int) -> None:
    """The table as a person reads it, so a change to it is visible in review."""
    assert outcomes.status_for(refusal) == status


def test_a_refusal_never_maps_to_an_internal_failure() -> None:
    """`http-api`: an outcome the domain expressed is not an unexpected failure.

    `UNAVAILABLE` is the one refusal in the server-error range, and 503 rather
    than 500 is exactly the distinction: *a precondition outside the caller's
    control is unmet — for now* is retryable and was not caused by the caller,
    which is a different sentence from *something here broke*.
    """
    assert outcomes.INTERNAL_STATUS not in set(outcomes.STATUSES.values())


def test_the_error_body_carries_identifier_message_and_subject() -> None:
    """The three fields `http-api` enumerates, and the subject may be absent."""
    body = outcomes.error_body(
        NotFound(identifier="asset.unknown", message="no such asset", subject="mech_scout"),
        version=VERSION,
        correlation_id="abc",
    )

    assert body[outcomes.ERROR_FIELD] == {
        "id": "asset.unknown",
        "message": "no such asset",
        "subject": "mech_scout",
    }
    assert body[outcomes.VERSION_FIELD] == VERSION
    assert body[outcomes.CORRELATION_FIELD] == "abc"


def test_a_subject_less_refusal_still_has_the_field() -> None:
    """One shape, so a client reads `subject` rather than checking for it."""
    body = outcomes.error_body(
        Invalid(identifier="page.token_unreadable", message="not ours"),
        version=VERSION,
        correlation_id="abc",
    )

    assert body[outcomes.ERROR_FIELD]["subject"] is None


def test_two_different_outcomes_of_one_kind_share_status_and_shape() -> None:
    """The requirement in its own words: *the same outcome maps identically everywhere*."""
    first = outcomes.respond(NotFound(identifier="asset.unknown", message="a"), version=VERSION)
    second = outcomes.respond(NotFound(identifier="project.unknown", message="b"), version=VERSION)

    assert first.status_code == second.status_code
    assert first.body and second.body
    assert set(_json(first)) == set(_json(second))
    assert set(_json(first)[outcomes.ERROR_FIELD]) == {"id", "message", "subject"}


def test_a_correlation_identifier_is_unique_per_response() -> None:
    assert outcomes.correlation() != outcomes.correlation()


def test_a_generic_failure_describes_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """No stack trace, no path, no connection string — and no exception message."""
    app = FastAPI()
    outcomes.register(app, version=VERSION)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError(f"cannot open {SECRET_PATH} using {CONNECTION_STRING}")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    body = response.text

    assert response.status_code == outcomes.INTERNAL_STATUS
    assert response.json()[outcomes.ERROR_FIELD]["id"] == outcomes.INTERNAL_IDENTIFIER
    assert response.json()[outcomes.CORRELATION_FIELD]
    assert SECRET_PATH not in body
    assert CONNECTION_STRING not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body


def test_the_correlation_identifier_is_also_a_header() -> None:
    """So a person quoting one from a log line can find the response it belongs to."""
    response = outcomes.respond(Ok({"a": 1}), version=VERSION)

    assert response.headers[outcomes.CORRELATION_HEADER]


def _json(response) -> dict:
    import json

    return json.loads(response.body)
