"""Building the real container: the one place an outbound adapter is named (D11).

:mod:`cybercanon.adapters.wiring.container` holds ports; this module chooses the
implementations. The split is structural, not stylistic — an inbound adapter
imports the container type, and if that type's module reached an outbound
adapter the CLI would acquire an import of `trimesh` through the layering
contract D10 forbids. So every concrete class in this change is named exactly
once, below.

Nothing here decides anything about an asset. It reads the project
configuration to learn what preview emission should aim for — a configuration
value, per D7 — and hands three adapters to the container.
"""

from __future__ import annotations

from pathlib import Path

from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.gltf_preview import PreviewSettings
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.spec_store import PreviewDefaults

CANON_DIR = ".canon"
"""Derived blobs live beside the configuration, inside the repository."""


def build_container(root: str | Path) -> Container:
    """The container an inbound adapter runs against, over a working copy.

    `root` is any path inside the repository — the working directory a person
    ran `canon` in is the ordinary case. The spec store resolves the repository
    root from it, and every other adapter is anchored to that same root, so two
    surfaces run against the same files whichever directory they started in.
    """
    spec_store = GitSpecStore(root)
    settings = preview_settings(spec_store.load_project("").preview)
    return Container(
        spec_store=spec_store,
        mesh_inspector=TrimeshInspector(root=spec_store.root, settings=settings),
        blob_store=FsBlobStore(spec_store.root / CANON_DIR),
    )


def preview_settings(declared: PreviewDefaults | None) -> PreviewSettings:
    """The project's decimation settings, falling back to the emitter's own."""
    if declared is None:
        return PreviewSettings()
    default = PreviewSettings()
    return PreviewSettings(
        ratio=declared.ratio if declared.ratio is not None else default.ratio,
        ceiling=declared.ceiling if declared.ceiling is not None else default.ceiling,
    )


__all__ = ["CANON_DIR", "build_container", "preview_settings"]
