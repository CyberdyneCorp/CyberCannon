"""Task 6.8 — the M1 acceptance test: a developer's agent, and no human asked.

The question the milestone is judged on is the one that started the project:

    "Where do I get the mech scout model, and what must it satisfy?"

A developer's agent has to answer it **using only MCP tools**, over a repository
it has never seen, with no credential configured and nobody to ask. So this runs
the real server as a subprocess — spawned the way an agent client spawns it —
puts the question to it as the sequence of calls an agent would make, and reads
the transcript back for every sub-answer a person would need before opening
Blender.

`ANSWERABLE` is the acceptance criterion: each entry is one thing the developer
has to learn, and the tool call that has to yield it. `CANDIDATE_GAPS` is the
other half of the task, and it is deliberately asserted rather than written
down: a question the surface *should* answer and currently answers with "not
recorded" stays visible in the build until somebody closes it, instead of
becoming a sentence in a report nobody re-reads.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

pytestmark = pytest.mark.integration

MECH = "mech_scout"
SPEC = "characters/mech_scout/asset.yaml"
QUESTION = "where do I get the mech scout model and what must it satisfy"

TRANSCRIPT: dict[str, tuple[str, dict[str, Any]]] = {
    "what is it called": ("search_assets", {"term": "mech scout"}),
    "where does it live": ("where_is", {"asset_id": MECH}),
    "what must it satisfy": ("get_constraints", {"asset_id": MECH}),
    "what is the whole contract": ("get_asset_spec", {"asset_id": MECH}),
    "what is still open": ("get_open_annotations", {"asset_id": MECH}),
    "has the contract moved": ("diff_spec", {"asset_id": MECH, "revision": "HEAD~1"}),
}
"""The calls an agent makes from the question alone. No other source of truth."""

ANSWERABLE: tuple[tuple[str, str, str], ...] = (
    ("the asset's identifier", "what is it called", MECH),
    ("its directory in the repository", "where does it live", "characters/mech_scout"),
    ("the authoring source file", "where does it live", "art/source/mech_scout.blend"),
    ("the engine content path", "where does it live", "Content/Ronin/Characters/MechScout"),
    ("the design document", "where does it live", "arche.cyberdynecorp.ai"),
    ("the triangle budget", "what must it satisfy", "12000"),
    ("the LOD budgets", "what must it satisfy", "6000"),
    ("the required attachment point", "what must it satisfy", "SOCKET_muzzle_l"),
    ("the object naming convention", "what must it satisfy", "SM_{asset}_LOD{n}"),
    ("the up axis", "what must it satisfy", "Up axis"),
    ("the skeleton", "what must it satisfy", "SK_MechScout"),
    ("the bone budget", "what must it satisfy", "64"),
    ("the animation states it must contain", "what is the whole contract", "walk"),
    ("the clip naming convention", "what must it satisfy", "A_{asset}_{state}"),
    ("the silhouette rule it is judged by", "what is the whole contract", "asymmetric shoulder"),
    ("the open art-direction thread", "what is still open", "pauldron"),
    ("what changed since the last revision", "has the contract moved", "12000"),
)
"""Question the developer has, which call answers it, and the evidence in the prose."""

CANDIDATE_GAPS: tuple[tuple[str, str], ...] = (
    ("which export was last validated, and when", "latest validated export | not recorded"),
)
"""Answered with an explicit absence rather than a fact.

Reporting an unrecorded location as absent is the specified behaviour, so this is
not a defect of the location answer. It is a gap in the *system*: no code path in
this change ever records a validated export against an asset, so the field is
absent in every real repository rather than only in a new one. Asserted here so
that the day something does record it, this line fails and is deleted.
"""


def git(root: Path, *arguments: str) -> None:
    environment = {
        **os.environ,
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Rafa",
        "GIT_AUTHOR_EMAIL": "rafa@cyberdyne.com",
        "GIT_COMMITTER_NAME": "Rafa",
        "GIT_COMMITTER_EMAIL": "rafa@cyberdyne.com",
    }
    subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, env=environment
    )


def without_identity() -> dict[str, str]:
    """The developer's machine as the acceptance criterion describes it: nothing configured."""
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CANON_", "CYBERDYNE_", "GIT_")) and name != "HOME"
    }


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory, repo_root: Path) -> Path:
    """The worked example as a committed repository, with one edit behind it."""
    root = tmp_path_factory.mktemp("acceptance") / "ronin"
    shutil.copytree(repo_root / "examples" / "ronin", root)
    (root / ".gitignore").write_text(
        (repo_root / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "the canon")
    spec = root / SPEC
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("tri_budget: 12000", "tri_budget: 9000"),
        encoding="utf-8",
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "lower the scout's budget")
    return root


@pytest.fixture(scope="module")
def answers(game: Path) -> dict[str, str]:
    """The whole session: one spawned server, the agent's calls, nobody asked."""

    async def _ask() -> dict[str, str]:
        transport = StdioTransport(
            command=sys.executable,
            args=["-m", "cybercanon.cli", "mcp", "serve", str(game)],
            env=without_identity(),
            cwd=str(game),
        )
        async with Client(transport) as client:
            collected = {}
            for question, (tool, arguments) in TRANSCRIPT.items():
                result = await client.call_tool(tool, arguments)
                collected[question] = "\n".join(block.text for block in result.content)
            return collected

    return asyncio.run(_ask())


def test_the_agent_used_nothing_but_the_server(answers: dict[str, str]) -> None:
    """The acceptance condition: every answer came from a tool, and none is empty."""
    assert set(answers) == set(TRANSCRIPT)
    assert all(text.strip() for text in answers.values()), QUESTION


@pytest.mark.parametrize(
    ("needed", "question", "evidence"),
    ANSWERABLE,
    ids=[needed for needed, _, _ in ANSWERABLE],
)
def test_the_agent_can_answer(
    answers: dict[str, str], needed: str, question: str, evidence: str
) -> None:
    assert evidence in answers[question], f"the agent could not learn {needed}"


@pytest.mark.parametrize(
    ("question", "absence"), CANDIDATE_GAPS, ids=[q for q, _ in CANDIDATE_GAPS]
)
def test_the_recorded_candidate_gap_is_still_a_gap(
    answers: dict[str, str], question: str, absence: str
) -> None:
    """Delete the entry when something finally records it — do not relax the test."""
    assert absence in answers["where does it live"], (
        f"{question!r} is answered now; remove it from CANDIDATE_GAPS"
    )


def test_a_lensed_answer_says_it_is_a_projection(answers: dict[str, str]) -> None:
    """The one misreading worth two lines: a subset taken for the whole contract."""
    lensed = answers["what must it satisfy"]

    assert "modeling" in lensed
    assert "full specification" in lensed


def test_the_session_survives_a_name_that_does_not_exist(game: Path) -> None:
    """An agent's typo offers the nearest identifiers and leaves the session usable."""

    async def _ask() -> tuple[str, str]:
        transport = StdioTransport(
            command=sys.executable,
            args=["-m", "cybercanon.cli", "mcp", "serve", str(game)],
            env=without_identity(),
            cwd=str(game),
        )
        async with Client(transport) as client:
            missed = await client.call_tool("where_is", {"asset_id": "mech_scot"})
            recovered = await client.call_tool("where_is", {"asset_id": MECH})
            return (
                "\n".join(block.text for block in missed.content),
                "\n".join(block.text for block in recovered.content),
            )

    missed, recovered = asyncio.run(_ask())

    assert MECH in missed, "a near miss must offer the closest identifiers"
    assert "characters/mech_scout" in recovered, "the session must remain usable"
