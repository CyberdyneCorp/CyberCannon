"""The in-memory `BlobStore` — previews in a dict, with their source recorded.

`FsBlobStore` and, later, `MinioBlobStore` store the same association: a preview
belongs to an asset **and** to the export it was derived from, so a consumer can
tell which export a preview represents and whether it is current.

It answers the content-addressed half of the port too (D14): `put` keys by
digest through the domain's own derivation, `exists` is true only for a complete
object, and `link_for` issues the same bounded link shape the real store issues,
through the same helper — so a suite that passes here is asserting the contract
rather than this dictionary.

`fail_with` makes this the network-capable fake of task 4.9: the blob store is
the one port in the validation path that will one day be a remote service, and
the guarantee is that validation and compilation complete unchanged while it is
raising on every call.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath

from cybercanon.application.ports.blob_store import (
    OCTET_STREAM,
    BlobNotStored,
    SignedLink,
    StoredBlob,
    signed_link,
    verified_bytes,
    verify_link,
)
from cybercanon.application.ports.preview import PreviewMesh, StoredPreview
from cybercanon.domain.revisions import ContentHash, blob_key


class InMemoryBlobStore:
    """Blobs keyed exactly as the real store keys them."""

    BASE_URL = "memory://blobs"
    SECRET = b"in-memory-signing-key"

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}
        self._previews: dict[str, StoredPreview] = {}
        self._types: dict[str, str] = {}
        self._failure: Exception | None = None

    def fail_with(self, error: Exception | None) -> None:
        """Make every call raise — the unreachable remote service, on demand."""
        self._failure = error

    def put_preview(
        self,
        asset_id: str,
        source_export: str,
        preview: PreviewMesh,
        *,
        source_digest: ContentHash | None = None,
    ) -> StoredPreview:
        self._raise_if_configured()
        record = StoredPreview(
            key=preview_key(asset_id, source_export, source_digest),
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

    # -- content-addressed blobs (D14) -----------------------------------

    def put(self, content: bytes, *, content_type: str = OCTET_STREAM) -> StoredBlob:
        """Store bytes under the key their digest derives. Idempotent by construction."""
        self._raise_if_configured()
        digest = ContentHash.of(content)
        key = blob_key(digest)
        self._blobs[key] = content
        self._types.setdefault(key, content_type)
        return StoredBlob(
            key=key,
            digest=digest,
            size_bytes=len(content),
            content_type=self._types[key],
        )

    def exists(self, key: str) -> bool:
        self._raise_if_configured()
        return key in self._blobs

    def link_for(self, key: str, *, expires_at: datetime) -> SignedLink:
        self._raise_if_configured()
        if key not in self._blobs:
            raise BlobNotStored(key)
        return signed_link(
            base_url=self.BASE_URL, key=key, expires_at=expires_at, secret=self.SECRET
        )

    def resolve_link(self, url: str, *, now: datetime) -> str:
        return verify_link(url, secret=self.SECRET, now=now)

    def verified(self, key: str) -> bytes:
        self._raise_if_configured()
        return verified_bytes(key, self._blobs.get(key))

    def empty(self) -> None:
        """Lose every blob — the total loss `blob-storage` requires recovery from.

        An operation rather than a test reaching into the dictionary, because
        the recovery drill the specification asks for is *"the blob store is
        emptied and re-mirroring runs"*, and a drill that could only be staged
        by one implementation would not be a drill.
        """
        self._blobs.clear()
        self._previews.clear()
        self._types.clear()

    def _raise_if_configured(self) -> None:
        if self._failure is not None:
            raise self._failure


def preview_key(asset_id: str, source_export: str, source_digest: ContentHash | None = None) -> str:
    """Where a preview of that export is stored. Deterministic, and traceable.

    Keyed by the export's content digest when the caller knows it (G1), so a
    re-mirror after total loss lands the preview on the key it had and two runs
    over the same bytes never produce two objects. Without a digest the key
    carries the export's file name, which is what a local run has and is still
    enough for two exports of one asset not to overwrite each other.
    """
    stem = source_digest.value if source_digest is not None else _name(source_export)
    return f"previews/{asset_id}/{stem}.preview.glb"


def _name(source_export: str) -> str:
    return PurePosixPath(source_export).name


__all__ = ["InMemoryBlobStore", "preview_key"]
