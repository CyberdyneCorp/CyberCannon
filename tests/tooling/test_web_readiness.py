"""Task 2.4 (D10) — the web application's readiness reaches for nothing.

The behaviour is asserted where it can be executed —
`apps/cybercanon/web/tests/availability.test.ts` calls the handler with a
`fetch` that throws and asserts it still answers, and drives the root load with
the same `fetch` and asserts it resolves to the degraded state. That suite runs
under `just check`, through `web-check`.

What is asserted *here* is the structural half, and it is here rather than there
for the reason `tests/tooling/test_web_structure.py` gives in its own docstring:
`just check` is the contract, it runs the Python suite, and a constraint that
only bites when somebody remembers to run the frontend's runner is a constraint
that stops biting in week three. This one has to keep biting: a readiness route
that grows one `fetch` of the API turns another service's outage into a failed
deploy of this one, which is the exact cascade the change exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path("apps") / "cybercanon" / "web"
READINESS_ROUTE = WEB / "src" / "routes" / "readyz" / "+server.ts"
ROOT_LOAD = WEB / "src" / "routes" / "+page.ts"
ROOT_SCREEN = WEB / "src" / "routes" / "+page.svelte"
AVAILABILITY = WEB / "src" / "lib" / "api" / "availability.ts"
SUITE = WEB / "tests" / "availability.test.ts"

REACHES_OUT = re.compile(r"\bfetch\b|\bCanonClient\b|\bCanonApi\b|\$api/|lib/api/")

COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
"""Prose about the rule is not a breach of it, so the guard reads the code."""


def code(source: str) -> str:
    return COMMENT.sub("", source)


@pytest.fixture(scope="module")
def readiness(repo_root: Path) -> str:
    path = repo_root / READINESS_ROUTE
    assert path.is_file(), f"{READINESS_ROUTE} is the web application's readiness (D10)"
    return path.read_text(encoding="utf-8")


def test_the_readiness_route_reaches_for_nothing(readiness: str) -> None:
    offending = sorted(set(REACHES_OUT.findall(code(readiness))))

    assert not offending, (
        "the web application's readiness is process-only: it never calls the API "
        f"to decide whether it is ready (D10). It reaches for {offending}"
    )


def test_the_readiness_route_answers_ready(readiness: str) -> None:
    assert "export const GET" in readiness
    assert "READY" in readiness


def test_the_root_screen_renders_an_unavailable_state_rather_than_an_error(
    repo_root: Path,
) -> None:
    """The other half: the page describes the outage instead of failing on it."""
    load = (repo_root / ROOT_LOAD).read_text(encoding="utf-8")
    screen = (repo_root / ROOT_SCREEN).read_text(encoding="utf-8")
    availability = (repo_root / AVAILABILITY).read_text(encoding="utf-8")

    assert "apiAvailability" in load
    assert "RouteScreen" in screen
    assert "degraded" in availability
    assert "throw" not in load, "a load that throws is the 500 D10 forbids"


def test_the_behaviour_is_executed_by_a_suite_check_runs(repo_root: Path) -> None:
    """A structural assertion with no behavioural one behind it proves nothing."""
    suite = (repo_root / SUITE).read_text(encoding="utf-8")
    justfile = (repo_root / "justfile").read_text(encoding="utf-8")

    assert "does not call fetch at all" in suite
    assert "web-check" in justfile.split("check:")[1].splitlines()[0]
