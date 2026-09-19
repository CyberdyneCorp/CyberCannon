"""The one HTTP shape the sign-in flows use, and the one error they read.

Both flows in :mod:`cybercanon.adapters.outbound.auth.flows` talk to the same
two endpoints in the same way — a form posted, a JSON document back, and an
`error` field when the issuer is saying no. Factoring that here means the flows
contain their *protocol* and nothing about sockets, which is what lets the whole
of the device flow and the whole of the authorization-code exchange be exercised
against an issuer that is a dictionary.

:class:`OAuthRefusal` is the issuer's own vocabulary, kept as a code rather than
a sentence, because two of its codes are not failures at all: `authorization_pending`
and `slow_down` are the device flow saying *the person has not clicked yet*.
A transport that raised on those would make polling impossible.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

AUTHORIZATION_PENDING = "authorization_pending"
SLOW_DOWN = "slow_down"
ACCESS_DENIED = "access_denied"
EXPIRED_TOKEN = "expired_token"
INVALID_GRANT = "invalid_grant"

STILL_WAITING = frozenset({AUTHORIZATION_PENDING, SLOW_DOWN})
"""The two codes that mean *keep waiting* rather than *it failed*."""


class OAuthRefusal(Exception):
    """The issuer answered, and the answer is no. `code` is its own word for why."""

    def __init__(self, code: str, description: str = "") -> None:
        super().__init__(f"{code}: {description}" if description else code)
        self.code = code
        self.description = description

    @property
    def is_still_waiting(self) -> bool:
        return self.code in STILL_WAITING


class OAuthUnreachable(Exception):
    """The issuer could not be reached at all. Never the same as a refusal."""


class OAuthTransport(Protocol):
    """Posts a form to one of the issuer's endpoints and reads its answer."""

    def post(self, url: str, form: Mapping[str, str]) -> Mapping[str, Any]:
        """The document the issuer answered with.

        Raises :class:`OAuthRefusal` when it answered with an error, and
        :class:`OAuthUnreachable` when it did not answer.
        """
        ...


class HttpOAuthTransport:
    """The real transport. The only thing in the sign-in path that opens a socket."""

    def __init__(self, *, timeout_s: float = 10.0, client: Any | None = None) -> None:
        self.timeout_s = timeout_s
        self._client = client

    def post(self, url: str, form: Mapping[str, str]) -> Mapping[str, Any]:
        import httpx

        client = self._client or httpx
        try:
            response = client.post(url, data=dict(form), timeout=self.timeout_s)
            document = response.json()
        except Exception as failure:
            raise OAuthUnreachable(f"{type(failure).__name__} talking to {url}") from failure
        return read(document)


def read(document: Any) -> Mapping[str, Any]:
    """One answer, checked once: a mapping, and an `error` field is a refusal."""
    if not isinstance(document, Mapping):
        raise OAuthUnreachable("the issuer did not answer with a document")
    error = document.get("error")
    if error:
        raise OAuthRefusal(str(error), str(document.get("error_description", "")))
    return document


__all__ = [
    "ACCESS_DENIED",
    "AUTHORIZATION_PENDING",
    "EXPIRED_TOKEN",
    "INVALID_GRANT",
    "SLOW_DOWN",
    "STILL_WAITING",
    "HttpOAuthTransport",
    "OAuthRefusal",
    "OAuthTransport",
    "OAuthUnreachable",
    "read",
]
