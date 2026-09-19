"""Task 3.3 — the digest recorded at build time, and the two checks over it.

`deployment-operations` names three behaviours and every one of them is a
question about the record rather than about a build, which is why they can be
asserted with nothing running:

* *"built once per revision"* — recording a **second, different** digest for a
  revision is refused. That refusal is the mechanism rather than a warning: a
  promotion that rebuilt would have to record its new digest somewhere, and
  there is nowhere for it to go;
* *"the digest of the running artifact SHALL equal the recorded digest"* — the
  promotion check compares them and, when they differ, names both. "Promotion
  failed" without the pair is a sentence nobody can act on;
* *"when the previous revision's recorded digest is deployed ... no rebuild
  SHALL be required"* — a rollback answers with the digest to deploy and says
  whether the ledger holds it, so the one case that would need a build is
  reported instead of performed.

What is *not* asserted here is that a real engine produced these digests; that
is `tests/tooling/test_container_artifacts.py`'s build, which needs one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_release.digests import (
    API,
    WEB,
    AlreadyBuilt,
    Build,
    Ledger,
    promotion,
    promotions,
    rollback,
)

pytestmark = pytest.mark.unit

FIRST = "sha256:" + "1" * 64
SECOND = "sha256:" + "2" * 64
OTHER = "sha256:" + "3" * 64

REVISION = "a" * 40
NEXT = "b" * 40


def built(image: str = API, revision: str = REVISION, digest: str = FIRST) -> Build:
    return Build(image=image, revision=revision, digest=digest, built_at="2026-09-19T10:00:00Z")


# --------------------------------------------------------------------------
# Built once per revision
# --------------------------------------------------------------------------


def test_a_build_is_recorded_against_its_revision() -> None:
    ledger = Ledger().record(built())

    assert ledger.digest_for(API, REVISION) == FIRST


def test_recording_the_same_build_again_changes_nothing() -> None:
    """A retried pipeline records what is already there rather than a duplicate."""
    ledger = Ledger().record(built()).record(built())

    assert len(ledger.builds) == 1


def test_a_second_digest_for_one_revision_is_refused() -> None:
    """The artifact is built once; a different digest means it was built twice."""
    ledger = Ledger().record(built())

    with pytest.raises(AlreadyBuilt) as refused:
        ledger.record(built(digest=SECOND))

    assert refused.value.recorded == FIRST
    assert refused.value.offered == SECOND


def test_the_two_images_are_recorded_separately() -> None:
    ledger = Ledger().record(built(API)).record(built(WEB, digest=SECOND))

    assert ledger.digest_for(WEB, REVISION) == SECOND
    assert ledger.digest_for(API, REVISION) == FIRST


def test_a_revision_nobody_built_has_no_digest() -> None:
    assert Ledger().digest_for(API, REVISION) == ""


def test_a_digest_is_a_content_digest_rather_than_a_tag() -> None:
    assert built().is_digest
    assert not Build(image=API, revision=REVISION, digest="latest").is_digest


# --------------------------------------------------------------------------
# Promotion preserves the digest
# --------------------------------------------------------------------------


def test_promotion_conforms_when_the_running_digest_is_the_recorded_one() -> None:
    ledger = Ledger().record(built())

    verdict = promotion(
        ledger, image=API, revision=REVISION, environment="production", running=FIRST
    )

    assert verdict.conforms
    assert verdict.reason == ""


def test_a_rebuilt_artifact_fails_the_promotion_check_naming_both_digests() -> None:
    ledger = Ledger().record(built())

    verdict = promotion(
        ledger, image=API, revision=REVISION, environment="production", running=OTHER
    )

    assert not verdict.conforms
    assert FIRST in verdict.reason and OTHER in verdict.reason


def test_an_unrecorded_revision_is_reported_as_never_verified() -> None:
    verdict = promotion(
        Ledger(), image=API, revision=REVISION, environment="production", running=FIRST
    )

    assert not verdict.conforms
    assert "never verified" in verdict.reason


def test_every_environment_is_checked_against_the_same_record() -> None:
    """The point of the check: pre-production and production run one artifact."""
    ledger = Ledger().record(built())

    verdicts = promotions(
        ledger,
        image=API,
        revision=REVISION,
        running={"pre-production": FIRST, "production": FIRST},
    )

    assert [verdict.environment for verdict in verdicts] == ["pre-production", "production"]
    assert all(verdict.conforms for verdict in verdicts)


# --------------------------------------------------------------------------
# Rollback selects a previously built artifact
# --------------------------------------------------------------------------


def test_the_previous_revision_is_the_one_built_before_it() -> None:
    ledger = Ledger().record(built()).record(built(revision=NEXT, digest=SECOND))

    assert ledger.previous(API, NEXT) == REVISION


def test_rolling_back_deploys_a_recorded_digest_and_needs_no_build() -> None:
    ledger = Ledger().record(built()).record(built(revision=NEXT, digest=SECOND))

    target = rollback(ledger, image=API, revision=ledger.previous(API, NEXT))

    assert target.digest == FIRST
    assert not target.requires_build


def test_rolling_back_to_a_revision_nobody_built_says_it_needs_one() -> None:
    target = rollback(Ledger(), image=API, revision=REVISION)

    assert target.requires_build


def test_the_first_recorded_revision_has_nothing_to_roll_back_to() -> None:
    ledger = Ledger().record(built())

    assert ledger.previous(API, REVISION) == ""


# --------------------------------------------------------------------------
# The ledger is a file in the repository
# --------------------------------------------------------------------------


def test_the_ledger_round_trips_through_its_file(tmp_path: Path) -> None:
    ledger = Ledger().record(built()).record(built(WEB, digest=SECOND))
    path = tmp_path / "digests.json"

    ledger.write(path)

    assert Ledger.read(path) == ledger


def test_a_missing_ledger_reads_as_an_empty_one(tmp_path: Path) -> None:
    """A checkout that has built nothing yet is not a broken checkout."""
    assert Ledger.read(tmp_path / "nothing.json") == Ledger()
