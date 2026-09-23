"""Tasks 5.6 and 4.4 — every advertised tool, against a real repository.

The first half of D6 is an exact-match test over the advertised names and lives
in the unit suite, where it costs nothing. This is the second half, and it can
only be done for real: **run every tool the server advertises against a clean,
committed working tree and assert what changed.**

An absence cannot be enforced by absence. "No advertised tool modifies
repository content" is the kind of claim that stays true by accident until
somebody adds a tool that writes a cache next to the file it read, and nothing
objects. Running the whole surface and diffing the tree is the only check that
notices.

`add-mcp-writes` D3 **refines** that assertion rather than dropping it, and the
refinement is the whole of why a write surface can be opened without losing the
guarantee:

* every **read** tool still leaves the tree exactly as it found it;
* a **write** tool's only permitted change is the annotations block of the asset
  it was given — no other path, and no other block of that path. A test that
  exempted the write tools would leave nothing at all enforcing *"an agent may
  not create a specification file"*.

The repository carries this project's own `.gitignore`, so the index, the query
log and the report outbox the server legitimately writes under `.canon/` are
ignored by the file that ships rather than by one written to make the test pass.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from game_repo import BARREL_EXPORT, MECH_EXPORT, MECH_SPEC, build_game_repo

from cybercanon.adapters.inbound.mcp.tools import (
    READ_TOOL_NAMES,
    TOOL_NAMES,
    WRITE_TOOL_NAMES,
    advertised,
    build_server,
)
from cybercanon.adapters.outbound.fs.outbox import FileOutbox
from cybercanon.adapters.outbound.git.annotation_writer import GitAnnotationWriter
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.adapters.outbound.sqlite.search_index import SqliteSearchIndex
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.identity_provider import ResolvedIdentity
from cybercanon.application.ports.search_index import FileFingerprint
from cybercanon.application.use_cases.index_assets import Fingerprinter
from cybercanon.application.use_cases.resolve_actor import ActorResolver, IdentityCache
from cybercanon.domain.identity import Actor, ActorId, AgentId, Role

pytestmark = pytest.mark.integration

MECH = "mech_scout"
MECH_DIRECTORY = "characters/mech_scout"
BARREL = "barrel"
LOWERED_BUDGET = "9000"

PROJECT = "Ronin"
BLENDER = AgentId("blender-agent")
UNREACHABLE = "12000 triangles is unreachable without losing the head silhouette"
ANNOTATIONS_KEY = "annotations:"

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
"""One call per advertised **read** tool. A tool with no entry here fails the build below."""

WRITES: dict[str, dict[str, object]] = {
    "add_annotation": {
        "asset": MECH,
        "target": "head",
        "text": UNREACHABLE,
        "kind": "technical",
        "observation_kind": "unattainable_constraint",
    },
    "report_export": {"asset": MECH, "path": MECH_EXPORT, "result": "passed"},
}
"""One call per advertised **write** tool, for the refined assertion (D3)."""


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


def _rafa() -> ActorResolver:
    """A signed-in person, so the write tools have somebody to attribute to."""
    resolver = ActorResolver(project=PROJECT, cache=IdentityCache())
    resolver.cache.remember(
        ResolvedIdentity(
            actor=Actor(
                id=ActorId("rafa"),
                display_name="Rafa",
                roles=(Role.ARTIST,),
                projects=(PROJECT,),
            )
        )
    )
    return resolver


def _container(committed_repo: Path) -> Container:
    """The whole surface, wired to the real adapters over that working copy."""
    store = GitSpecStore(committed_repo)
    return Container(
        spec_store=store,
        mesh_inspector=TrimeshInspector(root=store.root),
        search_index=SqliteSearchIndex(committed_repo),
        fingerprints=_fingerprinter(committed_repo),
        actor_resolver=_rafa(),
        annotation_writer=GitAnnotationWriter(store, root=store.root),
        outcome_reporter=FileOutbox(store.root),
        agent=BLENDER,
    )


@pytest.fixture
def server(committed_repo: Path) -> FastMCP:
    """The server an agent client spawns, over a real repository."""
    return build_server(_container(committed_repo))


def call(server: FastMCP, tool: str, arguments: dict[str, object]) -> str:
    async def _call() -> str:
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments)
            return "\n".join(block.text for block in result.content)

    return asyncio.run(_call())


def _status(root: Path) -> tuple[str, ...]:
    output = _git(root, "status", "--porcelain").stdout.decode("utf-8")
    return tuple(line for line in output.splitlines() if line.strip())


def _outside_annotations(text: str) -> str:
    """The specification with its annotations block removed — what may not move."""
    return text.split(ANNOTATIONS_KEY)[0]


def test_every_advertised_tool_is_exercised(server: FastMCP) -> None:
    """The guard on the guard: a tool nobody calls proves nothing about the tree."""
    assert tuple(sorted(CALLS)) == tuple(sorted(READ_TOOL_NAMES))
    assert tuple(sorted(WRITES)) == tuple(sorted(WRITE_TOOL_NAMES))
    assert advertised(server) == tuple(sorted(TOOL_NAMES))
    assert tuple(sorted(CALLS | WRITES)) == advertised(server)


def test_running_every_read_tool_leaves_the_working_tree_clean(
    server: FastMCP, committed_repo: Path
) -> None:
    """D6 — the read surface reads, and `git status` is the proof."""
    answers = {tool: call(server, tool, arguments) for tool, arguments in CALLS.items()}

    assert all(answers.values()), "a tool answered with nothing"
    assert _git(committed_repo, "status", "--porcelain").stdout == b""


def test_a_write_changes_the_named_assets_specification_and_nothing_else(
    server: FastMCP, committed_repo: Path
) -> None:
    """D3 — the refined assertion: one path, and one block inside it.

    Both write tools are called, so the report the second one produces has to be
    invisible to git as well: the outbox is under `.canon/` and ignored by the
    file that ships, and a report that landed in the repository would fail here.
    """
    before = (committed_repo / MECH_SPEC).read_text(encoding="utf-8")

    answers = {tool: call(server, tool, arguments) for tool, arguments in WRITES.items()}

    assert all(answers.values()), "a write tool answered with nothing"
    assert _status(committed_repo) == (f" M {MECH_SPEC}",)
    after = (committed_repo / MECH_SPEC).read_text(encoding="utf-8")
    assert _outside_annotations(after) == _outside_annotations(before)
    assert UNREACHABLE in after


def test_a_write_is_left_uncommitted_for_a_person_to_review(
    server: FastMCP, committed_repo: Path
) -> None:
    """D2 — the agent proposes; the diff is where a human decides."""
    head = _git(committed_repo, "rev-parse", "HEAD").stdout

    call(server, "add_annotation", WRITES["add_annotation"])

    assert _git(committed_repo, "rev-parse", "HEAD").stdout == head
    assert _git(committed_repo, "diff", "--cached", "--name-only").stdout == b""


def test_a_write_to_an_unknown_asset_creates_no_specification_file(
    server: FastMCP, committed_repo: Path
) -> None:
    """*"SHALL NOT create an asset, create a specification file, or cause one to come
    into existence as a side effect of a write."*"""
    answer = call(server, "add_annotation", {**WRITES["add_annotation"], "asset": "mech_scowt"})

    assert "mech_scowt" in answer
    assert _status(committed_repo) == ()
    assert not list(committed_repo.rglob("mech_scowt*"))


def test_the_answers_are_about_this_repository(server: FastMCP) -> None:
    """Clean is only interesting if the tools actually did their work."""
    assert MECH_DIRECTORY in call(server, "where_is", CALLS["where_is"])
    assert MECH_SPEC in call(server, "get_asset_spec", {"asset_id": MECH})
    assert BARREL in call(server, "list_assets", {})
    assert LOWERED_BUDGET in call(server, "diff_spec", CALLS["diff_spec"])
    assert MECH in call(server, "validate_export", {"export": MECH_EXPORT})
    assert BARREL in call(server, "validate_export", {"export": BARREL_EXPORT})
