"""CyberdyneAuth over a socket — the end-to-end stack's identity service.

`deploy/e2e/compose.yaml` used to point `CANON_AUTH_KEY_SET_URL` at
`http://api:8000/e2e-issuer/jwks.json`, and **nothing served that address**: the
API's catch-all refuses any path carrying no surface version, so the key set
retrieval answered 400, no credential could ever verify, and the browser suites
could only ever assert the signed-out half of the application. A stack that can
never authenticate is a stack that can never test a signed-in screen, and it
silently limited every verification in this project — including every screenshot
anybody ever took of it.

This module is the other half of that fix: :class:`~canon_issuer.FakeIssuer`,
which the port-conformance, integration and BDD layers already mint and rotate
real RSA-signed credentials with, answering over HTTP so that a **browser** can
complete an authorization-code exchange against it.

Nothing here is a second implementation of anything. The keys, the minting, the
authorization codes and the PKCE binding are the same objects the in-process
suites use, and :func:`~cybercanon.adapters.outbound.auth.pkce.verify` is the
check the adapter's own tests run. What is added is a socket, four addresses and
the cross-origin permission a browser needs to POST to a token endpoint on
another port.

**It is test support and it is never deployed.** `deploy/coolify.yaml` declares
the four hosted applications and `just deploy-check` refuses a fifth; this runs
only in `deploy/e2e/compose.yaml`, from `deploy/e2e/issuer.Dockerfile`, beside
the throwaway PostgreSQL and the throwaway git daemon. The identity it issues is
described entirely by environment variables, so the stack says who signs in
rather than this file deciding it.

**Two addresses, on purpose.** The browser reaches this service at the published
port on the host and the API reaches it inside the compose network, so the
issuer identifier in a credential (`iss`, which the API checks against
`CANON_AUTH_ISSUER`) and the address the key set is retrieved from
(`CANON_AUTH_KEY_SET_URL`) are different strings naming one service. That is
precisely why the service declares them as two settings, and the stack is the
first place it matters.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from canon_issuer import AUTHORIZE_PATH, TOKEN_PATH, FakeIssuer
from cybercanon.adapters.outbound.auth import pkce

DISCOVERY_PATH = "/.well-known/openid-configuration"
JWKS_PATH = "/jwks.json"
HEALTH_PATH = "/healthz"

DEFAULT_PORT = 9000
DEFAULT_ISSUER_URL = "http://localhost:9000"
DEFAULT_AUDIENCE = "cybercanon-e2e"
DEFAULT_CLIENT_ID = "cybercanon-web"
DEFAULT_SUBJECT = "auth|rafa"
DEFAULT_NAME = "Rafa Moreno"
LIFETIME_S = 3600

LIST_SEPARATOR = ","

INVALID_GRANT = "invalid_grant"
NO_SUCH_CODE = "no such authorization code"
NO_PROOF = "the proof does not match the challenge"
NOT_FOUND = "no endpoint at this address"


@dataclass(frozen=True)
class Profile:
    """Who signs in here, and as what. The whole of this service's policy.

    Every field is an environment variable, because the point of the stack is
    that the identity is the stack's decision rather than this module's: a suite
    that wanted a person holding no role would start the issuer with
    ``ISSUER_GROUPS`` empty rather than patch a constant.
    """

    issuer_url: str = DEFAULT_ISSUER_URL
    audience: str = DEFAULT_AUDIENCE
    client_id: str = DEFAULT_CLIENT_ID
    subject: str = DEFAULT_SUBJECT
    name: str = DEFAULT_NAME
    groups: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()
    git_emails: tuple[str, ...] = ()
    port: int = DEFAULT_PORT

    @property
    def claims(self) -> dict[str, Any]:
        """The non-registered claims every credential this service mints carries."""
        return {
            "name": self.name,
            "groups": self.groups,
            "projects": self.projects,
            "git_emails": self.git_emails,
        }


def profile_from(environment: Mapping[str, str]) -> Profile:
    """The profile this process serves, read from the environment and nothing else."""
    return Profile(
        issuer_url=environment.get("ISSUER_URL", DEFAULT_ISSUER_URL).rstrip("/"),
        audience=environment.get("ISSUER_AUDIENCE", DEFAULT_AUDIENCE),
        client_id=environment.get("ISSUER_CLIENT_ID", DEFAULT_CLIENT_ID),
        subject=environment.get("ISSUER_SUBJECT", DEFAULT_SUBJECT),
        name=environment.get("ISSUER_NAME", DEFAULT_NAME),
        groups=_listed(environment.get("ISSUER_GROUPS", "")),
        projects=_listed(environment.get("ISSUER_PROJECTS", "")),
        git_emails=_listed(environment.get("ISSUER_GIT_EMAILS", "")),
        port=int(environment.get("ISSUER_PORT", str(DEFAULT_PORT))),
    )


def _listed(raw: str) -> tuple[str, ...]:
    return tuple(entry.strip() for entry in raw.split(LIST_SEPARATOR) if entry.strip())


def discovery(profile: Profile) -> dict[str, Any]:
    """The document an OIDC client would read, for the addresses below to be findable."""
    return {
        "issuer": profile.issuer_url,
        "authorization_endpoint": f"{profile.issuer_url}{AUTHORIZE_PATH}",
        "token_endpoint": f"{profile.issuer_url}{TOKEN_PATH}",
        "jwks_uri": f"{profile.issuer_url}{JWKS_PATH}",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": [pkce.METHOD],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


@dataclass
class Authority:
    """The issuer, and the two answers the OAuth endpoints are made of.

    Split from the HTTP handler so that both are checkable without a socket:
    :meth:`authorization` and :meth:`exchange` take and return plain values, and
    the handler below only ever moves bytes.
    """

    profile: Profile
    issuer: FakeIssuer = field(init=False)

    def __post_init__(self) -> None:
        self.issuer = FakeIssuer(
            issuer=self.profile.issuer_url,
            audience=self.profile.audience,
            client_id=self.profile.client_id,
        )

    def jwks(self) -> dict[str, Any]:
        return self.issuer.jwks()

    def authorization(self, url: str) -> str:
        """Where the browser is sent back to, code and state attached.

        There is no consent screen and there is nobody to show one to: the
        person this service signs in is the one the stack configured, so the
        authorization endpoint approves and redirects. The PKCE challenge is
        remembered against the code, which is what makes :meth:`exchange` able
        to refuse an exchange that arrives without the matching verifier.
        """
        code, state = self.issuer.authorize(url, subject=self.profile.subject)
        query = {"code": code}
        if state:
            query["state"] = state
        return f"{_redirect_uri(url)}?{urlencode(query)}"

    def exchange(self, form: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
        """A code and its proof, for a signed credential — or the refusal, as OAuth states it."""
        held = self.issuer.codes.pop(form.get("code", ""), None)
        if held is None:
            return 400, _error(NO_SUCH_CODE)
        verifier = form.get("code_verifier", "")
        if not verifier or not pkce.verify(held.challenge, verifier, held.method):
            return 400, _error(NO_PROOF)
        return 200, self._issued(held.subject)

    def _issued(self, subject: str) -> dict[str, Any]:
        credential = self.issuer.mint(
            subject,
            issued_at=int(time.time()),
            lifetime_s=LIFETIME_S,
            **self.profile.claims,
        )
        return {
            "access_token": credential.value,
            "token_type": "Bearer",
            "expires_in": LIFETIME_S,
        }


def _error(description: str) -> dict[str, Any]:
    return {"error": INVALID_GRANT, "error_description": description}


def _redirect_uri(url: str) -> str:
    """Where the authorization request asked to be returned to."""
    return _query(url).get("redirect_uri", "")


def _query(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


class Endpoints(BaseHTTPRequestHandler):
    """The socket. Four addresses, and no decision of its own."""

    authority: Authority
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == HEALTH_PATH:
            self._json(200, {"status": "ok"})
        elif path == JWKS_PATH:
            self._json(200, self.authority.jwks())
        elif path == DISCOVERY_PATH:
            self._json(200, discovery(self.authority.profile))
        elif path == AUTHORIZE_PATH:
            self._redirect(self.authority.authorization(self.path))
        else:
            self._json(404, _error(NOT_FOUND))

    def do_POST(self) -> None:
        if urlsplit(self.path).path != TOKEN_PATH:
            self._json(404, _error(NOT_FOUND))
            return
        status, body = self.authority.exchange(self._form())
        self._json(status, body)

    def do_OPTIONS(self) -> None:
        """The preflight the browser sends before it posts to another origin.

        The application is served from one port and this service from another,
        which is the same split `deploy/coolify.yaml` has between `canon.backend`
        and `auth.backend`. Without this the browser refuses the token response
        it already received and the sign-in fails for a reason nothing logs.
        """
        self.send_response(204)
        self._cross_origin()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """One line per request on stdout, so `docker compose logs issuer` says something."""
        print(f"issuer {format % args}", flush=True)

    # -- moving bytes ----------------------------------------------------

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return {name: values[0] for name, values in parse_qs(raw).items()}

    def _json(self, status: int, body: Mapping[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self._cross_origin()
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self._cross_origin()
        self.end_headers()

    def _cross_origin(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")


def serve(profile: Profile | None = None) -> None:
    """Answer until the container is stopped."""
    described = profile or profile_from(os.environ)
    handler = type("BoundEndpoints", (Endpoints,), {"authority": Authority(described)})
    server = ThreadingHTTPServer(("0.0.0.0", described.port), handler)
    print(
        f"issuer serving {described.issuer_url} on port {described.port} as {described.subject}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    serve()


__all__ = [
    "DISCOVERY_PATH",
    "HEALTH_PATH",
    "JWKS_PATH",
    "Authority",
    "Endpoints",
    "Profile",
    "discovery",
    "profile_from",
    "serve",
]
