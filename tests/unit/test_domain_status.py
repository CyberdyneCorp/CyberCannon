"""Task 2.1 — the status lifecycle is an ordered set, and only that set."""

from __future__ import annotations

import operator
from collections.abc import Callable

import pytest

from cybercanon.domain.status import Status

ORDER = ("concept", "approved", "modeling", "validated", "in-engine")


def test_the_lifecycle_is_exactly_the_specified_set_in_order() -> None:
    assert Status.values() == ORDER


@pytest.mark.parametrize("value", ORDER)
def test_every_declared_value_parses(value: str) -> None:
    status = Status.from_value(value)

    assert status is not None
    assert status.value == value


@pytest.mark.parametrize("value", ["wip", "", "Concept", "in_engine", "archived"])
def test_a_status_outside_the_set_is_rejected(value: str) -> None:
    """Rejected by returning None, so the file's other findings survive the run."""
    assert Status.from_value(value) is None


def test_the_order_is_the_lifecycle_order() -> None:
    assert Status.CONCEPT.rank == 0
    assert Status.IN_ENGINE.rank == len(ORDER) - 1
    assert sorted(Status, key=lambda status: status.rank) == list(Status)


def test_statuses_compare_by_lifecycle_position() -> None:
    assert Status.CONCEPT < Status.APPROVED < Status.MODELING
    assert Status.IN_ENGINE > Status.VALIDATED
    assert Status.MODELING >= Status.MODELING
    assert Status.MODELING <= Status.VALIDATED


ORDERINGS = (operator.lt, operator.le, operator.gt, operator.ge)


@pytest.mark.parametrize("compare", ORDERINGS, ids=lambda item: item.__name__)
@pytest.mark.parametrize("other", ["approved", 2, None])
def test_comparison_with_a_non_status_is_not_defined(
    compare: Callable[[object, object], bool], other: object
) -> None:
    """A status is ordered against a status; anything else is a type error."""
    with pytest.raises(TypeError):
        compare(Status.APPROVED, other)


def test_a_status_renders_as_the_value_a_file_declares() -> None:
    assert str(Status.IN_ENGINE) == "in-engine"
