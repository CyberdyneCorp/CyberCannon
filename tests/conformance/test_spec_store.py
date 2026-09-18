"""Task 4.1 and 5.1 — the `SpecStore` contract against every implementation.

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
"""

from __future__ import annotations

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


implementation = implementation_fixture(fake=in_memory, real=git)


class TestSpecStore(SpecStoreContract):
    """The `SpecStore` contract, against the in-memory fake and `GitSpecStore`."""
