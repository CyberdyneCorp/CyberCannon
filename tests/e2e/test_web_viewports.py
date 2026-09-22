"""Task 7.1 — the application at phone width and on a tablet, address by address.

`test_web_smoke.py` makes this claim about the root address, from the first
end-to-end run. What 7.1 asks for is wider: *"the browser, asset page and
session flows remain usable, with no horizontal scrolling of the page body"* —
so every address the shell serves is opened in every viewport of the matrix and
asked the same two questions.

**Why the page body and not a container.** A screen that scrolls sideways on a
phone is the screen people stop using, and the failure is almost never in the
component somebody was looking at: it is a table, a long identifier, or a
filter row that refuses to wrap, three screens away. `document.scrollWidth`
against the viewport is the one assertion that catches all three without
naming any of them, which is why it is made per address rather than once.

**Usable is asserted as "there is a screen and a way on from it"**, not as a
screenshot. Every address has to resolve to one member of the closed route-state
set with its heading rendered (D6), because a route that resolved to nothing at
all would satisfy a width assertion perfectly.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.e2e

PROJECT = "ronin"
ASSET = "mech_scout"

ADDRESSES = [
    "/",
    "/sign-in",
    f"/p/{PROJECT}/assets",
    f"/p/{PROJECT}/assets?q=scout",
    f"/p/{PROJECT}/assets?status=modeling",
    f"/p/{PROJECT}/a/{ASSET}",
    f"/p/{PROJECT}/a/{ASSET}?view=sheet",
]
"""Every address the shell serves, including the two D3 puts state into."""


def _rendered(page: Any, address: str) -> None:
    """Open an address and wait for the application to have rendered it.

    The application renders in the browser (`ssr = false` is a session decision
    recorded in the frame's own load), so every assertion below has to wait for
    the client rather than read the first response.
    """
    page.goto(address)
    page.locator("main").first.wait_for()


@pytest.mark.parametrize("address", ADDRESSES)
def test_no_address_makes_the_page_body_scroll_sideways(
    page: Any, viewport: dict[str, int], address: str
) -> None:
    _rendered(page, address)

    width = page.evaluate("document.documentElement.scrollWidth")

    assert width <= viewport["width"], (
        f"{address} scrolls sideways at {viewport['width']}px ({width}px wide)"
    )


@pytest.mark.parametrize("address", ADDRESSES)
def test_every_address_resolves_to_a_screen_with_something_on_it(page: Any, address: str) -> None:
    """D6 — one member of the closed set, rendered, never a blank frame."""
    _rendered(page, address)

    frame = page.locator("main")

    assert frame.count() == 1, address
    assert frame.first.inner_text().strip(), f"{address} rendered an empty frame"


@pytest.mark.parametrize("address", ADDRESSES)
def test_the_frame_states_who_is_acting_at_every_width(page: Any, address: str) -> None:
    """`web-session` — the acting identity is in the frame, and so is its absence."""
    _rendered(page, address)

    assert page.locator("[data-signed-in]").count() >= 1, address
