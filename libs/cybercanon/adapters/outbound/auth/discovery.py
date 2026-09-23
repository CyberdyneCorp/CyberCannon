"""Where the issuer's endpoints are, asked of the issuer rather than guessed.

The command line used to build its token address by appending `/oauth/token` to
the configured issuer. CyberdyneAuth serves `/api/v1/auth/oauth2/token`, so
`canon auth login` posted its device-code redemption into a 404 — and the fix is
not a better constant. **The fixed path was the mistake.** An issuer publishes a
discovery document naming every endpoint it has, the web application already
reads it, and swapping one hard-coded guess for another would leave the same
defect in place for the next issuer, the next path change and the next studio.

So this module asks. :class:`IssuerEndpoints` answers the three addresses the
sign-in flows need, reading `<issuer>/.well-known/openid-configuration` **once,
on first use** — never at construction, because `canon` builds its container on
every invocation and a validator that opened a socket to an identity service to
tell an artist her mesh is fine would be unusable on a train.

Three properties it keeps:

* **The document must agree about who it is.** A discovery document whose
  `issuer` is not the configured one is refused rather than followed: the
  endpoints in it would be somebody else's, and following them would send a
  device code to whoever answered that address.
* **A configured address still wins.** `CANON_AUTH_TOKEN_URL` and
  `CANON_AUTH_DEVICE_CODE_URL` override what discovery says, for the deployment
  whose issuer publishes no document or publishes a wrong one. They are an
  escape hatch, not the default, which is the inversion this change is.
* **Being unreachable is a sign-in that is unavailable, never a wrong address.**
  Every failure here raises
  :class:`~cybercanon.application.ports.interactive_sign_in.SignInUnavailable`,
  so a person is told the identity service could not be reached rather than
  watching a request go somewhere that was never going to answer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from cybercanon.application.ports.interactive_sign_in import SignInUnavailable

DISCOVERY_PATH = "/.well-known/openid-configuration"
"""Where an OpenID Connect issuer publishes what it serves and where."""

DEFAULT_TIMEOUT_S = 10.0

type DocumentSource = Callable[[str], Mapping[str, Any]]
"""Retrieves one JSON document by address. The whole of the network in here."""


class EndpointDirectory(Protocol):
    """The three addresses a sign-in flow asks for, however they were learned.

    :class:`~cybercanon.adapters.outbound.auth.flows.Endpoints` answers them
    from what it was given and :class:`IssuerEndpoints` answers them from the
    issuer's own document, so a flow never learns which of the two it has — and
    every flow test keeps running against addresses a test wrote down.
    """

    @property
    def token(self) -> str:
        """Where a grant is redeemed."""

    @property
    def device_authorization(self) -> str:
        """Where a device authorization begins, or empty where there is none."""

    @property
    def authorization(self) -> str:
        """Where a person is sent to approve, or empty where there is none."""


@dataclass(frozen=True)
class Discovered:
    """What the document said, as the three addresses plus who published them."""

    issuer: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    device_authorization_endpoint: str = ""

    @classmethod
    def of(cls, document: Mapping[str, Any]) -> Discovered:
        """The fields this product uses, read defensively and never guessed."""
        return cls(
            issuer=_text(document.get("issuer")),
            authorization_endpoint=_text(document.get("authorization_endpoint")),
            token_endpoint=_text(document.get("token_endpoint")),
            device_authorization_endpoint=_text(document.get("device_authorization_endpoint")),
        )


class HttpDocuments:
    """The real source: one GET, one timeout, one JSON document.

    Everything that decides anything in this module runs against a
    :data:`DocumentSource`, so the agreement check, the caching and the failures
    are exercised with no socket and no server.
    """

    def __init__(self, *, timeout_s: float = DEFAULT_TIMEOUT_S, client: Any | None = None) -> None:
        self.timeout_s = timeout_s
        self._client = client

    def __call__(self, url: str) -> Mapping[str, Any]:
        import httpx

        client = self._client or httpx
        response = client.get(url, timeout=self.timeout_s)
        response.raise_for_status()
        document = response.json()
        if not isinstance(document, Mapping):
            raise ValueError("the address did not answer with a document")
        return document


class IssuerEndpoints:
    """The issuer's endpoints, read from its discovery document on first use.

    `overrides` is consulted first and per address, so a deployment can pin one
    endpoint and discover the rest. What it cannot do is make this class guess:
    an address nobody configured and nobody published is a refusal naming the
    endpoint, not a path appended to the issuer.
    """

    def __init__(
        self,
        issuer: str,
        *,
        source: DocumentSource | None = None,
        overrides: EndpointDirectory | None = None,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._source: DocumentSource = source or HttpDocuments()
        self._overrides = overrides
        self._document: Discovered | None = None

    @property
    def url(self) -> str:
        """The address the document is published at."""
        return f"{self._issuer}{DISCOVERY_PATH}"

    @property
    def token(self) -> str:
        return self._address("token", lambda found: found.token_endpoint, lambda given: given.token)

    @property
    def device_authorization(self) -> str:
        return self._address(
            "device authorization",
            lambda found: found.device_authorization_endpoint,
            lambda given: given.device_authorization,
        )

    @property
    def authorization(self) -> str:
        return self._address(
            "authorization",
            lambda found: found.authorization_endpoint,
            lambda given: given.authorization,
        )

    def discovered(self) -> Discovered:
        """The document, retrieved once and kept; a failure is retried next time.

        Only a *successful* retrieval is remembered, so an identity service that
        was down while somebody first tried to sign in does not keep a process
        from ever signing in again.
        """
        if self._document is None:
            self._document = self._agreed(self._retrieved())
        return self._document

    # -- the two things that can go wrong --------------------------------

    def _retrieved(self) -> Discovered:
        try:
            return Discovered.of(self._source(self.url))
        except Exception as failure:
            raise SignInUnavailable(
                f"the identity service's discovery document could not be read from "
                f"{self.url} ({type(failure).__name__})"
            ) from failure

    def _agreed(self, found: Discovered) -> Discovered:
        """A document that names a different issuer describes a different service."""
        if found.issuer.rstrip("/") != self._issuer:
            raise SignInUnavailable(
                f"{self.url} is published by a different issuer than the configured one, "
                "so the endpoints in it are not this identity service's"
            )
        return found

    def _address(
        self,
        endpoint: str,
        published_as: Callable[[Discovered], str],
        configured_as: Callable[[EndpointDirectory], str],
    ) -> str:
        """One address: what the deployment pinned, else what the issuer says."""
        configured = configured_as(self._overrides) if self._overrides is not None else ""
        if configured:
            return configured
        published = published_as(self.discovered())
        if not published:
            raise SignInUnavailable(
                f"the identity service publishes no {endpoint} endpoint, and none is configured"
            )
        return published


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "DISCOVERY_PATH",
    "Discovered",
    "DocumentSource",
    "EndpointDirectory",
    "HttpDocuments",
    "IssuerEndpoints",
]
