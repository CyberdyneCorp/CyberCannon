"""Groups 2, 3 and 7 — the ingestion use case, over fakes and with no git.

The order D2 fixes is what every test below is really about: **validate → stage
→ commit → mirror → derive**. A failure before the commit has nothing to undo,
and a failure after it has nothing to undo either, so "neither a partial commit
nor an orphan blob" is asserted as a property of the arrangement rather than of
a cleanup routine.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import timedelta

import pytest

from cybercanon.application.ports.repository_host import FileChange
from cybercanon.application.ports.spec_store import IngestionDefaults, ProjectConfig
from cybercanon.application.results import Conflict, Forbidden, Invalid
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.ingest_views import (
    DEFAULT_ASSET_ROOT,
    UploadedImage,
    limits_of,
    minimal_specification,
)
from cybercanon.application.use_cases.view_revisions import (
    DEFAULT_FRESHNESS_INTERVAL,
    aspect_tolerance_of,
    freshness_interval_of,
)
from cybercanon.domain.asset import AssetId
from cybercanon.domain.revisions import ContentHash, blob_key
from cybercanon.domain.views import DEFAULT_ASPECT_TOLERANCE, IngestionLimits
from views_world import ANA, PROJECT, RAFA, SCOUT, SCOUT_DIR, SCOUT_SPEC, a_world, with_asset

pytestmark = pytest.mark.unit

MEGABYTE = 1024 * 1024
FRONT = f"{SCOUT_DIR}/concept/front.png"
SIDE = f"{SCOUT_DIR}/concept/side.png"
BACK = f"{SCOUT_DIR}/concept/back.png"


# --------------------------------------------------------------------------
# 1.3 — the limits a project declares, merged with the defaults
# --------------------------------------------------------------------------


def test_a_project_that_declares_nothing_gets_the_defaults() -> None:
    assert limits_of(ProjectConfig()) == IngestionLimits()
    assert limits_of(ProjectConfig(ingestion=IngestionDefaults())) == IngestionLimits()


def test_each_declared_limit_overrides_and_the_rest_fall_back() -> None:
    declared = IngestionDefaults(accepted_formats=("png",), max_dimension=16384)

    limits = limits_of(ProjectConfig(ingestion=declared))

    assert limits.accepted_formats == ("png",)
    assert limits.max_dimension == 16384
    assert limits.max_bytes == IngestionLimits().max_bytes


def test_the_freshness_interval_and_the_tolerance_are_configuration() -> None:
    declared = IngestionDefaults(freshness_seconds=90, aspect_tolerance=0.05)
    project = ProjectConfig(ingestion=declared)

    assert freshness_interval_of(project) == timedelta(seconds=90)
    assert aspect_tolerance_of(project) == 0.05
    assert freshness_interval_of(ProjectConfig()) == DEFAULT_FRESHNESS_INTERVAL
    assert aspect_tolerance_of(ProjectConfig()) == DEFAULT_ASPECT_TOLERANCE


def test_a_configured_limit_is_what_an_upload_is_measured_against() -> None:
    """The merge is not decoration: it reaches the refusal."""
    world = with_asset()
    world.spec_store.config = ProjectConfig(ingestion=IngestionDefaults(accepted_formats=("webp",)))
    world.limits = limits_of(world.spec_store.load_project(""))

    refusal = refused(world.ingest(uploads=(world.upload(content=world.an_image("png")),)))

    assert "webp" in refusal.message
    assert "PNG" in refusal.message


# --------------------------------------------------------------------------
# 2.4 — attribution is a precondition (D5)
# --------------------------------------------------------------------------


def test_an_unmapped_person_is_refused_before_any_image_is_inspected() -> None:
    """*"No mapping, no ingestion"*, and the refusal names the missing entry."""
    world = with_asset()
    upload = world.upload()

    refusal = refused(world.ingest(uploads=(upload,), author=None, subject="auth|newcomer"))

    assert isinstance(refusal, Forbidden)
    assert ".canon/actors.yaml" in refusal.message
    assert "auth|newcomer" in refusal.message
    assert world.inspector.inspected == []
    assert world.files() == {SCOUT_SPEC: world.files()[SCOUT_SPEC]}
    assert world.stored_keys() == ()


def test_the_commit_is_authored_by_the_acting_person() -> None:
    world = with_asset()

    ran(world.ingest(uploads=(world.upload(),)))

    assert world.commits()[-1].author == RAFA


def test_a_second_person_commits_as_herself() -> None:
    """Attribution is the argument, never a default the use case invented."""
    world = with_asset()

    ran(world.ingest(uploads=(world.upload(),), author=ANA))

    assert world.commits()[-1].author == ANA


def test_an_agent_mediated_upload_records_the_person_and_the_agent() -> None:
    world = with_asset()

    ran(world.ingest(uploads=(world.upload(),), agent="blender-agent"))

    commit = world.commits()[-1]
    assert commit.author == RAFA
    assert "blender-agent" in commit.message


# --------------------------------------------------------------------------
# 2.5 — one request, one commit (D2)
# --------------------------------------------------------------------------


def test_three_slots_in_one_request_produce_exactly_one_commit() -> None:
    world = with_asset()
    before = len(world.commits())
    uploads = tuple(
        UploadedImage(slot=slot, content=world.an_image(seed=index))
        for index, slot in enumerate(("front", "side", "back"))
    )

    outcome = ran(world.ingest(uploads=uploads))

    assert len(world.commits()) == before + 1
    assert set(world.commits()[-1].paths) == {FRONT, SIDE, BACK}
    assert set(outcome.paths) == {FRONT, SIDE, BACK}


def test_the_commit_message_names_the_asset_and_every_slot() -> None:
    world = with_asset()
    uploads = tuple(
        UploadedImage(slot=slot, content=world.an_image(seed=index))
        for index, slot in enumerate(("front", "side"))
    )

    outcome = ran(world.ingest(uploads=uploads))

    assert SCOUT in outcome.commit_message
    assert "front" in outcome.commit_message and "side" in outcome.commit_message


def test_a_replacement_writes_the_same_path_and_is_a_revision() -> None:
    world = with_asset()
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))

    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=2)),)))

    assert [path for path in world.files() if path.startswith(f"{SCOUT_DIR}/concept")] == [FRONT]
    assert len(ran(world.revisions()).revisions) == 2


def test_a_format_change_renames_rather_than_leaving_two_files() -> None:
    """D4: history follows the slot, so the old path goes in the same commit."""
    world = with_asset()
    ran(world.ingest(uploads=(world.upload(content=world.an_image("png")),)))

    ran(world.ingest(uploads=(world.upload(content=world.an_image("webp")),)))

    concept = sorted(path for path in world.files() if "/concept/" in path)
    assert concept == [f"{SCOUT_DIR}/concept/front.webp"]


# --------------------------------------------------------------------------
# 2.6, 2.7 — creating an asset, and never moving its status (D10)
# --------------------------------------------------------------------------


def test_an_upload_naming_an_unknown_asset_creates_a_minimal_specification() -> None:
    world = a_world()

    outcome = ran(world.ingest(uploads=(world.upload(),), name="Scout Mech"))

    created = f"{DEFAULT_ASSET_ROOT}/{SCOUT}/asset.yaml"
    assert outcome.created_asset
    assert created in world.files()
    written = world.files()[created].decode()
    assert "design" not in written and "constraints" not in written
    assert "status: concept" in written


def test_the_created_specification_and_the_image_are_in_one_commit() -> None:
    world = a_world()

    ran(world.ingest(uploads=(world.upload(),)))

    paths = set(world.commits()[-1].paths)
    assert f"{DEFAULT_ASSET_ROOT}/{SCOUT}/asset.yaml" in paths
    assert f"{DEFAULT_ASSET_ROOT}/{SCOUT}/concept/front.png" in paths


def test_the_minimal_specification_declares_identity_and_status_and_nothing_else() -> None:
    written = minimal_specification(AssetId(SCOUT), "Scout Mech").decode()

    assert written.splitlines() == [
        "schema_version: 1",
        f"id: {SCOUT}",
        "name: Scout Mech",
        "status: concept",
    ]


def test_an_invalid_asset_identifier_creates_nothing() -> None:
    world = a_world()

    refusal = refused(world.ingest(asset_id="mech scout", uploads=(world.upload(),)))

    assert isinstance(refusal, Invalid)
    assert "mech scout" in refusal.message
    assert world.files() == {}


@pytest.mark.parametrize("status", ["concept", "modeling", "validated"])
def test_ingestion_never_changes_an_assets_status(status: str) -> None:
    world = with_asset(status=status)

    ran(world.ingest(uploads=(world.upload(),)))

    assert f"status: {status}" in world.files()[SCOUT_SPEC].decode()


def test_an_existing_specifications_authored_content_is_untouched() -> None:
    authored = (
        b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"
        b"constraints:\n  tri_budget: 12000\n"
        b"  required_sockets: [SOCKET_muzzle_l, SOCKET_muzzle_r]\n"
    )
    world = a_world({SCOUT_SPEC: authored})

    ran(world.ingest(uploads=(world.upload(),)))

    assert world.files()[SCOUT_SPEC] == authored


# --------------------------------------------------------------------------
# 2.8, 2.9, 2.10 — rejection, duplicates, and the identical re-upload
# --------------------------------------------------------------------------


def test_one_oversized_image_among_three_rejects_the_whole_request() -> None:
    world = with_asset()
    world.limits = IngestionLimits(max_bytes=25 * MEGABYTE)
    before = len(world.commits())
    uploads = (
        UploadedImage(slot="front", content=world.an_image(seed=1), filename="front.png"),
        UploadedImage(
            slot="side",
            content=world.an_image(seed=2, byte_size=41 * MEGABYTE),
            filename="side.png",
        ),
        UploadedImage(slot="back", content=world.an_image(seed=3), filename="back.png"),
    )

    refusal = refused(world.ingest(uploads=uploads))

    assert isinstance(refusal, Invalid)
    assert "side.png" in refusal.message
    assert "41 MB" in refusal.message and "25 MB" in refusal.message
    assert len(world.commits()) == before
    assert not [path for path in world.files() if "/concept/" in path]
    assert world.stored_keys() == ()


def test_an_unsupported_format_is_rejected_naming_it_and_the_accepted_set() -> None:
    world = with_asset()
    upload = UploadedImage(slot="front", content=world.an_image("tiff"), filename="front.png")

    refusal = refused(world.ingest(uploads=(upload,)))

    assert "TIFF" in refusal.message
    assert "png, jpeg, webp" in refusal.message
    assert not [path for path in world.files() if "/concept/" in path]


def test_an_invalid_slot_name_is_rejected_naming_that_value() -> None:
    world = with_asset()

    refusal = refused(
        world.ingest(uploads=(UploadedImage(slot="Front View!", content=world.an_image()),))
    )

    assert "'Front View!'" in refusal.message


def test_two_images_naming_one_slot_are_rejected_naming_the_slot() -> None:
    world = with_asset()
    uploads = (
        UploadedImage(slot="side", content=world.an_image(seed=1)),
        UploadedImage(slot="side", content=world.an_image(seed=2)),
    )

    refusal = refused(world.ingest(uploads=uploads))

    assert "'side'" in refusal.message
    assert not [path for path in world.files() if "/concept/" in path]


def test_a_request_carrying_no_image_is_refused() -> None:
    world = with_asset()

    assert refused(world.ingest(uploads=()))


def test_a_byte_identical_re_upload_creates_no_revision() -> None:
    world = with_asset()
    content = world.an_image()
    ran(world.ingest(uploads=(world.upload(content=content),)))
    before = len(world.commits())

    outcome = ran(world.ingest(uploads=(world.upload(content=content),)))

    assert not outcome.committed
    assert outcome.unchanged == ("front",)
    assert len(world.commits()) == before
    assert len(ran(world.revisions()).revisions) == 1


# --------------------------------------------------------------------------
# 2.11 — serialised writes and the pre-commit re-check (D11)
# --------------------------------------------------------------------------


def test_a_slot_that_changed_under_a_request_is_refused_explicitly() -> None:
    """D11's loser gets a sentence, not a lost image.

    The other writer arrives in the one window that exists: between this
    request being prepared and its taking the lock. A host whose `writer`
    commits somebody else's bytes on entry is exactly that window, and it is
    the only way to stage it deterministically in one thread.
    """
    world = with_asset()
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))
    world.host = _RacedOn(world.host, FRONT, world.an_image(seed=9))
    world.spec_store.host = world.host

    refusal = refused(world.ingest(uploads=(world.upload(content=world.an_image(seed=2)),)))

    assert isinstance(refusal, Conflict)
    assert "front" in refusal.message
    assert "changed while you were uploading" in refusal.message


class _RacedOn:
    """The repository host, with another writer landing as the lock is taken."""

    def __init__(self, host, path: str, content: bytes) -> None:
        self._host = host
        self._path = path
        self._content = content
        self._raced = False

    def __getattr__(self, name):
        return getattr(self._host, name)

    @contextmanager
    def writer(self, project: str):
        with self._host.writer(project):
            if not self._raced:
                self._raced = True
                self._host.commit(
                    project,
                    [FileChange(path=self._path, content=self._content)],
                    author=ANA,
                    message="somebody else got here first",
                )
                self._host.push(project)
            yield


def test_two_concurrent_ingestions_into_one_slot_produce_one_commit_and_one_refusal() -> None:
    """The writer lock serialises them; the re-check decides which one loses."""
    world = with_asset()
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))
    first, second = world.an_image(seed=2), world.an_image(seed=3)
    outcomes: list[object] = []
    barrier = threading.Barrier(2)

    def attempt(content: bytes) -> None:
        barrier.wait()
        outcomes.append(world.ingest(uploads=(world.upload(content=content),)))

    threads = [threading.Thread(target=attempt, args=(content,)) for content in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    committed = [outcome for outcome in outcomes if getattr(outcome, "value", None) is not None]
    assert len(committed) == 1, outcomes
    assert len(ran(world.revisions()).revisions) == 2


# --------------------------------------------------------------------------
# 3.4, 3.6, 3.7 — mirroring and its absences
# --------------------------------------------------------------------------


def test_a_committed_view_is_mirrored_under_its_content_hash() -> None:
    world = with_asset()
    content = world.an_image()

    outcome = ran(world.ingest(uploads=(world.upload(content=content),)))

    key = blob_key(ContentHash.of(content))
    assert key in world.stored_keys()
    assert outcome.views[0].mirrored
    assert outcome.awaiting_mirror == ()


def test_mirroring_records_the_hash_to_view_row_in_the_index() -> None:
    world = with_asset()
    content = world.an_image()

    ran(world.ingest(uploads=(world.upload(content=content),)))

    row = world.index.row_for(PROJECT, ContentHash.of(content))
    assert row is not None
    assert (row.asset_id, row.slot, row.path) == (SCOUT, "front", FRONT)


def test_an_unreachable_mirror_delays_a_mirror_and_never_a_view() -> None:
    world = with_asset()
    world.blobs.fail_with(RuntimeError("the object store is unreachable"))

    outcome = ran(world.ingest(uploads=(world.upload(),)))

    assert outcome.committed
    assert outcome.awaiting_mirror == (FRONT,)
    assert "unreachable" in outcome.mirror_reason
    assert FRONT in world.files()


def test_with_no_blob_storage_at_all_the_view_is_committed_and_readable() -> None:
    world = with_asset()
    world.blobs = None

    outcome = ran(world.ingest(uploads=(world.upload(),)))

    assert outcome.committed
    assert outcome.awaiting_mirror == (FRONT,)
    assert FRONT in world.files()


def test_a_failure_before_the_commit_retains_no_blob_object() -> None:
    world = with_asset()
    world.limits = IngestionLimits(max_dimension=100)

    refused(world.ingest(uploads=(world.upload(content=world.an_image(width=4000)),)))

    assert world.stored_keys() == ()


# --------------------------------------------------------------------------
# 3.2, 3.3 — thumbnails
# --------------------------------------------------------------------------


def test_thumbnails_never_reach_the_working_copy_or_the_commit() -> None:
    world = with_asset()

    ran(world.ingest(uploads=(world.upload(),)))

    assert world.renderer.derived, "the thumbnail step did not run"
    assert all("thumb" not in path for path in world.files())
    assert all("thumb" not in path for path in world.commits()[-1].paths)
    assert set(world.commits()[-1].paths) == {FRONT}


def test_a_failed_thumbnail_step_is_pending_rather_than_a_failed_upload() -> None:
    world = with_asset()
    world.renderer.fail_with(RuntimeError("the encoder went away"))

    outcome = ran(world.ingest(uploads=(world.upload(),)))

    assert outcome.committed
    assert outcome.thumbnails_pending
    assert FRONT in world.files()


# --------------------------------------------------------------------------
# 7.2 — ingestion produces no derived metadata
# --------------------------------------------------------------------------


def test_the_specification_contains_only_what_was_uploaded_or_authored() -> None:
    world = a_world()

    ran(world.ingest(uploads=(world.upload(),), name="Scout Mech"))

    written = world.files()[f"{DEFAULT_ASSET_ROOT}/{SCOUT}/asset.yaml"].decode()
    for generated in ("description", "tags", "suggested", "aliases"):
        assert generated not in written


# --------------------------------------------------------------------------
# 7.3 — the failure guarantee, end to end
# --------------------------------------------------------------------------


def test_a_failure_during_the_write_leaves_every_path_absent_or_unchanged() -> None:
    world = with_asset()
    ran(world.ingest(uploads=(world.upload(content=world.an_image(seed=1)),)))
    before = dict(world.files())
    commits_before = len(world.commits())
    world.limits = IngestionLimits(max_dimension=100)

    refused(
        world.ingest(
            uploads=(
                world.upload(slot="side", content=world.an_image(seed=2)),
                world.upload(slot="back", content=world.an_image(seed=3, width=4000)),
            )
        )
    )

    assert world.files() == before
    assert len(world.commits()) == commits_before
    assert SIDE not in world.files() and BACK not in world.files()
