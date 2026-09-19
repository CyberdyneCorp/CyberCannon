"""Revisions, content hashes and staleness — the values a hosted read carries.

Three ideas, and each of them is a rule the hosted surface is specified in terms
of rather than a convenience:

* **A revision is what a read was served from.** D3 makes reads resolve content
  through the git object store at a pinned revision, so *which revision* stops
  being an implementation detail and becomes part of every answer:
  `hosted-repository` requires a response carrying specification content to name
  it.
* **A content hash is what an edit was composed against.** D5 makes conflict
  detection per file, by the digest of the bytes the editor started from, and
  D14 makes a blob's storage key the digest of its bytes. One value object, two
  uses, and they agree by construction — a re-mirrored blob lands on the key it
  had, and a re-read file conflicts exactly when somebody else touched it.
* **Staleness is arithmetic, not a status somebody sets.** A served revision
  knows when it was last confirmed against the remote; whether that is stale is
  a pure comparison against the configured interval, which is why it can be
  computed in the domain and stated on every read rather than surfaced by a
  separate endpoint nobody calls.

`hashlib` and `datetime` are standard library, so this module stays inside the
domain's import contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

DIGEST = "sha256"
"""The digest the whole system is addressed by. One algorithm, named in the key."""

BLOB_PREFIX = "blobs"
"""Where content-addressed objects live under the store's root."""

FANOUT = 2
"""How many leading hex characters become a directory, as git does it.

A flat namespace of a hundred thousand objects is a directory listing nobody can
use and, on some object stores, a hot prefix. Two characters is the convention
every tool that has faced the problem settled on.
"""


@dataclass(frozen=True)
class Revision:
    """One commit, as the repository identifies it.

    A value object rather than a bare `str` because it travels in responses
    beside paths, keys and identifiers, and because a read served from "the
    working tree" and one served from a revision are different things that must
    not be confusable.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValueError(f"revision {self.value!r} must be non-empty and unpadded")
        if any(character.isspace() for character in self.value):
            raise ValueError(f"revision {self.value!r} must not contain whitespace")

    @property
    def short(self) -> str:
        """The abbreviated form a person reads in a log line."""
        return self.value[:12]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ContentHash:
    """The digest of some bytes: a blob's key, and an edit's precondition (D5, D14).

    `value` is the hex digest without the algorithm prefix; :attr:`labelled`
    carries the algorithm, because a key that does not name its algorithm cannot
    be migrated to another one without rewriting every reference.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValueError(f"content hash {self.value!r} must be non-empty and unpadded")

    @classmethod
    def of(cls, content: bytes) -> ContentHash:
        """The digest of these bytes. The only way one is ever produced."""
        return cls(hashlib.new(DIGEST, content).hexdigest())

    @property
    def labelled(self) -> str:
        """`sha256:<hex>` — the digest with the algorithm that produced it."""
        return f"{DIGEST}:{self.value}"

    @property
    def short(self) -> str:
        return self.value[:12]

    def matches(self, content: bytes) -> bool:
        """Whether these bytes are the ones this hash was taken of."""
        return ContentHash.of(content) == self

    def __str__(self) -> str:
        return self.labelled


def blob_key(digest: ContentHash) -> str:
    """Where content with this digest is stored (D14).

    Derived from the digest and from nothing else — not the file name, not the
    asset, not the time of upload, not the order things were stored in. That is
    what makes mirroring idempotent, a rename free, and a re-mirror after total
    loss produce byte-identical keys.
    """
    return f"{BLOB_PREFIX}/{DIGEST}/{digest.value[:FANOUT]}/{digest.value[FANOUT:]}"


def digest_of_key(key: str) -> ContentHash | None:
    """The digest a key encodes, or ``None`` when the key is not one of ours.

    The inverse of :func:`blob_key`, and the reason a read can verify what it
    served: the key states what the bytes must hash to.
    """
    parts = key.split("/")
    if len(parts) != 4 or parts[0] != BLOB_PREFIX or parts[1] != DIGEST:
        return None
    return ContentHash(parts[2] + parts[3])


@dataclass(frozen=True)
class ServedRevision:
    """The revision reads are being served from, and when it was last confirmed.

    Both halves are required by `hosted-repository`: *"the response SHALL name
    the revision it was produced from"* and *"SHALL state when that revision was
    last confirmed against the remote"*. A failed refresh moves the second not
    at all, which is exactly how staleness becomes visible.
    """

    revision: Revision
    confirmed_at: datetime

    def age(self, now: datetime) -> timedelta:
        """How long since the remote last confirmed this revision."""
        return now - self.confirmed_at

    def may_be_stale(self, now: datetime, interval: timedelta) -> bool:
        """Whether the last successful refresh is older than the configured interval.

        *May be*, deliberately: the content is usually still current, and the
        thing that is certainly true is that nobody has checked recently. The
        response says the weaker, honest thing.
        """
        return self.age(now) > interval


__all__ = [
    "BLOB_PREFIX",
    "DIGEST",
    "FANOUT",
    "ContentHash",
    "Revision",
    "ServedRevision",
    "blob_key",
    "digest_of_key",
]
