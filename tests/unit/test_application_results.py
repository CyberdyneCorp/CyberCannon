"""Task 4.1 — the outcome vocabulary: seven members, one mapping, no gaps.

D10 makes two promises that only hold if they are checked mechanically: every
member carries a stable identifier and the subject at fault, and every kind of
failure has exactly one member to become. Both are asserted here over the union
itself rather than through a use case, so a member added without an identifier
or without a mapping fails the build before anything tries to render it.
"""

from __future__ import annotations

import pytest

from cybercanon.application.errors import GENERIC_FAILURE, FailureKind, OperationFailed
from cybercanon.application.ports.mesh_inspector import UnsupportedExport
from cybercanon.application.ports.spec_store import SpecNotFound, SpecUnreadable
from cybercanon.application.results import (
    OK,
    REFUSALS,
    Conflict,
    Forbidden,
    Invalid,
    NotFound,
    Ok,
    Refusal,
    Unauthenticated,
    Unavailable,
    as_result,
    attempt,
    classify,
    first_refusal,
    refuse,
    succeeded,
    values,
)

MEMBERS = (Ok, NotFound, Forbidden, Unauthenticated, Invalid, Conflict, Unavailable)

IDENTIFIER = "spec.not_found"
SUBJECT = "characters/mech_scout/asset.yaml"
MESSAGE = "no asset.yaml governs that path"


# --------------------------------------------------------------------------
# Every member carries an identifier and a subject
# --------------------------------------------------------------------------


@pytest.mark.parametrize("member", MEMBERS, ids=[member.__name__ for member in MEMBERS])
def test_every_member_is_constructible_with_a_subject_and_an_identifier(
    member: type,
) -> None:
    """`http-api` requires both in every error body, so both live on every member."""
    outcome = (
        member(value=None, identifier=IDENTIFIER, subject=SUBJECT)
        if member is Ok
        else member(identifier=IDENTIFIER, message=MESSAGE, subject=SUBJECT)
    )

    assert outcome.identifier == IDENTIFIER
    assert outcome.subject == SUBJECT


def test_a_success_carries_its_value_and_says_nothing() -> None:
    outcome = Ok("the briefing")

    assert succeeded(outcome)
    assert outcome.value == "the briefing"
    assert outcome.identifier == OK
    assert outcome.message == ""


def test_a_refusal_is_not_a_success() -> None:
    assert not succeeded(NotFound(identifier=IDENTIFIER, message=MESSAGE))


def test_a_refusal_renders_as_its_message() -> None:
    assert str(Forbidden(identifier="project.read_refused", message="you may not")) == (
        "you may not"
    )


def test_a_subject_is_optional_because_some_refusals_have_none() -> None:
    assert Unavailable(identifier="index.unavailable", message="no index").subject == ""


# --------------------------------------------------------------------------
# One mapping, covering every kind exactly once
# --------------------------------------------------------------------------


def test_every_failure_kind_has_exactly_one_member() -> None:
    """The exhaustiveness D10 asks for, over the union rather than over routers."""
    assert set(REFUSALS) == set(FailureKind)
    assert len(set(REFUSALS.values())) == len(FailureKind)


@pytest.mark.parametrize("kind", list(FailureKind), ids=FailureKind.values())
def test_a_kind_becomes_its_member(kind: FailureKind) -> None:
    outcome = refuse(kind, IDENTIFIER, MESSAGE, SUBJECT)

    assert isinstance(outcome, Refusal)
    assert outcome.kind is kind


def test_every_member_declares_the_kind_it_is_registered_under() -> None:
    for kind, member in REFUSALS.items():
        assert member.kind is kind


# --------------------------------------------------------------------------
# Classification comes from the failure's own declaration
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (SpecNotFound("exports/x.glb"), NotFound),
        (SpecUnreadable("asset.yaml", "not YAML"), Invalid),
        (UnsupportedExport("model.3ds", "3DS"), Invalid),
    ],
)
def test_a_named_failure_classifies_as_the_kind_it_declared(
    failure: OperationFailed, expected: type
) -> None:
    assert isinstance(classify(failure), expected)


def test_a_failure_that_declared_nothing_is_unavailable_and_generically_identified() -> None:
    """Visible, safe, and obviously in want of a declaration."""
    outcome = classify(OperationFailed("something went wrong", "a subject"))

    assert isinstance(outcome, Unavailable)
    assert outcome.identifier == GENERIC_FAILURE
    assert outcome.subject == "a subject"


def test_a_failure_with_no_subject_classifies_with_an_empty_one() -> None:
    assert classify(OperationFailed("no subject here")).subject == ""


# --------------------------------------------------------------------------
# `attempt`, and the decorator every use case wears
# --------------------------------------------------------------------------


def test_attempt_turns_a_named_failure_into_a_refusal() -> None:
    def raising() -> str:
        raise SpecNotFound("exports/x.glb")

    assert isinstance(attempt(raising), NotFound)


def test_attempt_lets_an_unexpected_exception_through() -> None:
    """An unexpected error is not an outcome the domain expressed (`http-api`)."""

    def raising() -> str:
        raise ZeroDivisionError("this is a bug, not a refusal")

    with pytest.raises(ZeroDivisionError):
        attempt(raising)


def test_a_use_case_returns_the_union_and_keeps_its_body_reachable() -> None:
    @as_result
    def doubled(value: int) -> int:
        if value < 0:
            raise SpecUnreadable("negative", "no negatives")
        return value * 2

    assert doubled(3) == Ok(6)
    assert isinstance(doubled(-1), Invalid)
    assert doubled.raising(3) == 6
    assert doubled.__name__ == "doubled"


def test_the_first_refusal_is_the_one_the_caller_reads() -> None:
    """`canon validate a.glb b.glb` ends once, in argument order."""
    first = NotFound(identifier="a", message="first")
    second = Invalid(identifier="b", message="second")

    assert first_refusal((Ok(1), first, second)) is first
    assert first_refusal((Ok(1), Ok(2))) is None


def test_the_values_of_a_batch_are_its_successes_in_order() -> None:
    assert values((Ok(1), Ok(2))) == (1, 2)
