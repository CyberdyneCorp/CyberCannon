"""Step definitions for `concept-ingestion` — the first thing an artist does.

Everything bound here runs against the in-memory repository host, the in-memory
image inspector and the in-memory blob store, so a full upload — validate,
commit, mirror, derive — is exercised with no git, no disk, no network and no
image decoder, exactly as the validator suite is exercised with no mesh file.
That is D1 and D2 paying for themselves: the *rules* are pure, so the scenarios
that check them can be too.

The arrangement is `tests/views_world.py`, shared with
`tests/unit/test_use_case_ingest_views.py`, so a scenario and a unit test are
exercising one arrangement rather than two that drift.
"""

from __future__ import annotations

import json
from base64 import b64encode
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.adapters.inbound.http.views import read_upload
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.outcomes import ran as ran_ok
from cybercanon.application.use_cases.ingest_views import (
    DEFAULT_ASSET_ROOT,
    UploadedImage,
    view_reference,
)
from cybercanon.application.use_cases.resolve_actor import strip_identity_claims
from cybercanon.application.use_cases.view_mirror import mirror_views
from cybercanon.application.use_cases.view_revisions import PresentedView
from cybercanon.domain.revisions import ContentHash, blob_key
from cybercanon.domain.views import IngestionLimits
from views_world import (
    PROJECT,
    RAFA,
    SCOUT,
    SCOUT_DIR,
    SCOUT_SPEC,
    Views,
    a_spec,
    with_asset,
)

MEGABYTE = 1024 * 1024
FRONT = f"{SCOUT_DIR}/concept/front.png"
SIDE = f"{SCOUT_DIR}/concept/side.png"
BACK = f"{SCOUT_DIR}/concept/back.png"

CREATED_SPEC = f"{DEFAULT_ASSET_ROOT}/{SCOUT}/asset.yaml"
CREATED_FRONT = f"{DEFAULT_ASSET_ROOT}/{SCOUT}/concept/front.png"

AUTHORED = (
    b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"
    b"constraints:\n"
    b"  tri_budget: 12000\n"
    b"  required_sockets: [SOCKET_muzzle_l, SOCKET_muzzle_r]\n"
)

MULE = "mule"
CRATE = "crate"
BARREL = "barrel"


@pytest.fixture
def views() -> Views:
    """A cloned project holding `mech_scout` and nothing else."""
    return with_asset()


@pytest.fixture
def upload() -> dict[str, Any]:
    """What this scenario uploaded, and what came back."""
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "An unsupported format is rejected",
)
def test_an_unsupported_format_is_rejected() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Content decides, not the extension",
)
def test_content_decides_not_the_extension() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Oversized file is rejected with numbers",
)
def test_oversized_file_is_rejected_with_numbers() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Oversized dimensions are rejected",
)
def test_oversized_dimensions_are_rejected() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Exactly at the limit is accepted",
)
def test_exactly_at_the_limit_is_accepted() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Canonical slot",
)
def test_canonical_slot() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Arbitrary named view",
)
def test_arbitrary_named_view() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Invalid slot name",
)
def test_invalid_slot_name() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "A slot holds one view",
)
def test_a_slot_holds_one_view() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Creating an asset by uploading its first concept",
)
def test_creating_an_asset_by_uploading_its_first_concept() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Existing authored content is untouched",
)
def test_existing_authored_content_is_untouched() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "An invalid asset identifier creates nothing",
)
def test_an_invalid_asset_identifier_creates_nothing() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "A late concept view does not demote an asset",
)
def test_a_late_concept_view_does_not_demote_an_asset() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "A first view does not promote an asset",
)
def test_a_first_view_does_not_promote_an_asset() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Commit authorship is the uploader",
)
def test_commit_authorship_is_the_uploader() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "A supplied author is ignored",
)
def test_a_supplied_author_is_ignored() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Agent-mediated upload names both",
)
def test_agent_mediated_upload_names_both() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "An unmappable person is refused before any write",
)
def test_an_unmappable_person_is_refused_before_any_write() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Rebuilding the mirror from the repository",
)
def test_rebuilding_the_mirror_from_the_repository() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Mirror outage does not block ingestion",
)
def test_mirror_outage_does_not_block_ingestion() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "No blob storage configured at all",
)
def test_no_blob_storage_configured_at_all() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Thumbnails stay out of the repository",
)
def test_thumbnails_stay_out_of_the_repository() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Deterministic derivation",
)
def test_deterministic_derivation() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Thumbnails are recoverable",
)
def test_thumbnails_are_recoverable() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Three views, one commit",
)
def test_three_views_one_commit() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "One bad image rejects the request",
)
def test_one_bad_image_rejects_the_request() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Two images cannot claim the same slot",
)
def test_two_images_cannot_claim_the_same_slot() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Failure while writing leaves the working copy as it was",
)
def test_failure_while_writing_leaves_the_working_copy_as_it_was() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Failure before commit retains no blob object",
)
def test_failure_before_commit_retains_no_blob_object() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Post-commit derived failure is a pending step, not a failed upload",
)
def test_post_commit_derived_failure_is_a_pending_step() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Ingestion with model access disabled",
)
def test_ingestion_with_model_access_disabled() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Uploading generates nothing",
)
def test_uploading_generates_nothing() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "A newly exported render appears",
)
def test_a_newly_exported_render_appears() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Freshness cannot be established",
)
def test_freshness_cannot_be_established() -> None: ...


