"""Step definitions for `blob-storage` — content addressing, from group 4.

Task 4.5 gives the `BlobStore` port its content-addressed half (D14): a key is
the digest of the bytes, derived in the domain
(:func:`cybercanon.domain.revisions.blob_key`) so the two implementations cannot
disagree about it. Four of this capability's scenarios are answerable by that
alone, and they are the four bound here — every one of them is a property *of
the key*, which is exactly what content addressing buys.

The rest stay in `tests/bdd/pending.txt` for group 7, and for a reason worth
writing down: they are about **serving** a blob rather than keying one. An
expired link, a link rewritten to another object, an authorization decision
before issuance, a corrupt object reported rather than served, a store emptied
and re-mirrored — all need the verification and re-mirroring operations that
group 7 builds. Binding them now against issuance alone would assert nothing.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.domain.revisions import ContentHash, blob_key

CONCEPT = b"\x89PNG\r\n\x1a\nthe scout mech, three-quarter view"
REPAINTED = b"\x89PNG\r\n\x1a\nthe scout mech, three-quarter view, repainted"


@pytest.fixture
def mirror() -> InMemoryBlobStore:
    """The blob store this scenario mirrors into."""
    return InMemoryBlobStore()


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
def _both_are_mirrored(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    mirrored["first"] = mirror.put(mirrored["from_scout"])
    mirrored["second"] = mirror.put(mirrored["from_mule"])


@then("both SHALL resolve to the same key and one stored object")
def _one_key_one_object(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    first, second = mirrored["first"], mirrored["second"]

    assert first.key == second.key == blob_key(ContentHash.of(CONCEPT))
    assert mirror.read(first.key) == CONCEPT


@given("a stored blob")
def _a_stored_blob(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    mirrored["old"] = mirror.put(CONCEPT)


@when("its source file's bytes change")
def _the_bytes_change(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    mirrored["new"] = mirror.put(REPAINTED)


@then("the new content SHALL store under a different key")
def _a_different_key(mirrored: dict[str, Any]) -> None:
    assert mirrored["new"].key != mirrored["old"].key


@then("references to the old key SHALL continue to resolve to the old content until it is removed")
def _the_old_key_still_resolves(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    assert mirror.read(mirrored["old"].key) == CONCEPT
    assert mirror.exists(mirrored["old"].key)


@given("a mirrored file")
def _a_mirrored_file(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    mirrored["before"] = mirror.put(CONCEPT)
    mirrored["named"] = "concept/scout_three_quarter.png"


@when("the file is renamed in the repository with unchanged content")
def _it_is_renamed(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    mirrored["named"] = "concept/scout_hero.png"
    mirrored["after"] = mirror.put(CONCEPT)


@then("its key SHALL be unchanged")
def _the_key_did_not_move(mirrored: dict[str, Any]) -> None:
    assert mirrored["after"].key == mirrored["before"].key


# --------------------------------------------------------------------------
# Mirroring is idempotent
# --------------------------------------------------------------------------


@given("content already stored under its key")
def _content_already_stored(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    mirrored["before"] = mirror.put(CONCEPT)


@when("it is mirrored again")
def _mirrored_again(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    mirrored["again"] = mirror.put(CONCEPT)


@then("the operation SHALL succeed")
def _it_succeeded(mirrored: dict[str, Any]) -> None:
    assert mirrored["again"].key == mirrored["before"].key


@then("the stored object SHALL be unchanged")
def _the_object_is_unchanged(mirrored: dict[str, Any], mirror: InMemoryBlobStore) -> None:
    assert mirror.read(mirrored["again"].key) == CONCEPT
    assert mirrored["again"].size_bytes == mirrored["before"].size_bytes
