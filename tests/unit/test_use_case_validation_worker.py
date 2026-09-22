"""Group 12 — the fetch-triggered validation worker (G1, G2).

`add-mcp-read-server` shipped a reader for an asset's validated export and
validation date, and until this worker existed nothing in the product wrote
them: that half of `where_is` — the tool answering the complaint the product
exists for — was always empty. These tests pin the five properties the gate
decisions make load-bearing:

* **it calls the same use case the CLI and the agent surface call** (12.1), and
  a worker that grew a rule of its own fails
  :func:`test_the_worker_has_no_opinion_of_its_own_about_a_verdict`, which
  replaces `validate_export` outright and asserts the worker records whatever it
  said;
* **the outcome is repository content** (12.3) — a file beside the asset, one
  commit, naming the export, attributed to automation when there is no person;
* **a repeated run over an unchanged export writes nothing** (12.4);
* **the preview comes from that same read** (12.5) — one inspection, and the
  stored preview keyed by the export's digest;
* **the index gains the answer without becoming the place it lives** — the row
  is updated after the commit has landed, never instead of it.

12.2 (outside the request path) is
`tests/unit/test_validation_is_not_in_the_request_path.py`, because it needs a
transport; 12.6 and 12.7 are
`tests/unit/test_validated_export_survives_a_rebuild.py`, because they are about
what a reader answers afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.results import as_result
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases import validate_export as validate_export_module
from cybercanon.application.use_cases import validation_worker
from cybercanon.application.use_cases.validate_export import ValidationOutcome, validate_export
from cybercanon.application.use_cases.validation_records import (
    RECORD_NAME,
    from_document,
    path_for,
)
from cybercanon.application.use_cases.validation_worker import (
    AUTOMATION_AUTHOR,
    validate_changed_exports,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFacts, MeshFormat
from cybercanon.domain.report import Report
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.validation_outcome import AUTOMATION
from cybercanon.domain.violations import Severity, Violation

PROJECT = "cyberdyne-game"
ASSET = "mech_scout"
SPEC = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
RECORD = f"characters/mech_scout/{RECORD_NAME}"

SPEC_BYTES = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\n"
MESH = b"glTF-ish bytes, and nothing here ever parses them"
CHANGED_MESH = b"glTF-ish bytes, re-exported"

BUDGET = 12000
WITHIN = 11840
OVER = 14310

NOON = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def an_asset() -> Asset:
    return Asset(
        id=AssetId(ASSET),
        name="Scout Mech",
        constraints=Constraints(tri_budget=BUDGET),
    )


def a_glb(triangles: int) -> MeshFacts:
    return facts_for(MeshFormat.GLB, triangles=triangles)


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    """A cloned project holding one specification and one export."""
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC: SPEC_BYTES, EXPORT: MESH})
    built.clone(PROJECT)
    return built


@pytest.fixture
def store(host: InMemoryRepositoryHost) -> InMemorySpecStore:
    built = InMemorySpecStore()
    built.add(SPEC, an_asset())
    built.snapshot(host.head(PROJECT).value)
    return built


def an_inspector(triangles: int = WITHIN) -> InMemoryMeshInspector:
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, a_glb(triangles))
    return inspector


def a_pass(
    host: InMemoryRepositoryHost,
    store: InMemorySpecStore,
    inspector: InMemoryMeshInspector,
    **extra: object,
):
    """One worker pass with the fakes wired, pinned to a fixed clock."""
    return ran(
        validate_changed_exports(
            PROJECT,
            repository_host=host,
            spec_store=store,
            mesh_inspector=inspector,
            clock=fixed_clock(NOON),
            **extra,  # type: ignore[arg-type]
        )
    )


def recorded(host: InMemoryRepositoryHost):
    """The outcome file the worker committed, parsed back out of the remote."""
    return from_document(host.remote_files(PROJECT)[RECORD], RECORD)


# --------------------------------------------------------------------------
# 12.1 — the same use case the CLI and the agent surface call
# --------------------------------------------------------------------------


def test_the_worker_calls_the_one_validate_export() -> None:
    """Not a copy of its steps, not a subclass: the imported object (G1)."""
    assert validation_worker.validate_export is validate_export
    assert validate_export_module.validate_export is validate_export


def test_the_worker_records_the_verdict_the_command_line_would_print(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """The cross-surface property, at the level a worker can break it."""
    inspector = an_inspector(OVER)
    directly = ran(
        validate_export(
            EXPORT,
            spec_store=store.pinned(host.head(PROJECT).value),
            mesh_inspector=inspector,
        )
    )

    report = a_pass(host, store, an_inspector(OVER))

    assert not directly.passed
    assert recorded(host).passed is directly.passed
    assert recorded(host).errors == len(directly.report.errors)
    assert report.validated == (EXPORT,)


def test_the_worker_has_no_opinion_of_its_own_about_a_verdict(
    host: InMemoryRepositoryHost,
    store: InMemorySpecStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace the use case, and the worker records exactly what it said.

    This is the test that fails the day somebody adds a threshold, a severity or
    a "but the budget is only slightly exceeded" to this module: the mesh below
    is comfortably within budget, and the stubbed use case fails it anyway.
    """

    invented = Violation(
        rule_id="invented.by.the.worker",
        severity=Severity.ERROR,
        subject=ASSET,
        message="a rule that exists in no rule registry",
    )

    @as_result
    def always_fails(export: str, **_: object) -> ValidationOutcome:
        return ValidationOutcome(
            report=Report(
                asset_id=ASSET,
                export_format=MeshFormat.GLB,
                export=export,
                violations=(invented,),
            ),
            spec_path=SPEC,
        )

    monkeypatch.setattr(validation_worker, "validate_export", always_fails)

    a_pass(host, store, an_inspector(WITHIN))

    assert recorded(host).passed is False
    assert recorded(host).errors == 1


