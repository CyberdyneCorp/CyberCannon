"""Tasks 2.6-2.7 and 4.2, 4.4 — history and the actor mapping, every implementation.

Three fixtures rather than one, because the mapping's three outcomes are three
different repositories: one that authored `.canon/actors.yaml`, one that never
did, and one whose file cannot be parsed. Each is parametrised over the fake and
over `GitSpecStore`, so a divergence between what the unit suite is tested
against and what a working copy actually answers fails the build.

`GitSpecStore`'s factories build a **real repository** in the directory the
fixture hands them: `git init`, the specification committed twice with different
triangle budgets, and `vehicles/mule/asset.yaml` written but never committed. A
fake can be told it has a revision series; only a repository can prove that the
series comes back newest first, that a bounded list is the newest slice of it,
and that an uncommitted file has no history at all — which are the three things
`diff_spec` depends on.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from contract import implementation_fixture
from spec_store_history_contract import (
    BUDGET_NOW,
    BUDGET_THEN,
    HISTORY,
    MAPPING,
    SPEC_PATH,
    UNPARSEABLE_DETAIL,
    UNTRACKED_SPEC,
    SpecStoreHistoryContract,
    SpecStoreMappingContract,
)

from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.domain.actors import ACTORS_PATH

SPEC_TEMPLATE = """\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
constraints:
  tri_budget: {budget}
"""

ACTORS_YAML = """\
schema_version: 1
actors:
  - subject: auth|rafa
    display_name: Rafa
    emails:
      - rafa@cyberdyne.com
      - rafa@personal.dev
    chat_handle: "@rafa"
    default_role: ARTIST
"""

BROKEN_ACTORS_YAML = """\
schema_version: 1
actors:
  - subject: auth|rafa
    emails: [rafa@cyberdyne.com
    display_name: "Rafa
"""


# --------------------------------------------------------------------------
# The in-memory fake
# --------------------------------------------------------------------------


def _seeded() -> InMemorySpecStore:
    """The corpus every factory starts from: the current spec and its series."""
    store = InMemorySpecStore()
    for revision, asset in HISTORY.items():
        store.add_revision(SPEC_PATH, revision, asset)
    store.add(SPEC_PATH, HISTORY["rev-newer"])
    store.add(UNTRACKED_SPEC, HISTORY["rev-newer"])
    return store


def in_memory(directory: Path) -> InMemorySpecStore:
    """A project that authored an actor mapping."""
    store = _seeded()
    store.set_actor_mapping(MAPPING)
    return store


def in_memory_without_mapping(directory: Path) -> InMemorySpecStore:
    """A project that never wrote `.canon/actors.yaml`. It stays fully readable."""
    return _seeded()


def in_memory_with_broken_mapping(directory: Path) -> InMemorySpecStore:
    """A project whose mapping cannot be parsed — a violation, never an exception."""
    store = _seeded()
    store.set_actor_mapping_unparseable(UNPARSEABLE_DETAIL)
    return store


# --------------------------------------------------------------------------
# The real adapter, over a throwaway repository
# --------------------------------------------------------------------------


def _git(root: Path, *arguments: str) -> None:
    """One git command in the throwaway repository, isolated from this machine.

    `HOME` points at the repository and the system configuration is switched
    off, so the developer's own git configuration — a signing key, a hook path,
    a commit template — cannot change what these commits look like.
    """
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
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        env=environment,
    )


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repository(directory: Path, mapping: str | None = None) -> GitSpecStore:
    """A working copy whose specification was committed twice, then edited once."""
    root = directory / "game"
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for budget in (BUDGET_THEN, BUDGET_NOW):
        _write(root, SPEC_PATH, SPEC_TEMPLATE.format(budget=budget))
        _git(root, "add", SPEC_PATH)
        _git(root, "commit", "-q", "-m", f"triangle budget {budget}")
    if mapping is not None:
        _write(root, ACTORS_PATH, mapping)
        _git(root, "add", ACTORS_PATH)
        _git(root, "commit", "-q", "-m", "map rafa to their git identity")
    _write(root, UNTRACKED_SPEC, SPEC_TEMPLATE.format(budget=BUDGET_NOW))
    return GitSpecStore(root)


def git(directory: Path) -> GitSpecStore:
    """A repository that authored an actor mapping and committed it."""
    return _repository(directory, ACTORS_YAML)


def git_without_mapping(directory: Path) -> GitSpecStore:
    """A repository with no `.canon/actors.yaml` at all."""
    return _repository(directory)


def git_with_broken_mapping(directory: Path) -> GitSpecStore:
    """A repository whose `.canon/actors.yaml` is not YAML any more."""
    return _repository(directory, BROKEN_ACTORS_YAML)


implementation = implementation_fixture(fake=in_memory, real=git)
without_mapping = implementation_fixture(fake=in_memory_without_mapping, real=git_without_mapping)
unparseable_mapping = implementation_fixture(
    fake=in_memory_with_broken_mapping, real=git_with_broken_mapping
)


class TestSpecStoreHistory(SpecStoreHistoryContract):
    """The history contract (D10), against the fake and `GitSpecStore`."""


class TestSpecStoreMapping(SpecStoreMappingContract):
    """The actor-mapping contract (D12), against the fake and `GitSpecStore`."""
