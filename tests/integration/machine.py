"""A whole machine for the write surface: an issuer on a socket, a keychain in a file.

Group 6 of `add-mcp-writes` is about *processes* — `canon login` as a person runs
it, the agent server as an agent client spawns it — and a process cannot be
handed an in-memory fake. So the two things a write needs from outside the
repository are stood up for real, and each of them is real in the place that
matters:

* **the issuer is on a socket.** :func:`signing_issuer` serves
  `canon_issuer.FakeIssuer` over HTTP — the device-code endpoint, the token
  endpoint and the published key set — so the child process performs the actual
  device authorization exchange over the actual transport, mints a real
  RS256 credential and verifies it against a real JWKS. What is stubbed is the
  *authorization server*, never the flow;
* **the keychain is a module on the child's path.** `keyring` is imported by
  name inside the credential-store adapter, so :func:`stub_keychain` writes a
  `keyring.py` whose three functions keep their entry in a JSON file under the
  test's temporary directory. **The product is unchanged**: no path reaches the
  adapter, D5's *"no file fallback"* still holds in the code under test, and the
  file exists only so a test run never touches — or prompts for — the developer's
  own login keychain.

`SUBJECT`, `PERSON` and the rest describe the same person `examples/ronin`'s
`.canon/actors.yaml` maps, because the whole point of two-party attribution is
that the signed-in subject and the git author are bound to one another.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from canon_issuer import (
    DEVICE_CODE_PATH,
    HOME_ORG,
    ORG_ID,
    PRO_MONTHLY,
    TOKEN_PATH,
    FakeIssuer,
)
from cybercanon.application.ports.identity_provider import Credential

JWKS_PATH = "/.well-known/jwks.json"
DISCOVERY_PATH = "/.well-known/openid-configuration"

SUBJECT = "auth|rafa"
"""What the credential says, and the only name of a person that ever crosses it."""

PERSON = "Rafa"
"""What `.canon/actors.yaml` calls that subject — never a claim.

A CyberdyneAuth access token carries no `name` and no `email`, so a readable
name reaches a surface from the mapping file or from nowhere (D13). It is here
because the git author and the mapping use it, and it is deliberately *not*
minted into a credential any more.
"""
GIT_EMAIL = "rafa@cyberdyne.com"
PROJECT = "Ronin"
AGENT = "blender-agent"

ART_DIRECTION_ROLE = "art_director"
GROUP_ROLES = f"{ART_DIRECTION_ROLE}=ART_DIRECTOR"
"""The one role key this machine maps, so an agent can act as an art director.

Promotion is the thing the milestone has to refuse *for a caller who would
otherwise be allowed it*, and a refusal that came from a missing role would
prove nothing about the prohibition.

The key is unprefixed because that is what the mapping is configured with; the
issuer writes it into the token as `<client id>:art_director`, which is how
CyberdyneAuth really writes it.
"""

KEYCHAIN = '''\
"""A keychain for one test run: the three calls the adapter makes, in one file.

