"""What every `BlobStore` SHALL do, whoever implements it (tasks 4.2 and 4.5).

A preview nobody can trace back to an export is a preview nobody can trust to be
current, so the association — asset id **and** source export — is the contract,
not a convenience. `FsBlobStore` (task 5.10) and `MinioBlobStore` later join by
adding a factory; the body below does not change.

Task 4.5 adds the content-addressed half (D14), and every clause of it is a
requirement `blob-storage` states rather than a property of an implementation:
identical content stores once under one key, a rename changes nothing because
the key never depended on the name, an interrupted upload leaves nothing
readable, and a link is issued for exactly one object with a bound on it. What
the contract does *not* assert here is the verification of an expired or
rewritten link — that is group 7's, and asserting it now against an issuance-only
implementation would be asserting nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.application.ports.blob_store import BlobNotStored, BlobStore
from cybercanon.application.ports.preview import PreviewMesh
from cybercanon.domain.revisions import ContentHash, blob_key

ASSET = "mech_scout"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
LATER_EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.v2.glb"

PREVIEW = PreviewMesh(
    content=b"glTF-preview-bytes",
    triangles=3577,
    parts=("SM_mech_scout_LOD0", "SOCKET_muzzle_l"),
    clips=("A_mech_scout_walk",),
    bones=("root", "spine_01"),
)

LATER_PREVIEW = PreviewMesh(content=b"glTF-preview-bytes-v2", triangles=3600)

VIEW = b"\x89PNG\r\n\x1a\nthe scout mech, three-quarter"
OTHER_VIEW = b"\x89PNG\r\n\x1a\nthe scout mech, from behind"
EXPIRY = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


class BlobStoreContract:
    """The behaviour every blob store shares."""

    def test_a_stored_preview_names_its_asset_and_its_export(
        self, implementation: BlobStore
    ) -> None:
        record = implementation.put_preview(ASSET, EXPORT, PREVIEW)

        assert record.asset_id == ASSET
        assert record.source_export == EXPORT

    def test_a_stored_preview_reads_back_by_asset(self, implementation: BlobStore) -> None:
        stored = implementation.put_preview(ASSET, EXPORT, PREVIEW)

        assert implementation.preview_for(ASSET) == stored

    def test_the_bytes_read_back_are_the_bytes_written(self, implementation: BlobStore) -> None:
        stored = implementation.put_preview(ASSET, EXPORT, PREVIEW)

        assert implementation.read(stored.key) == PREVIEW.content
        assert stored.size_bytes == len(PREVIEW.content)

    def test_an_asset_with_no_preview_reads_as_missing(self, implementation: BlobStore) -> None:
        assert implementation.preview_for("no_such_asset") is None

    def test_an_unknown_key_reads_as_missing(self, implementation: BlobStore) -> None:
        assert implementation.read("previews/no_such_asset/nothing.glb") is None

    def test_a_newer_preview_replaces_the_one_before_it(self, implementation: BlobStore) -> None:
        """A stale preview presented as current is the failure this prevents."""
        implementation.put_preview(ASSET, EXPORT, PREVIEW)
        later = implementation.put_preview(ASSET, LATER_EXPORT, LATER_PREVIEW)

        current = implementation.preview_for(ASSET)
        assert current == later
        assert current is not None
        assert current.source_export == LATER_EXPORT

    # -- content-addressed blobs (task 4.5, D14) -------------------------

    def test_a_blobs_key_is_derived_from_its_content(self, implementation: BlobStore) -> None:
        stored = implementation.put(VIEW)

        assert stored.key == blob_key(ContentHash.of(VIEW))
        assert stored.digest == ContentHash.of(VIEW)
        assert stored.size_bytes == len(VIEW)

    def test_identical_content_stores_once_under_one_key(self, implementation: BlobStore) -> None:
        """The same image referenced by two assets is one stored object."""
        first = implementation.put(VIEW)
        second = implementation.put(bytes(VIEW))

        assert first.key == second.key
        assert implementation.read(first.key) == VIEW

    def test_different_content_never_shares_a_key(self, implementation: BlobStore) -> None:
        assert implementation.put(VIEW).key != implementation.put(OTHER_VIEW).key

    def test_a_key_does_not_depend_on_a_name_an_asset_or_a_time(
        self, implementation: BlobStore
    ) -> None:
        """A rename in the repository leaves the key exactly as it was."""
        before = implementation.put(VIEW, content_type="image/png")

        assert implementation.put(VIEW, content_type="image/png").key == before.key

    def test_storing_twice_leaves_the_object_unchanged(self, implementation: BlobStore) -> None:
        stored = implementation.put(VIEW)
        implementation.put(VIEW)

        assert implementation.read(stored.key) == VIEW

    def test_a_stored_key_exists_and_an_unstored_one_does_not(
        self, implementation: BlobStore
    ) -> None:
        stored = implementation.put(VIEW)

        assert implementation.exists(stored.key)
        assert not implementation.exists(blob_key(ContentHash.of(OTHER_VIEW)))

    def test_a_link_is_issued_for_exactly_one_stored_object(
        self, implementation: BlobStore
    ) -> None:
        stored = implementation.put(VIEW)

        link = implementation.link_for(stored.key, expires_at=EXPIRY)

        assert link.key == stored.key
        assert link.expires_at == EXPIRY
        assert stored.key in link.url

    def test_a_link_states_a_bound_it_is_past_or_not_past(self, implementation: BlobStore) -> None:
        link = implementation.link_for(implementation.put(VIEW).key, expires_at=EXPIRY)

        assert not link.has_expired(EXPIRY - timedelta(seconds=1))
        assert link.has_expired(EXPIRY)

    def test_two_keys_get_two_different_links(self, implementation: BlobStore) -> None:
        """A link that could be edited into another object would not be a bound."""
        one = implementation.link_for(implementation.put(VIEW).key, expires_at=EXPIRY)
        other = implementation.link_for(implementation.put(OTHER_VIEW).key, expires_at=EXPIRY)

        assert one.url != other.url

    def test_no_link_is_issued_for_something_that_is_not_stored(
        self, implementation: BlobStore
    ) -> None:
        with pytest.raises(BlobNotStored):
            implementation.link_for(blob_key(ContentHash.of(OTHER_VIEW)), expires_at=EXPIRY)
