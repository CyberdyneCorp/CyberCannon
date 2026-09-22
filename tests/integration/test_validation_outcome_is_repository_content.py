"""Tasks 12.3, 12.4 and 12.7 against a real repository — G2 where it has to hold.

The unit suite runs the worker over the in-memory host, which models the states
a repository can be in. What it cannot show is the thing G2 actually claims: the
outcome is **repository content**, so it is on the configured branch of a real
remote, authored by a real git identity, visible to `git log`, and readable back
by `GitSpecStore` after the index has been thrown away.

So this suite stages a bare remote, clones it through `GitRepositoryHost`, runs
the worker, and then asks git — not the service — what happened.

The mesh is read through the in-memory inspector, because what is under test
here is the commit and not the extraction: `trimesh` against real exports is
`test_trimesh_inspector` and `test_format_coverage`, and a corpus carrying a
genuine multi-megabyte GLB would make this suite slow for no assertion it adds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from staged_project import BRANCH, PROJECT, SCOUT_EXPORT, SCOUT_SPEC, Staged, git, ready

from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.use_cases.hosted_repository import rebuild_project_index
from cybercanon.application.use_cases.lookup_assets import (
    VALIDATED_AT,
    VALIDATED_EXPORT,
    where_is,
)
from cybercanon.application.use_cases.validation_records import RECORD_NAME, from_document
from cybercanon.application.use_cases.validation_worker import (
    AUTOMATION_AUTHOR,
    validate_changed_exports,
)
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat

pytestmark = pytest.mark.integration

ASSET = "mech_scout"
RECORD = f"characters/mech_scout/{RECORD_NAME}"

NOON = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
WITHIN = 11840
OVER = 14310


def an_inspector(triangles: int = WITHIN) -> InMemoryMeshInspector:
    inspector = InMemoryMeshInspector()
    inspector.add(SCOUT_EXPORT, facts_for(MeshFormat.GLB, triangles=triangles))
    return inspector


def a_pass(staged: Staged, inspector: InMemoryMeshInspector, **extra: object):
    return ran(
        validate_changed_exports(
            PROJECT,
            repository_host=staged.host,
            spec_store=staged.spec_store(),
            mesh_inspector=inspector,
            clock=fixed_clock(NOON),
            **extra,  # type: ignore[arg-type]
        )
    )


def on_the_branch(staged: Staged, path: str) -> bytes:
    """What the configured branch of the *remote* holds at that path."""
    return git(
        None,
        ["--git-dir", str(staged.bare), "show", f"refs/heads/{BRANCH}:{path}"],
        staged.home,
    ).encode("utf-8")


def branch_log(staged: Staged, fields: str) -> list[str]:
    """`git log` over the remote's branch, newest first."""
    printed = git(
        None,
        ["--git-dir", str(staged.bare), "log", f"--format={fields}", BRANCH],
        staged.home,
    )
    return [line for line in printed.splitlines() if line]


# --------------------------------------------------------------------------
# 12.3 — committed to the configured branch, attributed, naming the export
# --------------------------------------------------------------------------


def test_the_outcome_lands_on_the_configured_branch_of_the_remote(tmp_path: Path) -> None:
    staged = ready(tmp_path)

    report = a_pass(staged, an_inspector())

    written = from_document(on_the_branch(staged, RECORD), RECORD)
    assert report.committed == (SCOUT_EXPORT,)
    assert written.asset_id == ASSET
    assert written.export == SCOUT_EXPORT
    assert written.validated_at == NOON


def test_the_commit_is_authored_by_automation_and_names_the_export(tmp_path: Path) -> None:
    """G2's attribution, asked of `git log` rather than of the service."""
    staged = ready(tmp_path)

    a_pass(staged, an_inspector())

    assert branch_log(staged, "%an <%ae>")[0] == str(AUTOMATION_AUTHOR)
    subject = branch_log(staged, "%s")[0]
    assert ASSET in subject
    assert SCOUT_EXPORT in subject


def test_the_outcome_sits_beside_the_specification_it_concerns(tmp_path: Path) -> None:
    staged = ready(tmp_path)

    a_pass(staged, an_inspector())

    assert (staged.working_copy / RECORD).is_file()
    assert Path(RECORD).parent == Path(SCOUT_SPEC).parent


# --------------------------------------------------------------------------
# 12.4 — a repeated run over an unchanged export writes nothing
# --------------------------------------------------------------------------


def test_a_second_pass_over_an_unchanged_export_adds_no_commit(tmp_path: Path) -> None:
    staged = ready(tmp_path)
    a_pass(staged, an_inspector())
    before = branch_log(staged, "%H")

    again = a_pass(staged, an_inspector())

    assert again.wrote_nothing
    assert branch_log(staged, "%H") == before


def test_a_re_exported_mesh_produces_exactly_one_further_commit(tmp_path: Path) -> None:
    staged = ready(tmp_path)
    a_pass(staged, an_inspector())
    first = from_document(on_the_branch(staged, RECORD), RECORD)
    before = len(branch_log(staged, "%H"))
    staged.commit_outside(SCOUT_EXPORT, b"glTF\x02\x00\x00\x00re-exported, and heavier")
    staged.host.fetch(PROJECT, confirmed_at=NOON)

    again = a_pass(staged, an_inspector(OVER))

    assert again.committed == (SCOUT_EXPORT,)
    assert from_document(on_the_branch(staged, RECORD), RECORD).export_hash != first.export_hash
    assert len(branch_log(staged, "%H")) == before + 2  # the outside commit, and ours


# --------------------------------------------------------------------------
# 12.7 — the answer survives the index being dropped and rebuilt
# --------------------------------------------------------------------------


def test_dropping_the_index_and_rebuilding_from_the_working_copy_keeps_the_answer(
    tmp_path: Path,
) -> None:
    staged = ready(tmp_path)
    index = InMemorySearchIndex()
    a_pass(staged, an_inspector(), search_index=index)
    ran(
        rebuild_project_index(
            PROJECT,
            repository_host=staged.host,
            spec_store=staged.spec_store(),
            search_index=index,
        )
    )
    before = ran(where_is(ASSET, spec_store=staged.spec_store(), search_index=index))

    dropped = InMemorySearchIndex()
    ran(
        rebuild_project_index(
            PROJECT,
            repository_host=staged.host,
            spec_store=staged.spec_store(),
            search_index=dropped,
        )
    )
    after = ran(where_is(ASSET, spec_store=staged.spec_store(), search_index=dropped))

    assert before.location(VALIDATED_EXPORT).value == SCOUT_EXPORT
    assert after.location(VALIDATED_EXPORT).value == SCOUT_EXPORT
    assert after.location(VALIDATED_AT).value == before.location(VALIDATED_AT).value
    assert after.locations == before.locations
