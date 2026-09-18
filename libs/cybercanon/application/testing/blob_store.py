"""The in-memory `BlobStore` — previews in a dict, with their source recorded.

`FsBlobStore` and, later, `MinioBlobStore` store the same association: a preview
belongs to an asset **and** to the export it was derived from, so a consumer can
tell which export a preview represents and whether it is current.

`fail_with` makes this the network-capable fake of task 4.9: the blob store is
the one port in the validation path that will one day be a remote service, and
the guarantee is that validation and compilation complete unchanged while it is
raising on every call.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from cybercanon.application.ports.preview import PreviewMesh, StoredPreview


class InMemoryBlobStore:
    """Blobs keyed exactly as the real store keys them."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}
        self._previews: dict[str, StoredPreview] = {}
        self._failure: Exception | None = None

    def fail_with(self, error: Exception | None) -> None:
        """Make every call raise — the unreachable remote service, on demand."""
        self._failure = error

    def put_preview(self, asset_id: str, source_export: str, preview: PreviewMesh) -> StoredPreview:
        self._raise_if_configured()
        record = StoredPreview(
            key=preview_key(asset_id, source_export),
            asset_id=asset_id,
            source_export=source_export,
            size_bytes=preview.size_bytes,
            content_type=preview.content_type,
        )
        self._blobs[record.key] = preview.content
        self._previews[asset_id] = record
        return record

    def preview_for(self, asset_id: str) -> StoredPreview | None:
        self._raise_if_configured()
        return self._previews.get(asset_id)

    def read(self, key: str) -> bytes | None:
        self._raise_if_configured()
        return self._blobs.get(key)

    def _raise_if_configured(self) -> None:
        if self._failure is not None:
            raise self._failure


def preview_key(asset_id: str, source_export: str) -> str:
    """Where a preview of that export is stored. Deterministic, and traceable."""
    return f"previews/{asset_id}/{PurePosixPath(source_export).name}.preview.glb"


__all__ = ["InMemoryBlobStore", "preview_key"]
