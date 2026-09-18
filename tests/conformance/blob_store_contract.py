"""What every `BlobStore` SHALL do, whoever implements it (task 4.2).

A preview nobody can trace back to an export is a preview nobody can trust to be
current, so the association — asset id **and** source export — is the contract,
not a convenience. `FsBlobStore` (task 5.10) and `MinioBlobStore` later join by
adding a factory; the body below does not change.
"""

from __future__ import annotations

from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.preview import PreviewMesh

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
