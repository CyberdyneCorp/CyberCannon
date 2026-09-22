"""Task 12.4 in the domain — when a validation outcome is worth a commit (G2).

Two decisions, both pure, both here rather than in the worker: whether a run is
worth doing at all, and whether its outcome is different enough from the
recorded one to be written back. G2's mitigation is the second one — *"a
repeated run of an unchanged export writes nothing"* — and the reason it is a
function is that a worker which re-derived it would eventually derive it
differently from the surface that reports it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from cybercanon.domain.validation_outcome import (
    AUTOMATION,
    ValidationRecord,
    needs_commit,
    needs_validation,
)

NOON = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

RECORDED = ValidationRecord(
    asset_id="mech_scout",
    export=EXPORT,
    export_hash="a" * 8,
    passed=True,
    validated_at=NOON,
    spec_hash="b" * 8,
)


def test_an_export_nobody_has_validated_is_always_worth_a_run() -> None:
    assert needs_validation(None, export=EXPORT, export_hash="a" * 8, spec_hash="b" * 8)


def test_an_unchanged_export_under_an_unchanged_spec_is_not_re_read() -> None:
    """G1 — the worker runs *when the working copy fetches a changed export*."""
    assert not needs_validation(RECORDED, export=EXPORT, export_hash="a" * 8, spec_hash="b" * 8)


def test_a_changed_export_is_re_validated() -> None:
    assert needs_validation(RECORDED, export=EXPORT, export_hash="c" * 8, spec_hash="b" * 8)


def test_a_changed_specification_is_re_validated_against_the_same_export() -> None:
    """A promoted constraint changes the verdict without changing one byte of mesh."""
    assert needs_validation(RECORDED, export=EXPORT, export_hash="a" * 8, spec_hash="z" * 8)


def test_a_different_export_of_the_same_asset_is_validated() -> None:
    other = "characters/mech_scout/exports/SM_mech_scout_LOD1.glb"
    assert needs_validation(RECORDED, export=other, export_hash="a" * 8, spec_hash="b" * 8)


def test_a_first_outcome_is_always_committed() -> None:
    assert needs_commit(None, RECORDED)


def test_an_identical_outcome_taken_later_is_not_committed() -> None:
    """The validation time moves on every run; comparing it would make G2 vacuous."""
    again = replace(RECORDED, validated_at=NOON + timedelta(hours=3))

    assert not needs_commit(RECORDED, again)


def test_a_changed_verdict_is_committed() -> None:
    assert needs_commit(RECORDED, replace(RECORDED, passed=False))


def test_a_changed_export_hash_is_committed() -> None:
    assert needs_commit(RECORDED, replace(RECORDED, export_hash="d" * 8))


def test_a_different_export_is_committed_even_at_the_same_verdict() -> None:
    """*Which* export was validated is half the answer `where_is` gives."""
    other = replace(RECORDED, export="characters/mech_scout/exports/SM_mech_scout_LOD1.glb")

    assert needs_commit(RECORDED, other)


def test_an_outcome_with_no_person_is_attributed_to_automation() -> None:
    assert RECORDED.attributed_to == AUTOMATION
    assert RECORDED.by_automation


def test_the_verdict_is_a_word_a_commit_message_can_carry() -> None:
    assert RECORDED.verdict == "passed"
    assert replace(RECORDED, passed=False).verdict == "failed"
