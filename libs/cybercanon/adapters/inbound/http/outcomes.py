"""The single seam: one outcome vocabulary, one set of status codes (D10).

`http-api` states the requirement twice, from both ends. *"Each outcome the
domain can express ... SHALL map to exactly one status class, through one
mapping used by every endpoint"*, and *"An outcome the domain expressed SHALL
NOT be reported as an unexpected internal failure."* D10 explains why it is one
function rather than a habit:

> *"A per-router `try/except` satisfies that on the day it is written and stops
> doing so at the fourth endpoint. A single mapping is exhaustively testable —
> one test asserts every member of the union has a mapping."*

So this module owns three things and no router owns any of them:

* :data:`STATUSES` — :class:`~cybercanon.application.errors.FailureKind` to
  status code, one entry each, asserted exhaustive by
  `tests/unit/test_http_outcomes.py`;
* :func:`respond` — the only place in the HTTP adapter that builds a response
  with a status code on it. A router calls it and returns what it gets;
* :func:`unexpected` — the middleware for everything the domain did *not*
  express. It is the only `except` in the package, and what it produces is a
  generic failure carrying a correlation identifier and nothing else: no stack
  trace, no path, no connection string, no configuration value.

The envelope is deliberately an open map. The surface evolves additively within
a version (`http-api`), so a client reads the fields it knows and ignores the
rest, and adding an optional field is never a breaking change.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from cybercanon.application.errors import FailureKind
from cybercanon.application.results import Refusal, Result, succeeded

OK_STATUS = 200
"""What a use case that ran answers with. A verdict inside it is still an `Ok`."""

INTERNAL_STATUS = 500
"""The one status this module produces from something the domain did not say."""

STATUSES: Mapping[FailureKind, int] = {
    FailureKind.NOT_FOUND: 404,
    FailureKind.FORBIDDEN: 403,
    FailureKind.UNAUTHENTICATED: 401,
    FailureKind.INVALID: 400,
    FailureKind.CONFLICT: 409,
    FailureKind.UNAVAILABLE: 503,
}
"""The mapping, entire. Six kinds, six status classes, no seventh of either.

`UNAVAILABLE` is 503 rather than 500 on purpose: *"a precondition outside the
caller's control is unmet — for now"* is a retryable condition the caller did
not cause, and reporting it as an internal failure is precisely what
`http-api` forbids.
"""

CORRELATION_HEADER = "X-Correlation-Id"
"""Where the identifier a person quotes in a bug report is also carried."""

INTERNAL_IDENTIFIER = "internal.failure"
"""The stable identifier of a failure the domain did not express."""

INTERNAL_MESSAGE = (
    "the request could not be completed; quote the correlation identifier when reporting this"
)
"""Everything a caller is told. The detail goes to the log, never to the body."""

VERSION_FIELD = "version"
DATA_FIELD = "data"
ERROR_FIELD = "error"
CORRELATION_FIELD = "correlation_id"

logger = logging.getLogger("cybercanon.http")
"""Where the detail of an unexpected failure goes, since the response cannot have it."""


def correlation() -> str:
    """A fresh identifier for one request, so a body and a log line can be paired."""
    return uuid.uuid4().hex


def status_for(result: Result[Any]) -> int:
    """The status class of one outcome. The whole of D10's translation."""
    return OK_STATUS if succeeded(result) else STATUSES[result.kind]


def error_body(
    refusal: Refusal,
    *,
    version: str,
    correlation_id: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The error shape every failing response carries, whatever produced it.

    Three fields under `error`, exactly the three `http-api` enumerates: *"a
    stable machine-readable error identifier, a human-readable message, and the
    subject at fault where one exists"*. The subject is `None` rather than
    absent when there is none, so a client reads one shape instead of two.

    `extra` is merged *first*, so an envelope field can never displace one of
    the three. A refusal carries the same envelope a success does — which is
    what lets a conflict *"name the current revision"* without the write path
    building a second kind of body for it.
    """
    return {
        **dict(extra or {}),
        VERSION_FIELD: version,
        CORRELATION_FIELD: correlation_id,
        ERROR_FIELD: {
            "id": refusal.identifier,
            "message": refusal.message,
            "subject": refusal.subject or None,
        },
    }


def success_body(value: Any, *, version: str, extra: Mapping[str, Any] | None = None) -> Any:
    """The success shape: the rendered value under `data`, plus whatever else."""
    return {VERSION_FIELD: version, DATA_FIELD: value, **dict(extra or {})}


type Rendering = Callable[[Any], Any]
"""How a router turns one use case's value into JSON. Presentation, never a decision."""


def identity(value: Any) -> Any:
    """The rendering of a value that is already JSON."""
    return value


def respond(
    result: Result[Any],
    render: Rendering = identity,
    *,
    version: str,
    extra: Mapping[str, Any] | None = None,
) -> JSONResponse:
    """One outcome as one response. The only place a status code is chosen.

    A router hands this whatever the use case returned and returns what comes
    back. It cannot report a refusal as an internal failure, because it never
    sees a status code; and two endpoints producing the same outcome cannot
    disagree, because they are both here.
    """
    correlation_id = correlation()
    if succeeded(result):
        body = success_body(render(result.value), version=version, extra=extra)
    else:
        body = error_body(result, version=version, correlation_id=correlation_id, extra=extra)
    return _response(status_for(result), body, correlation_id)


def generic_failure(*, version: str, correlation_id: str) -> JSONResponse:
    """What an unexpected failure looks like from outside: a number and a name.

    `http-api`: *"SHALL NOT include a stack trace, a file system path, a
    connection string, a credential, or the content of a configuration value"*.
    Nothing derived from the exception reaches this body — not its message, not
    its type — because every one of those has been a leak somewhere.
    """
    body = {
        VERSION_FIELD: version,
        CORRELATION_FIELD: correlation_id,
        ERROR_FIELD: {
            "id": INTERNAL_IDENTIFIER,
            "message": INTERNAL_MESSAGE,
            "subject": None,
        },
    }
    return _response(INTERNAL_STATUS, body, correlation_id)


def _response(status: int, body: Any, correlation_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content=body, headers={CORRELATION_HEADER: correlation_id}
    )


type Next = Callable[[Request], Awaitable[Response]]
"""The rest of the application, from a middleware's point of view."""


def register(app: FastAPI, *, version: str) -> None:
    """Install the one `except` in this package (task 9.4).

    A middleware rather than a decorator on each router, for D10's reason: a
    per-router `try/except` is correct on the day it is written and absent from
    the fourth endpoint somebody adds. Here there is nothing for a router to
    forget.
    """

    @app.middleware("http")
    async def unexpected(request: Request, call_next: Next) -> Response:
        """Everything the domain did not express, reported without describing it."""
        correlation_id = correlation()
        try:
            return await call_next(request)
        except Exception:
            logger.exception("unexpected failure [%s] on %s", correlation_id, request.url.path)
            return generic_failure(version=version, correlation_id=correlation_id)


__all__ = [
    "CORRELATION_FIELD",
    "CORRELATION_HEADER",
    "DATA_FIELD",
    "ERROR_FIELD",
    "INTERNAL_IDENTIFIER",
    "INTERNAL_MESSAGE",
    "INTERNAL_STATUS",
    "OK_STATUS",
    "STATUSES",
    "VERSION_FIELD",
    "Rendering",
    "correlation",
    "error_body",
    "generic_failure",
    "identity",
    "register",
    "respond",
    "status_for",
    "success_body",
]
