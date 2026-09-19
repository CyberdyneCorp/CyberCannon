"""Task 2.8 — one parseable JSON line per request, carrying the three fields (D11).

The whole logging design is "structured JSON on stdout", so the whole test is:
make a request, read what was written, and parse it. A line that has to be
regex-matched is a line nobody reads afterwards, which is the failure D11 exists
to avoid.

The three fields the specification names are a request id, the acting actor when
there is one, and the project when there is one — *when there is one* being the
half that is easy to fake. A request that was refused before it was
authenticated logs no actor, and a request that names no project logs no
project: the line describes what happened rather than what was hoped for.
"""

from __future__ import annotations

import json
import logging
import sys
from io import StringIO

from http_world import PROJECT, RAFA, TOKEN, a_surface

from cybercanon.adapters.inbound.http import logs
from cybercanon.adapters.inbound.http.health import LIVE_PATH
from cybercanon.adapters.inbound.http.versioning import VERSION

BASE = f"/{VERSION}/projects/{PROJECT}"


def _capturing() -> StringIO:
    """Point the access logger at a buffer, the way `configure` points it at stdout."""
    stream = StringIO()
    logs.configure(stream)
    return stream


def _lines(stream: StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


# --------------------------------------------------------------------------
# One line, parseable, with all three
# --------------------------------------------------------------------------


def test_a_request_emits_one_json_line_carrying_id_actor_and_project() -> None:
    stream = _capturing()
    wired = a_surface()

    wired.get(f"{BASE}/assets", token=TOKEN)
    (line,) = _lines(stream)

    assert line["request_id"]
    assert line["actor"] == RAFA
    assert line["project"] == PROJECT
    assert line["path"] == f"{BASE}/assets"
    assert line["status"] == 200


def test_an_unauthenticated_request_logs_no_actor_rather_than_a_wrong_one() -> None:
    stream = _capturing()
    wired = a_surface()

    wired.client.get(f"{BASE}/assets")
    (line,) = _lines(stream)

    assert line["actor"] is None
    assert line["project"] == PROJECT
    assert line["status"] == 401


def test_an_open_endpoint_logs_neither_actor_nor_project() -> None:
    stream = _capturing()
    wired = a_surface()

    wired.client.get(LIVE_PATH)
    (line,) = _lines(stream)

    assert line["actor"] is None
    assert line["project"] is None
    assert line["path"] == LIVE_PATH


def test_the_caller_s_request_id_is_the_one_logged_and_returned() -> None:
    """One request has one identifier, whoever minted it."""
    stream = _capturing()
    wired = a_surface()

    response = wired.client.get(LIVE_PATH, headers={logs.REQUEST_ID_HEADER: "req-42"})
    (line,) = _lines(stream)

    assert line["request_id"] == "req-42"
    assert response.headers[logs.REQUEST_ID_HEADER] == "req-42"


def test_two_requests_without_an_identifier_are_told_apart() -> None:
    stream = _capturing()
    wired = a_surface()

    wired.client.get(LIVE_PATH)
    wired.client.get(LIVE_PATH)
    first, second = _lines(stream)

    assert first["request_id"] != second["request_id"]


def test_no_credential_is_ever_written_to_the_line() -> None:
    stream = _capturing()
    wired = a_surface()

    wired.get(f"{BASE}/assets", token=TOKEN)

    assert TOKEN not in stream.getvalue()


# --------------------------------------------------------------------------
# Where the lines go
# --------------------------------------------------------------------------


def test_the_configured_handler_writes_to_stdout_and_formats_nothing_else() -> None:
    handler = logs.configure()
    try:
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stdout
        assert handler.format(_a_record()) == '{"a": 1}'
    finally:
        _capturing()


def _a_record() -> logging.LogRecord:
    return logging.LogRecord(
        name=logs.LOGGER,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='{"a": 1}',
        args=(),
        exc_info=None,
    )
