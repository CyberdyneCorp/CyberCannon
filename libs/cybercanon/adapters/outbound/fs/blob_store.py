"""`FsBlobStore` — previews on disk, each recording the export it came from.

The association is the requirement, not a convenience: a preview nobody can
trace back to an export is a preview nobody can trust to be current, and a stale
preview presented as current is exactly the "it passed on my machine" class of
confusion one layer down. So every stored preview writes two files — the blob
and a sidecar recording its asset and its source export — and `preview_for`
reads the association back rather than inferring it from a filename.

Sidecars rather than one index file: two validations running at once would race
on a shared index, and a directory of self-describing records rebuilds from
itself. The current preview for an asset is the most recently written sidecar in
its directory, which is a fact on disk rather than a pointer that can rot.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path, PurePosixPath

from cybercanon.application.ports.blob_store import (
    OCTET_STREAM,
    BlobNotStored,
    SignedLink,
    StoredBlob,
    signed_link,
    verified_bytes,
    verify_link,
)
from cybercanon.application.ports.preview import GLB_CONTENT_TYPE, PreviewMesh, StoredPreview
from cybercanon.domain.revisions import ContentHash, blob_key

SIDECAR_SUFFIX = ".json"
PREVIEWS = "previews"
STORED_AT = "stored_at"
"""When the sidecar was written, so "most recent" never depends on a file clock."""


class FsBlobStore:
    """Blobs under a root directory, keyed exactly as a remote store would key them."""

    def __init__(self, root: str | Path, *, base_url: str = "file://", secret: bytes = b"") -> None:
        self._root = Path(root)
        self._base_url = base_url
        self._secret = secret or os.urandom(32)

    @property
    def root(self) -> Path:
        return self._root

    def put_preview(
        self,
        asset_id: str,
        source_export: str,
        preview: PreviewMesh,
        *,
        source_digest: ContentHash | None = None,
    ) -> StoredPreview:
        """Write the preview and the record that says where it came from."""
        record = StoredPreview(
            key=preview_key(asset_id, source_export, source_digest),
            asset_id=asset_id,
            source_export=source_export,
            size_bytes=preview.size_bytes,
            content_type=preview.content_type,
        )
        path = self._path(record.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(preview.content)
        sidecar = {**asdict(record), STORED_AT: time.time_ns()}
        self._sidecar(path).write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        return record

    def preview_for(self, asset_id: str) -> StoredPreview | None:
        """The most recently stored preview for that asset, read back off disk."""
        directory = self._root / PREVIEWS / asset_id
        stored = sorted(
            (
                sidecar
                for sidecar in map(_sidecar_contents, directory.glob(f"*{SIDECAR_SUFFIX}"))
                if sidecar is not None
            ),
            key=lambda sidecar: sidecar.get(STORED_AT, 0),
        )
        return _record(stored[-1]) if stored else None

    def read(self, key: str) -> bytes | None:
        """The bytes behind a stored key, or ``None`` when nothing is stored there."""
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    # -- content-addressed blobs (D14) -----------------------------------

    def put(self, content: bytes, *, content_type: str = OCTET_STREAM) -> StoredBlob:
        """Store bytes under the key their digest derives, atomically.

        Written to a temporary name in the same directory and then renamed, so
        an interrupted upload leaves nothing readable at the key: a key either
        resolves to complete, correct content or does not resolve at all.
        """
        digest = ContentHash.of(content)
        key = blob_key(digest)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f"{path.name}.partial")
        partial.write_bytes(content)
        partial.replace(path)
        return StoredBlob(
            key=key, digest=digest, size_bytes=len(content), content_type=content_type
        )

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def link_for(self, key: str, *, expires_at: datetime) -> SignedLink:
        if not self.exists(key):
            raise BlobNotStored(key)
        return signed_link(
            base_url=self._base_url, key=key, expires_at=expires_at, secret=self._secret
        )

    def empty(self) -> None:
        """Lose every blob — the total loss `blob-storage` requires recovery from."""
        if self._root.is_dir():
            shutil.rmtree(self._root)

    def resolve_link(self, url: str, *, now: datetime) -> str:
        return verify_link(url, secret=self._secret, now=now)

    def verified(self, key: str) -> bytes:
        """The bytes at that key, checked against the digest the key states."""
        return verified_bytes(key, self.read(key))

    def _path(self, key: str) -> Path:
        return self._root / PurePosixPath(key)

    def _sidecar(self, path: Path) -> Path:
        return path.with_name(path.name + SIDECAR_SUFFIX)


def preview_key(asset_id: str, source_export: str, source_digest: ContentHash | None = None) -> str:
    """Where a preview of that export is stored. Deterministic, and traceable.

    Keyed by the export's content digest when the caller knows it (G1), so a
    re-mirror after total loss lands the preview on the key it had and two runs
    over the same bytes never produce two objects. Without a digest the key
    carries the export's file name, which is what a local run has and is still
    enough for two exports of one asset not to overwrite each other.
    """
    stem = source_digest.value if source_digest is not None else _name(source_export)
    return f"{PREVIEWS}/{asset_id}/{stem}.preview.glb"


def _name(source_export: str) -> str:
    return PurePosixPath(source_export).name


def _sidecar_contents(sidecar: Path) -> dict[str, object] | None:
    """One sidecar as raw fields, or ``None`` when it is not one this store wrote."""
    try:
        stored = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return stored if isinstance(stored, dict) and "key" in stored else None


def _record(stored: dict[str, object]) -> StoredPreview:
    """The port's record, rebuilt from what was written beside the blob."""
    return StoredPreview(
        key=str(stored["key"]),
        asset_id=str(stored.get("asset_id", "")),
        source_export=str(stored.get("source_export", "")),
        size_bytes=int(stored.get("size_bytes", 0)),
        content_type=str(stored.get("content_type", GLB_CONTENT_TYPE)),
    )


__all__ = ["FsBlobStore", "preview_key"]
