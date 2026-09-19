"""Structured JSON on stdout, and that is the whole logging design (D11).

One line per request, parseable, carrying a request id, the acting actor when
there is one and the project when there is one. Coolify collects stdout; nothing
ships logs anywhere else, and there is no aggregation stack to operate.

*Why so little:* the operational questions `deployment-operations` actually
states — is the index stale, when did the working copy last fetch — are answered
by `/status`, not by log search. Logs are for afterwards, and a line that cannot
be parsed is a line that is not read afterwards either. So the line is
`json.dumps` of a flat object and never a formatted sentence.

**Identity is not read here.** The middleware cannot verify a credential — that
is the `authenticate` use case's job, reached through
:func:`~cybercanon.adapters.inbound.http.routing.prepared_for` — so the pipeline
records who it resolved and which project the address named, and this module
reports what was recorded. A request refused before authentication logs a line
with no actor, which is the honest description of what happened.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response

from cybercanon.adapters.inbound.http.outcomes import correlation

LOGGER = "cybercanon.http.access"
"""One logger, named so a deployment can raise or lower it on its own."""

REQUEST_ID_HEADER = "X-Request-Id"
"""Honoured when the caller or a proxy set one, so one request has one id."""

REQUEST_ID_FIELD = "request_id"
ACTOR_FIELD = "actor"
PROJECT_FIELD = "project"
METHOD_FIELD = "method"
PATH_FIELD = "path"
STATUS_FIELD = "status"

ACTOR_STATE = "actor"
PROJECT_STATE = "project"
REQUEST_ID_STATE = "request_id"
"""Where the pipeline leaves what it resolved, for this middleware to report."""

logger = logging.getLogger(LOGGER)

type Next = Callable[[Request], Awaitable[Response]]


def configure(stream: Any = None) -> logging.Handler:
    """Send this logger's lines to stdout, one JSON object per line.

    Called by the deployable's entry point rather than at import: a library that
    configured logging on import would take the decision away from every process
    that ever imported it, including the command line.
    """
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return handler


def register(app: FastAPI) -> None:
    """Log one line per request, after the response has been produced."""

    @app.middleware("http")
    async def access(request: Request, call_next: Next) -> Response:
        identifier = request_id(request)
        request.state.request_id = identifier
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = identifier
        logger.info(line(request, response, identifier))
        return response


def request_id(request: Request) -> str:
    """The caller's identifier when it sent one, or a fresh one for this request."""
    offered = request.headers.get(REQUEST_ID_HEADER, "").strip()
    return offered or correlation()


def line(request: Request, response: Response, identifier: str) -> str:
    """One request as one JSON object. Absent fields are `null`, never missing."""
    return json.dumps(fields(request, response, identifier), sort_keys=True)


def fields(request: Request, response: Response, identifier: str) -> dict[str, Any]:
    return {
        REQUEST_ID_FIELD: identifier,
        ACTOR_FIELD: recorded(request, ACTOR_STATE),
        PROJECT_FIELD: recorded(request, PROJECT_STATE),
        METHOD_FIELD: request.method,
        PATH_FIELD: request.url.path,
        STATUS_FIELD: response.status_code,
    }


def recorded(request: Request, name: str) -> str | None:
    """What the pipeline resolved under that name, or nothing."""
    return getattr(request.state, name, None)


def remember(request: Request, name: str, value: str) -> None:
    """Record something the pipeline resolved, for the line to carry."""
    setattr(request.state, name, value)


__all__ = [
    "ACTOR_FIELD",
    "ACTOR_STATE",
    "LOGGER",
    "METHOD_FIELD",
    "PATH_FIELD",
    "PROJECT_FIELD",
    "PROJECT_STATE",
    "REQUEST_ID_FIELD",
    "REQUEST_ID_HEADER",
    "REQUEST_ID_STATE",
    "STATUS_FIELD",
    "configure",
    "fields",
    "line",
    "logger",
    "register",
    "remember",
    "request_id",
]