@scenario(
    "../features/add-concept-ingestion/concept-ingestion.feature",
    "Cached images are distinguishable by content",
)
def test_cached_images_are_distinguishable_by_content() -> None: ...


# --------------------------------------------------------------------------
# Accepted formats
# --------------------------------------------------------------------------


@given("a project whose accepted formats are PNG, JPEG and WebP")
def _the_default_accepted_set(views: Views) -> None:
    views.limits = IngestionLimits()


@when("a TIFF image is uploaded as a concept view")
def _a_tiff_is_uploaded(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=(UploadedImage(slot="front", content=views.an_image("tiff"), filename="front.tif"),)
    )


@then("the upload SHALL be rejected with a message naming TIFF and the accepted set")
def _rejected_naming_tiff(upload: dict[str, Any]) -> None:
    message = refused(upload["result"]).message
    assert "TIFF" in message
    assert "png, jpeg, webp" in message


@then("no file SHALL be written to the repository")
def _nothing_written(views: Views) -> None:
    assert not [path for path in views.files() if "/concept/" in path]


@given("a TIFF image whose filename ends in `.png`")
def _a_mislabelled_tiff(views: Views, upload: dict[str, Any]) -> None:
    upload["image"] = UploadedImage(
        slot="front", content=views.an_image("tiff"), filename="front.png"
    )


