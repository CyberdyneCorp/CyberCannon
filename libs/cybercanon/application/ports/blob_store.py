"""The `BlobStore` port — where previews and other derived blobs live.

`FsBlobStore` now, `MinioBlobStore` when a networked surface exists. It is the
one port in the validation path that is allowed to be a remote service, which is
exactly why nothing in that path may depend on it succeeding: preview emission
is guarded (D7), and validation itself never touches it.

A stored preview records the asset and the export it came from, because a
preview nobody can trace back to an export is a preview nobody can trust to be
current.
"""

from __future__ import annotations

from typing import Protocol

from cybercanon.application.ports.preview import PreviewMesh, StoredPreview


class BlobStore(Protocol):
    """Stores derived blobs, keyed by what they were derived from."""

    def put_preview(self, asset_id: str, source_export: str, preview: PreviewMesh) -> StoredPreview:
        """Store a preview against its asset and the export it came from."""
        ...

    def preview_for(self, asset_id: str) -> StoredPreview | None:
        """The most recently stored preview for that asset, or ``None``."""
        ...

    def read(self, key: str) -> bytes | None:
        """The bytes behind a stored key, or ``None`` when nothing is stored there."""
        ...


__all__ = ["BlobStore"]
