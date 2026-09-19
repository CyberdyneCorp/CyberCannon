"""Building the real container: the one place an outbound adapter is named (D11).

:mod:`cybercanon.adapters.wiring.container` holds ports; this module chooses the
implementations. The split is structural, not stylistic — an inbound adapter
imports the container type, and if that type's module reached an outbound
adapter the CLI would acquire an import of `trimesh` through the layering
contract D10 forbids. So every concrete class in this change is named exactly
once, below.

**One container, both inbound surfaces (task 6.4).** `canon` and the FastMCP
server are built from the same call, so there is no second place a use case
could be assembled differently: the agent's `validate_export` and the artist's
`canon validate` reach the identical object graph, and a test resolves every use
case in :data:`~cybercanon.adapters.wiring.container.USE_CASES` through both.

Nothing here decides anything about an asset. It reads the project
configuration to learn what preview emission should aim for — a configuration
value, per D7 — and hands the adapters to the container, plus the two callables
the core deliberately refuses to grow a port for: the file fingerprint the
staleness rule compares (D8) and the commit authors the unmapped-author list
works through (D12).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from cybercanon.adapters.outbound.auth.flows import DeviceAuthorization, Endpoints
from cybercanon.adapters.outbound.auth.keychain import KeychainCredentialStore
from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
from cybercanon.adapters.outbound.git import revisions
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.gltf_preview import PreviewSettings
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.adapters.outbound.sqlite.search_index import SqliteSearchIndex
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.search_index import FileFingerprint
from cybercanon.application.ports.spec_store import PreviewDefaults
from cybercanon.application.use_cases.index_assets import Fingerprinter
from cybercanon.application.use_cases.resolve_actor import ActorResolver, AuthorSource

CANON_DIR = ".canon"
"""Derived blobs live beside the configuration, inside the repository."""

ISSUER = "CANON_AUTH_ISSUER"
CLIENT_ID = "CANON_AUTH_CLIENT_ID"
AUDIENCE = "CANON_AUTH_AUDIENCE"
DEVICE_CODE_URL = "CANON_AUTH_DEVICE_CODE_URL"
TOKEN_URL = "CANON_AUTH_TOKEN_URL"

DEVICE_CODE_PATH = "/oauth/device/code"
TOKEN_PATH = "/oauth/token"


def build_container(root: str | Path, environment: Mapping[str, str] | None = None) -> Container:
    """The container an inbound adapter runs against, over a working copy.

    `root` is any path inside the repository — the working directory a person
    ran `canon` in is the ordinary case, and the directory an agent client was
    pointed at is the other. The spec store resolves the repository root from
    it, and every other adapter is anchored to that same root, so two surfaces
    run against the same files whichever directory they started in.

    No credential is configured here, and that is the specified behaviour rather
    than an omission: the resolver's chain ends in a local unauthenticated actor
    (D4), so every read works with no identity, no network and no services.
    `canon auth login` is how a person puts one in the machine's credential
    store, and nothing else in `canon` asks for it — which is why the store is
    wired unconditionally (it needs no configuration and opens nothing until it
    is used) while the sign-in flow is wired only when an issuer is configured.
    """
    spec_store = GitSpecStore(root)
    settings = preview_settings(spec_store.load_project("").preview)
    return Container(
        spec_store=spec_store,
        mesh_inspector=TrimeshInspector(root=spec_store.root, settings=settings),
        blob_store=FsBlobStore(spec_store.root / CANON_DIR),
        search_index=SqliteSearchIndex(spec_store.root),
        actor_resolver=ActorResolver(project=spec_store.load_project("").name or ""),
        fingerprints=file_fingerprints(spec_store.root),
        authors=commit_authors(spec_store.root),
        credential_store=KeychainCredentialStore(),
        interactive_sign_in=device_sign_in(environment),
    )


def device_sign_in(environment: Mapping[str, str] | None = None) -> DeviceAuthorization | None:
    """The terminal sign-in flow, when an issuer and a client are configured.

    ``None`` when either is absent, and the container turns that into a refusal
    naming the two variables. That is the honest shape for a local-first tool:
    `canon` is useful on a machine that has never heard of an identity service,
    so an unconfigured issuer is a command that is unavailable rather than an
    application that will not start — which is the opposite of the hosted
    service's rule, and deliberately so.

    The two endpoint addresses default to CyberdyneAuth's paths under the issuer
    and are overridable, because deriving an endpoint from an issuer is a
    convention rather than a guarantee.
    """
    source = os.environ if environment is None else environment
    issuer = source.get(ISSUER, "").strip().rstrip("/")
    client_id = source.get(CLIENT_ID, "").strip()
    if not issuer or not client_id:
        return None
    return DeviceAuthorization(
        endpoints=Endpoints(
            token=source.get(TOKEN_URL, "").strip() or f"{issuer}{TOKEN_PATH}",
            device_authorization=(
                source.get(DEVICE_CODE_URL, "").strip() or f"{issuer}{DEVICE_CODE_PATH}"
            ),
        ),
        client_id=client_id,
        audience=source.get(AUDIENCE, "").strip(),
    )


def file_fingerprints(root: Path) -> Fingerprinter:
    """What a specification file looks like right now, by `os.stat` (D8).

    Injected rather than reached for, because the core does no file-system work:
    the staleness comparison is the use case's, and the two numbers it compares
    are this function's.
    """

    def fingerprints(path: str) -> FileFingerprint | None:
        absolute = root / path
        if not absolute.is_file():
            return None
        stat = absolute.stat()
        return FileFingerprint(path=path, size=stat.st_size, mtime_ns=stat.st_mtime_ns)

    return fingerprints


def commit_authors(root: Path) -> AuthorSource:
    """Who has committed to this repository, for the unmapped-author list (D12)."""

    def authors() -> tuple[str, ...]:
        return revisions.authors(root)

    return authors


def preview_settings(declared: PreviewDefaults | None) -> PreviewSettings:
    """The project's decimation settings, falling back to the emitter's own."""
    if declared is None:
        return PreviewSettings()
    default = PreviewSettings()
    return PreviewSettings(
        ratio=declared.ratio if declared.ratio is not None else default.ratio,
        ceiling=declared.ceiling if declared.ceiling is not None else default.ceiling,
    )


__all__ = [
    "AUDIENCE",
    "CANON_DIR",
    "CLIENT_ID",
    "DEVICE_CODE_PATH",
    "DEVICE_CODE_URL",
    "ISSUER",
    "TOKEN_PATH",
    "TOKEN_URL",
    "build_container",
    "commit_authors",
    "device_sign_in",
    "file_fingerprints",
    "preview_settings",
]
