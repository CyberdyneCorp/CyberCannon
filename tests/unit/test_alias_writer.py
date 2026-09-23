"""Task 6.1 and 6.3 — the accepted alias is one term in one sequence, and nothing else.

`metadata-acceptance`: *"the difference SHALL show only the added alias"*, and
*"the file SHALL contain no marker distinguishing it"*. Both are properties of
:mod:`cybercanon.adapters.outbound.git.writer`, so both are asserted here over
hand-authored text with comments, a deliberate key order and a flow-style list —
the file an artist actually writes, rather than one a dumper produced.
"""

from __future__ import annotations

import difflib

import pytest

from cybercanon.adapters.outbound.git import writer
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.status import Status

pytestmark = pytest.mark.unit

AUTHORED = """\
# The scout. Keep the silhouette readable at 32 px.
schema_version: 1
id: mech_scout
name: Scout Mech
aliases: [mech, walker] # what people call it in standups
status: modeling
owner_art: rafa@cyberdyne.com
constraints:
  # raised after the LOD pass, 2026-08
  tri_budget: 12000
"""

BLOCK_STYLE = """\
schema_version: 1
id: mech_scout
name: Scout Mech
aliases:
  - mech
  # the one the animators use
  - walker
status: modeling
"""

NO_ALIASES = """\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
"""

MODEL_WORDS = ("generated", "suggested", "llm", "derived", "vision", "proposed", "machine")
"""Words a marker of model origin would be spelled with. None may appear.

`model` is deliberately absent from this list: `status: modeling` contains it,
and a guard that fired on an artist's lifecycle value would be a guard people
learn to work around rather than one that ever catches anything.
"""


def an_asset(aliases: tuple[str, ...]) -> Asset:
    return Asset(
        id=AssetId("mech_scout"),
        name="Scout Mech",
        status=Status.MODELING,
        aliases=aliases,
    )


def changed_lines(before: str, after: str) -> tuple[str, ...]:
    """Every line the difference adds or removes, markers included."""
    return tuple(
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )


# --------------------------------------------------------------------------
# 6.1 — only the intended change appears
# --------------------------------------------------------------------------


def test_only_the_added_alias_appears_in_the_difference() -> None:
    written = writer.render(
        AUTHORED, an_asset(("mech", "walker", "recon")), an_asset(("mech", "walker"))
    )

    changed = changed_lines(AUTHORED, written)
    assert len(changed) == 2
    assert changed[0].startswith("-aliases:")
    assert "recon" in changed[1]


def test_comments_and_key_order_are_unchanged() -> None:
    written = writer.render(
        AUTHORED, an_asset(("mech", "walker", "recon")), an_asset(("mech", "walker"))
    )

    assert "# The scout. Keep the silhouette readable at 32 px." in written
    assert "# what people call it in standups" in written
    assert "# raised after the LOD pass, 2026-08" in written
    assert _top_level_keys(written) == AUTHORED_KEYS


AUTHORED_KEYS = ["schema_version", "id", "name", "aliases", "status", "owner_art", "constraints"]


def _top_level_keys(text: str) -> list[str]:
    """The document's keys, in the order a reader meets them."""
    return [
        line.split(":", 1)[0]
        for line in text.splitlines()
        if line and not line[0].isspace() and not line.startswith("#") and ":" in line
    ]


def test_a_flow_style_list_stays_a_flow_style_list() -> None:
    """A one-word change must not rewrite the block the artist wrote."""
    written = writer.render(
        AUTHORED, an_asset(("mech", "walker", "recon")), an_asset(("mech", "walker"))
    )

    assert "aliases: [mech, walker, recon]" in written


def test_a_block_style_list_keeps_its_own_comments() -> None:
    written = writer.render(
        BLOCK_STYLE, an_asset(("mech", "walker", "recon")), an_asset(("mech", "walker"))
    )

    assert "# the one the animators use" in written
    assert "- recon" in written


def test_a_file_with_no_aliases_gains_the_key_and_nothing_else() -> None:
    written = writer.render(NO_ALIASES, an_asset(("recon",)), an_asset(()))

    changed = changed_lines(NO_ALIASES, written)
    assert [line for line in changed if line.startswith("-")] == []
    assert "recon" in "".join(changed)


def test_an_unchanged_alias_list_is_not_rewritten() -> None:
    """A caller that changed nothing gets its input back, byte for byte."""
    assert writer.render(AUTHORED, an_asset(("mech", "walker")), an_asset(("mech", "walker"))) == (
        AUTHORED
    )


def test_removing_the_last_alias_removes_the_key() -> None:
    written = writer.render(AUTHORED, an_asset(()), an_asset(("mech", "walker")))

    assert "aliases" not in written
    assert "tri_budget: 12000" in written


# --------------------------------------------------------------------------
# 6.3 — indistinguishable from a hand-written alias
# --------------------------------------------------------------------------


def test_an_accepted_alias_is_written_exactly_as_a_hand_written_one_would_be() -> None:
    """The same file, reached two ways: typed by hand, and accepted."""
    by_hand = AUTHORED.replace("[mech, walker]", "[mech, walker, recon]")

    accepted = writer.render(
        AUTHORED, an_asset(("mech", "walker", "recon")), an_asset(("mech", "walker"))
    )

    assert accepted == by_hand


def test_the_file_carries_no_marker_of_model_origin() -> None:
    written = writer.render(
        AUTHORED, an_asset(("mech", "walker", "recon")), an_asset(("mech", "walker"))
    )

    lowered = written.lower()
    assert not [word for word in MODEL_WORDS if word in lowered]
