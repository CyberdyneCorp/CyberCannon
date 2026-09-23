"""Tasks 3.1-3.4 — the derived-metadata domain: keys, normalisation, parsing, decisions.

Pure, with no model, no index and no file anywhere. That is the payoff the same
boundary bought for meshes and for images: *"asking a model politely not to
repeat existing aliases is a suggestion; filtering afterwards is a guarantee —
and it is testable with no model"*.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cybercanon.domain.derived import (
    GENERATED,
    MAX_ALIAS_LENGTH,
    MAX_SUGGESTIONS,
    DerivedRecord,
    Provenance,
    SuggestionDecision,
    SuggestionState,
    accepted_decision,
    decided,
    excluded_terms,
    is_normalised,
    normalise,
    normalised_aliases,
    parse_aliases,
    pending,
    rejected_decision,
    suggestions_by_asset,
)

pytestmark = pytest.mark.unit

MOMENT = datetime(2026, 9, 22, 11, 30, tzinfo=UTC)
ONE = "a" * 64
TWO = "b" * 64


def a_record(
    source_hash: str = ONE,
    asset_id: str = "mech_scout",
    suggested: tuple[str, ...] = ("mech", "walker"),
    model: str = "vision-v1",
) -> DerivedRecord:
    return DerivedRecord(
        provenance=Provenance(model=model, generated_at=MOMENT, source_hash=source_hash),
        asset_id=asset_id,
        source_path="characters/mech_scout/concept/front.png",
        description="A light reconnaissance walker.",
        suggested_aliases=suggested,
    )


# --------------------------------------------------------------------------
# 3.1 — keyed by source content, and equality is that key (D5)
# --------------------------------------------------------------------------


def test_two_records_for_the_same_image_are_the_same_record() -> None:
    """Regeneration produces *the same record*, however the words came out."""
    first = a_record(suggested=("mech",))
    second = a_record(suggested=("walker", "quadruped"))

    assert first == second
    assert len({first, second}) == 1


def test_a_record_for_different_bytes_is_a_different_record() -> None:
    """A replaced image never inherits the description of the one before it."""
    assert a_record(ONE) != a_record(TWO)


def test_a_record_carries_its_whole_provenance() -> None:
    record = a_record()

    assert record.model == "vision-v1"
    assert record.generated_at == MOMENT
    assert record.source_hash == ONE
    assert record.label == GENERATED


def test_provenance_reads_as_one_line_naming_all_three() -> None:
    described = a_record().provenance.described

    assert GENERATED in described
    assert "vision-v1" in described
    assert MOMENT.isoformat() in described
    assert ONE[:12] in described


def test_a_record_must_name_the_content_it_came_from() -> None:
    with pytest.raises(ValueError, match="came from"):
        Provenance(model="vision-v1", generated_at=MOMENT, source_hash="")


def test_a_record_is_never_equal_to_something_that_is_not_one() -> None:
    assert a_record() != ONE


# --------------------------------------------------------------------------
# 3.2 — normalisation and exclusion (D11)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Mech  ", "mech"),
        ("Scout Mech", "scout_mech"),
        ("Heavy/Hauler", "heavy_hauler"),
        ("MECH!!", "mech"),
        ("quad-ruped", "quad-ruped"),
        ("---", ""),
        ("", ""),
        ("a" * (MAX_ALIAS_LENGTH + 10), "a" * MAX_ALIAS_LENGTH),
    ],
)
def test_normalisation_produces_specification_form(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_a_normalised_term_is_already_normalised() -> None:
    """The property the scenario asserts: suggestions are in specification form."""
    for raw in ("Scout Mech", "MECH", " walker "):
        assert is_normalised(normalise(raw))


def test_existing_aliases_are_never_suggested() -> None:
    """`derived-metadata`: an asset declaring `mech` is never offered `mech`."""
    excluded = excluded_terms("mech_scout", "Scout Mech", ("mech",))

    assert normalised_aliases(("Mech", "walker", "MECH"), excluding=excluded) == ("walker",)


def test_the_identifier_and_the_name_are_excluded_too() -> None:
    excluded = excluded_terms("mech_scout", "Scout Mech", ())

    assert normalised_aliases(("mech_scout", "Scout Mech", "recon"), excluding=excluded) == (
        "recon",
    )


def test_duplicates_collapse_in_first_seen_order() -> None:
    assert normalised_aliases(("walker", "Walker", "mech", "walker")) == ("walker", "mech")


def test_suggestions_are_capped() -> None:
    many = tuple(f"term{index}" for index in range(MAX_SUGGESTIONS + 5))

    assert len(normalised_aliases(many)) == MAX_SUGGESTIONS


# --------------------------------------------------------------------------
# 3.3 — defensive parsing: malformed rather than partly accepted (D10)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("mech, walker, quadruped", ("mech", "walker", "quadruped")),
        ("[mech, walker]", ("mech", "walker")),
        ("mech\nwalker\n", ("mech", "walker")),
        ("- mech\n- walker", ("mech", "walker")),
        ('1. "mech"\n2. "walker"', ("mech", "walker")),
        ("Scout Mech, recon", ("scout_mech", "recon")),
    ],
)
def test_a_well_formed_answer_reads_as_terms(answer: str, expected: tuple[str, ...]) -> None:
    assert parse_aliases(answer) == expected


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "   ",
        "mech, , walker",
        "mech, !!!, walker",
        ", ".join(f"term{index}" for index in range(MAX_SUGGESTIONS * 2 + 1)),
    ],
)
def test_an_answer_that_is_not_a_list_of_terms_is_refused_whole(answer: str) -> None:
    """A half-parsed alias list is worse than none: it is the one somebody accepts."""
    assert parse_aliases(answer) is None


def test_prose_around_the_list_is_not_silently_salvaged() -> None:
    """A model that explained itself produced something this cannot read."""
    assert parse_aliases("Here are some terms: mech; walker") is None


# --------------------------------------------------------------------------
# 3.4 — decisions are keyed by (content hash, value) (D6)
# --------------------------------------------------------------------------


def test_a_decision_is_filed_under_the_image_and_the_value() -> None:
    decision = rejected_decision(ONE, "walker", actor="auth|rafa", at=MOMENT)

    assert decision.key == (ONE, "walker")
    assert decision.state is SuggestionState.REJECTED


def test_an_acceptance_records_the_person_and_the_moment() -> None:
    decision = accepted_decision(ONE, "walker", "auth|rafa", MOMENT)

    assert decision.actor == "auth|rafa"
    assert decision.at == MOMENT
    assert decision.recorded == "walker"


def test_an_edited_acceptance_records_what_was_actually_written() -> None:
    decision = accepted_decision(ONE, "walker", "auth|rafa", MOMENT, written="strider")

    assert decision.value == "walker"
    assert decision.recorded == "strider"


def test_an_acceptance_with_nobody_behind_it_is_not_constructible() -> None:
    with pytest.raises(ValueError, match="attributed"):
        accepted_decision(ONE, "walker", "", MOMENT)


def test_a_pending_decision_is_not_a_decision() -> None:
    with pytest.raises(ValueError, match="never pending"):
        SuggestionDecision(source_hash=ONE, value="walker", state=SuggestionState.PENDING)


def test_a_rejection_survives_regenerating_the_same_image() -> None:
    """The key is the image, so the same record produced again is still refused."""
    rejection = rejected_decision(ONE, "walker")

    assert pending(a_record(ONE), [rejection]) == ("mech",)
    assert pending(a_record(ONE), [rejection]) == ("mech",)


def test_a_rejection_for_one_image_says_nothing_about_another() -> None:
    assert pending(a_record(TWO), [rejected_decision(ONE, "walker")]) == ("mech", "walker")


def test_every_suggestion_carries_the_state_somebody_left_it_in() -> None:
    taken = (accepted_decision(ONE, "mech", "auth|rafa", MOMENT),)

    states = {entry.value: entry.state for entry in decided(a_record(ONE), taken)}

    assert states == {"mech": SuggestionState.ACCEPTED, "walker": SuggestionState.PENDING}


def test_a_pending_suggestion_is_labelled_generated_and_an_accepted_one_is_not() -> None:
    taken = (accepted_decision(ONE, "mech", "auth|rafa", MOMENT),)

    labels = {entry.value: entry.label for entry in decided(a_record(ONE), taken)}

    assert labels == {"mech": "accepted", "walker": GENERATED}


def test_an_assets_pending_suggestions_are_collected_across_its_images() -> None:
    records = (a_record(ONE, suggested=("mech",)), a_record(TWO, suggested=("walker", "mech")))

    assert suggestions_by_asset(records, ()) == {"mech_scout": ("mech", "walker")}


def test_a_record_with_no_asset_contributes_nothing_to_the_sixth_pass() -> None:
    assert suggestions_by_asset((a_record(asset_id=""),), ()) == {}
