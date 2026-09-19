"""Tasks 7.1-7.6 — the blob mirror, over a real working copy and a real S3 API.

The port conformance suite already holds the in-memory fake, `FsBlobStore` and
`S3BlobStore` to one behaviour, and the BDD steps bind every scenario of
`blob-storage`. What is left is what only a real repository and a real object
store can show, and it is the claim the whole capability rests on:

* **7.1** identical content referenced by two assets is one stored object, and a
  rename in the repository changes no key — asserted by renaming a file in a
  real git repository and mirroring again;
* **7.2** mirroring what is already there succeeds and changes nothing;
* **7.3** the recovery drill: empty the bucket, re-mirror from the working copy,
  and find every view, export and preview mesh readable again **under the key it
  had before**;
* **7.4** an object damaged in the bucket is reported as corrupt rather than
  served, and re-mirroring repairs it;
* **7.5** a link is issued only after the authorization decision, and is refused
  once expired or once edited to address another object;
* **7.6** content with no repository source is refused, and a view removed from
  the repository stops being listed while its object is still sitting there.

`moto` provides the S3 API in process. It is not a double this repository wrote:
the several spellings of *there is nothing there* that the adapter has to
classify are exactly the thing a hand-rolled double would agree with by
construction and get wrong in production.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from staged_project import (
    EXPORT,
    FRONT,
    MULE_SHARED,
    PALETTE,
    PROJECT,
    SCOUT_EXPORT,
    SCOUT_FRONT,
    SCOUT_SHARED,
    SCOUT_SPEC,
    Staged,
    ready,
)

from cybercanon.adapters.outbound.minio.blob_store import S3BlobStore
from cybercanon.application.ports.blob_store import BlobCorrupted, LinkRefused
from cybercanon.application.ports.preview import PreviewMesh
from cybercanon.application.results import Forbidden, Invalid, Ok, Unavailable
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.blob_mirror import (
    DerivedPreview,
    accept_blob,
    link_to_blob,
    mirror_project,
    views_of,
)
from cybercanon.domain.identity import Actor, ActorId
from cybercanon.domain.revisions import ContentHash, blob_key

pytestmark = pytest.mark.integration

BUCKET = "cybercanon-blobs"
REGION = "us-east-1"

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
EXPIRY = NOON + timedelta(minutes=5)

RAFA = Actor(id=ActorId("auth|rafa"), display_name="Rafa", projects=(PROJECT,))
OUTSIDER = Actor(id=ActorId("auth|outsider"), display_name="Outsider", projects=())

PREVIEW = PreviewMesh(content=b"glTF-preview-bytes", triangles=3577)
EXPORTS = {"mech_scout": (SCOUT_EXPORT,)}
PREVIEWS = (DerivedPreview(asset_id="mech_scout", source_export=SCOUT_EXPORT, mesh=PREVIEW),)


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    return ready(tmp_path)


@pytest.fixture
def blobs() -> Iterator[S3BlobStore]:
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name=REGION,
            aws_access_key_id="integration",
            aws_secret_access_key="integration",
        )
        client.create_bucket(Bucket=BUCKET)
        yield S3BlobStore(
            client,
            BUCKET,
            base_url="https://blobs.cyberdyne.example",
            secret=b"a-configured-link-signing-key",
        )


def mirror(staged: Staged, blobs: S3BlobStore, *, previews=PREVIEWS):
    report = mirror_project(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        blob_store=blobs,
        exports=EXPORTS,
        previews=previews,
    )
    assert isinstance(report, Ok), report
    return report.value


# --------------------------------------------------------------------------
# 7.1 — content addressing, over real files
# --------------------------------------------------------------------------


def test_one_image_referenced_by_two_assets_is_one_stored_object(
    staged: Staged, blobs: S3BlobStore
) -> None:
    report = mirror(staged, blobs)

    keys = report.keys
    assert keys[SCOUT_SHARED] == keys[MULE_SHARED] == blob_key(ContentHash.of(PALETTE))
    assert blobs.verified(keys[SCOUT_SHARED]) == PALETTE


def test_a_rename_in_the_repository_leaves_the_key_where_it_was(
    staged: Staged, blobs: S3BlobStore
) -> None:
    """The key never depended on the name, so a rename costs nothing at all."""
    before = mirror(staged, blobs).keys[SCOUT_FRONT]
    renamed = "characters/mech_scout/concept/hero.png"
    staged.commit_outside(SCOUT_FRONT, None, "rename the front view")
    staged.commit_outside(renamed, FRONT, "rename the front view")
    staged.commit_outside(
        SCOUT_SPEC,
        staged.host.read(PROJECT, SCOUT_SPEC, staged.host.head(PROJECT)).replace(
            SCOUT_FRONT.encode(), renamed.encode()
        ),
        "point the spec at the renamed view",
    )
    staged.host.fetch(PROJECT, confirmed_at=NOON)

    after = mirror(staged, blobs).keys

    assert after[renamed] == before
    assert SCOUT_FRONT not in after


def test_the_mirror_holds_every_view_and_export_the_repository_describes(
    staged: Staged, blobs: S3BlobStore
) -> None:
    report = mirror(staged, blobs)

    assert set(report.keys) == {SCOUT_FRONT, SCOUT_SHARED, MULE_SHARED, SCOUT_EXPORT}
    assert report.is_complete


# --------------------------------------------------------------------------
# 7.2 — idempotent, and never partially visible
# --------------------------------------------------------------------------


def test_mirroring_again_changes_nothing(staged: Staged, blobs: S3BlobStore) -> None:
    first = mirror(staged, blobs)

    second = mirror(staged, blobs)

    assert second.keys == first.keys
    assert blobs.verified(second.keys[SCOUT_EXPORT]) == EXPORT


def test_a_view_the_repository_does_not_have_is_reported_not_invented(
    tmp_path: Path, blobs: S3BlobStore
) -> None:
    """A missing file lands in `missing`, and the pass keeps going."""
    staged = ready(tmp_path)
    staged.commit_outside(SCOUT_FRONT, None, "delete the front view without editing the spec")
    staged.host.fetch(PROJECT, confirmed_at=NOON)

    report = mirror(staged, blobs)

    assert [source.path for source in report.missing] == [SCOUT_FRONT]
    assert SCOUT_SHARED in report.keys


def test_an_upload_that_fails_leaves_nothing_readable_at_its_key(blobs: S3BlobStore) -> None:
    """*"An upload that fails or is interrupted SHALL leave no readable object."*

    One `PutObject` and no multipart, so there is no half-uploaded state for the
    key to resolve to: the request either completes or the object is not there.
    Staged by making the request itself fail.
    """
    key = blob_key(ContentHash.of(PALETTE))
    failing = _refusing_client(blobs)

    with pytest.raises(ConnectionError):
        failing.put(PALETTE)

    assert not blobs.exists(key)
    assert blobs.read(key) is None


def _refusing_client(blobs: S3BlobStore) -> S3BlobStore:
    """The same store over a client whose upload never completes."""

    class Dropped:
        def __getattr__(self, name: str):
            raise ConnectionError("the connection dropped mid-upload")

    return S3BlobStore(Dropped(), blobs.bucket)


# --------------------------------------------------------------------------
# 7.3 — total loss, and recovery under the same keys
# --------------------------------------------------------------------------


def test_emptying_the_store_and_re_mirroring_restores_every_key(
    staged: Staged, blobs: S3BlobStore
) -> None:
    """`blob-storage`: *"each SHALL resolve under the key it had before."*"""
    before = mirror(staged, blobs)

    blobs.empty()
    assert not any(blobs.exists(key) for key in before.keys.values())

    after = mirror(staged, blobs)

    assert after.keys == before.keys
    assert all(blobs.verified(key) for key in after.keys.values())


def test_the_preview_mesh_comes_back_too(staged: Staged, blobs: S3BlobStore) -> None:
    before = mirror(staged, blobs)

    blobs.empty()
    after = mirror(staged, blobs)

    assert blobs.preview_for("mech_scout") == before.previews[0]
    assert after.previews[0].key == before.previews[0].key
    assert blobs.read(after.previews[0].key) == PREVIEW.content


def test_a_blob_not_yet_re_mirrored_is_temporarily_unavailable(
    staged: Staged, blobs: S3BlobStore
) -> None:
    """Not *"this asset has no such view"* — the repository still describes it."""
    mirror(staged, blobs)
    blobs.empty()

    outcome = link_to_blob(
        RAFA,
        PROJECT,
        SCOUT_FRONT,
        repository_host=staged.host,
        blob_store=blobs,
        expires_at=EXPIRY,
    )

    assert isinstance(outcome, Unavailable)
    assert refused(outcome).identifier == "blob.not_mirrored"
    listed = ran(
        views_of(
            PROJECT,
            SCOUT_SPEC,
            repository_host=staged.host,
            spec_store=staged.spec_store(),
            blob_store=blobs,
        )
    )
    assert [view.path for view in listed] == [SCOUT_FRONT, SCOUT_SHARED]
    assert not any(view.stored for view in listed)


# --------------------------------------------------------------------------
# 7.4 — corruption is reported, and repaired by re-mirroring
# --------------------------------------------------------------------------


def test_a_corrupted_object_is_reported_rather_than_served(
    staged: Staged, blobs: S3BlobStore
) -> None:
    key = mirror(staged, blobs).keys[SCOUT_FRONT]
    _damage(blobs, key)

    with pytest.raises(BlobCorrupted):
        blobs.verified(key)


def test_re_mirroring_repairs_a_corrupted_object(staged: Staged, blobs: S3BlobStore) -> None:
    key = mirror(staged, blobs).keys[SCOUT_FRONT]
    _damage(blobs, key)

    mirror(staged, blobs)

    assert blobs.verified(key) == FRONT


# --------------------------------------------------------------------------
# 7.5 — bounded, single-object links, issued after the decision
# --------------------------------------------------------------------------


def test_a_link_is_issued_and_resolves_inside_its_bound(staged: Staged, blobs: S3BlobStore) -> None:
    key = mirror(staged, blobs).keys[SCOUT_FRONT]

    link = ran(
        link_to_blob(
            RAFA,
            PROJECT,
            SCOUT_FRONT,
            repository_host=staged.host,
            blob_store=blobs,
            expires_at=EXPIRY,
        )
    )

    assert link.key == key
    assert blobs.resolve_link(link.url, now=NOON) == key


def test_an_expired_link_is_refused(staged: Staged, blobs: S3BlobStore) -> None:
    mirror(staged, blobs)
    link = ran(
        link_to_blob(
            RAFA,
            PROJECT,
            SCOUT_FRONT,
            repository_host=staged.host,
            blob_store=blobs,
            expires_at=EXPIRY,
        )
    )

    with pytest.raises(LinkRefused):
        blobs.resolve_link(link.url, now=EXPIRY + timedelta(seconds=1))


def test_a_link_rewritten_to_another_object_is_refused(staged: Staged, blobs: S3BlobStore) -> None:
    keys = mirror(staged, blobs).keys
    link = ran(
        link_to_blob(
            RAFA,
            PROJECT,
            SCOUT_FRONT,
            repository_host=staged.host,
            blob_store=blobs,
            expires_at=EXPIRY,
        )
    )

    rewritten = link.url.replace(link.key, keys[SCOUT_SHARED])

    assert blobs.exists(keys[SCOUT_SHARED])
    with pytest.raises(LinkRefused):
        blobs.resolve_link(rewritten, now=NOON)


def test_no_link_is_issued_to_an_actor_who_may_not_read_the_asset(
    staged: Staged, blobs: S3BlobStore
) -> None:
    mirror(staged, blobs)

    outcome = link_to_blob(
        OUTSIDER,
        PROJECT,
        SCOUT_FRONT,
        repository_host=staged.host,
        blob_store=blobs,
        expires_at=EXPIRY,
    )

    assert isinstance(outcome, Forbidden)
    assert refused(outcome).identifier == "project.read_refused"


# --------------------------------------------------------------------------
# 7.6 — the repository decides what there is
# --------------------------------------------------------------------------


def test_content_with_no_repository_source_is_refused(staged: Staged, blobs: S3BlobStore) -> None:
    outcome = accept_blob(
        PROJECT,
        b"\x89PNG\r\n\x1a\na painting nobody committed",
        repository_host=staged.host,
        path="characters/mech_scout/concept/never_committed.png",
    )

    assert isinstance(outcome, Invalid)
    assert refused(outcome).identifier == "blob.no_repository_source"


def test_content_that_disagrees_with_the_repository_is_refused(
    staged: Staged, blobs: S3BlobStore
) -> None:
    """A real path is not a source; the same *bytes* at that path are."""
    outcome = accept_blob(PROJECT, PALETTE, repository_host=staged.host, path=SCOUT_FRONT)

    assert isinstance(outcome, Invalid)


def test_content_the_repository_holds_is_accepted_under_its_content_key(
    staged: Staged, blobs: S3BlobStore
) -> None:
    accepted = ran(accept_blob(PROJECT, FRONT, repository_host=staged.host, path=SCOUT_FRONT))

    assert accepted.key == blob_key(ContentHash.of(FRONT))


def test_a_view_removed_from_the_repository_stops_being_listed(
    staged: Staged, blobs: S3BlobStore
) -> None:
    """Its object stays in the bucket, and the bucket gets no vote."""
    key = mirror(staged, blobs).keys[SCOUT_FRONT]
    staged.commit_outside(SCOUT_FRONT, None, "remove the front view")
    staged.host.fetch(PROJECT, confirmed_at=NOON)

    listed = ran(
        views_of(
            PROJECT,
            SCOUT_SPEC,
            repository_host=staged.host,
            spec_store=staged.spec_store(),
            blob_store=blobs,
        )
    )

    assert [view.path for view in listed] == [SCOUT_SHARED]
    assert blobs.exists(key)


def _damage(blobs: S3BlobStore, key: str) -> None:
    """Write bytes that do not hash to their key — what only an accident does."""
    blobs._client.put_object(
        Bucket=blobs.bucket, Key=key, Body=b"\x89PNG\r\n\x1a\nnot those bytes at all"
    )
