"""Task 6.5 — the documented launch entry, run verbatim against a clean clone.

A documented configuration nobody executes is a configuration that drifts, so
the entry in `README.md` is *parsed out of the document* and used as-is: the
command, its arguments and its environment. If the README's JSON block ever
stops naming an agent identifier, or starts naming a secret, this fails.

The repository is a genuine `git clone` — cloned from a committed copy of
`examples/ronin` rather than copied — because the two claims here are claims
about a fresh machine:

* **a read works, a write is refused.** Nobody has signed in on this clone, so
  the eight reads answer and the two writes are refused naming the sign-in
  action. That is the whole of *"an unauthenticated agent keeps the entire read
  surface and loses exactly these two tools"*;
* **nothing the write path leaves behind is committable.** The report outbox
  lands under `.canon/`, the `.gitignore` entry covers it, and `git status` on
  the clone stays clean — which is what keeps a delivered report from becoming a
  second copy of the outcome beside the one G2 makes the real one.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from machine import AGENT, bare_environment

from cybercanon.adapters.outbound.fs.outbox import OUTBOX_PATH, FileOutbox
from cybercanon.application.ports.outcome_reporter import ReportedOutcome
from cybercanon.application.use_cases.observations import SIGN_IN_ACTION

pytestmark = pytest.mark.integration

MECH = "mech_scout"
MECH_DIRECTORY = "characters/mech_scout"

CONFIG_BLOCK = re.compile(r"```json\n(\{\n  \"mcpServers\".*?\n\})\n```", re.DOTALL)

CREDENTIAL_WORDS = ("token", "secret", "password", "credential", "api_key", "apiKey")
"""What must never appear in a launch entry. The store is the only place for one."""


def documented_entry(repo_root: Path) -> dict[str, Any]:
    """The `mcpServers` entry `README.md` tells an agent client to use."""
    block = CONFIG_BLOCK.search((repo_root / "README.md").read_text(encoding="utf-8"))
    assert block is not None, "README.md no longer documents an agent client configuration"
    return dict(json.loads(block.group(1))["mcpServers"]["cybercanon"])


def git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "HOME": str(root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Rafa",
            "GIT_AUTHOR_EMAIL": "rafa@cyberdyne.com",
            "GIT_COMMITTER_NAME": "Rafa",
            "GIT_COMMITTER_EMAIL": "rafa@cyberdyne.com",
        },
    )


@pytest.fixture(scope="module")
def clone(tmp_path_factory: pytest.TempPathFactory, repo_root: Path) -> Path:
    """`examples/ronin`, committed once and then cloned, as a new machine gets it."""
    workspace = tmp_path_factory.mktemp("documented")
    origin = workspace / "origin"
    shutil.copytree(repo_root / "examples" / "ronin", origin)
    shutil.copy(repo_root / ".gitignore", origin / ".gitignore")
    git(origin, "init", "-q")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "the canon")

    cloned = workspace / "ronin"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(cloned)], check=True, capture_output=True
    )
    return cloned


def ask(
    command: str,
    arguments: list[str],
    calls: dict[str, dict[str, Any]],
    *,
    cwd: Path,
    env: dict[str, str],
) -> dict[str, str]:
    """Spawn the documented command as a process and put the calls to it."""

    async def _ask() -> dict[str, str]:
        transport = StdioTransport(command=command, args=arguments, env=env, cwd=str(cwd))
        async with Client(transport) as client:
            answers = {}
            for tool, payload in calls.items():
                result = await client.call_tool(tool, payload)
                answers[tool] = "\n".join(block.text for block in result.content)
            return answers

    return asyncio.run(_ask())


# --------------------------------------------------------------------------
# What the document says
# --------------------------------------------------------------------------


def test_the_documented_entry_names_an_agent_identifier(repo_root: Path) -> None:
    """D4's identifier, in the one place it is allowed to come from."""
    entry = documented_entry(repo_root)

    assert entry.get("env", {}).get("CANON_AGENT"), "the launch entry names no agent"


@pytest.mark.parametrize("word", CREDENTIAL_WORDS)
def test_the_documented_entry_contains_no_credential(repo_root: Path, word: str) -> None:
    """*"The configuration SHALL contain no credential."*"""
    assert word not in json.dumps(documented_entry(repo_root)).lower()


def test_the_outbox_is_git_ignored_by_the_shipped_gitignore(repo_root: Path) -> None:
    assert OUTBOX_PATH in (repo_root / ".gitignore").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# What the document does
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def answers(clone: Path, repo_root: Path) -> dict[str, str]:
    """The documented command, run verbatim on a clone nobody has signed into."""
    entry = documented_entry(repo_root)
    installed = shutil.which(str(entry["command"]))
    assert installed is not None, f"the documented command {entry['command']!r} is not installed"
    return ask(
        installed,
        [str(argument) for argument in entry["args"]],
        {
            "where_is": {"asset_id": MECH},
            "add_annotation": {"asset": MECH, "target": "head", "text": "cannot reach 12000"},
        },
        cwd=clone,
        env=bare_environment(**{str(k): str(v) for k, v in entry.get("env", {}).items()}),
    )


def test_a_read_completes_on_a_clean_clone(answers: dict[str, str]) -> None:
    assert MECH_DIRECTORY in answers["where_is"]


def test_the_write_is_refused_naming_the_sign_in_action(answers: dict[str, str]) -> None:
    assert SIGN_IN_ACTION in answers["add_annotation"]


def test_the_refused_write_left_the_clone_untouched(clone: Path, answers: dict[str, str]) -> None:
    """*"No specification file SHALL be created"*, and nothing else either."""
    assert answers["add_annotation"], "the call answered nothing"

    status = subprocess.run(
        ["git", "-C", str(clone), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert status.stdout == "", status.stdout


def test_a_retained_report_never_appears_in_git_status(clone: Path) -> None:
    """The outbox is derived state beside the index, and the entry covers it."""
    FileOutbox(clone).report(
        ReportedOutcome(
            asset_id=MECH,
            export="exports/SM_mech_scout_LOD0.glb",
            export_hash="a1b2",
            verdict_hash="c3d4",
            passed=True,
            attributed_to="Rafa",
            via=AGENT,
        )
    )

    status = subprocess.run(
        ["git", "-C", str(clone), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (clone / OUTBOX_PATH).is_file(), "the report was retained"
    assert status.stdout == "", status.stdout


def test_the_agent_snippet_documents_the_two_write_tools(repo_root: Path) -> None:
    """The integration for an agent that does not speak MCP says what it may record."""
    snippet = (repo_root / "examples" / "ronin" / "CLAUDE.md").read_text(encoding="utf-8")

    assert "add_annotation" in snippet
    assert "report_export" in snippet
    assert "never write constraints" in snippet


def test_the_readme_states_the_prohibition_that_has_no_tool(repo_root: Path) -> None:
    """A reader must be able to learn the rule from the document, not from the code."""
    readme = (repo_root / "README.md").read_text(encoding="utf-8").lower()

    assert "no promotion tool" in readme
    assert "canon login" in readme
    assert "canon_agent" in readme
