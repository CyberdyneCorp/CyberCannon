"""Every text-on-background pair this interface produces meets WCAG AA.

`openspec/project.md` ("Visual language — neo-brutalism") makes this an
obligation the style raises rather than relaxes: *"The contrast obligation is
higher, not lower. Flat saturated colour on flat saturated colour fails
legibility easily, and this interface is read on an iPad in a studio. Every
text-on-background pair meets WCAG AA."*

`test_design_tokens.py` checks that the tokens are the design's and that no
component writes a colour of its own. Neither of those notices a *legal*
token used in an *illegal* pairing, which is the failure this file exists for:
every colour here comes from the ramp, and two of them were still under the
line.

REGRESSION, both found by measuring rather than by looking:

* `SearchForm`'s `::placeholder` took `--color-neutral-500`, the ramp's middle
  step and the obvious choice for quiet text. On the field's white ground it
  measures **4.39:1** — under AA for its 16px body text. `--color-neutral-600`
  is 7.08:1.
* `SheetView`'s selected pin filled with `--color-accent` and wrote its label
  in `--color-bg`: **4.19:1** behind a 13px letter. `--color-accent-600` is
  5.49:1 and is still recognisably the same blue.

Both were one step down the ramp, which is the only kind of fix this file
accepts — a nudge to an off-ramp colour would pass here and fail the gate next
door, and that is deliberate.

TWO CLAIMS ARE CHECKED, and the second is what stops this file rotting.

* **Every pair in `PAIRS` clears its threshold.** The table is the interface's
  real pairings, read off the components, each with the size it is actually set
  at — 4.5:1 for body text, 3:1 only where the text is genuinely large.
* **The table still describes the application.** Every `--color-*` token the
  source uses as a foreground appears in the table as a foreground, and every
  one used as a background appears as a background. A new colour pairing cannot
  be introduced without a line here, so the measurement cannot silently fall
  behind the screens.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path("apps/cybercanon/web")
TOKENS = WEB / "src" / "lib" / "styles" / "tokens.css"
SOURCE = WEB / "src"

COMMENT = re.compile(r"/\*.*?\*/", re.S)
DECLARATION = re.compile(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;}]+)")
STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
NOT_SOURCE = {"node_modules", ".svelte-kit", "build"}

FOREGROUND = re.compile(r"(?<![-\w])color:\s*var\(\s*(--color-[a-z0-9-]+)\s*\)")
BACKGROUND = re.compile(r"background(?:-color)?:\s*var\(\s*(--color-[a-z0-9-]+)\s*\)")

# WCAG 2.2 SC 1.4.3. "Large" is 18.66px and bold, or 24px at any weight; this
# interface's type scale puts almost everything under both, which is why the
# table below is nearly all 4.5.
AA_NORMAL = 4.5
AA_LARGE = 3.0
LARGE_PX = 24.0
LARGE_BOLD_PX = 18.66

# WCAG 2.2 SC 1.4.11 — a focus ring and a mark a person has to see are not text
# and take the lower bar, but they do take one.
NON_TEXT = 3.0

# The disabled opacity the system's own readme sets. SC 1.4.3 exempts an
# inactive control from the contrast requirement outright ("Incidental"), so the
# composite below is recorded rather than asserted — but it is recorded, because
# an interface that put *information* only in a disabled control would be
# relying on an exemption to hide a legibility problem. See the test.
DISABLED = "--opacity-disabled"


# (foreground, background, px, bold, where it is)
#
# Read off the components. The size is the one the element is actually set at —
# `--text-body` 15px, `--text-small` 13px, `--text-h5` 16px — because the
# threshold depends on it.
PAIRS: list[tuple[str, str, float, bool, str]] = [
    # Ink, which is most of the interface.
    ("--color-text", "--color-bg", 15, False, "body copy on the ground"),
    ("--color-text", "--color-surface", 15, False, "card and panel copy"),
    ("--color-text", "--color-neutral-100", 15, False, "copy on a quiet fill"),
    ("--color-text", "--color-neutral-200", 13, False, "filter chip and tag text"),
    ("--color-text", "--color-accent-100", 15, False, "the forbidden route-state panel"),
    ("--color-text", "--color-accent-2-100", 15, False, "the failed panel, orphan blocks"),
    ("--color-text", "--color-accent-2-200", 13, False, "the orphaned-annotation tag"),
    ("--color-text", "--color-highlight", 13, True, "primary button, table head, marks"),
    ("--color-text", "--color-highlight-hover", 13, True, "primary button, hovered"),
    ("--color-text", "--color-accent-2", 15, False, "the unmapped-identity notice"),
    # Secondary copy. The single most-used non-ink colour in the application.
    ("--color-neutral-700", "--color-bg", 13, False, "secondary copy on the ground"),
    ("--color-neutral-700", "--color-surface", 13, False, "secondary copy in a card"),
    ("--color-neutral-700", "--color-neutral-100", 13, False, "secondary copy on a fill"),
    ("--color-neutral-700", "--color-neutral-200", 13, False, "secondary copy on a chip"),
    ("--color-neutral-700", "--color-highlight", 13, False, "secondary copy on the yellow"),
    # REGRESSION — was `--color-neutral-500` at 4.39:1.
    ("--color-neutral-600", "--color-surface", 16, False, "the search field's placeholder"),
    ("--color-neutral-600", "--color-bg", 16, False, "a placeholder on the ground"),
    # Links and the link-shaped buttons.
    ("--color-accent-700", "--color-bg", 15, False, "links on the ground"),
    ("--color-accent-700", "--color-surface", 15, False, "links in a card"),
    ("--color-accent-700", "--color-accent-100", 15, False, "the forbidden panel's sign-in link"),
    ("--color-accent-700", "--color-accent-2-100", 15, False, "a link in the failed panel"),
    ("--color-accent-700", "--color-neutral-100", 15, False, "a link on a quiet fill"),
    ("--color-accent-700", "--color-highlight", 13, False, "a quiet button on the yellow"),
    ("--color-accent-600", "--color-bg", 15, False, "a hovered link on the ground"),
    ("--color-accent-600", "--color-surface", 15, False, "a hovered link in a card"),
    # The warning colour, which is what an unmapped identity and an orphan use.
    ("--color-accent-2-700", "--color-bg", 13, False, "the no-git-identity warning"),
    ("--color-accent-2-700", "--color-surface", 13, False, "that warning inside a card"),
    ("--color-accent-2-800", "--color-accent-2-100", 13, False, "orphan copy on its own tint"),
    ("--color-accent-2-800", "--color-accent-2-200", 13, False, "the orphan tag's own text"),
    ("--color-accent-2-800", "--color-surface", 13, False, "orphan copy in a card"),
    # Knocked out of ink and out of the accent.
    ("--color-bg", "--color-text", 13, False, "an ordinary pin's letter"),
    # REGRESSION — was `--color-accent` at 4.19:1.
    ("--color-bg", "--color-accent-600", 13, False, "the selected pin's letter"),
]

# (colour, against, what it is). SC 1.4.11 — 3:1, and none of these carry text.
NON_TEXT_PAIRS: list[tuple[str, str, str]] = [
    ("--color-accent", "--color-bg", "the :focus-visible ring on the ground"),
    ("--color-accent", "--color-surface", "the :focus-visible ring on a card"),
    ("--color-accent", "--color-highlight", "the :focus-visible ring on a primary button"),
    ("--color-accent-2", "--color-surface", "an annotation stroke on the model sheet"),
    ("--color-divider", "--color-bg", "every border and rule in the system"),
]


def _tokens(repo_root: Path) -> dict[str, str]:
    text = COMMENT.sub("", (repo_root / TOKENS).read_text(encoding="utf-8"))
    return {name: value.strip() for name, value in DECLARATION.findall(text)}


@pytest.fixture(scope="module")
def tokens(repo_root: Path) -> dict[str, str]:
    return _tokens(repo_root)


def _channels(value: str) -> tuple[int, int, int]:
    digits = value.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(character * 2 for character in digits)
    if len(digits) != 6:
        raise AssertionError(f"{value!r} is not a hex colour this test can measure")
    return tuple(int(digits[at : at + 2], 16) for at in (0, 2, 4))  # type: ignore[return-value]


def _luminance(colour: tuple[int, int, int]) -> float:
    """Relative luminance, WCAG 2.2 definition."""

    def channel(raw: int) -> float:
        value = raw / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(part) for part in colour)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _ratio(foreground: tuple[int, int, int], background: tuple[int, int, int]) -> float:
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _contrast(tokens: dict[str, str], foreground: str, background: str) -> float:
    for name in (foreground, background):
        assert name in tokens, f"{name} is not declared in {TOKENS}"
    return _ratio(_channels(tokens[foreground]), _channels(tokens[background]))


def _threshold(px: float, bold: bool) -> float:
    large = px >= LARGE_PX or (bold and px >= LARGE_BOLD_PX)
    return AA_LARGE if large else AA_NORMAL


STYLE_LAYER = ("tokens.css", "fonts.css", "base.css")
"""The global layer. It *declares* the system — the token values, the faces, and
the one `:disabled` rule every control inherits — so it is where the things the
component checks below forbid are supposed to live."""


def _style(repo_root: Path, *, components_only: bool = False) -> str:
    """Every piece of CSS this application ships, concatenated, comments gone.

    `components_only` drops the global style layer, for the checks whose whole
    subject is a component doing for itself what the base layer already does.
    """
    blocks: list[str] = []
    for path in sorted((repo_root / SOURCE).rglob("*")):
        if path.suffix not in {".css", ".svelte"} or NOT_SOURCE & set(path.parts):
            continue
        if path.name in STYLE_LAYER and (components_only or path.name != "base.css"):
            continue
        text = path.read_text(encoding="utf-8")
        blocks.extend([text] if path.suffix == ".css" else STYLE_BLOCK.findall(text))
    return COMMENT.sub("", "\n".join(blocks))


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("foreground", "background", "px", "bold", "where"),
    PAIRS,
    ids=[f"{fg[8:]}-on-{bg[8:]}" for fg, bg, _, _, _ in PAIRS],
)
def test_every_text_pair_clears_wcag_aa(
    tokens: dict[str, str],
    foreground: str,
    background: str,
    px: float,
    bold: bool,
    where: str,
) -> None:
    measured = _contrast(tokens, foreground, background)
    needed = _threshold(px, bold)

    assert measured >= needed, (
        f"{where}: {foreground} on {background} is {measured:.2f}:1, under AA's "
        f"{needed}:1 for {px:g}px{' bold' if bold else ''} text. The fix is the next "
        "step along that colour's ramp — a hand-picked colour near it would pass here "
        "and fail the adherence gate, which is the point of having both."
    )


@pytest.mark.parametrize(
    ("colour", "against", "where"),
    NON_TEXT_PAIRS,
    ids=[f"{fg[8:]}-on-{bg[8:]}" for fg, bg, _ in NON_TEXT_PAIRS],
)
def test_every_non_text_pair_clears_wcag_aa(
    tokens: dict[str, str], colour: str, against: str, where: str
) -> None:
    """SC 1.4.11. A focus ring nobody can see is a keyboard user with no cursor."""
    measured = _contrast(tokens, colour, against)

    assert measured >= NON_TEXT, (
        f"{where}: {colour} on {against} is {measured:.2f}:1, under {NON_TEXT}:1."
    )


def test_a_disabled_control_is_never_the_only_place_a_thing_is_said(
    repo_root: Path, tokens: dict[str, str]
) -> None:
    """The 45% state is legally exempt, so what is checked is that it stays incidental.

    SC 1.4.3 excuses an inactive control from contrast, and the composite really
    is under the line — ink at 45% on the ground measures about 3.3:1. That is
    the system's own number and it is not changed here. What would be a defect
    is an interface that said something *only* by disabling a control, because
    then the exemption is covering a sentence nobody can read. The rule this
    asserts is the cheap structural one: nothing in the application sets
    `opacity: var(--opacity-disabled)` itself — the state comes from the base
    layer's `:disabled` alone, so it is always a real control being switched
    off and never a paragraph being dimmed.
    """
    assert DISABLED in tokens, f"{DISABLED} is not declared in {TOKENS}"

    faded = [
        line.strip()
        for line in _style(repo_root, components_only=True).splitlines()
        if f"var({DISABLED})" in line
    ]

    assert not faded, (
        f"{faded} fade content with {DISABLED} outside the base layer's `:disabled` "
        "rule. That opacity composites to roughly 3.3:1, which WCAG allows only "
        "because an inactive control carries no information. Anything else wearing it "
        "is information nobody can read."
    )


# ---------------------------------------------------------------------------
# The guard on the table
# ---------------------------------------------------------------------------


def test_the_table_describes_this_application(repo_root: Path) -> None:
    """A colour used in the source that nobody measured is the failure mode here.

    The table above is hand-written, and a hand-written table is only worth the
    thing that stops it drifting. Every token the application sets as a
    foreground has to appear in it as a foreground, and every one it sets as a
    background as a background — so a new pairing arrives with a measurement or
    it does not arrive.
    """
    style = _style(repo_root)
    used_foreground = set(FOREGROUND.findall(style))
    used_background = set(BACKGROUND.findall(style))

    assert used_foreground and used_background, "found no colour declarations at all"

    measured_foreground = {pair[0] for pair in PAIRS}
    measured_background = {pair[1] for pair in PAIRS}

    assert not used_foreground - measured_foreground, (
        f"{sorted(used_foreground - measured_foreground)} are set as text colours in "
        "the application and measured against nothing. Add each one to PAIRS against "
        "the backgrounds it actually lands on."
    )
    assert not used_background - measured_background, (
        f"{sorted(used_background - measured_background)} are set as backgrounds in the "
        "application and measured against nothing. Add each one to PAIRS against the "
        "text colours that actually land on it."
    )


def test_the_table_is_not_measuring_colours_nobody_uses(repo_root: Path) -> None:
    """The other direction: a table that outgrew the screens is a table nobody trusts."""
    style = _style(repo_root)
    paired = {pair[0] for pair in PAIRS} | {pair[1] for pair in PAIRS}
    used = set(FOREGROUND.findall(style)) | set(BACKGROUND.findall(style))

    assert not paired - used, (
        f"{sorted(paired - used)} are measured in PAIRS but no longer appear in the "
        "application. Delete the rows, so the table stays a description of the "
        "screens rather than a wish about them."
    )
