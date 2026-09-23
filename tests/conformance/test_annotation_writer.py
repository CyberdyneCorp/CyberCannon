"""Tasks 2.2 and 3.3 — the `AnnotationWriter` contract against every implementation.

Two implementations now, which is what the port was for: D1 says the tool must
behave identically *"whether the person is working locally or through the hosted
surface"*, and the only way that survives two deployments is for both
destinations to answer one contract. The fake is what every unit test and BDD
step writes through; `GitAnnotationWriter` is what an agent on a developer's
machine actually writes through, over a real `asset.yaml` on disk.

The specification below is written by hand, with a comment and a blank line in
it, for the reason the `SpecStore` suite writes its corpus by hand: a file
generated from the domain objects would let a reader bug and a writer bug cancel
out, and this is the file an artist would commit. The byte-for-byte assertion
about everything *outside* the annotations block lives in
`tests/integration/test_annotation_write_back.py`, where a real repository makes
it meaningful; here the contract asks the smaller question both implementations
must answer the same way.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from annotation_writer_contract import ASSET, AnnotationWriterContract
from contract import implementation_fixture

from cybercanon.adapters.outbound.git.annotation_writer import GitAnnotationWriter
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.testing.annotation_writer import InMemoryAnnotationWriter

SPEC_PATH = "characters/mech_scout/asset.yaml"

MECH_SCOUT_YAML = """\
# The scout mech. Every line outside the annotations block survives a write.
schema_version: 1
id: mech_scout
name: "Scout Mech"
status: modeling

constraints:
  tri_budget: 12000
"""


def in_memory(directory: Path) -> InMemoryAnnotationWriter:
    writer = InMemoryAnnotationWriter()
    writer.declare(ASSET, SPEC_PATH)
    return writer


def git(directory: Path) -> GitAnnotationWriter:
    """The real writer, over a working copy holding that one specification.

    A real `git init`, not a `.git` directory conjured to satisfy discovery.
    The writer asks git whether the file it is about to touch is mid-merge, and
    since that check **fails closed** — a git that cannot answer refuses the
    write — a directory only shaped like a repository would have this suite
    asserting the contract against a question nothing can answer.
    """
    subprocess.run(
        ["git", "-C", str(directory), "init", "-q"],
        check=True,
        capture_output=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(directory),
            "GIT_CONFIG_NOSYSTEM": "1",
        },
    )
    spec = directory / SPEC_PATH
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(MECH_SCOUT_YAML, encoding="utf-8")
    return GitAnnotationWriter(GitSpecStore(directory), root=directory)


implementation = implementation_fixture(fake=in_memory, real=git)


class TestAnnotationWriter(AnnotationWriterContract):
    """The `AnnotationWriter` contract, against every implementation there is."""
