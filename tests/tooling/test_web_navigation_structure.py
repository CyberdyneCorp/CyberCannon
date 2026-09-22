"""Groups 5 and 6 of `add-web-app-shell` — the structural half of the shell.

The behaviour is executed where it can be executed: `apps/cybercanon/web/tests/`
drives the real switching decisions, the real asset page and the real route
loads, and `just check` runs those suites through `web-check`.

What is asserted **here** is what a behavioural suite cannot keep true on its
own, for the reason `tests/tooling/test_web_structure.py` gives in its own
docstring: `just check` is the contract, it runs the Python suite, and a
constraint that only bites when somebody remembers to run the frontend's runner
is a constraint that stops biting in week three.

Three rules, and all three are rules about what must not drift:

* **the project is identified in the frame, not in each screen.**
  `app-navigation` requires *every* screen to state the project it belongs to;
  a disclosure each screen has to remember is a disclosure some screen will
  forget.
* **the asset screen's heading comes from the address, never from what was
  loaded.** That is what keeps *not permitted* a screen that knows nothing but
  the identifier the person themselves opened.
* **the asset page's sections are a closed, total set**, rendered by iteration.
  A section rendered by a conditional is a section that disappears exactly when
  its absence is the information — which is the one thing
  `app-navigation` rules out.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path("apps") / "cybercanon" / "web"
LAYOUT = WEB / "src" / "routes" / "+layout.svelte"
ASSET_SCREEN = WEB / "src" / "routes" / "p" / "[project]" / "a" / "[asset]" / "+page.svelte"
ASSET_PAGE = WEB / "src" / "lib" / "asset" / "page.ts"
OVERVIEW = WEB / "src" / "lib" / "components" / "AssetOverview.svelte"
SUITES = (
    WEB / "tests" / "projects.test.ts",
    WEB / "tests" / "asset-page.test.ts",
    WEB / "tests" / "asset-load.test.ts",
    WEB / "tests" / "asset-render.test.ts",
    WEB / "tests" / "session-notices.test.ts",
)

SECTIONS = ("identity", "owners", "constraints", "annotations", "views", "exports", "links")
HEADING = re.compile(r"<h1>\{([^}]+)\}</h1>")


@pytest.fixture(scope="module")
def layout(repo_root: Path) -> str:
    return (repo_root / LAYOUT).read_text(encoding="utf-8")


def test_the_frame_states_which_project_is_being_shown(layout: str) -> None:
    """5.3 — in the frame, so "every screen" needs no screen's cooperation."""
    assert "ProjectBar" in layout, (
        f"{LAYOUT} is the frame every screen renders inside; the project it belongs "
        "to is identified there rather than in each screen that remembers to"
    )


def test_the_frame_re_reads_itself_when_the_acting_identity_changes(layout: str) -> None:
    """Which projects a person may open is an answer about *that person*.

    The frame's load takes no parameter saying who is acting, so without this the
    projects read for an anonymous visitor would still be on screen after they
    signed in.
    """
    assert "SESSION_DEPENDENCY" in layout and "invalidate(" in layout, (
        f"{LAYOUT} must invalidate the frame's data when the session changes, or "
        "signing in leaves the switcher showing what a signed-out visitor saw"
    )


def test_the_asset_screen_heads_itself_from_the_address(repo_root: Path) -> None:
    """5.4 — a refused asset's name never reaches the screen that refused it."""
    source = (repo_root / ASSET_SCREEN).read_text(encoding="utf-8")
    heading = HEADING.search(source)

    assert heading, f"{ASSET_SCREEN} has no heading to check"
    assert "address" in heading.group(1), (
        "the asset screen's heading must come from the address the person opened, "
        f"not from anything loaded about the asset: {heading.group(1)!r}"
    )


def test_the_asset_page_has_a_closed_set_of_sections(repo_root: Path) -> None:
    """6.1 — the seven `app-navigation` names, declared once and in order."""
    declared = (repo_root / ASSET_PAGE).read_text(encoding="utf-8")
    listed = re.search(r"export const SECTIONS = \[(?P<body>.*?)\] as const;", declared, re.S)

    assert listed, f"{ASSET_PAGE} must declare the section set as a closed list"
    found = tuple(re.findall(r"'([a-z]+)'", listed.group("body")))
    assert found == SECTIONS, f"the asset page's sections drifted: {found}"


def test_every_section_states_its_own_absence(repo_root: Path) -> None:
    """6.2 — a section with nothing to say says so; there is no seventh silence."""
    declared = (repo_root / ASSET_PAGE).read_text(encoding="utf-8")
    absences = re.search(
        r"ABSENCES: Readonly<Record<SectionId, string>> = \{(?P<body>.*?)\n\};", declared, re.S
    )

    assert absences, f"{ASSET_PAGE} must state, per section, what its emptiness means"
    for section in SECTIONS:
        assert f"{section}:" in absences.group("body"), (
            f"the {section} section has no sentence for the case where it is empty; "
            "`app-navigation` requires absence to be stated, not omitted"
        )


def test_the_asset_page_renders_its_sections_by_iteration(repo_root: Path) -> None:
    """A section behind an `{#if}` is the section that vanishes when it matters."""
    source = (repo_root / OVERVIEW).read_text(encoding="utf-8")

    assert "{#each page.sections" in source, (
        f"{OVERVIEW} must render the section list it is given rather than naming "
        "sections itself, so a section cannot be dropped by a conditional"
    )
    for section in SECTIONS:
        assert f"'{section}'" not in source, (
            f"{OVERVIEW} names the {section} section, which is how a screen starts "
            "deciding which sections are worth showing"
        )


def test_the_behavioural_suites_exist(repo_root: Path) -> None:
    """The rules above are about drift; these are where the behaviour is asserted."""
    missing = [path.as_posix() for path in SUITES if not (repo_root / path).is_file()]

    assert not missing, f"the suites executing groups 5 and 6 are gone: {missing}"
