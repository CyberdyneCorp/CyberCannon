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

from pathlib import Path

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


def build_container(root: str | Path) -> Container:
    """The container an inbound adapter runs against, over a working copy.

    `root` is any path inside the repository — the working directory a person
    ran `canon` in is the ordinary case, and the directory an agent client was
    pointed at is the other. The spec store resolves the repository root from
    it, and every other adapter is anchored to that same root, so two surfaces
    run against the same files whichever directory they started in.

    No credential is configured here, and that is the specified behaviour rather
    than an omission: the resolver's chain ends in a local unauthenticated actor
    (D4), so every read works with no identity, no network and no services. The
    CyberdyneAuth adapter becomes the chain's first link in a later change,
    without touching anything else.
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
    "CANON_DIR",
    "build_container",
    "commit_authors",
    "file_fingerprints",
    "preview_settings",
]