@when("it is uploaded")
def _it_is_uploaded(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(uploads=(upload["image"],))


@then("the upload SHALL be rejected as a TIFF")
def _rejected_as_a_tiff(upload: dict[str, Any]) -> None:
    assert "TIFF" in refused(upload["result"]).message


# --------------------------------------------------------------------------
# Size and dimension limits
# --------------------------------------------------------------------------


@given("a configured maximum of 25 MB per image")
def _a_configured_size_limit(views: Views) -> None:
    views.limits = IngestionLimits(max_bytes=25 * MEGABYTE)


@when("a 41 MB image is uploaded")
def _an_oversized_image(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=(
            UploadedImage(
                slot="front",
                content=views.an_image(byte_size=41 * MEGABYTE),
                filename="front.png",
            ),
        )
    )


@then("the upload SHALL be rejected stating observed 41 MB and allowed 25 MB")
def _rejected_with_both_numbers(upload: dict[str, Any]) -> None:
    message = refused(upload["result"]).message
    assert "41 MB" in message and "25 MB" in message


@given("a configured maximum dimension of 8192 pixels")
def _a_configured_dimension_limit(views: Views) -> None:
    views.limits = IngestionLimits(max_dimension=8192)


@when("an image of 12000 by 4000 pixels is uploaded")
def _an_over_wide_image(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=(
            UploadedImage(
                slot="front",
                content=views.an_image(width=12000, height=4000),
                filename="front.png",
            ),
        )
    )


@then("the upload SHALL be rejected stating the observed width and the allowed maximum")
def _rejected_with_the_width(upload: dict[str, Any]) -> None:
    message = refused(upload["result"]).message
    assert "12000" in message and "8192" in message


@when("an image of 8192 by 8192 pixels within the size limit is uploaded")
def _an_image_at_the_limit(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=(
            UploadedImage(
                slot="front",
                content=views.an_image(width=8192, height=8192, byte_size=MEGABYTE),
                filename="front.png",
            ),
        )
    )


@then("the upload SHALL be accepted")
def _accepted(upload: dict[str, Any]) -> None:
    assert ran(upload["result"]).committed


# --------------------------------------------------------------------------
# Slots
# --------------------------------------------------------------------------


@when("an image is uploaded to the slot `front` of an asset")
def _uploaded_to_front(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(uploads=(views.upload("front"),))


@then("it SHALL become that asset's `front` view")
def _it_is_the_front_view(views: Views, upload: dict[str, Any]) -> None:
    outcome = ran(upload["result"])
    assert outcome.paths == (FRONT,)
    assert str(outcome.views[0].slot) == "front"


@when("an image is uploaded to the slot `three_quarter_left`")
def _uploaded_to_a_named_slot(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(uploads=(views.upload("three_quarter_left"),))


@then("it SHALL be accepted as a named view of that asset")
def _accepted_as_a_named_view(views: Views, upload: dict[str, Any]) -> None:
    outcome = ran(upload["result"])
    assert outcome.paths == (f"{SCOUT_DIR}/concept/three_quarter_left.png",)


@when("an image is uploaded to the slot `Front View!`")
def _uploaded_to_an_invalid_slot(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=(UploadedImage(slot="Front View!", content=views.an_image()),)
    )


@then("the upload SHALL be rejected naming that value as an invalid slot name")
def _rejected_naming_the_slot(upload: dict[str, Any]) -> None:
    assert "'Front View!'" in refused(upload["result"]).message


@given("an asset whose `front` slot already holds a view")
def _a_slot_that_is_taken(views: Views, upload: dict[str, Any]) -> None:
    upload["first"] = views.an_image(seed=1)
    ran(views.ingest(uploads=(views.upload(content=upload["first"]),)))


@when("another image is uploaded to `front`")
def _another_image_to_front(views: Views, upload: dict[str, Any]) -> None:
    upload["second"] = views.an_image(seed=2)
    upload["result"] = views.ingest(uploads=(views.upload(content=upload["second"]),))


@then("the existing view SHALL be replaced rather than a second `front` view created")
def _replaced_rather_than_duplicated(views: Views) -> None:
    assert [path for path in views.files() if "/concept/" in path] == [FRONT]


@then("the replacement SHALL be recorded as a new revision of that view")
def _recorded_as_a_revision(views: Views) -> None:
    assert len(ran(views.revisions()).revisions) == 2


# --------------------------------------------------------------------------
# Creating an asset
# --------------------------------------------------------------------------


@given("no specification exists for `mech_scout`")
def _no_specification(views: Views) -> None:
    views.host.add_project(PROJECT, {})
    views.host.clone(PROJECT)


@when("an image is uploaded to the `front` slot of `mech_scout`")
def _the_first_concept(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(uploads=(views.upload(),), name="Scout Mech")


@then("a specification for `mech_scout` SHALL be created with status `concept`")
def _a_specification_is_created(views: Views, upload: dict[str, Any]) -> None:
    assert ran(upload["result"]).created_asset
    assert "status: concept" in views.files()[CREATED_SPEC].decode()


@then("it SHALL contain no `design` or `constraints` fields")
def _no_scaffolded_blocks(views: Views) -> None:
    written = views.files()[CREATED_SPEC].decode()
    assert "design" not in written and "constraints" not in written


@then("the specification and the image SHALL appear in the same commit")
def _one_commit_for_both(views: Views) -> None:
    paths = set(views.commits()[-1].paths)
    assert {CREATED_SPEC, CREATED_FRONT} <= paths


@given("an asset whose specification declares a triangle budget and two sockets")
def _an_asset_with_authored_content(views: Views, upload: dict[str, Any]) -> None:
    views.host.add_project(PROJECT, {SCOUT_SPEC: AUTHORED})
    views.host.clone(PROJECT)
    upload["authored"] = AUTHORED


@when("a new concept view is uploaded to it")
def _a_new_view_is_uploaded(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(uploads=(views.upload(),))


@then("the triangle budget and sockets SHALL be unchanged in the resulting specification")
def _authored_content_untouched(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    assert views.files()[SCOUT_SPEC] == upload["authored"]


@when("an upload names an asset identifier that does not satisfy the identifier rule")
def _an_invalid_identifier(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(asset_id="mech scout", uploads=(views.upload(),))


@then("the upload SHALL be rejected naming the identifier")
def _rejected_naming_the_identifier(upload: dict[str, Any]) -> None:
    assert "mech scout" in refused(upload["result"]).message


@then("no specification SHALL be created")
def _no_specification_created(views: Views) -> None:
    """Nothing was created: the project holds exactly what it held before."""
    assert set(views.files()) == {SCOUT_SPEC}
    assert views.commits() == ()


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------


@given("an asset at status `validated`")
def _a_validated_asset(views: Views) -> None:
    views.host.add_project(PROJECT, {SCOUT_SPEC: a_spec(status="validated")})
    views.host.clone(PROJECT)


@then("its status SHALL still be `validated`")
def _still_validated(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    assert "status: validated" in views.files()[SCOUT_SPEC].decode()


@given("an asset created by its first upload at status `concept`")
def _an_asset_created_by_an_upload(views: Views) -> None:
    views.host.add_project(PROJECT, {})
    views.host.clone(PROJECT)
    ran(views.ingest(uploads=(views.upload(),)))


@when("two further views are uploaded")
def _two_further_views(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=(
            UploadedImage(slot="side", content=views.an_image(seed=2)),
            UploadedImage(slot="back", content=views.an_image(seed=3)),
        )
    )


@then("its status SHALL still be `concept`")
def _still_concept(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    assert "status: concept" in views.files()[CREATED_SPEC].decode()


# --------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------


@given("an artist whose identity maps to a git author")
def _a_mapped_artist(upload: dict[str, Any]) -> None:
    upload["author"] = RAFA


@when("she uploads a concept view")
def _she_uploads(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(uploads=(views.upload(),), author=upload["author"])


@then("the resulting commit's author SHALL be that git author")
def _authored_by_her(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    assert views.commits()[-1].author == upload["author"]


@given("an upload request that also carries an author field naming another person")
def _a_request_claiming_another_author(views: Views, upload: dict[str, Any]) -> None:
    """A real request body, with an `author` in it that nothing reads."""
    upload["claimed"] = {
        "images": [{"slot": "front", "content": b64encode(views.an_image()).decode("ascii")}],
        "author": "ana@cyberdyne.com",
        "actor": "auth|ana",
    }
    upload["image"] = views.upload()


@when("it is ingested")
def _it_is_ingested(views: Views, upload: dict[str, Any]) -> None:
    """Ingest whatever this scenario arranged — one image, or a whole request.

    One step for both because the sentence is the same in both scenarios, and a
    second step with the same text would silently shadow the first: pytest-bdd
    keeps the last definition, which is how a suite starts asserting something
    other than what it reads as.

    For the claimed-author scenario it also runs the claim through
    :func:`~cybercanon.application.use_cases.resolve_actor.strip_identity_claims`,
    because that is where a supplied actor is dropped *and named*: `ingest_views`
    has no parameter a claimed author could arrive through, and the git identity
    is an argument the surface resolved from the credential.
    """
    if "claimed" in upload:
        upload["read"] = ran_ok(read_upload(json.dumps(upload["claimed"]).encode()))
        upload["dropped"] = strip_identity_claims(upload["claimed"])[1]
    images = upload.get("images") or (upload["image"],)
    upload["result"] = views.ingest(uploads=images, author=RAFA)


@then("the commit SHALL be attributed to the person the credential identifies")
def _attributed_to_the_credential(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    assert views.commits()[-1].author == RAFA


@then("the supplied author field SHALL have no effect on attribution")
def _the_claim_had_no_effect(upload: dict[str, Any]) -> None:
    """There is nowhere for it to go, which is stronger than ignoring it.

    The envelope reader keeps the slot, the bytes, the file name, the asset's
    name and the performing agent — and nothing else. A claimed `actor` is
    additionally *named* by
    :func:`~cybercanon.application.use_cases.resolve_actor.strip_identity_claims`,
    because a caller who sent one should be told it had no effect rather than
    met with silence.
    """
    read = upload["read"]
    assert not hasattr(read, "author")
    assert read.agent == "" and read.name == ""
    assert "actor" in upload["dropped"]


@given("an agent acting for a person")
def _an_agent(upload: dict[str, Any]) -> None:
    upload["agent"] = "blender-agent"


@when("it ingests a view on that person's behalf")
def _the_agent_ingests(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(uploads=(views.upload(),), agent=upload["agent"])


@then("the recorded attribution SHALL name the person and the agent")
def _both_are_named(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    commit = views.commits()[-1]
    assert commit.author == RAFA
    assert upload["agent"] in commit.message


@given("an acting person with no entry in the identity mapping")
def _an_unmapped_person(upload: dict[str, Any]) -> None:
    upload["author"] = None
    upload["subject"] = "auth|newcomer"


@when("an upload is attempted")
def _an_upload_is_attempted(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=(views.upload(),), author=None, subject=upload["subject"]
    )


@then("it SHALL be refused with a message naming the missing mapping")
def _refused_naming_the_mapping(upload: dict[str, Any]) -> None:
    message = refused(upload["result"]).message
    assert ".canon/actors.yaml" in message
    assert upload["subject"] in message


@then("no file SHALL be written and no blob object SHALL be retained")
def _nothing_written_and_nothing_stored(views: Views) -> None:
    assert not [path for path in views.files() if "/concept/" in path]
    assert views.stored_keys() == ()


# --------------------------------------------------------------------------
# The mirror
# --------------------------------------------------------------------------


@given("a project with twelve concept views and a populated blob store")
def _twelve_views(views: Views, upload: dict[str, Any]) -> None:
    views.host.add_project(
        PROJECT,
        {
            SCOUT_SPEC: a_spec(),
            f"vehicles/{MULE}/asset.yaml": a_spec(MULE, "Mule"),
            f"props/{CRATE}/asset.yaml": a_spec(CRATE, "Crate"),
            f"props/{BARREL}/asset.yaml": a_spec(BARREL, "Barrel"),
        },
    )
    views.host.clone(PROJECT)
    for index, asset_id in enumerate((SCOUT, MULE, CRATE, BARREL)):
        ran(
            views.ingest(
                asset_id=asset_id,
                uploads=tuple(
                    UploadedImage(slot=slot, content=views.an_image(seed=index * 10 + offset))
                    for offset, slot in enumerate(("front", "side", "back"))
                ),
            )
        )
    upload["before"] = ran(_mirror(views)).keys
    assert len(upload["before"]) == 12


@when("every mirrored object and thumbnail is deleted and a rebuild is run")
def _the_mirror_is_destroyed_and_rebuilt(views: Views, upload: dict[str, Any]) -> None:
    views.blobs.empty()
    views.index.clear()
    assert views.stored_keys() == ()
    upload["after"] = ran(_mirror(views)).keys


@then("all twelve views SHALL be available again with the same content hashes")
def _restored_unchanged(views: Views, upload: dict[str, Any]) -> None:
    assert upload["after"] == upload["before"]
    assert len(upload["after"]) == 12
    assert all(views.blobs.exists(key) for key in upload["after"].values())


@given("blob storage is unreachable")
def _an_unreachable_mirror(views: Views) -> None:
    views.blobs.fail_with(RuntimeError("the object store is unreachable"))


@when("a concept view is uploaded")
def _a_view_is_uploaded(views: Views, upload: dict[str, Any]) -> None:
    upload["content"] = views.an_image()
    upload["result"] = views.ingest(uploads=(views.upload(content=upload["content"]),))


@then("the view SHALL be committed to the repository")
def _committed(views: Views, upload: dict[str, Any]) -> None:
    assert ran(upload["result"]).committed
    assert FRONT in views.files()


@then("it SHALL be reported as awaiting mirroring rather than as failed")
def _awaiting_mirroring(upload: dict[str, Any]) -> None:
    outcome = ran(upload["result"])
    assert outcome.awaiting_mirror == (FRONT,)
    assert not outcome.views[0].mirrored


@given("a project configured with no blob storage")
def _no_blob_storage(views: Views) -> None:
    views.blobs = None


@then("the view SHALL be committed and readable from the repository")
def _committed_and_readable(views: Views, upload: dict[str, Any]) -> None:
    assert ran(upload["result"]).committed
    assert views.files()[FRONT] == upload["content"]


# --------------------------------------------------------------------------
# Thumbnails
# --------------------------------------------------------------------------


@when("a concept view is ingested")
def _a_view_is_ingested(views: Views, upload: dict[str, Any]) -> None:
    upload["content"] = views.an_image()
    upload["result"] = views.ingest(uploads=(views.upload(content=upload["content"]),))


@then("no thumbnail file SHALL appear in the repository working copy or in the commit")
def _no_thumbnail_anywhere(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    assert views.renderer.derived, "the thumbnail step did not run at all"
    assert set(views.files()) == {SCOUT_SPEC, FRONT}
    assert set(views.commits()[-1].paths) == {FRONT}


@when("thumbnails are derived twice from the same committed image")
def _derived_twice(views: Views, upload: dict[str, Any]) -> None:
    content = views.an_image()
    ran(views.ingest(uploads=(views.upload(content=content),)))
    upload["first"] = views.renderer.derive(views.files()[FRONT])
    upload["second"] = views.renderer.derive(views.files()[FRONT])


@then("both derivations SHALL produce the same content hashes")
def _identical_hashes(upload: dict[str, Any]) -> None:
    assert [thumbnail.digest for thumbnail in upload["first"]] == [
        thumbnail.digest for thumbnail in upload["second"]
    ]


@given("every thumbnail has been deleted")
def _thumbnails_deleted(views: Views, upload: dict[str, Any]) -> None:
    ran(views.ingest(uploads=(views.upload(),)))
    upload["before"] = ran(_mirror(views)).thumbnails
    assert upload["before"] > 0
    views.blobs.empty()


@when("derivation is run again over the project")
def _derivation_runs_again(views: Views, upload: dict[str, Any]) -> None:
    upload["after"] = ran(_mirror(views))


@then("every view SHALL have its thumbnails again with no upload required")
def _thumbnails_are_back(views: Views, upload: dict[str, Any]) -> None:
    assert upload["after"].thumbnails == upload["before"]
    assert views.inspector.inspected  # nothing was re-uploaded; the repository was read


# --------------------------------------------------------------------------
# All or nothing
# --------------------------------------------------------------------------


@when("a request uploads images to `front`, `side` and `back` of one asset")
def _three_slots(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=tuple(
            UploadedImage(slot=slot, content=views.an_image(seed=index))
            for index, slot in enumerate(("front", "side", "back"))
        )
    )


@then("exactly one commit SHALL be produced containing all three files")
def _one_commit_with_three_files(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    assert set(views.commits()[-1].paths) == {FRONT, SIDE, BACK}
    assert len(views.commits()) == 1


@given("a request carrying three images of which one exceeds the size limit")
def _three_images_one_too_big(views: Views, upload: dict[str, Any]) -> None:
    views.limits = IngestionLimits(max_bytes=25 * MEGABYTE)
    upload["images"] = (
        UploadedImage(slot="front", content=views.an_image(seed=1), filename="front.png"),
        UploadedImage(
            slot="side",
            content=views.an_image(seed=2, byte_size=41 * MEGABYTE),
            filename="side.png",
        ),
        UploadedImage(slot="back", content=views.an_image(seed=3), filename="back.png"),
    )


@then("the request SHALL be rejected naming the oversized image and its size")
def _rejected_naming_the_image(upload: dict[str, Any]) -> None:
    message = refused(upload["result"]).message
    assert "side.png" in message
    assert "41 MB" in message and "25 MB" in message


@then("no commit SHALL be produced and none of the three views SHALL exist")
def _nothing_committed(views: Views) -> None:
    assert views.commits() == ()
    assert not [path for path in views.files() if "/concept/" in path]


@when("a request uploads two images both naming the slot `side` of one asset")
def _two_images_one_slot(views: Views, upload: dict[str, Any]) -> None:
    upload["result"] = views.ingest(
        uploads=(
            UploadedImage(slot="side", content=views.an_image(seed=1)),
            UploadedImage(slot="side", content=views.an_image(seed=2)),
        )
    )


@then("the request SHALL be rejected naming the conflicting slot")
def _rejected_naming_the_conflict(upload: dict[str, Any]) -> None:
    assert "'side'" in refused(upload["result"]).message


@then("no commit SHALL be produced")
def _no_commit(views: Views) -> None:
    assert views.commits() == ()


# --------------------------------------------------------------------------
# Failure leaves nothing behind
# --------------------------------------------------------------------------


@given("an ingestion request that fails while writing its files")
def _a_request_that_fails_writing(views: Views, upload: dict[str, Any]) -> None:
    ran(views.ingest(uploads=(views.upload(content=views.an_image(seed=1)),)))
    upload["before"] = dict(views.files())
    upload["commits"] = len(views.commits())
    views.limits = IngestionLimits(max_dimension=100)
    upload["result"] = views.ingest(
        uploads=(
            UploadedImage(slot="side", content=views.an_image(seed=2)),
            UploadedImage(slot="back", content=views.an_image(seed=3, width=4000)),
        )
    )
    refused(upload["result"])


@when("the repository working copy is examined")
def _the_working_copy_is_examined(views: Views, upload: dict[str, Any]) -> None:
    upload["after"] = dict(views.files())


@then("every path the request would have written SHALL be absent or unchanged")
def _paths_absent_or_unchanged(upload: dict[str, Any]) -> None:
    assert upload["after"] == upload["before"]
    assert SIDE not in upload["after"] and BACK not in upload["after"]


@then("no commit from that request SHALL exist")
def _no_commit_from_the_request(views: Views, upload: dict[str, Any]) -> None:
    assert len(views.commits()) == upload["commits"]


@given("an ingestion request that fails before its commit succeeds")
def _a_request_that_fails_before_committing(views: Views, upload: dict[str, Any]) -> None:
    views.limits = IngestionLimits(max_dimension=100)
    upload["result"] = views.ingest(
        uploads=(UploadedImage(slot="front", content=views.an_image(width=4000)),)
    )
    refused(upload["result"])


@when("blob storage is examined")
def _blob_storage_is_examined(views: Views, upload: dict[str, Any]) -> None:
    upload["keys"] = views.stored_keys()


@then("no object written for that request SHALL remain")
def _no_orphan_object(upload: dict[str, Any]) -> None:
    assert upload["keys"] == ()


@given("a request whose commit succeeded and whose thumbnail derivation then failed")
def _a_failing_derived_step(views: Views, upload: dict[str, Any]) -> None:
    views.renderer.fail_with(RuntimeError("the encoder went away"))
    upload["result"] = views.ingest(uploads=(views.upload(),))


@when("the result is reported")
def _the_result_is_reported(upload: dict[str, Any]) -> None:
    upload["outcome"] = ran(upload["result"])


@then("the view SHALL be reported as ingested with thumbnail derivation pending")
def _ingested_with_pending_thumbnails(views: Views, upload: dict[str, Any]) -> None:
    outcome = upload["outcome"]
    assert outcome.committed
    assert outcome.thumbnails_pending
    assert FRONT in views.files()


# --------------------------------------------------------------------------
# No model, ever
# --------------------------------------------------------------------------


@given("model access is disabled")
def _model_access_disabled(views: Views) -> None:
    """There is nothing to disable, and that is the point (D12).

    Ingestion has no model port to wire, so *"SHALL complete with model access
    disabled"* is true by construction; the structural test in
    `tests/unit/test_ingestion_never_calls_a_model.py` is what keeps it true.
    """
    assert views.notes.get("llm") is None


@then("ingestion SHALL succeed and the view SHALL be committed and mirrored")
def _committed_and_mirrored(views: Views, upload: dict[str, Any]) -> None:
    outcome = ran(upload["result"])
    assert outcome.committed
    assert outcome.views[0].mirrored
    assert blob_key(ContentHash.of(upload["content"])) in views.stored_keys()


@then("no description, tag or suggested alias SHALL be produced by that action")
def _nothing_generated(views: Views, upload: dict[str, Any]) -> None:
    ran(upload["result"])
    written = views.files()[SCOUT_SPEC].decode()
    for generated in ("description", "tags", "suggested", "aliases"):
        assert generated not in written


@then("the asset's specification SHALL contain nothing that was not uploaded or authored")
def _only_authored_content(views: Views) -> None:
    assert views.files()[SCOUT_SPEC] == a_spec()


# --------------------------------------------------------------------------
# Freshness (D8)
# --------------------------------------------------------------------------


@given("a person viewing the `front` view of an asset")
def _a_person_viewing_front(views: Views, upload: dict[str, Any]) -> None:
    content = views.an_image(seed=1)
    ran(views.ingest(uploads=(views.upload(content=content),)))
    upload["shown"] = ContentHash.of(content)


@when("a new export replaces that view's file in the repository")
def _a_new_export_replaces_it(views: Views, upload: dict[str, Any]) -> None:
    ran(views.ingest(uploads=(views.upload(content=views.an_image(seed=2)),)))
    upload["presented"] = PresentedView(shown=upload["shown"], token=ran(views.token()))


@then(
    "within the configured interval that person SHALL be shown the new revision, "
    "or the view SHALL be marked stale"
)
def _superseded_or_stale(upload: dict[str, Any]) -> None:
    presented = upload["presented"]
    assert presented.is_superseded or presented.is_stale
    assert presented.interval.total_seconds() > 0


@then("in neither case SHALL the superseded image be labelled current")
def _never_labelled_current(upload: dict[str, Any]) -> None:
    assert not upload["presented"].is_current


@given("a surface that cannot determine whether the view it shows is current")
def _a_surface_with_no_token(upload: dict[str, Any]) -> None:
    upload["presented"] = PresentedView(shown=ContentHash.of(b"whatever"), token=None)


@when("it presents the view")
def _it_presents_the_view(upload: dict[str, Any]) -> None:
    upload["stale"] = upload["presented"].is_stale


@then("it SHALL mark the view as stale rather than assert that it is current")
def _marked_stale(upload: dict[str, Any]) -> None:
    assert upload["stale"]
    assert not upload["presented"].is_current


@given("two revisions of one view with different content hashes")
def _two_revisions(views: Views, upload: dict[str, Any]) -> None:
    upload["identities"] = []
    for seed in (1, 2):
        outcome = ran(views.ingest(uploads=(views.upload(content=views.an_image(seed=seed)),)))
        upload["identities"].append(view_reference(outcome.views[0], outcome.revision))


@when("either is presented")
def _either_is_presented(upload: dict[str, Any]) -> None:
    upload["presented_identities"] = upload["identities"]


@then("the presented identity SHALL include the content hash of the revision shown")
def _identity_includes_the_hash(upload: dict[str, Any]) -> None:
    hashes = [identity["content_hash"] for identity in upload["presented_identities"]]
    assert all(value.startswith("sha256:") for value in hashes)
    assert len(set(hashes)) == 2


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------


def _mirror(views: Views):
    return mirror_views(
        PROJECT,
        repository_host=views.host,
        spec_store=views.spec_store,
        blob_store=views.blobs,
        view_index=views.index,
        thumbnail_renderer=views.renderer,
    )
