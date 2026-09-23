"""The HTTP half of the CyberArche adapter: one request, and what went wrong.

Separated from :mod:`cybercanon.adapters.outbound.arche.platform` for the same
reason `JwksKeySource` is separated from the key policy: everything that
*decides* anything — which state a status code means, what a payload turns into
— runs against :class:`Response` values with no socket anywhere, and what is
left here is a request and a timeout.

The one rule that is a decision rather than mechanics: **the caller's own bearer
token is the only credential this module knows how to send** (D2). There is no
service token, no API key and no impersonation header, because there is no
constructor argument that could hold one — which is the point of the port's
per-call credential and would be undone by a convenience default here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from cybercanon.application.ports.document_platform import (
    Credential,
    PlatformUnavailable,
    UnavailabilityReason,
)

JSON_ACCEPT = "application/json"

TIMEOUT_NAMES = ("timeout", "timedout", "readtimeout", "connecttimeout", "pooltimeout")
"""Exception type names that mean *the budget ran out*, whichever client raised.

Matched by name rather than by class so this module imports no HTTP library at
module scope — the same reason `httpx` is imported inside the function below.
"""


@dataclass(frozen=True)
class Response:
    """One HTTP answer, reduced to the two things any decision here needs."""

    status: int
    payload: Any = None

    @property
    def is_ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass
class ArcheTransport:
    """Sends one request to CyberArche, as the person who asked.

    `client` exists so the suite can hand in a recorder and assert what actually
    went out — the token, the query, the scope — rather than what the code
    appears to send. It defaults to `httpx`, which is the only thing this
    adapter would otherwise need at import time.
    """

    base_url: str
    timeout: timedelta
    client: Any | None = None
    sent: list[tuple[str, str]] = field(default_factory=list)

    def get(
        self, path: str, credential: Credential, params: Mapping[str, Any] | None = None
    ) -> Response:
        return self.request("GET", path, credential, params=params)

    def post(self, path: str, credential: Credential, body: Mapping[str, Any]) -> Response:
        return self.request("POST", path, credential, body=body)

    def request(
        self,
        method: str,
        path: str,
        credential: Credential,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Response:
        """One call, or the reason there is no answer.

        Every way of not answering becomes exactly one
        :class:`~cybercanon.application.ports.document_platform.UnavailabilityReason`:
        a timeout is `TIMED_OUT`, anything else the client raises is
        `UNREACHABLE`, and an answer that is not the JSON this adapter was
        written against is `MALFORMED` — which is a different sentence from
        *the service is down*, and the difference is what a person needs to
        know which team to talk to.
        """
        url = f"{self.base_url}{path}"
        self.sent.append((method, url))
        client = self._client()
        try:
            response = client.request(
                method,
                url,
                headers=self.headers(credential),
                params=dict(params or {}),
                json=dict(body) if body is not None else None,
                timeout=self.timeout.total_seconds(),
            )
        except Exception as failure:  # every HTTP client raises its own family
            raise self._unreachable(failure) from failure
        return Response(status=response.status_code, payload=_decoded(response))

    @staticmethod
    def headers(credential: Credential) -> dict[str, str]:
        """The caller's own token, forwarded verbatim, and nothing else (D2).

        A request with no end-user credential carries no `Authorization` header
        at all rather than a service one: the platform then answers as it would
        to an anonymous caller, which is the honest thing for it to be told.
        """
        headers = {"Accept": JSON_ACCEPT}
        if credential.is_present:
            headers["Authorization"] = f"Bearer {credential.token}"
        return headers

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        import httpx

        return httpx

    @staticmethod
    def _unreachable(failure: Exception) -> PlatformUnavailable:
        name = type(failure).__name__.lower()
        reason = (
            UnavailabilityReason.TIMED_OUT
            if any(marker in name for marker in TIMEOUT_NAMES)
            else UnavailabilityReason.UNREACHABLE
        )
        return PlatformUnavailable(reason, type(failure).__name__)


def _decoded(response: Any) -> Any:
    """The body as data, or the refusal that a *successful* answer was not JSON.

    A failing status with an HTML body is not malformed — it is a refusal this
    adapter already knows how to read from the status line, and turning it into
    *the platform is answering nonsense* would hide a 404 behind a parser
    complaint.
    """
    try:
        return response.json()
    except Exception as failure:
        if 200 <= response.status_code < 300:
            raise PlatformUnavailable(
                UnavailabilityReason.MALFORMED, "the response body was not JSON"
            ) from failure
        return None


__all__ = ["JSON_ACCEPT", "TIMEOUT_NAMES", "ArcheTransport", "Response"]
