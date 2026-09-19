"""Tasks 6.1 and 6.4 — the browser, the viewport matrix, and what a failure leaves behind.

D6 chose Playwright over Cypress for two reasons and both are implemented here:
it drives multiple viewports in one run — which the iPad-width requirement in
`model-sheet-2d` and task 7.1 of `add-web-app-shell` need — and it can attach a
trace to a failure, *"which is the difference between a flaky e2e suite being
debugged and being deleted"*.

**Browsers are installed by the run, not by CI.** CI may run `just check` and
`just test-e2e` and nothing else (`tests/tooling/test_ci_workflow.py`), so an
`npx playwright install` step in the workflow would be a check leaking out of
the justfile. The install is idempotent and costs nothing once the browser is in
the cache, so the rule holds without a special case.

Nothing here runs at collection time. `just test-e2e --collect-only` has to work
on a machine with no browser and no docker, because that is how the recipe is
checked for selecting only its own layer.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import stack

# Task 6.1 — the matrix, including tablet width, which is the one the model
# sheet is specified against. Sizes are the CSS viewports of the devices the
# people using this actually hold, not round numbers.
VIEWPORTS: dict[str, dict[str, int]] = {
    "phone": {"width": 390, "height": 844},
    "tablet": {"width": 834, "height": 1112},
    "laptop": {"width": 1280, "height": 800},
    "desktop": {"width": 1920, "height": 1080},
}

ARTIFACTS = Path("reports/e2e")
"""Where a failing run leaves its trace, its screenshot and its video (6.4)."""


_REPORTS = pytest.StashKey[dict]()
"""Where each phase's outcome is kept, so a teardown can see what happened."""


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Any:
    """Record each phase's outcome so a fixture's teardown can see the failure."""
    outcome = yield
    report = outcome.get_result()
    item.stash.setdefault(_REPORTS, {})[report.when] = report.failed


def _failed(item: pytest.Item) -> bool:
    return any(item.stash.get(_REPORTS, {}).values())


@pytest.fixture(scope="session")
def base_url(repo_root: Path) -> Iterator[str]:
    """Where the application is: a stack that is running, or one brought up here."""
    declared = stack.declared_base_url()
    if declared:
        yield declared
        return
    if not stack.docker_available():
        pytest.skip(stack.NO_STACK)
    with stack.compose_stack(repo_root) as url:
        yield url


@pytest.fixture(scope="session")
def playwright_browsers() -> None:
    """The browsers, installed by the run itself rather than by a CI step."""
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
        check=False,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def browser(playwright_browsers: None) -> Iterator[Any]:
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as driver:
        launched = driver.chromium.launch()
        yield launched
        launched.close()


@pytest.fixture(params=sorted(VIEWPORTS), ids=sorted(VIEWPORTS))
def viewport(request: pytest.FixtureRequest) -> dict[str, int]:
    """One entry of the matrix. Every test using it runs in every viewport."""
    return VIEWPORTS[request.param]


@pytest.fixture
def page(
    browser: Any, viewport: dict[str, int], base_url: str, request: pytest.FixtureRequest
) -> Iterator[Any]:
    """A page in one viewport, tracing, that leaves its evidence when it fails.

    The trace, the screenshot and the video are written **only** on failure:
    a green run that produced 200MB of video is a run whose artifacts nobody
    keeps, and artifacts nobody keeps are not there on the day one is needed.
    """
    directory = ARTIFACTS / _slug(request.node.nodeid)
    context = browser.new_context(
        viewport=viewport, base_url=base_url, record_video_dir=str(directory)
    )
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    opened = context.new_page()
    try:
        yield opened
    finally:
        _preserve(opened, context, directory, keep=_failed(request.node))


def _preserve(page: Any, context: Any, directory: Path, *, keep: bool) -> None:
    if keep:
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(directory / "screenshot.png"), full_page=True)
        context.tracing.stop(path=str(directory / "trace.zip"))
        context.close()
        return
    context.tracing.stop()
    video = page.video
    context.close()
    if video is not None:
        video.delete()


def _slug(node_id: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in node_id).strip("-")
