"""The half of `web-session` no end-to-end run could reach until the stack had an issuer.

`deploy/e2e/compose.yaml` pointed `CANON_AUTH_KEY_SET_URL` at an address on the
api that **nothing served** — the catch-all refuses any path carrying no surface
version — so the key set retrieval answered 400, no credential could ever
verify, and `tests/e2e/test_web_session.py` says so in as many words: *"the
signed-in half deliberately stops here"*. Every browser assertion this project
has ever made was therefore made about a signed-out page.

The stack now runs `tools/canon_issuer` behind a socket
(`deploy/e2e/issuer.Dockerfile`), which is the same issuer the port-conformance,
integration and BDD layers mint against: real RSA keys, a real authorization
code, a real PKCE binding. So this suite drives the **real** flow — the button,
the redirect out, the redirect back, the code exchange — and asserts what only a
browser can: that the application ends up holding a credential the API accepts,
and that an address which answered `forbidden` to a visitor answers with a
screen to a person.

It deliberately asserts *reachability* rather than rows. What the seeded project
contains is the index's business and an empty index is a legitimate answer here;
what was impossible before and is being checked now is that the screen is no
longer the one shown to somebody who is not signed in.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.e2e

PROJECT = "ronin"
"""What `CANON_PROJECT` serves in `deploy/e2e/compose.yaml`, and what the
credential the issuer mints is entitled to read. The two are asserted against
each other without a browser in `tests/tooling/test_e2e_stack.py`."""

ASSETS = f"/p/{PROJECT}/assets"
ASSET = f"/p/{PROJECT}/a/mech_scout"

SIGN_IN_TIMEOUT_MS = 30_000


def _sign_in(page: Any) -> None:
    """The whole flow, as a person performs it: one button and two redirects."""
    page.goto("/sign-in?next=/")
    page.locator("button.start").first.wait_for()
    page.locator("button.start").first.click()
    page.wait_for_url(
        lambda url: "/sign-in" not in url and "/signed-in" not in url,
        timeout=SIGN_IN_TIMEOUT_MS,
    )
    page.locator('[data-signed-in="yes"]').first.wait_for(timeout=SIGN_IN_TIMEOUT_MS)


@pytest.fixture
def signed_in(page: Any) -> Any:
    """A page holding a credential this deployment's API actually accepts."""
    _sign_in(page)
    return page


def test_a_real_authorization_code_exchange_produces_a_session(signed_in: Any) -> None:
    """The frame names the acting identity, which is what a session looks like here."""
    assert signed_in.locator('[data-signed-in="yes"]').count() == 1


def test_an_address_that_refused_a_visitor_answers_a_signed_in_person(signed_in: Any) -> None:
    """`forbidden` is what `tests/e2e/test_web_session.py` asserts for the same address."""
    signed_in.goto(ASSET)
    signed_in.locator("main").first.wait_for()

    assert signed_in.locator('[data-state="forbidden"]').count() == 0


def test_the_browser_screen_is_reached_rather_than_refused(signed_in: Any) -> None:
    """A listing is served to a credential the surface verified against the issuer.

    The offer of sign-in is the tell. `tests/e2e/test_web_session.py` asserts
    that a visitor at a project address is given one and shown nothing of the
    canon; a person the API accepted is given the screen instead, and a
    credential the API refused would put the offer back.
    """
    signed_in.goto(ASSETS)
    signed_in.locator("main").first.wait_for()

    assert signed_in.locator("a.sign-in").count() == 0, "the credential was not accepted"
    assert signed_in.locator('[data-state="forbidden"]').count() == 0


def test_signing_out_returns_the_person_to_what_a_visitor_sees(signed_in: Any) -> None:
    """The other half of a session: it ends, and the frame says so (`web-session`)."""
    signed_in.locator('[data-signed-in="yes"] button').first.click()
    signed_in.locator('[data-signed-in="no"]').first.wait_for(timeout=SIGN_IN_TIMEOUT_MS)

    assert signed_in.locator('[data-signed-in="no"]').count() == 1
