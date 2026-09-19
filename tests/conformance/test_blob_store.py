"""Tasks 4.2, 5.10 and 7.1-7.5 — the `BlobStore` contract, every implementation.

The in-memory fake, `FsBlobStore` and `S3BlobStore`, through one contract body.
The association a preview has to record — asset id **and** source export — is
the same one asserted for all three, and so are the group 7 clauses: a bounded
link that refuses expiry and rewriting, and a digest check that reports
corruption rather than serving it.

`S3BlobStore` runs against **moto**, which is an in-process implementation of
the S3 API rather than a mock this repository wrote. That distinction is the
whole value: a hand-rolled double would agree with whatever the adapter happens
to do, and the errors this adapter has to classify — the several spellings of
*there is nothing there* — are exactly the ones a double would get wrong.

The `corrupt` fixture is per implementation on purpose. Producing bytes that do
not match their key is something only an accident does; `put` cannot, by
construction. So the suite stages it the way each store would actually be
damaged — a dictionary entry, a file on disk, an object written past the
adapter — and the contract asserts the same reporting for all three.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import boto3
import pytest
from blob_store_contract import BlobStoreContract
from contract import implementation_fixture
from moto import mock_aws

from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
from cybercanon.adapters.outbound.minio.blob_store import S3BlobStore
from cybercanon.application.testing.blob_store import InMemoryBlobStore

BUCKET = "cybercanon-blobs"
REGION = "us-east-1"


def in_memory(directory: Path) -> InMemoryBlobStore:
    return InMemoryBlobStore()


def filesystem(directory: Path) -> FsBlobStore:
    return FsBlobStore(directory / "blobs")


implementation = implementation_fixture(fake=in_memory, filesystem=filesystem)


@pytest.fixture
def corrupt(implementation) -> Callable[[str, bytes], None]:
    """Make the bytes at a key disagree with the digest that key states."""
    if isinstance(implementation, FsBlobStore):

        def damage(key: str, content: bytes) -> None:
            path = implementation.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        return damage

    def replace(key: str, content: bytes) -> None:
        implementation._blobs[key] = content

    return replace


class TestBlobStore(BlobStoreContract):
    """The contract, against the in-memory fake and `FsBlobStore`."""


# --------------------------------------------------------------------------
# The same contract, over a real S3 API (task 7.1)
# --------------------------------------------------------------------------


@pytest.fixture
def s3_store() -> Iterator[S3BlobStore]:
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name=REGION,
            aws_access_key_id="conformance",
            aws_secret_access_key="conformance",
        )
        client.create_bucket(Bucket=BUCKET)
        yield S3BlobStore(
            client,
            BUCKET,
            base_url="https://blobs.cyberdyne.example",
            secret=b"a-configured-link-signing-key",
        )


class TestS3BlobStore(BlobStoreContract):
    """The contract, against `S3BlobStore` over the S3 API."""

    @pytest.fixture
    def implementation(self, s3_store: S3BlobStore) -> S3BlobStore:
        return s3_store

    @pytest.fixture
    def corrupt(self, s3_store: S3BlobStore) -> Callable[[str, bytes], None]:
        def damage(key: str, content: bytes) -> None:
            s3_store._client.put_object(Bucket=s3_store.bucket, Key=key, Body=content)

        return damage
