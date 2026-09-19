"""Task 9.6 — a total order, a bounded page, and a token that grants nothing.

The traversal property is checked the way the specification phrases it: page
through an unchanged data set to exhaustion, and assert every result appeared
exactly once. Asserting the *count* alone would pass for an implementation that
returned one result twice and skipped another, which is the failure paging
actually has.

The token's emptiness is checked directly rather than argued: it is decoded and
the decoded value is compared against the position, so a token that started
carrying a project, a filter or an actor would fail here rather than in a
security review.
"""

from __future__ import annotations

import base64

import pytest

from cybercanon.adapters.inbound.http import pagination
from cybercanon.application.results import Invalid, Ok

ITEMS = tuple(f"asset_{index:03d}" for index in range(0, 57))


def _page(token: str | None = None, size: int | None = None) -> pagination.Page[str]:
    sliced = pagination.page_of(ITEMS, token=token, size=size)
    assert isinstance(sliced, Ok)
    return sliced.value


def test_a_caller_who_asked_for_no_size_gets_the_default() -> None:
    assert pagination.bounded(None) == pagination.DEFAULT_PAGE_SIZE


def test_an_oversized_page_request_is_bounded_not_refused() -> None:
    """*"the response SHALL return at most the maximum page size"* — bounded, served."""
    page = _page(size=pagination.MAX_PAGE_SIZE * 10)

    assert page.size == pagination.MAX_PAGE_SIZE
    assert len(page.items) == min(pagination.MAX_PAGE_SIZE, len(ITEMS))


def test_a_nonsensical_size_is_bounded_from_below_too() -> None:
    assert pagination.bounded(0) == pagination.MIN_PAGE_SIZE
    assert pagination.bounded(-4) == pagination.MIN_PAGE_SIZE


def test_full_traversal_returns_every_result_exactly_once() -> None:
    """The guarantee itself, over a data set that does not change during traversal."""
    seen: list[str] = []
    token: str | None = None
    for _ in range(len(ITEMS)):
        page = _page(token, size=10)
        seen.extend(page.items)
        token = page.next_token
        if token is None:
            break

    assert token is None
    assert seen == list(ITEMS)
    assert len(seen) == len(set(seen))


def test_the_last_page_carries_no_continuation_token() -> None:
    """Exhaustion is observable, which is what makes the traversal terminate."""
    page = _page(size=len(ITEMS))

    assert page.is_last
    assert page.next_token is None


def test_a_token_carries_a_position_and_nothing_else() -> None:
    """Not a filter and not a grant, because there is nothing in it to be one."""
    token = pagination.encode(25)
    decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode("ascii")

    assert decoded == "25"
    assert pagination.decode(token) == Ok(25)


def test_a_token_this_surface_did_not_issue_is_refused() -> None:
    """Never a silent restart: a traversal resumed from zero never exhausts."""
    refusal = pagination.decode("not-a-token-we-made")

    assert isinstance(refusal, Invalid)
    assert refusal.identifier == pagination.TOKEN_IDENTIFIER


@pytest.mark.parametrize("token", ["!!!", "bm90LWEtbnVtYmVy", "MTA9PQ"])
def test_unreadable_tokens_are_invalid_rather_than_ignored(token: str) -> None:
    """A listing resumed from a token we did not issue stops where a caller sees it."""
    assert isinstance(pagination.page_of(ITEMS, token=token), Invalid)


def test_a_negative_position_is_refused() -> None:
    """Otherwise Python's slicing would read from the end and repeat results."""
    assert isinstance(pagination.decode(pagination.encode(-3)), Invalid)


def test_a_page_reports_the_total_and_the_size_it_applied() -> None:
    page = _page(size=7)

    assert page.total == len(ITEMS)
    assert page.size == 7
    assert len(page.items) == 7


def test_a_rendered_page_carries_its_items_and_its_next_token() -> None:
    body = pagination.rendered(_page(size=3), str.upper)

    assert body["items"] == ["ASSET_000", "ASSET_001", "ASSET_002"]
    assert body["next_token"] == pagination.encode(3)
    assert body["page_size"] == 3
    assert body["total"] == len(ITEMS)
