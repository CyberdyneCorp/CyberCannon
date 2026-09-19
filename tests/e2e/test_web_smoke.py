"""Task 6.1 — one smoke test, run in every configured viewport.

It asserts the least the application can be said to work: it serves its frame,
it names itself, an address resolves to a screen rather than to a stack trace,
and nothing makes the page scroll sideways at phone or tablet width. The last
one is `add-web-app-shell` task 7.1's acceptance in its cheapest form, checked
from the first e2e run rather than at the end of the change.

What this suite deliberately does **not** do is assert product behaviour that
the BDD layer already executes against the use cases. E2E covers what unit and
BDD cannot reach at all — that the surfaces are wired together and render in a
real browser — and every scenario it duplicated would be a scenario failing in
two places for one reason.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.e2e


def test_the_application_serves_its_frame(page: Any) -> None:
    page.goto("/")

    assert "CyberCanon" in page.title()


def test_the_page_body_never_scrolls_sideways(page: Any, viewport: dict[str, int]) -> None:
    """`add-web-app-shell` 7.1: usable at phone width, with no horizontal scroll."""
    page.goto("/")

    width = page.evaluate("document.documentElement.scrollWidth")

    assert width <= viewport["width"], (
        f"the page body scrolls sideways at {viewport['width']}px ({width}px wide)"
    )


def test_an_asset_address_resolves_to_a_screen(page: Any) -> None:
    """D6 — a route resolves to one of the closed set, never to nothing at all.

    The frame is waited for rather than counted straight away: the application
    renders in the browser, because the credential it acts under is obtained
    there and never reaches the server (`add-web-app-shell` group 3).
    """
    page.goto("/p/e2e/assets")

    frame = page.locator("main")
    frame.first.wait_for()

    assert frame.count() == 1
