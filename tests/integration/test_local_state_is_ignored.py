"""Task 4.3 — the derived state a read surface writes never reaches a diff.

The index and the query log are **derived**: the repository is the source of
truth, and both are rebuilt from it. Committing either would be committing a
cache — noise in every review, conflicts on every merge, and a file whose
contents depend on which machine last ran a search.

So this runs the whole cycle a developer's agent runs — validate an export,
rebuild the index, look an asset up, search for one that exists and one that
does not — inside a real repository carrying **this project's own
`.gitignore`**, and asserts that `git status` has nothing to say afterwards.
Copying the real ignore file rather than writing a convenient one is the point:
the test fails if somebody removes those lines from the file that ships.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from game_repo import MECH_EXPORT, build_game_repo

from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.adapters.outbound.sqlite.search_index import (
    INDEX_PATH,
    QUERY_LOG_PATH,
    SqliteSearchIndex,
)
from cybercanon.application.ports.search_index import FileFingerprint
from cybercanon.application.use_cases.index_assets import rebuild_index
from cybercanon.application.use_cases.lookup_assets import search_assets, where_is
from cybercanon.application.use_cases.validate_export import validate_export

pytestmark = pytest.mark.integration

LOCAL_STATE = (INDEX_PATH, QUERY_LOG_PATH)
"""What a read surface writes into the working copy, and nothing else."""

MISSING_TERM = "hovercraft"


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


def _fingerprint(root: Path) -> object:
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
    """A game repository carrying this project's own ignore rules, fully committed."""
    root = tmp_path / "game"
    root.mkdir()
    _git(root, "init", "-q")
    build_game_repo(root)
    (root / ".gitignore").write_text(
        (repo_root / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the canon, as an artist committed it")
    return root


def test_the_project_ignores_the_index_and_the_query_log(repo_root: Path) -> None:
    ignored = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()

    for path in LOCAL_STATE:
        assert path in ignored, f"{path} is derived state and must not be committable"


def test_a_validate_index_search_cycle_leaves_the_working_tree_clean(committed_repo: Path) -> None:
    """The whole read surface, run end to end, and `git status` has nothing to say."""
    store = GitSpecStore(committed_repo)
    index = SqliteSearchIndex(committed_repo)
    fingerprints = _fingerprint(committed_repo)

    validate_export(
        MECH_EXPORT, spec_store=store, mesh_inspector=TrimeshInspector(root=committed_repo)
    )
    report = rebuild_index("", spec_store=store, search_index=index, fingerprints=fingerprints)
    located = where_is(
        "mech_scout", spec_store=store, search_index=index, fingerprints=fingerprints
    )
    found = search_assets("mech_scout", search_index=index)
    missed = search_assets(MISSING_TERM, search_index=index)

    assert report.indexed_count == 3
    assert located.asset_id == "mech_scout"
    assert found.asset_ids == ("mech_scout",)
    assert missed.recorded_as_miss
    assert index.database.is_file()
    assert index.query_log.is_file()
    assert _git(committed_repo, "status", "--porcelain").stdout == b""


def test_each_piece_of_local_state_is_ignored_by_name(committed_repo: Path) -> None:
    """Named individually, so a rule that stopped matching is visible here."""
    index = SqliteSearchIndex(committed_repo)
    index.record_miss(MISSING_TERM)

    for path in LOCAL_STATE:
        assert (committed_repo / path).is_file()
        assert _git(committed_repo, "check-ignore", path).returncode == 0
