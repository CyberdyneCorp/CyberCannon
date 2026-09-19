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
from datetime import UTC, datetime
from typing import Protocol

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.preview import PreviewMesh, StoredPreview
from cybercanon.domain.revisions import BLOB_PREFIX, ContentHash, digest_of_key

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


class BlobCorrupted(OperationFailed):
    """The stored bytes do not hash to what the key says they must.

    *"the service SHALL report it as corrupt rather than serve content that does
    not match"*. Unavailable rather than not-found, and deliberately: the object
    is there, the repository can produce it again, and re-mirroring is the
    documented repair — so the condition resolves without the caller changing
    anything about the request.
    """

    kind = FailureKind.UNAVAILABLE
    identifier = "blob.corrupt"

    def __init__(self, key: str) -> None:
        super().__init__(
            f"the object stored at {key!r} does not match the digest its key states; "
            "re-mirror the project to repair it",
            key,
        )
        self.key = key


class LinkRefused(OperationFailed):
    """A link that has expired, was altered, or was never issued by this store.

    One failure for all three, on purpose: *"an expired link SHALL be refused"*
    and *"a link ... modified to address a different stored object"* SHALL be
    refused, and a caller learning **which** of the two it was would be learning
    something about objects it was never granted.
    """

    kind = FailureKind.FORBIDDEN
    identifier = "blob.link_refused"

    def __init__(self, reason: str = "the link is not valid for this object") -> None:
        super().__init__(f"access was refused: {reason}")
        self.reason = reason


EXPIRES = "expires"
SIGNATURE = "signature"
"""The two query parameters a link carries. Both are covered by the signature."""


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
    signature = link_signature(key, stamp, secret)
    separator = "" if base_url.endswith("/") or not base_url else "/"
    return SignedLink(
        url=f"{base_url}{separator}{key}?{EXPIRES}={stamp}&{SIGNATURE}={signature}",
        key=key,
        expires_at=expires_at,
    )


def link_signature(key: str, stamp: int, secret: bytes) -> str:
    """The signature over one key and one expiry. Neither can move without it."""
    return hmac.new(secret, f"{key}:{stamp}".encode(), hashlib.sha256).hexdigest()


def verify_link(url: str, *, secret: bytes, now: datetime) -> str:
    """The key this link grants, or :class:`LinkRefused`.

    The counterpart of :func:`signed_link`, and here for the same reason it is:
    the bound *is* the security property, so it is checked in one place rather
    than by each store. Three ways to be refused and they all read the same from
    outside — a signature that does not cover this key and this expiry (which is
    what "rewritten to another object" produces), an expiry in the past, and a
    link that is not one of ours at all.
    """
    address, _, query = url.partition("?")
    parameters = dict(pair.partition("=")[::2] for pair in query.split("&") if pair)
    key = _key_of(address)
    stamp = parameters.get(EXPIRES, "")
    signature = parameters.get(SIGNATURE, "")
    if not key or not stamp.isdigit():
        raise LinkRefused("the link is malformed")
    if not hmac.compare_digest(signature, link_signature(key, int(stamp), secret)):
        raise LinkRefused("the link's signature does not cover this object")
    if now >= datetime.fromtimestamp(int(stamp), tz=UTC):
        raise LinkRefused("the link has expired")
    return key


def _key_of(address: str) -> str:
    """The stored key an address names, or the empty string when it names none.

    Derived from the address rather than trusted from a parameter: a link whose
    key travelled beside the bytes it addresses could be pointed at one object
    and signed for another.

    Every place the address could begin a key is tried, and the one that parses
    as a key wins — because a base URL is free to contain the word `blobs`
    itself, and `memory://blobs/blobs/sha256/...` is not a hypothetical: the
    in-memory store's base URL ends in exactly that.
    """
    marker = f"{BLOB_PREFIX}/"
    starts = [index for index in range(len(address)) if address.startswith(marker, index)]
    for candidate in (address[index:] for index in (*starts, 0)):
        if digest_of_key(candidate) is not None:
            return candidate
    return ""


def verified_bytes(key: str, content: bytes | None) -> bytes:
    """These bytes, if they are the ones the key says they are.

    Shared rather than written per store for the reason every other shared
    helper here exists: the check *is* the requirement, and a store that
    implemented it slightly differently would serve mismatched content on
    exactly one deployment.

    A key that encodes no digest — a preview, keyed by its asset and the export
    it came from — has nothing to check against and is returned as it is. That
    is stated rather than hidden: content addressing is what makes verification
    possible, and a key that is not content-addressed cannot be verified by
    anything.
    """
    if content is None:
        raise BlobNotStored(key)
    digest = digest_of_key(key)
    if digest is not None and not digest.matches(content):
        raise BlobCorrupted(key)
    return content


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

    def resolve_link(self, url: str, *, now: datetime) -> str:
        """The key a link grants right now, or :class:`LinkRefused`.

        The other half of `link_for`, and the half that makes the bound real: an
        expired link and a link edited to address another object are both
        refused here, by the store that issued it.
        """
        ...

    def verified(self, key: str) -> bytes:
        """The bytes at that key, checked against the digest the key states.

        Raises :class:`BlobNotStored` when nothing is there and
        :class:`BlobCorrupted` when what is there does not match — *"SHALL NOT
        serve the mismatched bytes as the asset's content"*. Every read that
        reaches a caller goes through here; `read` stays the raw accessor the
        mirror itself uses.
        """
        ...


__all__ = [
    "EXPIRES",
    "OCTET_STREAM",
    "SIGNATURE",
    "BlobCorrupted",
    "BlobNotStored",
    "BlobStore",
    "LinkRefused",
    "SignedLink",
    "StoredBlob",
    "link_signature",
    "signed_link",
    "verified_bytes",
    "verify_link",
]
