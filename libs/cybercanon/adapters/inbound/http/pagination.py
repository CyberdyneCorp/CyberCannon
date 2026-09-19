"""Paging: a deterministic order, a bounded page, and a token that grants nothing.

`http-api` asks for four properties and the fourth is the one that shapes the
other three:

1. **a deterministic total order** — otherwise "each result exactly once" is not
   even definable;
2. **a default and a maximum page size** — a caller asking for everything gets
   the maximum rather than an unbounded scan;
3. **an opaque continuation token** when more results exist;
4. **a token that is not interpretable as a filter or an authorization grant.**

The fourth is satisfied by *what the token does not contain*, which is the only
way to satisfy it honestly. A token carries a position and nothing else — no
project, no query, no actor, no entitlement — so presenting somebody else's
token cannot widen what a caller may see: the request is authorized on its own
terms, exactly as a first page would be, and the token only says *where in the
order to resume*. A token that carried the query it came from would be a filter;
one that carried the actor it was issued to would be a grant. This one cannot
become either, because there is nothing in it to become.

It is still **opaque**: base64 without padding, so a client that tried to
construct one by hand is doing something the next version will break, and a
client that round-trips ours is doing the specified thing. Opaque is not
security — a caller who decodes it learns an integer — and it is not claimed to
be. Security is that the integer grants nothing.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cybercanon.application.results import Invalid, Ok, Result

DEFAULT_PAGE_SIZE = 25
"""What a caller who asked for no size gets."""

MAX_PAGE_SIZE = 100
"""The ceiling. A request above it is bounded, never refused (`http-api`)."""

MIN_PAGE_SIZE = 1

TOKEN_IDENTIFIER = "page.token_unreadable"
SIZE_IDENTIFIER = "page.size_invalid"

ENCODING = "ascii"
PADDING = "="


def bounded(size: int | None) -> int:
    """The page size this request actually gets.

    *"When a caller requests a page larger than the maximum ... the response
    SHALL return at most the maximum page size."* Bounded rather than refused,
    because a client asking for more than we will give is not making a mistake
    it can act on — it is asking for everything, and the answer is the ceiling.
    """
    if size is None:
        return DEFAULT_PAGE_SIZE
    return max(MIN_PAGE_SIZE, min(size, MAX_PAGE_SIZE))


def encode(position: int) -> str:
    """One position as an opaque token. Nothing else travels in it."""
    return base64.urlsafe_b64encode(str(position).encode(ENCODING)).decode(ENCODING).rstrip(PADDING)


def decode(token: str) -> Result[int]:
    """The position a token names, or a refusal — never a silent zero.

    Resuming from the beginning because a token was unreadable would return the
    first page again, and a caller following tokens to exhaustion would never
    exhaust. So an unreadable token is `Invalid` and the traversal stops where
    the caller can see it.
    """
    try:
        padded = token + PADDING * (-len(token) % 4)
        position = int(base64.urlsafe_b64decode(padded.encode(ENCODING)).decode(ENCODING))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return _unreadable(token)
    if position < 0:
        return _unreadable(token)
    return Ok(position)


def _unreadable(token: str) -> Invalid:
    return Invalid(
        identifier=TOKEN_IDENTIFIER,
        message=(
            "the continuation token is not one this surface issued; start the "
            "listing again rather than composing a token"
        ),
        subject=token,
    )


@dataclass(frozen=True)
class Page[T]:
    """One page of a listing: its items, and how to ask for the next.

    `next_token` is `None` at the end, which is what makes exhaustion
    observable: a caller follows tokens until there is none, and every result
    appeared exactly once because every page was a contiguous slice of one
    order.
    """

    items: tuple[T, ...]
    next_token: str | None = None
    size: int = DEFAULT_PAGE_SIZE
    total: int = 0

    @property
    def is_last(self) -> bool:
        return self.next_token is None


def page_of[T](
    ordered: Sequence[T],
    *,
    token: str | None = None,
    size: int | None = None,
) -> Result[Page[T]]:
    """The slice this request asks for, from an already-ordered sequence.

    The order is the caller's, and it has to be *total*: two results that
    compare equal would swap between requests and the exactly-once guarantee
    would quietly stop holding. Ordering by the identifier the specification
    already uses gives that for free, which is why the read endpoints sort by it
    rather than by anything derived.
    """
    limit = bounded(size)
    start = decode(token) if token else Ok(0)
    if not isinstance(start, Ok):
        return start
    items = tuple(ordered[start.value : start.value + limit])
    finished = start.value + limit >= len(ordered)
    return Ok(
        Page(
            items=items,
            next_token=None if finished else encode(start.value + limit),
            size=limit,
            total=len(ordered),
        )
    )


def rendered(page: Page[Any], render: Any) -> dict[str, Any]:
    """One page as the body a client reads: its items, and the next token."""
    return {
        "items": [render(item) for item in page.items],
        "next_token": page.next_token,
        "page_size": page.size,
        "total": page.total,
    }


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "MIN_PAGE_SIZE",
    "SIZE_IDENTIFIER",
    "TOKEN_IDENTIFIER",
    "Page",
    "bounded",
    "decode",
    "encode",
    "page_of",
    "rendered",
]