# --------------------------------------------------------------------------
# 12.3 — the outcome is repository content, committed and attributed
# --------------------------------------------------------------------------


def test_the_outcome_is_written_beside_the_asset(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    report = a_pass(host, store, an_inspector())

    assert path_for(SPEC) == RECORD
    assert RECORD in host.remote_files(PROJECT)
    assert report.committed == (EXPORT,)


def test_the_commit_names_the_asset_and_the_export_it_concerns(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    a_pass(host, store, an_inspector())

    commit = host.commits(PROJECT)[-1]
    assert ASSET in commit.message
    assert EXPORT in commit.message
    assert commit.paths == (RECORD,)


def test_a_personless_run_is_attributed_to_automation(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """G2 — *"the reporting actor, or automation when there is no person"*."""
    a_pass(host, store, an_inspector())

    assert host.commits(PROJECT)[-1].author == AUTOMATION_AUTHOR
    assert recorded(host).attributed_to == AUTOMATION
    assert recorded(host).by_automation


def test_a_reporting_actor_is_recorded_when_there_is_one(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    a_pass(host, store, an_inspector(), attributed_to="rafa")

    assert recorded(host).attributed_to == "rafa"
    assert not recorded(host).by_automation


def test_the_outcome_names_the_export_and_when_it_was_validated(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    a_pass(host, store, an_inspector())

    written = recorded(host)
    assert written.export == EXPORT
    assert written.validated_at == NOON
    assert written.export_hash == ContentHash.of(MESH).value


# --------------------------------------------------------------------------
# 12.4 — commit only when the verdict or the export hash changes
# --------------------------------------------------------------------------


def test_a_repeated_run_over_an_unchanged_export_writes_nothing(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    first = a_pass(host, store, an_inspector())
    store.snapshot(host.head(PROJECT).value)
    commits = len(host.commits(PROJECT))

    again = a_pass(host, store, an_inspector())

    assert first.committed == (EXPORT,)
    assert again.wrote_nothing
    assert again.unchanged == (EXPORT,)
    assert len(host.commits(PROJECT)) == commits


def test_an_unchanged_export_is_not_even_re_read(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """G1 runs *when the working copy fetches a changed export*, and only then."""
    a_pass(host, store, an_inspector())
    store.snapshot(host.head(PROJECT).value)
    second = an_inspector()

    a_pass(host, store, second)

    assert second.inspected == []


def test_a_re_exported_mesh_is_validated_again_and_committed(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    a_pass(host, store, an_inspector())
    host.push_to_remote(PROJECT, EXPORT, CHANGED_MESH)
    ran_fetch = host.fetch(PROJECT, confirmed_at=NOON)
    store.snapshot(ran_fetch.revision.value)
    changed = InMemoryMeshInspector()
    changed.add(EXPORT, a_glb(OVER))

    again = a_pass(host, store, changed)

    assert again.committed == (EXPORT,)
    assert recorded(host).passed is False
    assert recorded(host).export_hash == ContentHash.of(CHANGED_MESH).value


def test_a_changed_specification_re_validates_the_same_export(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """A tightened budget must bite without anybody re-exporting the mesh."""
    a_pass(host, store, an_inspector())
    host.push_to_remote(PROJECT, SPEC, SPEC_BYTES + b"tri_budget: 10000\n")
    served = host.fetch(PROJECT, confirmed_at=NOON)
    tightened = InMemorySpecStore()
    tightened.add(
        SPEC,
        Asset(id=AssetId(ASSET), name="Scout Mech", constraints=Constraints(tri_budget=10000)),
    )
    tightened.snapshot(served.revision.value)

    again = a_pass(host, tightened, an_inspector())

    assert again.committed == (EXPORT,)
    assert recorded(host).passed is False


# --------------------------------------------------------------------------
# 12.5 — the preview comes from that same read
# --------------------------------------------------------------------------


def test_the_export_is_read_once_and_the_preview_comes_from_that_read(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    inspector = an_inspector()
    blobs = InMemoryBlobStore()

    report = a_pass(host, store, inspector, blob_store=blobs)

    assert inspector.inspected == [EXPORT]
    assert len(inspector.previewed) == 1
    assert report.outcomes[0].preview is not None


def test_the_preview_is_keyed_by_the_export_content_hash(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """G1 — *"mirrored to blob storage keyed by the export's content hash"*."""
    blobs = InMemoryBlobStore()

    report = a_pass(host, store, an_inspector(), blob_store=blobs)

    preview = report.outcomes[0].preview
    assert preview is not None
    assert ContentHash.of(MESH).value in preview.key
    assert blobs.read(preview.key) is not None


def test_a_preview_failure_does_not_change_the_recorded_verdict(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """D7, one layer up: the mirror is down and the outcome is still recorded."""
    inspector = an_inspector()
    inspector.fail_preview(EXPORT)

    a_pass(host, store, inspector, blob_store=InMemoryBlobStore())

    assert recorded(host).passed is True


# --------------------------------------------------------------------------
# The index gains the answer — after the commit, never instead of it
# --------------------------------------------------------------------------


def test_the_index_row_gains_the_validated_export_after_the_commit(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    index = InMemorySearchIndex()
    from cybercanon.application.use_cases.index_assets import entry_for

    index.upsert(entry_for(store.load(SPEC)))

    a_pass(host, store, an_inspector(), search_index=index)

    entry = index.get(ASSET)
    assert entry is not None
    assert entry.validated_export == EXPORT
    assert entry.validated_at == NOON.isoformat()
    assert RECORD in host.remote_files(PROJECT)


# --------------------------------------------------------------------------
# What the worker will not do
# --------------------------------------------------------------------------


def test_an_export_governed_by_no_specification_is_skipped() -> None:
    orphan = "sandbox/scratch.glb"
    host = InMemoryRepositoryHost()
    host.add_project(PROJECT, {orphan: MESH})
    host.clone(PROJECT)
    store = InMemorySpecStore()
    store.snapshot(host.head(PROJECT).value)
    inspector = InMemoryMeshInspector()
    inspector.add(orphan, a_glb(WITHIN))

    report = a_pass(host, store, inspector)

    assert report.validated == ()
    assert report.unchanged == (orphan,)
    assert host.commits(PROJECT) == ()


def test_an_unreadable_export_is_reported_and_nothing_is_committed(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    inspector = InMemoryMeshInspector()
    inspector.add_unreadable(EXPORT, "the file is truncated")

    report = a_pass(host, store, inspector)

    assert report.validated == ()
    assert [failed.export for failed in report.failed] == [EXPORT]
    assert host.commits(PROJECT) == ()


def test_only_files_the_format_matrix_covers_are_candidates(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """A README beside an export is not an export, and is never inspected."""
    host.push_to_remote(PROJECT, "characters/mech_scout/exports/README.md", b"# exports")
    served = host.fetch(PROJECT, confirmed_at=NOON)
    store.snapshot(served.revision.value)
    inspector = an_inspector()

    report = a_pass(host, store, inspector)

    assert report.validated == (EXPORT,)
    assert inspector.inspected == [EXPORT]
