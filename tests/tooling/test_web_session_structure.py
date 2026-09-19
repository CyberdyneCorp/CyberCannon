"""Group 3 of `add-web-app-shell` — the structural half of the session experience.

The behaviour is executed where it can be executed: `apps/cybercanon/web/tests/`
drives the real session store, the real write gate, the real sign-in flow and
the real route loads, and `just check` runs those suites through `web-check`.

What is asserted **here** is what a behavioural suite cannot keep true on its
own, and it is here for the reason `tests/tooling/test_web_structure.py` gives
in its own docstring: `just check` is the contract, it runs the Python suite,
and a constraint that only bites when somebody remembers to run the frontend's
runner is a constraint that stops biting in week three.

Two rules, and both are rules about what must not drift:

* **no data-bearing route may ask the surface for anything before it has a
  session.** `web-session` requires that an unauthenticated person is shown *"no
  project or asset content"*, and the cheapest way for that to stop being true
  is a new route that builds a client and forgets the guard. A route that never
  asks cannot leak.
* **the acting identity, the unmapped warning and the outage notice are in the
  frame.** Each is required on *every* screen, and a disclosure that each screen
  has to remember is a disclosure some screen will forget.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path("apps") / "cybercanon" / "web"
SOURCE = WEB / "src"
LAYOUT = SOURCE / "routes" / "+layout.svelte"
LAYOUT_LOAD = SOURCE / "routes" / "+layout.ts"
SESSION = SOURCE / "lib" / "session"
SUITES = (
    WEB / "tests" / "session.test.ts",
    WEB / "tests" / "writes.test.ts",
    WEB / "tests" / "oidc.test.ts",
    WEB / "tests" / "intent.test.ts",
    WEB / "tests" / "session-routes.test.ts",
)

CLIENT = re.compile(r"\bnew\s+CanonApi\b")
GUARD = re.compile(r"\bsignedOutScreen\b")


@pytest.fixture(scope="module")
def web_root(repo_root: Path) -> Path:
    root = repo_root / WEB
    assert root.is_dir(), f"{WEB} is the SvelteKit application (task 1.1)"
    return root


def _routes(web_root: Path) -> list[Path]:
    return sorted((web_root / "src" / "routes").rglob("+page.ts"))


def test_no_route_reads_the_canon_without_a_session(web_root: Path) -> None:
    """3.1 — a route that asks the surface for content asks the session first."""
    unguarded = [
        path.relative_to(web_root).as_posix()
        for path in _routes(web_root)
        if CLIENT.search(source := path.read_text(encoding="utf-8")) and not GUARD.search(source)
    ]

    assert not unguarded, (
        "`web-session` requires an unauthenticated person to be shown no project "
        "or asset content. These routes build an API client without first "
        f"resolving the signed-out screen: {unguarded}"
    )


def test_some_route_actually_reads_the_canon(web_root: Path) -> None:
    """The other half: a rule no route could break is a rule about nothing."""
    reading = [
        path.relative_to(web_root).as_posix()
        for path in _routes(web_root)
        if CLIENT.search(path.read_text(encoding="utf-8"))
    ]

    assert reading, "no route reads the canon at all; the guard above guards nothing"


def test_the_frame_shows_who_is_acting_and_what_they_are_owed(repo_root: Path) -> None:
    """3.6, 3.7 and 3.8 — in the layout, so "every screen" needs no cooperation."""
    layout = (repo_root / LAYOUT).read_text(encoding="utf-8")

    for component in ("SessionBar", "SessionNotices", "ReauthenticatePrompt"):
        assert component in layout, (
            f"{LAYOUT} is the frame every screen renders inside; {component} belongs "
            "in it rather than in each screen that remembers to include it"
        )


def test_the_session_is_the_browsers_because_the_credential_is(repo_root: Path) -> None:
    """The credential never reaches the node process, so no screen is rendered there.

    A server render would produce every authenticated screen with no credential,
    and SvelteKit does not re-run a universal load during hydration — so a
    signed-in person would be left looking at the signed-out screen their own
    server render produced. Worse, a module-level session on a shared server
    process is one request able to read another person's session.
    """
    load = (repo_root / LAYOUT_LOAD).read_text(encoding="utf-8")

    assert re.search(r"export\s+const\s+ssr\s*=\s*false", load), (
        f"{LAYOUT_LOAD} must keep rendering in the browser while the session lives there"
    )


def test_a_held_write_is_replayed_under_its_original_key(repo_root: Path) -> None:
    """D5 — a fresh key per attempt would turn every expiry into a double write."""
    gate = (repo_root / SESSION / "writes.ts").read_text(encoding="utf-8")

    assert "write.send(write.key)" in gate, (
        "the gate must send a held write under the key the write carries; "
        "`http-api` makes a replayed key return the original outcome, and a new "
        "key on the retry would create a second commit"
    )


def test_the_behaviour_is_executed_by_suites_check_runs(repo_root: Path) -> None:
    """A structural assertion with no behavioural one behind it proves nothing."""
    justfile = (repo_root / "justfile").read_text(encoding="utf-8")

    for suite in SUITES:
        assert (repo_root / suite).is_file(), f"{suite} executes the session scenarios"
    assert "web-check" in justfile.split("check:")[1].splitlines()[0]
