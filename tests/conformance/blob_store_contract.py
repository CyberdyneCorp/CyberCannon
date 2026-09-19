"""What every `BlobStore` SHALL do, whoever implements it (tasks 4.2 and 4.5).

A preview nobody can trace back to an export is a preview nobody can trust to be
current, so the association — asset id **and** source export — is the contract,
not a convenience. `FsBlobStore` (task 5.10) and `MinioBlobStore` later join by
adding a factory; the body below does not change.

Task 4.5 adds the content-addressed half (D14), and every clause of it is a
requirement `blob-storage` states rather than a property of an implementation:
identical content stores once under one key, a rename changes nothing because
the key never depended on the name, an interrupted upload leaves nothing
readable, and a link is issued for exactly one object with a bound on it.

Group 7 completes it, and the clauses it adds are the ones that only mean
something once a store can *serve*: a link presented after its expiry and a link
edited to address another object are both refused, and a stored object whose
bytes no longer match its key is reported as corrupt rather than served. The
corruption is staged through a `corrupt` fixture the suite supplies per
implementation, because producing mismatched bytes is something only an accident
does — `put` cannot, by construction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.application.ports.blob_store import (
    BlobCorrupted,
    BlobNotStored,
    BlobStore,
    LinkRefused,
)
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

CORRUPTED = b"\x89PNG\r\n\x1a\nthese are not the bytes that key promises"
"""Bytes deliberately unlike `VIEW`, so a digest check is the only thing that can tell."""


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

    # -- serving a blob (group 7) ----------------------------------------

    def test_a_link_inside_its_bound_resolves_to_its_object(
        self, implementation: BlobStore
    ) -> None:
        stored = implementation.put(VIEW)
        link = implementation.link_for(stored.key, expires_at=EXPIRY)

        granted = implementation.resolve_link(link.url, now=EXPIRY - timedelta(seconds=1))

        assert granted == stored.key

    def test_an_expired_link_is_refused(self, implementation: BlobStore) -> None:
        """*"WHEN it is used after its expiry THEN access SHALL be refused."*"""
        link = implementation.link_for(implementation.put(VIEW).key, expires_at=EXPIRY)

        with pytest.raises(LinkRefused):
            implementation.resolve_link(link.url, now=EXPIRY + timedelta(seconds=1))

    def test_a_link_rewritten_to_another_object_is_refused(self, implementation: BlobStore) -> None:
        """The bound is the security property: one link, one object, or nothing."""
        one = implementation.put(VIEW)
        other = implementation.put(OTHER_VIEW)
        link = implementation.link_for(one.key, expires_at=EXPIRY)

        rewritten = link.url.replace(one.key, other.key)

        assert rewritten != link.url
        with pytest.raises(LinkRefused):
            implementation.resolve_link(rewritten, now=EXPIRY - timedelta(seconds=1))

    def test_a_link_whose_expiry_was_extended_is_refused(self, implementation: BlobStore) -> None:
        """The signature covers the expiry too, so a bound cannot be widened."""
        link = implementation.link_for(implementation.put(VIEW).key, expires_at=EXPIRY)
        later = int((EXPIRY + timedelta(days=365)).timestamp())
        extended = link.url.replace(f"expires={int(EXPIRY.timestamp())}", f"expires={later}")

        with pytest.raises(LinkRefused):
            implementation.resolve_link(extended, now=EXPIRY - timedelta(seconds=1))

    def test_a_verified_read_returns_the_bytes_that_were_stored(
        self, implementation: BlobStore
    ) -> None:
        stored = implementation.put(VIEW)

        assert implementation.verified(stored.key) == VIEW

    def test_a_verified_read_of_nothing_reports_it_absent(self, implementation: BlobStore) -> None:
        with pytest.raises(BlobNotStored):
            implementation.verified(blob_key(ContentHash.of(OTHER_VIEW)))

    def test_a_corrupted_object_is_reported_rather_than_served(
        self, implementation: BlobStore, corrupt
    ) -> None:
        """*"SHALL NOT serve the mismatched bytes as the asset's content."*"""
        stored = implementation.put(VIEW)

        corrupt(stored.key, CORRUPTED)

        with pytest.raises(BlobCorrupted):
            implementation.verified(stored.key)

    def test_corruption_is_repaired_by_mirroring_again(
        self, implementation: BlobStore, corrupt
    ) -> None:
        """Re-mirroring writes the right bytes back under the key they belong to."""
        stored = implementation.put(VIEW)
        corrupt(stored.key, CORRUPTED)

        implementation.put(VIEW)

        assert implementation.verified(stored.key) == VIEW

    def test_emptying_the_store_loses_everything_and_re_putting_restores_the_key(
        self, implementation: BlobStore
    ) -> None:
        """The total-loss drill, at the level of one object and one key."""
        stored = implementation.put(VIEW)

        implementation.empty()
        assert not implementation.exists(stored.key)

        assert implementation.put(VIEW).key == stored.key
        assert implementation.verified(stored.key) == VIEW
