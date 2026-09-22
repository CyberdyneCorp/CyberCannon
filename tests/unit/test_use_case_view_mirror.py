"""Tasks 3.4 and 3.5 — the mirror pass, and rebuilding it from the repository.

The claim `concept-ingestion` makes is *"deleting every mirrored object and
every thumbnail and rebuilding SHALL restore every view"*, and the only way to
believe it is to delete them and rebuild. That is what the drill below does, and
it compares the content hashes on both sides rather than counting objects —
restoring *something* is not the requirement.
"""

from __future__ import annotations

import pytest

from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.ingest_views import UploadedImage
from cybercanon.application.use_cases.view_mirror import mirror_views, views_at
from cybercanon.domain.revisions import ContentHash, blob_key
from views_world import PROJECT, SCOUT, SCOUT_DIR, SCOUT_SPEC, a_spec, a_world, with_asset

pytestmark = pytest.mark.unit

MULE = "mule"
MULE_SPEC = f"vehicles/{MULE}/asset.yaml"


def a_project_with_twelve_views():
    """Four assets, three slots each — a project a recovery is worth running on."""
    world = a_world(
        {
            SCOUT_SPEC: a_spec(),
            MULE_SPEC: a_spec(MULE, "Mule"),
            "props/crate/asset.yaml": a_spec("crate", "Crate"),
            "props/barrel/asset.yaml": a_spec("barrel", "Barrel"),
        }
    )
    for index, asset_id in enumerate((SCOUT, MULE, "crate", "barrel")):
        uploads = tuple(
            UploadedImage(slot=slot, content=world.an_image(seed=index * 10 + offset))
            for offset, slot in enumerate(("front", "side", "back"))
        )
        ran(world.ingest(asset_id=asset_id, uploads=uploads))
    return world


def test_the_repository_is_what_says_which_views_a_project_has() -> None:
    """Not `asset.yaml`, not the index — the deterministic path and the tree (D4)."""
    world = with_asset()
    ran(world.ingest(uploads=(world.upload(),)))

    located = views_at(
        PROJECT,
        world.host.head(PROJECT),
        repository_host=world.host,
        spec_store=world.spec_store,
    )

    assert [(view.asset_id, str(view.slot)) for view in located] == [(SCOUT, "front")]
    assert located[0].path == f"{SCOUT_DIR}/concept/front.png"


def test_a_file_that_is_not_a_view_is_not_one() -> None:
    world = a_world({SCOUT_SPEC: a_spec(), f"{SCOUT_DIR}/exports/front.png": b"an export"})

    located = views_at(
        PROJECT,
        world.host.head(PROJECT),
        repository_host=world.host,
        spec_store=world.spec_store,
    )

    assert located == ()


def test_mirroring_stores_every_view_under_its_content_hash() -> None:
    world = a_project_with_twelve_views()

    report = ran(
        mirror_views(
            PROJECT,
            repository_host=world.host,
            spec_store=world.spec_store,
            blob_store=world.blobs,
            view_index=world.index,
        )
    )

    assert len(report.mirrored) == 12
    for entry in report.mirrored:
        assert entry.key == blob_key(entry.digest)
        assert world.blobs.exists(entry.key)


def test_re_running_the_mirror_writes_nothing_new() -> None:
    """*"Mirroring content that is already stored SHALL succeed without re-uploading."*"""
    world = a_project_with_twelve_views()
    first = ran(
        mirror_views(
            PROJECT,
            repository_host=world.host,
            spec_store=world.spec_store,
            blob_store=world.blobs,
        )
    )

    second = ran(
        mirror_views(
            PROJECT,
            repository_host=world.host,
            spec_store=world.spec_store,
            blob_store=world.blobs,
        )
    )

    assert second.wrote_nothing
    assert second.keys == first.keys


def test_deleting_every_object_and_rebuilding_restores_every_view_unchanged() -> None:
    """The drill: twelve views, an emptied store, and the same hashes afterwards."""
    world = a_project_with_twelve_views()
    before = ran(
        mirror_views(
            PROJECT,
            repository_host=world.host,
            spec_store=world.spec_store,
            blob_store=world.blobs,
            thumbnail_renderer=world.renderer,
        )
    )
    world.blobs.empty()
    world.index.clear()
    assert world.stored_keys() == ()

    after = ran(
        mirror_views(
            PROJECT,
            repository_host=world.host,
            spec_store=world.spec_store,
            blob_store=world.blobs,
            view_index=world.index,
            thumbnail_renderer=world.renderer,
        )
    )

    assert after.keys == before.keys
    assert len(after.mirrored) == 12
    assert after.thumbnails == before.thumbnails > 0
    assert all(world.blobs.exists(key) for key in after.keys.values())


def test_the_rebuild_restores_the_hash_to_view_rows_too() -> None:
    world = a_project_with_twelve_views()
    world.index.clear()

    ran(
        mirror_views(
            PROJECT,
            repository_host=world.host,
            spec_store=world.spec_store,
            blob_store=world.blobs,
            view_index=world.index,
        )
    )

    rows = world.index.rows_for(PROJECT, SCOUT)
    assert [row.slot for row in rows] == ["back", "front", "side"]
    assert all(row.digest == ContentHash(row.digest.value) for row in rows)


def test_thumbnails_are_re_derived_and_never_written_into_the_repository() -> None:
    world = a_project_with_twelve_views()
    files_before = dict(world.host.remote_files(PROJECT))

    report = ran(
        mirror_views(
            PROJECT,
            repository_host=world.host,
            spec_store=world.spec_store,
            blob_store=world.blobs,
            thumbnail_renderer=world.renderer,
        )
    )

    assert report.thumbnails == 24  # two sizes per view
    assert world.host.remote_files(PROJECT) == files_before
