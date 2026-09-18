"""Tasks 4.2 and 5.10 — the `BlobStore` contract against every implementation.

`MinioBlobStore` joins with one more factory when a networked surface exists;
the association it has to record — asset id **and** source export — is the same
one asserted here, which is the point of running the fake and the real adapter
through one body.
"""

from __future__ import annotations

from pathlib import Path

from blob_store_contract import BlobStoreContract
from contract import implementation_fixture

from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
from cybercanon.application.testing.blob_store import InMemoryBlobStore


def in_memory(directory: Path) -> InMemoryBlobStore:
    return InMemoryBlobStore()


def filesystem(directory: Path) -> FsBlobStore:
    return FsBlobStore(directory / "blobs")


implementation = implementation_fixture(fake=in_memory, real=filesystem)


class TestBlobStore(BlobStoreContract):
    """The `BlobStore` contract, against the in-memory fake and `FsBlobStore`."""
