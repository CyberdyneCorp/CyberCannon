"""Group 3 of `add-web-app-shell` in a real browser: what a visitor with no session sees.

The session's *logic* is executed by the frontend's own suites, which `just
check` runs (`apps/cybercanon/web/tests/session*.test.ts`, `writes.test.ts`,
`oidc.test.ts`). What only a browser can answer is whether the application
**renders** it: that an address opened cold offers sign-in, that the offer
carries the address the person was going to, and that nothing of a project is
on the page while nobody is signed in.

The signed-in half deliberately stops here. Driving a real authorization-code
exchange would need CyberdyneAuth in the compose stack, and until it is there an
e2e test that stubbed a credential would be asserting the stub. The scenarios
those would close stay on `tests/bdd/pending.txt`.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.e2e

ASSET_ADDRESS = "/p/e2e/a/mech_scout"


def _rendered(page: Any, selector: str) -> Any:
    """The element, once the application has rendered it.

    The application renders in the browser — the credential it acts under never
    reaches the server, so no authenticated screen is rendered there — which
    makes every assertion below one that has to wait for the client rather than
    read the first response.
    """
    locator = page.locator(selector)
    locator.first.wait_for()
    return locator


def test_an_unauthenticated_visitor_is_offered_sign_in(page: Any) -> None:
    page.goto(ASSET_ADDRESS)

    assert _rendered(page, "a.sign-in").count() >= 1


def test_the_offer_carries_the_address_they_were_going_to(page: Any) -> None:
    """`web-session`: sign-in returns the person to where they were going."""
    page.goto(ASSET_ADDRESS)

    href = _rendered(page, "a.sign-in").first.get_attribute("href")

    assert href is not None
    assert href.startswith("/sign-in?next=")
    assert "mech_scout" in href


def test_no_asset_content_is_shown_before_authentication(page: Any) -> None:
    page.goto(ASSET_ADDRESS)

    _rendered(page, '[data-state="forbidden"]')

    assert page.locator("article.overview").count() == 0


def test_the_frame_says_nobody_is_signed_in(page: Any) -> None:
    """The acting identity is in the frame, and so is its absence."""
    page.goto("/")

    assert _rendered(page, '[data-signed-in="no"]').count() == 1


def test_the_sign_in_screen_shows_nothing_from_the_canon(page: Any) -> None:
    page.goto(f"/sign-in?next={ASSET_ADDRESS}")

    _rendered(page, "h1")

    assert page.locator("ul.assets").count() == 0
    assert page.locator("article.overview").count() == 0
