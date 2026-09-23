"""The design tokens are transcribed, and the gate that keeps them the only copy.

`openspec/project.md` ("Visual language — neo-brutalism") records the decision
and repoints D4 at it: *"Tokens live in exactly one file. A component that
writes a hex value, a font stack, a border width or a shadow offset inline is a
bug, and the check is mechanical rather than a review habit."*

Two claims are checked here, and they are different claims.

* **The transcription is faithful.** Every custom property the design's own
  `:root` declares is in `tokens.css` with the design's value. A restyle that
  rounds a ramp step or drops one it thinks is unused has changed the design
  without saying so, and nobody would find out from a screenshot.
* **The gate bites.** The gate is the deliverable, not the intention, so it is
  run here against files written to fail it — one per rule. A gate nobody has
  seen fail is a gate nobody knows works.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path("apps/cybercanon/web")
GATE = WEB / "scripts" / "adherence.mjs"
STYLES = Path("src") / "lib" / "styles"
TOKENS = WEB / STYLES / "tokens.css"
DESIGN = Path("design") / "cybercanon-neo-brutal.html"

ROOT_BLOCK = re.compile(r":root\s*\{(.*?)\}", re.S)
COMMENT = re.compile(r"/\*.*?\*/", re.S)

# The two tokens allowed to differ from the design, and only by growing a
# fallback stack behind the family the design chose.
FONT_STACKS = ("--font-heading", "--font-body")
DECLARATION = re.compile(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;}]+)")

# One file per rule the gate carries, each a real violation of it.
OFFENDERS = {
    "color": ".x { color: #ff4f8b; }",
    "font": ".x { font-family: 'Comic Sans MS', cursive; }",
    "border": ".x { border: 3px solid black; }",
    "radius": ".x { border-radius: 8px; }",
    "shadow": ".x { box-shadow: 4px 4px 0 black; }",
    # A `var(--…)` that names nothing is the quietest failure CSS has: the
    # declaration is dropped and the element keeps whatever it had.
    "token": ".x { color: var(--color-accent-2-500); }",
}

CLEAN = """.x {
	color: var(--color-accent-700);
	font-family: var(--font-body);
	border: var(--border-thick) solid var(--color-divider);
	border-radius: var(--radius-md);
	box-shadow: var(--shadow-md);
}"""


def _node() -> str:
    found = shutil.which("node")
    if found is None:
        pytest.skip("node is not installed; the frontend gate runs under `just check`")
    return found


def _run(repo_root: Path, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_node(), str(repo_root / GATE), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def _styles(repo_root: Path, root: Path) -> None:
    """Give the fixture the real token layer, so `var(--…)` means what it means here."""
    shutil.copytree(repo_root / WEB / STYLES, root / STYLES, dirs_exist_ok=True)


def _component(root: Path, style: str, name: str = "Offender.svelte") -> Path:
    directory = root / "src" / "lib" / "components"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"<p>hello</p>\n\n<style>\n{style}\n</style>\n", encoding="utf-8")
    return path


def _declarations(text: str) -> dict[str, str]:
    block = ROOT_BLOCK.search(COMMENT.sub("", text))
    assert block is not None, "no `:root` block found"
    return {name: value.strip() for name, value in DECLARATION.findall(block.group(1))}


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace('"', "'")).strip()


# ---------------------------------------------------------------------------
# The transcription
# ---------------------------------------------------------------------------


@pytest.fixture
def designed(repo_root: Path) -> dict[str, str]:
    return _declarations((repo_root / DESIGN).read_text(encoding="utf-8"))


@pytest.fixture
def transcribed(repo_root: Path) -> dict[str, str]:
    return _declarations((repo_root / TOKENS).read_text(encoding="utf-8"))


def test_the_design_declares_the_tokens_this_test_thinks_it_does(designed: dict[str, str]) -> None:
    """A guard on the guard: a design file that stopped parsing would pass silently."""
    assert len(designed) > 30, designed
    assert designed["--color-bg"] == "#fff6e5"


def test_every_token_the_design_declares_is_transcribed(
    designed: dict[str, str], transcribed: dict[str, str]
) -> None:
    missing = sorted(name for name in designed if name not in transcribed)
    assert not missing, (
        f"{TOKENS} is missing {missing}. Every custom property the design's `:root` "
        "declares belongs here, including a ramp step nothing uses yet — the next "
        "screen is the one that needs it."
    )


def test_the_transcribed_value_is_the_designed_value(
    designed: dict[str, str], transcribed: dict[str, str]
) -> None:
    """Values are copied, not rounded, retuned or improved on.

    The font stacks are the one exception and have their own test below.
    """
    wrong = {
        name: (designed[name], transcribed[name])
        for name in designed
        if name not in FONT_STACKS and _normalise(transcribed[name]) != _normalise(designed[name])
    }
    assert not wrong, f"{TOKENS} disagrees with the design: {wrong}"


def test_the_font_tokens_keep_the_designed_families_and_add_a_fallback(
    designed: dict[str, str], transcribed: dict[str, str]
) -> None:
    """The one deliberate deviation, and the shape it is allowed to take.

    A blocked font file must cost the page its voice, never its layout, so each
    stack grows a real fallback. What it may not do is change the family the
    design chose, or the generic it lands on.
    """
    for name in FONT_STACKS:
        wanted = [part.strip() for part in _normalise(designed[name]).split(",")]
        got = [part.strip() for part in _normalise(transcribed[name]).split(",")]
        assert got[0] == wanted[0], f"{name} changed family: {got[0]} is not {wanted[0]}"
        assert got[-1] == wanted[-1], f"{name} changed generic: {got[-1]} is not {wanted[-1]}"
        assert len(got) > len(wanted), f"{name} has no fallback between family and generic"


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_the_gate_passes_over_this_repository(repo_root: Path) -> None:
    result = _run(repo_root, repo_root / WEB)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("rule", sorted(OFFENDERS))
def test_the_gate_fails_on_a_hard_coded_value(repo_root: Path, tmp_path: Path, rule: str) -> None:
    _component(tmp_path, OFFENDERS[rule])
    _styles(repo_root, tmp_path)

    result = _run(repo_root, tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[{rule}]" in result.stderr, result.stderr


def test_the_gate_passes_when_every_value_comes_from_a_token(
    repo_root: Path, tmp_path: Path
) -> None:
    _component(tmp_path, CLEAN)
    _styles(repo_root, tmp_path)

    result = _run(repo_root, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_gate_ignores_markup_and_script(repo_root: Path, tmp_path: Path) -> None:
    """`#each` is not a hex colour, and a `.ts` comment is not a stylesheet."""
    directory = tmp_path / "src" / "lib"
    directory.mkdir(parents=True)
    (directory / "List.svelte").write_text(
        "{#each rows as row (row.id)}<li>{row.id}</li>{/each}\n", encoding="utf-8"
    )
    (directory / "note.ts").write_text(
        "// The design used #ff4f8b and a 3px border.\nexport const N = 1;\n", encoding="utf-8"
    )

    result = _run(repo_root, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_file_awaiting_the_restyle_is_waived_but_still_reported(
    repo_root: Path, tmp_path: Path
) -> None:
    _component(tmp_path, OFFENDERS["color"])
    (tmp_path / "adherence.json").write_text(
        '{"pending": ["src/lib/components/Offender.svelte"]}', encoding="utf-8"
    )

    result = _run(repo_root, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "awaiting the restyle" in result.stderr


def test_the_waiver_list_is_only_allowed_to_shrink(repo_root: Path, tmp_path: Path) -> None:
    """A file that has been restyled must leave the list, or the list rots."""
    _component(tmp_path, CLEAN)
    (tmp_path / "adherence.json").write_text(
        '{"pending": ["src/lib/components/Offender.svelte"]}', encoding="utf-8"
    )

    result = _run(repo_root, tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "only allowed to shrink" in result.stderr


# ---------------------------------------------------------------------------
# The style layer parses
# ---------------------------------------------------------------------------
#
# REGRESSION. `tokens.css` once carried `design/_ds/broadsheet-*//styles.css`
# — written without the second slash — inside two of its comments. `*/` ends a
# CSS comment wherever it appears, so the file's header comment finished in the
# middle of a sentence, the prose after it ran on into the `:root` that follows,
# and a browser dropped the whole rule as an unreadable selector. Every token in
# the application resolved to nothing; every `var(--…)` fell back to the
# browser's default, and the page still rendered, still passed `svelte-check`,
# still passed the adherence gate and still passed all 757 frontend tests,
# because not one of them asks a CSS parser anything.
#
# Python's own non-greedy comment regex ends at the same place a parser does,
# which is why the transcription tests above could read the tokens out of a file
# no browser could. What gives the mistake away is the `*/` left standing
# afterwards: strip the comments the way a parser strips them, and a comment
# that closed early leaves its real terminator behind as stray text.

STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
STYLED = (".css", ".svelte")
NOT_SOURCE = {"node_modules", ".svelte-kit", "build"}


def _style_sheets(root: Path) -> list[tuple[Path, str]]:
    """Every piece of CSS this application ships, as a browser would receive it."""
    found: list[tuple[Path, str]] = []
    for path in sorted((root / WEB / "src").rglob("*")):
        if path.suffix not in STYLED or NOT_SOURCE & set(path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        blocks = [text] if path.suffix == ".css" else STYLE_BLOCK.findall(text)
        found.extend((path, block) for block in blocks)
    return found


def test_there_is_style_to_check(repo_root: Path) -> None:
    """A guard on the guard: a walk that found nothing would pass silently."""
    sheets = _style_sheets(repo_root)

    assert len(sheets) > 10, sheets
    assert any(path.name == "tokens.css" for path, _ in sheets)


def test_no_comment_in_the_style_layer_ends_before_it_means_to(repo_root: Path) -> None:
    broken = {
        str(path.relative_to(repo_root))
        for path, block in _style_sheets(repo_root)
        if "*/" in COMMENT.sub("", block)
    }

    assert not broken, (
        f"{sorted(broken)} leave a `*/` behind once comments are stripped, which means a "
        "comment closed earlier than its author meant it to — usually a path with a `*` "
        "before a `/` in it. Everything from there to the real terminator is parsed as "
        "CSS, and whatever rule it runs into is dropped in silence."
    )


def test_the_token_layer_declares_its_tokens_to_a_parser(repo_root: Path) -> None:
    """The tokens survive being parsed, not merely being read.

    `_declarations` finds a custom property wherever it is written down. A
    browser only sees one that is inside a rule it could parse, so this asks
    the stricter question: with the comments gone, is the file nothing but
    `:root` blocks?
    """
    stripped = COMMENT.sub("", (repo_root / TOKENS).read_text(encoding="utf-8")).strip()

    remainder = re.sub(r":root\s*\{[^{}]*\}", "", stripped).strip()

    assert not remainder, (
        f"{TOKENS} has {remainder[:120]!r} outside any `:root` block once comments are "
        "stripped. A browser reads that as the start of a selector and drops the rule "
        "that follows, so every token in it resolves to nothing at all."
    )
