"""Step definitions for `blob-storage` — content addressing, then serving.

Task 4.5 gives the `BlobStore` port its content-addressed half (D14): a key is
the digest of the bytes, derived in the domain
(:func:`cybercanon.domain.revisions.blob_key`) so no two implementations can
disagree about it. Four of this capability's scenarios are answerable by that
alone, and they are the four bound first below — every one of them is a property
*of the key*, which is exactly what content addressing buys.

The other ten waited for group 7, and for a reason worth having written down:
they are about **serving** a blob rather than keying one. An expired link, a
link rewritten to another object, an authorization decision before issuance, a
corrupt object reported rather than served, a store emptied and re-mirrored —
all need the mirroring pass, the digest check and the link verification that
group 7 builds, and binding them against issuance alone would have asserted
nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.errors import FailureKind
from cybercanon.application.ports.blob_store import (
    BlobCorrupted,
    BlobNotStored,
    LinkRefused,
    SignedLink,
)
from cybercanon.application.ports.preview import PreviewMesh
from cybercanon.application.results import Forbidden, Invalid, Unavailable
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.blob_mirror import (
    DerivedPreview,
    accept_blob,
    link_to_blob,
    mirror_project,
    views_of,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.concept import Concept
from cybercanon.domain.identity import Actor, ActorId
from cybercanon.domain.revisions import ContentHash, blob_key

CONCEPT = b"\x89PNG\r\n\x1a\nthe scout mech, three-quarter view"
REPAINTED = b"\x89PNG\r\n\x1a\nthe scout mech, three-quarter view, repainted"


class CountingBlobStore(InMemoryBlobStore):
    """The fake, counting the links it hands out.

    *"AND no link SHALL be issued"* is an absence, and an absence cannot be
    asserted by looking at what came back — a refusal and a refusal after a link
    was quietly minted look identical from outside. So the store counts.
    """

    def __init__(self) -> None:
        super().__init__()
        self.issued = 0

    def link_for(self, key: str, *, expires_at: datetime) -> SignedLink:
        link = super().link_for(key, expires_at=expires_at)
        self.issued += 1
        return link


@pytest.fixture
def mirror() -> CountingBlobStore:
    """The blob store this scenario mirrors into."""
    return CountingBlobStore()


@pytest.fixture
def mirrored() -> dict[str, Any]:
    """What this scenario stored, and under which keys."""
    return {}


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario("../features/add-web-backend/blob-storage.feature", "Identical content stores once")
def test_identical_content_stores_once() -> None: ...


@scenario("../features/add-web-backend/blob-storage.feature", "Changed content gets a new key")
def test_changed_content_gets_a_new_key() -> None: ...


@scenario("../features/add-web-backend/blob-storage.feature", "Renaming does not change the key")
def test_renaming_does_not_change_the_key() -> None: ...


@scenario("../features/add-web-backend/blob-storage.feature", "Re-mirroring is a no-op")
def test_re_mirroring_is_a_no_op() -> None: ...


# --------------------------------------------------------------------------
# One key per content
# --------------------------------------------------------------------------


@given("the same image referenced by two assets")
def _one_image_two_assets(mirrored: dict[str, Any]) -> None:
    """Two references, one set of bytes — which is the only thing a key sees."""
    mirrored["from_scout"] = CONCEPT
    mirrored["from_mule"] = bytes(CONCEPT)


@when("both are mirrored")
def _both_are_mirrored(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["first"] = mirror.put(mirrored["from_scout"])
    mirrored["second"] = mirror.put(mirrored["from_mule"])


@then("both SHALL resolve to the same key and one stored object")
def _one_key_one_object(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    first, second = mirrored["first"], mirrored["second"]

    assert first.key == second.key == blob_key(ContentHash.of(CONCEPT))
    assert mirror.read(first.key) == CONCEPT


@given("a stored blob")
def _a_stored_blob(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["old"] = mirror.put(CONCEPT)


@when("its source file's bytes change")
def _the_bytes_change(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["new"] = mirror.put(REPAINTED)


@then("the new content SHALL store under a different key")
def _a_different_key(mirrored: dict[str, Any]) -> None:
    assert mirrored["new"].key != mirrored["old"].key


@then("references to the old key SHALL continue to resolve to the old content until it is removed")
def _the_old_key_still_resolves(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    assert mirror.read(mirrored["old"].key) == CONCEPT
    assert mirror.exists(mirrored["old"].key)


@given("a mirrored file")
def _a_mirrored_file(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["before"] = mirror.put(CONCEPT)
    mirrored["named"] = "concept/scout_three_quarter.png"


@when("the file is renamed in the repository with unchanged content")
def _it_is_renamed(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["named"] = "concept/scout_hero.png"
    mirrored["after"] = mirror.put(CONCEPT)


@then("its key SHALL be unchanged")
def _the_key_did_not_move(mirrored: dict[str, Any]) -> None:
    assert mirrored["after"].key == mirrored["before"].key


# --------------------------------------------------------------------------
# Mirroring is idempotent
# --------------------------------------------------------------------------


@given("content already stored under its key")
def _content_already_stored(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["before"] = mirror.put(CONCEPT)


@when("it is mirrored again")
def _mirrored_again(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["again"] = mirror.put(CONCEPT)


@then("the operation SHALL succeed")
def _it_succeeded(mirrored: dict[str, Any]) -> None:
    assert mirrored["again"].key == mirrored["before"].key


@then("the stored object SHALL be unchanged")
def _the_object_is_unchanged(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    assert mirror.read(mirrored["again"].key) == CONCEPT
    assert mirrored["again"].size_bytes == mirrored["before"].size_bytes


# --------------------------------------------------------------------------
# Serving a blob, and the repository deciding what there is to serve (group 7)
# --------------------------------------------------------------------------
#
# The ten scenarios group 4 deliberately left pending. Each of them is about
# *serving* rather than keying, and each needed something group 7 built: the
# mirroring pass that reads the repository, the digest check on read, the
# verification of a link, and the distinction the whole capability turns on —
# a view the repository does not describe is **not found**, a view it describes
# whose object is missing is **temporarily unavailable**.
#
# Bound against the in-memory host and the in-memory store, because the port
# conformance suite is what holds the fake, `FsBlobStore` and `S3BlobStore` to
# one behaviour and `tests/integration/test_blob_mirror.py` runs the recovery
# drill against a real working copy. Re-proving either here would be slower and
# would prove nothing new.


@scenario(
    "../features/add-web-backend/blob-storage.feature", "Repository decides which blobs matter"
)
def test_repository_decides_which_blobs_matter() -> None: ...


@scenario(
    "../features/add-web-backend/blob-storage.feature",
    "Upload without a repository source is refused",
)
def test_upload_without_a_repository_source_is_refused() -> None: ...


@scenario(
    "../features/add-web-backend/blob-storage.feature",
    "Interrupted upload leaves nothing readable",
)
def test_interrupted_upload_leaves_nothing_readable() -> None: ...


@scenario("../features/add-web-backend/blob-storage.feature", "Empty store rebuilds")
def test_empty_store_rebuilds() -> None: ...


@scenario(
    "../features/add-web-backend/blob-storage.feature", "A missing blob is reported, not fabricated"
)
def test_a_missing_blob_is_reported_not_fabricated() -> None: ...


@scenario("../features/add-web-backend/blob-storage.feature", "Expired link is refused")
def test_expired_link_is_refused() -> None: ...


@scenario("../features/add-web-backend/blob-storage.feature", "A link is scoped to one object")
def test_a_link_is_scoped_to_one_object() -> None: ...


@scenario("../features/add-web-backend/blob-storage.feature", "Authorization precedes issuance")
def test_authorization_precedes_issuance() -> None: ...


@scenario(
    "../features/add-web-backend/blob-storage.feature", "Corrupted object is not served as valid"
)
def test_corrupted_object_is_not_served_as_valid() -> None: ...


@scenario("../features/add-web-backend/blob-storage.feature", "Corruption is repairable")
def test_corruption_is_repairable() -> None: ...


PROJECT = "cyberdyne-game"
SCOUT_SPEC = "characters/mech_scout/asset.yaml"
FRONT = "characters/mech_scout/concept/front.png"
BEHIND = "characters/mech_scout/concept/behind.png"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

BEHIND_VIEW = b"\x89PNG\r\n\x1a\nthe scout mech, from behind"
EXPORT_BYTES = b"glTF\x02\x00\x00\x00the scout mech, exported"
PREVIEW = PreviewMesh(content=b"glTF-preview-bytes", triangles=3577)

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
EXPIRY = NOON + timedelta(minutes=5)

RAFA = Actor(id=ActorId("auth|rafa"), display_name="Rafa", projects=(PROJECT,))
OUTSIDER = Actor(id=ActorId("auth|outsider"), display_name="Outsider", projects=())

WITH_TWO_VIEWS = f"""\
schema_version: 1
id: mech_scout
name: Scout Mech
concept:
  views:
    - {FRONT}
    - {BEHIND}