It shadows the real `keyring` because it is earlier on `PYTHONPATH`. Nothing in
CyberCanon knows it is here — the adapter still imports `keyring` by name and
still has no path anywhere in its construction.
"""

import json
import pathlib

PATH = pathlib.Path(r"{path}")


def _entries():
    if not PATH.is_file():
        return {{}}
    return json.loads(PATH.read_text(encoding="utf-8"))


def _write(entries):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(entries), encoding="utf-8")


def get_password(service, account):
    return _entries().get(f"{{service}}/{{account}}")


def set_password(service, account, password):
    entries = _entries()
    entries[f"{{service}}/{{account}}"] = password
    _write(entries)


def delete_password(service, account):
    entries = _entries()
    key = f"{{service}}/{{account}}"
    if key not in entries:
        raise KeyError(key)
    del entries[key]
    _write(entries)
'''

LOCKED_KEYCHAIN = '''\
"""A keychain that cannot be reached — the locked-store case D5 names."""


class KeyringLocked(Exception):
    pass


def get_password(service, account):
    raise KeyringLocked("the credential store is locked")


def set_password(service, account, password):
    raise KeyringLocked("the credential store is locked")


def delete_password(service, account):
    raise KeyringLocked("the credential store is locked")
'''


@dataclass
class PersonIsAlreadyAtTheBrowser(FakeIssuer):
    """The stubbed authorization server, with the person's claims and their click.

    Two overrides, and both are about what a *server* does rather than about
    what the flow does. The device grant is approved as soon as it is issued —
    the person in this story already has the browser open — and the credential
    it then mints carries the claims a real CyberdyneAuth puts in it: the role
    keys a domain role is configured from, the organisation the person belongs
    to, and their billing entitlements.

    It carries **no display name and no git emails**, because a real access
    token carries neither. `GIT_EMAIL` still names the same person, but the
    binding between the subject and that address is `.canon/actors.yaml`'s job
    (D13) rather than a claim's, and a machine that minted the claim would be
    testing a provider that does not exist.

    It carries no `projects` either, and that is the load-bearing absence: this
    machine used to mint `projects=[PROJECT]`, so every suite downstream watched
    a person read a project they were entitled to by a claim the identity
    service has never sent. What entitles them here is `orgs` and `roles`,
    exactly as it does in production.
    """

    roles: tuple[str, ...] = ()
    entitlements: tuple[str, ...] = (PRO_MONTHLY,)
    orgs: tuple[Mapping[str, Any], ...] = (HOME_ORG,)
    lifetime_s: int = 3600
    """What a real CyberdyneAuth would put in the credential it issues."""

    def _device_grant(self) -> Mapping[str, Any]:
        grant = super()._device_grant()
        self.approve(str(grant["user_code"]))
        return grant

    def mint(self, subject: str = SUBJECT, **overrides: Any) -> Credential:
        claims: dict[str, Any] = {
            "roles": list(self.roles),
            "entitlements": list(self.entitlements),
            "orgs": list(self.orgs),
            "lifetime_s": self.lifetime_s,
        }
        return super().mint(subject, **(claims | overrides))


@dataclass(frozen=True)
class Issuing:
    """A running authorization server: where it is, and what it has issued."""

    issuer: PersonIsAlreadyAtTheBrowser
    base_url: str

    @property
    def environment(self) -> dict[str, str]:
        """The variables a machine needs to sign in against this issuer and verify it."""
        return {
            "CANON_AUTH_ISSUER": self.base_url,
            "CANON_AUTH_CLIENT_ID": self.issuer.client_id,
            "CANON_AUTH_AUDIENCE": self.issuer.audience,
            "CANON_AUTH_KEY_SET_URL": f"{self.base_url}{JWKS_PATH}",
            "CANON_AUTH_GROUP_ROLES": GROUP_ROLES,
            # The organisation this machine's deployment belongs to, and the one
            # the credential's `orgs` claim carries. Never a real org id: it is
            # an invented value that lives in `canon_issuer` and is read from
            # the environment here, because the product must not name one.
            "CANON_AUTH_ORG_ID": ORG_ID,
        }

    def credential(self, **overrides: Any) -> Credential:
        """A credential this issuer signs, for a test that skips the browser."""
        return self.issuer.mint(**overrides)


class _Endpoints(BaseHTTPRequestHandler):
    """The four requests a sign-in makes, answered by the issuer behind them.

    The fourth is the discovery document, and it is here because `canon` no
    longer knows where an issuer's endpoints are: it reads them from
    `/.well-known/openid-configuration`, the way an OpenID client does, rather
    than appending a path it believes in. A machine whose issuer published no
    document would refuse the sign-in naming the identity service — which is the
    behaviour, and is why this fixture publishes one.
    """

    issuer: PersonIsAlreadyAtTheBrowser

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == DISCOVERY_PATH:
            self._answer(200, self._discovery())
            return
        if path != JWKS_PATH:
            self._answer(404, {"error": "not_found"})
            return
        self._answer(200, self.issuer.jwks())

    def _discovery(self) -> Mapping[str, Any]:
        """Where this issuer serves what, in the shape an OIDC client reads.

        The addresses are this fixture's own — `/oauth/token` and
        `/oauth/device/code` — and that is the point: nothing in the product
        knows them, so a suite that drives a real sign-in is proving that the
        client took them from here.
        """
        return {
            "issuer": self.issuer.issuer,
            "token_endpoint": f"{self.issuer.issuer}{TOKEN_PATH}",
            "device_authorization_endpoint": f"{self.issuer.issuer}{DEVICE_CODE_PATH}",
            "jwks_uri": f"{self.issuer.issuer}{JWKS_PATH}",
        }

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        form = {
            name: values[0]
            for name, values in parse_qs(self.rfile.read(length).decode("utf-8")).items()
        }
        path = self.path.split("?")[0]
        if path not in (DEVICE_CODE_PATH, TOKEN_PATH):
            self._answer(404, {"error": "not_found"})
            return
        self._answer(200, self._issued(path, form))

    def _issued(self, path: str, form: Mapping[str, str]) -> Mapping[str, Any]:
        """What the issuer answers, with its refusals kept as OAuth documents.

        `FakeIssuer.post` raises on a refusal because its in-process callers read
        an exception; over the wire the same thing is a document with an `error`
        field, which is what the real transport parses.
        """
        try:
            return self.issuer.post(f"{self.issuer.issuer}{path}", form)
        except Exception as refusal:
            return {"error": getattr(refusal, "code", "server_error"), "error_description": ""}

    def _answer(self, status: int, document: Mapping[str, Any]) -> None:
        body = json.dumps(document).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_arguments: Any) -> None:
        """Quiet. A test run is not a web server's access log."""


