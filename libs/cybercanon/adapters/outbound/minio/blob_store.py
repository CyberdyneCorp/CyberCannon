"""`S3BlobStore` — the blob mirror over the S3 API (MinIO in the deployment).

The mirror, and nothing more. *"Every stored blob SHALL correspond to content
that exists in, or is reproducible from, the project's repository"* — so this
adapter can put, read and bound access, and it has no opinion about **what**
belongs in it. That question is answered by the repository, in
:mod:`cybercanon.application.use_cases.blob_mirror`, which is what lets a view
removed from a specification stop being listed while its object is still sitting
here.

Four properties this implementation has to have, each a sentence of
`blob-storage`:

* **the key is the digest and nothing else** (D14) — derived by the domain's
  :func:`~cybercanon.domain.revisions.blob_key`, so identical content from two
  assets is one object, a rename is free, and a re-mirror after total loss lands
  on the keys it had before;
* **mirroring is idempotent** — a `put` of content already stored succeeds and
  changes nothing, because the bytes and the key are the same bytes and the same
  key;
* **an interrupted upload leaves nothing readable** — a single `PutObject` is
  atomic at the object store: the key resolves to the complete object or does
  not resolve. Multipart is deliberately not used here; an aborted multipart
  upload is exactly the partially-visible state the specification forbids, and
  the sizes this mirror holds — concept views, decimated preview meshes — do not
  need it;
* **bytes are never proxied** (D14). :meth:`link_for` issues a bounded link and
  :meth:`resolve_link` is what refuses an expired or rewritten one. Both use the
  port's shared shape rather than the object store's own presigning, for the
  reason the port states: the bound *is* the security property, and two stores
  that each presigned their own way would refuse differently. The objects are
  private; the bytes are served by the deployment's object-store edge, which
  verifies the signature this service issued.

`boto3` lives in this module and nowhere else, which is the ordinary rule: no
provider SDK outside the adapter.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

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

PREVIEWS = "previews"
SIDECAR_SUFFIX = ".json"
STORED_AT = "stored_at"
"""When a preview was stored, so "most recent" never depends on a clock we share."""

NOT_FOUND = ("404", "NoSuchKey", "NotFound")
"""How the S3 API says *there is nothing there*, across its several spellings."""


class S3BlobStore:
    """Blobs in one bucket, keyed by the digest of their bytes."""

    def __init__(
        self,
        client: Any,
        bucket: str,
        *,
        base_url: str = "",
        secret: bytes = b"",
        prefix: str = "",
    ) -> None:
        """Wrap an already-built S3 client.

        The client is injected rather than constructed here because the
        composition root owns configuration: endpoint, credential and region are
        environment, and an adapter that read them would be a second place
        configuration comes from.
        """
        self._client = client
        self._bucket = bucket
        self._base_url = base_url or f"s3://{bucket}"
        self._secret = secret or os.urandom(32)
        self._prefix = prefix.strip("/")

    @property
    def bucket(self) -> str:
        return self._bucket

    # -- previews --------------------------------------------------------

    def put_preview(
        self,
        asset_id: str,
        source_export: str,
        preview: PreviewMesh,
        *,
        source_digest: ContentHash | None = None,
    ) -> StoredPreview:
        """Store the preview and the record saying which export it came from."""
        record = StoredPreview(
            key=preview_key(asset_id, source_export, source_digest),
            asset_id=asset_id,
            source_export=source_export,
            size_bytes=preview.size_bytes,
            content_type=preview.content_type,
        )
        self._put(record.key, preview.content, record.content_type)
        sidecar = {
            "key": record.key,
            "asset_id": record.asset_id,
            "source_export": record.source_export,
            "size_bytes": record.size_bytes,
            "content_type": record.content_type,
            STORED_AT: self._next_ordinal(asset_id),
        }
        self._put(
            record.key + SIDECAR_SUFFIX,
            json.dumps(sidecar, indent=2).encode("utf-8"),
            "application/json",
        )
        return record

    def preview_for(self, asset_id: str) -> StoredPreview | None:
        """The most recently stored preview for that asset, read back from its sidecar."""
        sidecars = sorted(
            (
                stored
                for stored in map(self._sidecar, self._keys_under(f"{PREVIEWS}/{asset_id}/"))
                if stored is not None
            ),
            key=lambda stored: stored.get(STORED_AT, 0),
        )
        return _record(sidecars[-1]) if sidecars else None

    # -- content-addressed blobs (D14) -----------------------------------

    def put(self, content: bytes, *, content_type: str = OCTET_STREAM) -> StoredBlob:
        """Store bytes under the key their digest derives. One atomic request."""
        digest = ContentHash.of(content)
        key = blob_key(digest)
        self._put(key, content, content_type)
        return StoredBlob(
            key=key, digest=digest, size_bytes=len(content), content_type=content_type
        )

    def read(self, key: str) -> bytes | None:
        """The bytes behind a stored key, or ``None`` when nothing is stored there."""
        try:
            answer = self._client.get_object(Bucket=self._bucket, Key=self._at(key))
        except Exception as failure:
            if _is_absent(failure):
                return None
            raise
        return answer["Body"].read()

    def exists(self, key: str) -> bool:
        """Whether a complete object is readable at that key."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._at(key))
        except Exception as failure:
            if _is_absent(failure):
                return False
            raise
        return True

    def verified(self, key: str) -> bytes:
        """The bytes at that key, checked against the digest the key states."""
        return verified_bytes(key, self.read(key))

    def link_for(self, key: str, *, expires_at: datetime) -> SignedLink:
        """A bounded link to exactly that one object, issued only if it is there."""
        if not self.exists(key):
            raise BlobNotStored(key)
        return signed_link(
            base_url=self._base_url, key=key, expires_at=expires_at, secret=self._secret
        )

    def resolve_link(self, url: str, *, now: datetime) -> str:
        """The key a link grants right now, or a refusal — expired, or rewritten."""
        return verify_link(url, secret=self._secret, now=now)

    # -- operations the mirror needs --------------------------------------

    def empty(self) -> None:
        """Remove every object. The total loss `blob-storage` requires recovery from."""
        for key in self._keys_under(""):
            self._client.delete_object(Bucket=self._bucket, Key=self._at(key))

    # -- internals -------------------------------------------------------

    def _put(self, key: str, content: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=self._at(key), Body=content, ContentType=content_type
        )

    def _at(self, key: str) -> str:
        """The object name for a store key, under this store's prefix if it has one."""
        return f"{self._prefix}/{key}" if self._prefix else key

    def _keys_under(self, prefix: str) -> tuple[str, ...]:
        """Every store key under that prefix, with this store's own prefix removed."""
        paginator = self._client.get_paginator("list_objects_v2")
        found: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._at(prefix)):
            found.extend(entry["Key"] for entry in page.get("Contents", ()))
        offset = len(self._prefix) + 1 if self._prefix else 0
        return tuple(name[offset:] for name in found)

    def _sidecar(self, key: str) -> dict[str, Any] | None:
        """One preview sidecar as raw fields, or ``None`` when the key is not one."""
        if not key.endswith(SIDECAR_SUFFIX):
            return None
        content = self.read(key)
        if content is None:
            return None
        try:
            stored = json.loads(content.decode("utf-8"))
        except ValueError:
            return None
        return stored if isinstance(stored, dict) and "key" in stored else None

    def _next_ordinal(self, asset_id: str) -> int:
        """How many previews this asset already has — a monotonic "most recent".

        Counting rather than stamping, because two stores that disagreed about
        the time would disagree about which preview is current, and the only
        thing `preview_for` needs is an order.
        """
        return sum(
            1 for key in self._keys_under(f"{PREVIEWS}/{asset_id}/") if key.endswith(SIDECAR_SUFFIX)
        )


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
    return source_export.rsplit("/", 1)[-1]


def _record(stored: dict[str, Any]) -> StoredPreview:
    """The port's record, rebuilt from the sidecar written beside the blob."""
    return StoredPreview(
        key=str(stored["key"]),
        asset_id=str(stored.get("asset_id", "")),
        source_export=str(stored.get("source_export", "")),
        size_bytes=int(stored.get("size_bytes", 0)),
        content_type=str(stored.get("content_type", GLB_CONTENT_TYPE)),
    )


def _is_absent(failure: Exception) -> bool:
    """Whether this is the S3 API saying *there is nothing there*.

    Read off the response rather than matched on a class, because the SDK raises
    a dynamically built exception type and a store that caught the type would
    stop catching it the day the client is swapped.
    """
    response = getattr(failure, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {})
    return str(error.get("Code", "")) in NOT_FOUND


__all__ = ["NOT_FOUND", "PREVIEWS", "S3BlobStore", "preview_key"]