""".encode()

WITH_ONE_VIEW = f"""\
schema_version: 1
id: mech_scout
name: Scout Mech
concept:
  views:
    - {FRONT}
""".encode()


@pytest.fixture
def repository() -> InMemoryRepositoryHost:
    """A project whose specification points at two views and one export."""
    host = InMemoryRepositoryHost()
    host.add_project(
        PROJECT,
        {
            SCOUT_SPEC: WITH_TWO_VIEWS,
            FRONT: CONCEPT,
            BEHIND: BEHIND_VIEW,
            EXPORT: EXPORT_BYTES,
        },
    )
    host.clone(PROJECT)
    return host


def _specs(host: InMemoryRepositoryHost, views: tuple[str, ...]) -> InMemorySpecStore:
    """A spec store agreeing with the repository, snapshotted at its head."""
    store = InMemorySpecStore()
    store.add(
        SCOUT_SPEC,
        Asset(id=AssetId("mech_scout"), name="Scout Mech", concept=Concept(views=views)),
    )
    store.snapshot(host.head(PROJECT).value)
    return store


def _mirror(
    host: InMemoryRepositoryHost,
    store: InMemorySpecStore,
    blobs: CountingBlobStore,
    **extra: Any,
):
    return ran(
        mirror_project(
            PROJECT,
            repository_host=host,
            spec_store=store,
            blob_store=blobs,
            exports={"mech_scout": (EXPORT,)},
            **extra,
        )
    )


# -- the repository decides what there is ----------------------------------


@given("a blob present in the store whose source file has been removed from the repository")
def _a_view_removed_from_the_repository(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    store = _specs(repository, (FRONT, BEHIND))
    _mirror(repository, store, mirror)
    repository.push_to_remote(PROJECT, BEHIND, None)
    repository.fetch(PROJECT, confirmed_at=NOON)
    mirrored["store"] = _specs(repository, (FRONT, BEHIND))
    mirrored["key"] = blob_key(ContentHash.of(BEHIND_VIEW))


@when("the asset's views are listed")
def _the_views_are_listed(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    mirrored["views"] = ran(
        views_of(
            PROJECT,
            SCOUT_SPEC,
            repository_host=repository,
            spec_store=mirrored["store"],
            blob_store=mirror,
        )
    )


@then("the removed view SHALL NOT be listed")
def _the_removed_view_is_not_listed(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    listed = tuple(view.path for view in mirrored["views"])

    assert listed == (FRONT,)
    assert mirror.exists(mirrored["key"]), "the object is still stored, and still irrelevant"


@when(
    "content is submitted for storage that corresponds to no repository file and is not "
    "derivable from one"
)
def _sourceless_content_is_submitted(
    mirrored: dict[str, Any], repository: InMemoryRepositoryHost
) -> None:
    mirrored["outcome"] = accept_blob(
        PROJECT,
        b"\x89PNG\r\n\x1a\na painting nobody committed",
        repository_host=repository,
        path="characters/mech_scout/concept/never_committed.png",
    )


@then("it SHALL be refused")
def _sourceless_content_is_refused(mirrored: dict[str, Any]) -> None:
    outcome = mirrored["outcome"]

    assert isinstance(outcome, Invalid)
    assert refused(outcome).identifier == "blob.no_repository_source"


# -- nothing partially visible ---------------------------------------------


@given("an upload interrupted before completion")
def _an_interrupted_upload(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    """The store is told to fail, so `put` never returns and never publishes a key."""
    mirrored["key"] = blob_key(ContentHash.of(CONCEPT))
    mirror.fail_with(OSError("the connection dropped mid-upload"))
    with pytest.raises(OSError):
        mirror.put(CONCEPT)
    mirror.fail_with(None)


@when("its key is read")
def _the_key_is_read(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["read"] = mirror.read(mirrored["key"])
    mirrored["exists"] = mirror.exists(mirrored["key"])


@then("the read SHALL report the object as absent")
def _the_object_is_absent(mirrored: dict[str, Any]) -> None:
    assert mirrored["read"] is None
    assert not mirrored["exists"]


@then("SHALL NOT return truncated content")
def _nothing_truncated(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    with pytest.raises(BlobNotStored):
        mirror.verified(mirrored["key"])


# -- total loss is recoverable ---------------------------------------------


@given("a project whose views and preview meshes are readable")
def _a_mirrored_project(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    store = _specs(repository, (FRONT, BEHIND))
    report = _mirror(
        repository,
        store,
        mirror,
        previews=[DerivedPreview(asset_id="mech_scout", source_export=EXPORT, mesh=PREVIEW)],
    )
    mirrored["store"], mirrored["before"] = store, report
    assert report.is_complete
    assert all(mirror.exists(key) for key in report.keys.values())


@when("the blob store is emptied and re-mirroring runs")
def _the_store_is_emptied_and_re_mirrored(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    mirror.empty()
    assert not any(mirror.exists(key) for key in mirrored["before"].keys.values())
    mirrored["after"] = _mirror(
        repository,
        mirrored["store"],
        mirror,
        previews=[DerivedPreview(asset_id="mech_scout", source_export=EXPORT, mesh=PREVIEW)],
    )


@then("every previously readable view, export and preview mesh SHALL be readable again")
def _everything_is_readable_again(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    after = mirrored["after"]

    assert {blob.path for blob in after.mirrored} == {FRONT, BEHIND, EXPORT}
    assert all(mirror.verified(key) for key in after.keys.values())
    assert mirror.preview_for("mech_scout") == mirrored["before"].previews[0]


@then("each SHALL resolve under the key it had before")
def _the_keys_are_unchanged(mirrored: dict[str, Any]) -> None:
    assert mirrored["after"].keys == mirrored["before"].keys


@given("a blob absent from the store and not yet re-mirrored")
def _a_blob_not_yet_mirrored(mirrored: dict[str, Any], repository: InMemoryRepositoryHost) -> None:
    """The repository describes the view; nothing has mirrored it."""
    mirrored["store"] = _specs(repository, (FRONT, BEHIND))


@when("it is requested")
def _the_blob_is_requested(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    mirrored["outcome"] = link_to_blob(
        RAFA,
        PROJECT,
        FRONT,
        repository_host=repository,
        blob_store=mirror,
        expires_at=EXPIRY,
    )
    mirrored["views"] = ran(
        views_of(
            PROJECT,
            SCOUT_SPEC,
            repository_host=repository,
            spec_store=mirrored["store"],
            blob_store=mirror,
        )
    )


@then("the response SHALL report it as temporarily unavailable")
def _reported_temporarily_unavailable(mirrored: dict[str, Any]) -> None:
    outcome = mirrored["outcome"]

    assert isinstance(outcome, Unavailable)
    assert refused(outcome).identifier == "blob.not_mirrored"


@then("SHALL NOT report the asset as having no such view")
def _the_view_is_still_the_assets(mirrored: dict[str, Any]) -> None:
    listed = {view.path: view.stored for view in mirrored["views"]}

    assert listed == {FRONT: False, BEHIND: False}


# -- links are bounded ------------------------------------------------------


@given("a link issued for a blob")
def _a_link_issued(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    _mirror(repository, _specs(repository, (FRONT, BEHIND)), mirror)
    mirrored["link"] = ran(
        link_to_blob(
            RAFA,
            PROJECT,
            FRONT,
            repository_host=repository,
            blob_store=mirror,
            expires_at=EXPIRY,
        )
    )


@when("it is used after its expiry")
def _used_after_expiry(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    mirrored["refusal"] = _refused_access(
        mirror, mirrored["link"].url, EXPIRY + timedelta(seconds=1)
    )


@then("access SHALL be refused")
def _access_was_refused(mirrored: dict[str, Any]) -> None:
    assert isinstance(mirrored["refusal"], LinkRefused)


@given("a link issued for one blob")
def _a_link_for_one_blob(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    _a_link_issued(mirrored, mirror, repository)
    mirrored["other"] = blob_key(ContentHash.of(BEHIND_VIEW))


@when("it is modified to address a different stored object")
def _the_link_is_rewritten(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    link = mirrored["link"]
    rewritten = link.url.replace(link.key, mirrored["other"])

    assert rewritten != link.url
    assert mirror.exists(mirrored["other"]), "the other object really is stored"
    mirrored["refusal"] = _refused_access(mirror, rewritten, EXPIRY - timedelta(seconds=1))


@given("an actor not permitted to read an asset")
def _an_actor_who_may_not_read(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    _mirror(repository, _specs(repository, (FRONT, BEHIND)), mirror)
    mirrored["actor"] = OUTSIDER
    mirrored["issued_before"] = mirror.issued


@when("a link to one of that asset's blobs is requested")
def _a_link_is_requested(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    mirrored["outcome"] = link_to_blob(
        mirrored["actor"],
        PROJECT,
        FRONT,
        repository_host=repository,
        blob_store=mirror,
        expires_at=EXPIRY,
    )


@then("the request SHALL be refused")
def _the_link_request_was_refused(mirrored: dict[str, Any]) -> None:
    outcome = mirrored["outcome"]

    assert isinstance(outcome, Forbidden)
    assert refused(outcome).identifier == "project.read_refused"


@then("no link SHALL be issued")
def _no_link_was_issued(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    assert mirror.issued == mirrored["issued_before"] == 0


# -- corruption is reported, and repairable ---------------------------------


@given("a stored object whose bytes no longer match its key's digest")
def _a_corrupted_object(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    store = _specs(repository, (FRONT, BEHIND))
    _mirror(repository, store, mirror)
    key = blob_key(ContentHash.of(CONCEPT))
    mirror._blobs[key] = b"\x89PNG\r\n\x1a\nthese are not those bytes"
    mirrored["store"], mirrored["key"] = store, key


@when("it is read")
def _the_corrupted_object_is_read(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    try:
        mirrored["served"] = mirror.verified(mirrored["key"])
    except BlobCorrupted as reported:
        mirrored["served"], mirrored["reported"] = None, reported


@then("the service SHALL report it as corrupt")
def _corruption_was_reported(mirrored: dict[str, Any]) -> None:
    reported = mirrored.get("reported")

    assert isinstance(reported, BlobCorrupted)
    assert reported.kind is FailureKind.UNAVAILABLE


@then("SHALL NOT serve the mismatched bytes as the asset's content")
def _the_mismatched_bytes_were_not_served(mirrored: dict[str, Any]) -> None:
    assert mirrored["served"] is None


@given("an object reported as corrupt")
def _an_object_reported_corrupt(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    _a_corrupted_object(mirrored, mirror, repository)
    _the_corrupted_object_is_read(mirrored, mirror)
    assert isinstance(mirrored.get("reported"), BlobCorrupted)


@when("re-mirroring runs for its project")
def _re_mirroring_runs(
    mirrored: dict[str, Any], mirror: CountingBlobStore, repository: InMemoryRepositoryHost
) -> None:
    _mirror(repository, mirrored["store"], mirror)


@then("the object SHALL be replaced by content matching its key")
def _the_object_was_repaired(mirrored: dict[str, Any], mirror: CountingBlobStore) -> None:
    assert mirror.verified(mirrored["key"]) == CONCEPT


def _refused_access(mirror: CountingBlobStore, url: str, now: datetime) -> Exception | None:
    """What the store says when the link is presented at that moment."""
    try:
        mirror.resolve_link(url, now=now)
    except LinkRefused as refusal:
        return refusal
    return None