@contextmanager
def signing_issuer(**attributes: Any) -> Iterator[Issuing]:
    """A CyberdyneAuth on `127.0.0.1`, for as long as the block lasts.

    The issuer's own `iss` claim is rewritten to the address it is actually
    served at, because the credential is verified against the configured issuer
    and a value that did not match would be a test passing for the wrong reason.
    """
    issuer = PersonIsAlreadyAtTheBrowser(now=int(time.time()), **attributes)
    handler = type("_Bound", (_Endpoints,), {"issuer": issuer})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    issuer.issuer = base_url
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Issuing(issuer=issuer, base_url=base_url)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def stub_keychain(directory: Path, *, locked: bool = False) -> Path:
    """A directory holding a `keyring` the child process will import instead.

    Returned as a path to put on `PYTHONPATH`. `locked` produces the store D5
    describes — one that raises rather than answering — so *"writes report as
    unavailable, reads are untouched"* can be executed against a process.
    """
    directory.mkdir(parents=True, exist_ok=True)
    source = LOCKED_KEYCHAIN if locked else KEYCHAIN.format(path=directory / "keychain.json")
    (directory / "keyring.py").write_text(source, encoding="utf-8")
    return directory


def bare_environment(*paths: Path, **extra: str) -> dict[str, str]:
    """This machine's environment with nothing that could identify anybody.

    Every `CANON_`, `CYBERDYNE_` and `GIT_` variable is stripped, so a test never
    inherits the developer's own configuration, and what a scenario needs is
    added back explicitly. `paths` go on `PYTHONPATH` in the order given.
    """
    stripped = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CANON_", "CYBERDYNE_", "GIT_"))
        and name not in {"HOME", "GITHUB_TOKEN"}
    }
    if paths:
        stripped["PYTHONPATH"] = os.pathsep.join(str(path) for path in paths)
    return {**stripped, **extra}


def agent_client_configuration(command: str, project: Path, agent: str = AGENT) -> dict[str, Any]:
    """The launch entry an agent client holds, as `README.md` documents it (6.5).

    It names the command, the project directory and the agent identifier, and it
    holds **no credential** — which is the scenario *"no secret appears in
    configuration"* and the reason the credential lives in the operating
    system's store in the first place.
    """
    return {
        "mcpServers": {
            "cybercanon": {
                "command": command,
                "args": ["mcp", "serve", str(project)],
                "env": {"CANON_AGENT": agent},
            }
        }
    }


def secrets_in(configuration: Mapping[str, Any], candidates: Sequence[str]) -> tuple[str, ...]:
    """Any of `candidates` appearing anywhere in that configuration document."""
    rendered = json.dumps(configuration)
    return tuple(candidate for candidate in candidates if candidate and candidate in rendered)


__all__ = [
    "AGENT",
    "ART_DIRECTION_ROLE",
    "DISCOVERY_PATH",
    "GIT_EMAIL",
    "GROUP_ROLES",
    "JWKS_PATH",
    "PERSON",
    "PROJECT",
    "SUBJECT",
    "Issuing",
    "PersonIsAlreadyAtTheBrowser",
    "agent_client_configuration",
    "bare_environment",
    "secrets_in",
    "signing_issuer",
    "stub_keychain",
]
