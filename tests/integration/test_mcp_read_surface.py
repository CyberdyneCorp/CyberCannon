"""Task 5.6 — every advertised tool, run against a real repository, changes nothing.

The first half of D6 is an exact-match test over the advertised names and lives
in the unit suite, where it costs nothing. This is the second half, and it can
only be done for real: **run every tool the server advertises against a clean,
committed working tree and assert `git status` still has nothing to say.**

An absence cannot be enforced by absence. "No advertised tool modifies
repository content" is the kind of claim that stays true by accident until
somebody adds a tool that writes a cache next to the file it read, and nothing
objects. Running the whole surface and diffing the tree is the only check that
notices.

The repository carries this project's own `.gitignore`, so the index and the
query log the server legitimately writes under `.canon/` are ignored by the file
that ships rather than by one written to make the test pass.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from game_repo import BARREL_EXPORT, MECH_EXPORT, MECH_SPEC, build_game_repo

from cybercanon.adapters.inbound.mcp.tools import TOOL_NAMES, advertised, build_server
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.adapters.outbound.sqlite.search_index import SqliteSearchIndex
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.search_index import FileFingerprint
from cybercanon.application.use_cases.index_assets import Fingerprinter

pytestmark = pytest.mark.integration

MECH = "mech_scout"
MECH_DIRECTORY = "characters/mech_scout"
BARREL = "barrel"
LOWERED_BUDGET = "9000"

CALLS: dict[str, dict[str, object]] = {
    "where_is": {"asset_id": MECH},
    "list_assets": {},
    "search_assets": {"term": MECH},
    "get_asset_spec": {"asset_id": MECH, "lens": "modeling"},
    "get_constraints": {"asset_id": MECH},
    "get_open_annotations": {"asset_id": MECH},
    "diff_spec": {"asset_id": MECH, "revision": "HEAD~1"},
    "validate_export": {"export": MECH_EXPORT},
}
"""One call per advertised tool. A tool with no entry here fails the build below."""


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = {
        **os.environ,
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Rafa",
        "GIT_AUTHOR_EMAIL": "rafa@cyberdyne.com",
        "GIT_COMMITTER_NAME": "Rafa",
        "GIT_COMMITTER_EMAIL": "rafa@cyberdyne.com",
    }
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, env=environment
    )


def _fingerprinter(root: Path) -> Fingerprinter:
    """The `os.stat` fingerprinter D8 expects the composition root to supply."""

    def fingerprints(path: str) -> FileFingerprint | None:
        absolute = root / path
        if not absolute.is_file():
            return None
        stat = absolute.stat()
        return FileFingerprint(path=path, size=stat.st_size, mtime_ns=stat.st_mtime_ns)

    return fingerprints


@pytest.fixture
def committed_repo(tmp_path: Path, repo_root: Path) -> Path:
    """A game repository with two commits, so `diff_spec` has history to read."""
    root = tmp_path / "game"
    root.mkdir()
    _git(root, "init", "-q")
    build_game_repo(root)
    (root / ".gitignore").write_text(
        (repo_root / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the canon, as an artist committed it")
    spec = root / MECH_SPEC
    lowered = spec.read_text(encoding="utf-8").replace(
        "tri_budget: 12000", f"tri_budget: {LOWERED_BUDGET}"
    )
    spec.write_text(lowered, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "lower the scout's budget")
    return root


@pytest.fixture
def server(committed_repo: Path) -> FastMCP:
    """The read surface, wired to the real adapters over that working copy."""
    store = GitSpecStore(committed_repo)
    container = Container(
        spec_store=store,
        mesh_inspector=TrimeshInspector(root=store.root),
        search_index=SqliteSearchIndex(committed_repo),
        fingerprints=_fingerprinter(committed_repo),
    )
    return build_server(container)


def call(server: FastMCP, tool: str, arguments: dict[str, object]) -> str:
    async def _call() -> str:
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments)
            return "\n".join(block.text for block in result.content)

    return asyncio.run(_call())


def test_every_advertised_tool_is_exercised(server: FastMCP) -> None:
    """The guard on the guard: a tool nobody calls proves nothing about the tree."""
    assert tuple(sorted(CALLS)) == advertised(server) == tuple(sorted(TOOL_NAMES))


def test_running_every_tool_leaves_the_working_tree_clean(
    server: FastMCP, committed_repo: Path
) -> None:
    """D6 — the read surface reads, and `git status` is the proof."""
    answers = {tool: call(server, tool, arguments) for tool, arguments in CALLS.items()}

    assert all(answers.values()), "a tool answered with nothing"
    assert _git(committed_repo, "status", "--porcelain").stdout == b""


def test_the_answers_are_about_this_repository(server: FastMCP) -> None:
    """Clean is only interesting if the tools actually did their work."""
    assert MECH_DIRECTORY in call(server, "where_is", CALLS["where_is"])
    assert MECH_SPEC in call(server, "get_asset_spec", {"asset_id": MECH})
    assert BARREL in call(server, "list_assets", {})
    assert LOWERED_BUDGET in call(server, "diff_spec", CALLS["diff_spec"])
    assert MECH in call(server, "validate_export", {"export": MECH_EXPORT})
    assert BARREL in call(server, "validate_export", {"export": BARREL_EXPORT})
