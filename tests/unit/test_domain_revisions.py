"""Task 4.4/4.5 support — revisions, content hashes, keys and staleness.

Three values the hosted surface is specified in terms of, and three properties
that have to hold for the specification to mean anything:

* a **content hash** is a function of the bytes and nothing else, which is what
  makes D5's conflict detection exact and D14's mirroring idempotent;
* a **blob key** is a function of the hash and nothing else — not the name, not
  the asset, not the time — which is what lets recovery be stated as *"readable
  again under the same keys"*;
* **staleness** is arithmetic over the last confirmation, so a response can say
  *may be stale* without anybody maintaining a flag.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.domain.revisions import (
    BLOB_PREFIX,
    DIGEST,
    ContentHash,
    Revision,
    ServedRevision,
    blob_key,
    digest_of_key,
)

VIEW = b"\x89PNG\r\n\x1a\nthe scout mech"
OTHER = b"\x89PNG\r\n\x1a\nthe mule"

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
INTERVAL = timedelta(minutes=5)


# --------------------------------------------------------------------------
# Revision
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", " ", " padded", "has space"])
def test_a_revision_is_a_non_empty_unpadded_word(value: str) -> None:
    with pytest.raises(ValueError, match="revision"):
        Revision(value)


def test_a_revision_renders_as_its_value_and_abbreviates_for_a_person() -> None:
    revision = Revision("0123456789abcdef0123456789abcdef01234567")

    assert str(revision) == revision.value
    assert revision.short == "0123456789ab"


# --------------------------------------------------------------------------
# ContentHash
# --------------------------------------------------------------------------


def test_a_content_hash_is_the_digest_of_the_bytes() -> None:
    assert ContentHash.of(VIEW).value == hashlib.sha256(VIEW).hexdigest()


def test_identical_bytes_hash_identically_and_different_bytes_do_not() -> None:
    assert ContentHash.of(VIEW) == ContentHash.of(bytes(VIEW))
    assert ContentHash.of(VIEW) != ContentHash.of(OTHER)


def test_a_hash_names_the_algorithm_that_produced_it() -> None:
    """A key that does not name its algorithm cannot be migrated to another."""
    digest = ContentHash.of(VIEW)

    assert digest.labelled == f"{DIGEST}:{digest.value}"
    assert str(digest) == digest.labelled
    assert digest.short == digest.value[:12]


def test_a_hash_answers_whether_these_are_the_bytes_it_was_taken_of() -> None:
    digest = ContentHash.of(VIEW)

    assert digest.matches(VIEW)
    assert not digest.matches(OTHER)


@pytest.mark.parametrize("value", ["", " ", " padded"])
def test_a_content_hash_is_non_empty_and_unpadded(value: str) -> None:
    with pytest.raises(ValueError, match="content hash"):
        ContentHash(value)


# --------------------------------------------------------------------------
# Keys (D14)
# --------------------------------------------------------------------------


def test_a_key_is_derived_from_the_digest_and_from_nothing_else() -> None:
    digest = ContentHash.of(VIEW)

    key = blob_key(digest)

    assert key.startswith(f"{BLOB_PREFIX}/{DIGEST}/")
    assert key == blob_key(ContentHash.of(bytes(VIEW)))


def test_a_key_fans_out_so_no_directory_holds_everything() -> None:
    digest = ContentHash.of(VIEW)

    assert blob_key(digest).split("/")[2] == digest.value[:2]


def test_a_key_states_what_its_bytes_must_hash_to() -> None:
    """The inverse, and the reason a read can verify what it served."""
    digest = ContentHash.of(VIEW)

    assert digest_of_key(blob_key(digest)) == digest


@pytest.mark.parametrize(
    "key", ["", "previews/mech_scout/x.glb", "blobs/md5/aa/bb", "blobs/sha256/aa"]
)
def test_a_key_that_is_not_ours_decodes_to_nothing(key: str) -> None:
    assert digest_of_key(key) is None


# --------------------------------------------------------------------------
# Staleness
# --------------------------------------------------------------------------


def test_a_served_revision_knows_how_old_its_confirmation_is() -> None:
    served = ServedRevision(Revision("abc123"), NOON)

    assert served.age(NOON + INTERVAL) == INTERVAL


def test_content_confirmed_within_the_interval_is_not_stale() -> None:
    served = ServedRevision(Revision("abc123"), NOON)

    assert not served.may_be_stale(NOON + INTERVAL, INTERVAL)


def test_content_confirmed_longer_ago_than_the_interval_may_be_stale() -> None:
    """*May be*, because what is certainly true is that nobody has checked."""
    served = ServedRevision(Revision("abc123"), NOON)

    assert served.may_be_stale(NOON + INTERVAL + timedelta(seconds=1), INTERVAL)
