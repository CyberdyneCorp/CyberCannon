"""Tasks 4.1, 5.1 and 4.4 — the `SpecStore` contract against every implementation.

One factory per implementation, seeded with the same corpus: the in-memory fake
takes the assets directly, `GitSpecStore` gets them written into a working copy
as `asset.yaml` files. The contract body does not change, and any divergence
between the two — discovery that stops in a different place, a missing file that
reads as empty, an unknown field that becomes fatal — fails the build instead of
the product.

The YAML below is written by hand rather than generated from the domain objects
on purpose. A writer would let a reader bug and a writer bug cancel out; a
literal file is what an artist would actually commit, and it is the thing the
adapter is supposed to be able to read.

**Four implementations, not two** (task 4.4). D3 gives the store a second read
path — reads resolved at a pinned revision out of the object database rather
than off the checked-out tree — and states the cost it accepts: *"the local
'just read the file' path and the server's 'read this revision' path must be
covered by the same port-conformance suite or they will drift."* So the same
contract runs over the fake, the fake pinned at a snapshot, `GitSpecStore` over
a working copy, and `GitSpecStore` pinned at a committed revision. A pinned read
that answered anything different from a tree read of the same content would fail
here rather than in production.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from contract import implementation_fixture
from spec_store_contract import (
    CORPUS,
    MECH_SCOUT,
    MULE,
    PROJECT,
    WITH_UNKNOWN_FIELD,
    SpecStoreContract,
)

from cybercanon.adapters.outbound.git.discovery import GIT_DIR, PROJECT_CONFIG
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.testing.spec_store import InMemorySpecStore

MECH_SCOUT_YAML = """\
# The scout mech. Comments here survive a round trip (D4).
schema_version: 1
id: mech_scout
name: "Scout Mech"
status: modeling
design:
  sockets:
    - name: SOCKET_muzzle_l
      purpose: muzzle flash
constraints:
  tri_budget: 12000
  naming: "SM_{asset}_LOD{n}"
"""

MULE_YAML = """\
schema_version: 1
id: mule
name: Mule Hauler
status: concept
"""

CRATE_YAML = """\
schema_version: 1
id: crate
name: Supply Crate
constraints:
  shinyness: 3
"""

PROJECT_YAML = """\
schema_version: 1
name: Ironwood
defaults:
  up_axis: Z
  unit_scale: 1.0
  animation:
    frame_rate: 30
    clip_naming: "A_{asset}_{state}"
golden_rules:
  - The silhouette reads at 25 m.
"""

FILES = {
    MECH_SCOUT.path: MECH_SCOUT_YAML,
    MULE.path: MULE_YAML,
    WITH_UNKNOWN_FIELD.path: CRATE_YAML,
    PROJECT_CONFIG: PROJECT_YAML,
}


def in_memory(directory: Path) -> InMemorySpecStore:
    """The fake, holding exactly the corpus the contract asks about."""
    store = InMemorySpecStore()
    for fixture in CORPUS:
        store.add(fixture.path, fixture.asset, warnings=fixture.warnings)
    store.set_project(PROJECT)
    return store


def git(directory: Path) -> GitSpecStore:
    """The real adapter, over a working copy holding that same corpus."""
    (directory / GIT_DIR).mkdir(parents=True, exist_ok=True)
    for path, content in FILES.items():
        written = directory / path
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(content, encoding="utf-8")
    return GitSpecStore(directory)


PINNED = "corpus"
"""The snapshot name the fake pins to; the real store pins to a commit."""


def in_memory_pinned(directory: Path) -> InMemorySpecStore:
    """The fake, pinned at a snapshot of that same corpus (D3)."""
    store = in_memory(directory)
    store.snapshot(PINNED)
    return store.pinned(PINNED)


def _git(root: Path, *arguments: str) -> None:
    """One git command in a throwaway repository, isolated from this machine."""
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


def git_pinned(directory: Path) -> GitSpecStore:
    """The real adapter reading the same corpus out of the object database.

    The corpus is committed and then *changed on disk* before the store is
    pinned, so a pinned read that quietly fell back to the checkout would answer
    the edited budget and fail the contract. That is the whole point of running
    this fourth implementation: the two read paths have to be the same answer.
    """
    root = directory / "pinned"
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for path, content in FILES.items():
        written = root / path
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(content, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the corpus")
    store = GitSpecStore(root)
    pinned = store.pinned("HEAD")
    (root / MECH_SCOUT.path).write_text(MECH_SCOUT_YAML.replace("12000", "999"), encoding="utf-8")
    return pinned


implementation = implementation_fixture(
    fake=in_memory, fake_pinned=in_memory_pinned, real=git, real_pinned=git_pinned
)


class TestSpecStore(SpecStoreContract):
    """The contract, against the fake and `GitSpecStore`, each read both ways (D3)."""
