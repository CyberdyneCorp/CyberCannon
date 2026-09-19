"""The `BlobStore` port — where previews and mirrored blobs live.

`FsBlobStore` now, `MinioBlobStore` when the hosted surface has one. It is the
one port in the validation path that is allowed to be a remote service, which is
exactly why nothing in that path may depend on it succeeding: preview emission
is guarded (D7), and validation itself never touches it.

Two halves, and they arrived in that order:

* **previews**, keyed by the asset and the export they came from, because a
  preview nobody can trace back to an export is a preview nobody can trust to be
  current;
* **content-addressed blobs** (D14), keyed by the digest of their bytes and
  read through a short-lived signed link rather than proxied. Content addressing
  is what makes mirroring idempotent, a rename free, and a re-mirror after total
  loss produce identical keys — which is what lets `blob-storage` state recovery
  as *"readable again under the same keys"* instead of as a hope.

The key derivation is not this port's to choose: it is
:func:`cybercanon.domain.revisions.blob_key` over the digest, in the domain,
where the two implementations cannot disagree about it.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.preview import PreviewMesh, StoredPreview
from cybercanon.domain.revisions import ContentHash

OCTET_STREAM = "application/octet-stream"
"""What content whose type nobody stated is stored as."""


@dataclass(frozen=True)
class StoredBlob:
    """A blob in the store: where it is, what it hashes to, how big it is.

    `key` is derived from `digest` and from nothing else, so two assets
    referencing the same image resolve to one stored object and a rename resolves
    to the same key it had.
    """

    key: str
    digest: ContentHash
    size_bytes: int
    content_type: str = OCTET_STREAM


@dataclass(frozen=True)
class SignedLink:
    """Time-limited read access to exactly one stored object (D14).

    `key` travels with the link because the bound is part of what was issued:
    the link is for one object and cannot be altered into a link for another.
    `expires_at` is absolute rather than a duration so that an issued link does
    not quietly become longer-lived by being passed around.
    """

    url: str
    key: str
    expires_at: datetime

    def has_expired(self, now: datetime) -> bool:
        """Whether this link is past its bound."""
        return now >= self.expires_at


class BlobNotStored(OperationFailed):
    """Nothing is stored under that key — so no link is issued for it.

    `blob-storage` requires a blob that is absent to be *reported* rather than
    fabricated, and requires an asset whose view is temporarily unreachable not
    to be described as having no such view.
    """

    kind = FailureKind.NOT_FOUND
    identifier = "blob.not_stored"

    def __init__(self, key: str) -> None:
        super().__init__(f"no object is stored under {key!r}", key)
        self.key = key


def signed_link(*, base_url: str, key: str, expires_at: datetime, secret: bytes) -> SignedLink:
    """Build the one link shape every blob store issues (D14).

    Here rather than in each implementation for the same reason
    :func:`~cybercanon.domain.revisions.blob_key` is in the domain: two stores
    that each invented a link shape would eventually bound them differently, and
    the bound *is* the security property. The signature covers the key and the
    expiry together, so neither can be edited without invalidating it — which is
    what makes a link *"valid for exactly one stored object"* and unable to be
    *"altered into a link for another"*.
    """
    stamp = int(expires_at.timestamp())
    signature = hmac.new(secret, f"{key}:{stamp}".encode(), hashlib.sha256).hexdigest()
    separator = "" if base_url.endswith("/") or not base_url else "/"
    return SignedLink(
        url=f"{base_url}{separator}{key}?expires={stamp}&signature={signature}",
        key=key,
        expires_at=expires_at,
    )


class BlobStore(Protocol):
    """Stores derived blobs and content-addressed mirrors of repository content."""

    def put_preview(self, asset_id: str, source_export: str, preview: PreviewMesh) -> StoredPreview:
        """Store a preview against its asset and the export it came from."""
        ...

    def preview_for(self, asset_id: str) -> StoredPreview | None:
        """The most recently stored preview for that asset, or ``None``."""
        ...

    def read(self, key: str) -> bytes | None:
        """The bytes behind a stored key, or ``None`` when nothing is stored there."""
        ...

    def put(self, content: bytes, *, content_type: str = OCTET_STREAM) -> StoredBlob:
        """Store these bytes under the key their digest derives (D14).

        Idempotent by construction: storing content that is already there
        produces the same key and leaves the stored object unchanged.
        """
        ...

    def exists(self, key: str) -> bool:
        """Whether a complete object is readable at that key.

        Complete is the word that matters: an interrupted upload leaves nothing
        readable, so a key either resolves to correct content or does not
        resolve.
        """
        ...

    def link_for(self, key: str, *, expires_at: datetime) -> SignedLink:
        """A signed, time-limited link to exactly that one object.

        Raises :class:`BlobNotStored` when nothing is there. Issuing it is the
        caller's decision to make *after* the authorization decision that governs
        the owning asset — this port grants no access of its own, it only bounds
        the access the caller decided to give.
        """
        ...


__all__ = [
    "OCTET_STREAM",
    "BlobNotStored",
    "BlobStore",
    "SignedLink",
    "StoredBlob",
    "signed_link",
]
