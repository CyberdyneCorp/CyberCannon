"""The fetch-triggered validation worker — G1's half of the gate decision.

G1: *"A worker in the API deployment runs the existing `validate_export` use
case when the working copy fetches a changed export. The preview is emitted by
that same run and mirrored to blob storage keyed by the export's content hash."*

Everything this module does follows from three sentences of that decision, and
each one is a property a test in `tests/unit/test_use_case_validation_worker.py`
asserts rather than a paragraph anybody has to believe:

* **Same use case as the CLI and MCP.** :func:`validate_changed_exports` calls
  :func:`~cybercanon.application.use_cases.validate_export.validate_export` —
  the object, imported, not a copy of its steps — and *"no third
  implementation: that rule does not bend for a worker"*. There is no rule here,
  no threshold, no severity and no branch on what a specification says; the
  verdict this worker records for an export is the verdict `canon validate`
  prints for it, because it is the same function's answer.
* **Not in the request path.** Nothing here is called by a router. Mesh loading
  is unbounded work, so the composition root enqueues a project name and this
  runs on a worker thread — *"an HTTP handler that waits on it is a timeout with
  extra steps"*.
* **The preview comes from that same run.** `validate_export` emits it from the
  handle its single read produced (D7, `MeshInspector.inspect`), so the export
  is read once and the preview costs nothing extra. The worker hands down the
  export's digest so the stored preview is keyed by it, which is what makes the
  mirror idempotent after a total loss.

What the worker *does* own is the two questions the domain answers for it:
whether a run is worth doing (:func:`~cybercanon.domain.validation_outcome.needs_validation`)
and whether its outcome is worth a commit
(:func:`~cybercanon.domain.validation_outcome.needs_commit`). Both live in the
domain, so this module is orchestration and nothing else.

**Attribution** is G2's: the reporting actor, or automation when there is no
person. A fetch has no live caller, so the ordinary case is a commit authored by
:data:`~cybercanon.domain.validation_outcome.AUTOMATION_AUTHOR_NAME` — which is
not the shared-identity fallback D8 refuses, because D8 is about a *person*
whose work would otherwise be attributed to somebody else and there is no person
here to misattribute.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.mesh_inspector import MeshInspector
from cybercanon.application.ports.preview import StoredPreview
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.search_index import SearchIndex
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.hosted_repository import Edit, edit_message, write_back
from cybercanon.application.use_cases.validate_export import ValidationOutcome, validate_export
from cybercanon.application.use_cases.validation_records import (
    digest_at,
    path_for,
    recorded_validation,
    to_document,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.revisions import ContentHash, Revision
from cybercanon.domain.validation_outcome import (
    AUTOMATION,
    AUTOMATION_AUTHOR_EMAIL,
    AUTOMATION_AUTHOR_NAME,
    ValidationRecord,
    needs_commit,
    needs_validation,
)

AUTOMATION_AUTHOR = GitAuthor(name=AUTOMATION_AUTHOR_NAME, email=AUTOMATION_AUTHOR_EMAIL)
"""Who a personless validation commit is authored by (G2)."""

EXPORT_SUFFIXES: tuple[str, ...] = tuple(f".{fmt.value.lower()}" for fmt in MeshFormat)
"""Which tracked files are candidate exports — the format matrix, and nothing else.

Derived from :class:`~cybercanon.domain.mesh_facts.MeshFormat` rather than
listed, so a format added to the matrix is picked up by the worker in the same
commit and a format removed from it stops being scanned. A file whose extension
is on this list and which is not a mesh is refused by the inspector, by name,
and lands in :attr:`WorkerReport.failed` — never in a passing outcome.
"""


@dataclass(frozen=True)
class RecordedOutcome:
    """One export the worker looked at, and what became of it."""

    record: ValidationRecord
    spec_path: str
    committed: bool = False
    revision: str = ""
    preview: StoredPreview | None = None

    @property
    def export(self) -> str:
        return self.record.export

    @property
    def asset_id(self) -> str:
        return self.record.asset_id


@dataclass(frozen=True)
class SkippedExport:
    """An export the worker did not run, and why. Reported, never silent."""

    export: str
    reason: str

    def __str__(self) -> str:
        return f"{self.export}: {self.reason}"


@dataclass(frozen=True)
class WorkerReport:
    """One pass of the worker over one project at one revision.

    `unchanged` and `failed` travel beside `outcomes` for the same reason a
    rebuild names the files it could not read: a pass that quietly did nothing
    and a pass that had nothing to do are different, and an operator watching a
    fetch that never produces an outcome needs to be told which.
    """

    project: str
    revision: Revision
    outcomes: tuple[RecordedOutcome, ...] = ()
    unchanged: tuple[str, ...] = ()
    failed: tuple[SkippedExport, ...] = ()

    @property
    def committed(self) -> tuple[str, ...]:
        """The exports whose outcome changed enough to be written back (G2)."""
        return tuple(outcome.export for outcome in self.outcomes if outcome.committed)

    @property
    def validated(self) -> tuple[str, ...]:
        """Every export this pass actually ran the use case over."""
        return tuple(outcome.export for outcome in self.outcomes)

    @property
    def wrote_nothing(self) -> bool:
        return not self.committed


def exports_at(
    project: str,
    revision: Revision,
    *,
    repository_host: RepositoryHost,
) -> tuple[str, ...]:
    """Every tracked file at that revision whose extension the matrix covers.

    A tree listing rather than a walk of the checkout, exactly as a request
    listing is, so the set of candidate exports is pinned to the revision being
    served and a fetch landing mid-pass cannot add one (D3).
    """
    return tuple(
        path
        for path in repository_host.paths_at(project, revision)
        if path.lower().endswith(EXPORT_SUFFIXES)
    )


@as_result
def validate_changed_exports(
    project: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    mesh_inspector: MeshInspector,
    blob_store: BlobStore | None = None,
    search_index: SearchIndex | None = None,
    author: GitAuthor = AUTOMATION_AUTHOR,
    attributed_to: str = AUTOMATION,
    agent: str = "",
    clock: Clock = system_clock,
) -> WorkerReport:
    """Validate every export this project's working copy has that has moved.

    The pass is pinned to one revision (D3) and is otherwise a loop over
    :func:`_looked_at`. It is a use case rather than a script because it must be
    runnable with no HTTP, no thread and no scheduler — which is how the whole
    of G1 is exercised in the unit layer, and why the background runner in the
    composition root has nothing in it but a queue.
    """
    revision = repository_host.head(project)
    pinned = spec_store.pinned(revision.value)
    outcomes: list[RecordedOutcome] = []
    unchanged: list[str] = []
    failed: list[SkippedExport] = []
    for export in exports_at(project, revision, repository_host=repository_host):
        _looked_at(
            export,
            _Pass(
                project=project,
                revision=revision,
                repository_host=repository_host,
                spec_store=pinned,
                mesh_inspector=mesh_inspector,
                blob_store=blob_store,
                search_index=search_index,
                author=author,
                attributed_to=attributed_to,
                agent=agent,
                clock=clock,
            ),
            outcomes,
            unchanged,
            failed,
        )
    return WorkerReport(
        project=project,
        revision=revision,
        outcomes=tuple(outcomes),
        unchanged=tuple(unchanged),
        failed=tuple(failed),
    )


@dataclass(frozen=True)
class _Pass:
    """Everything one pass carries, so the per-export functions take two arguments.

    A value object rather than eleven parameters threaded through four
    functions: the alternative reads as a signature nobody checks, and the
    cognitive-complexity target is a target for the reader, not for a counter.
    """

    project: str
    revision: Revision
    repository_host: RepositoryHost
    spec_store: SpecStore
    mesh_inspector: MeshInspector
    blob_store: BlobStore | None
    search_index: SearchIndex | None
    author: GitAuthor
    attributed_to: str
    agent: str
    clock: Clock


def _looked_at(
    export: str,
    run: _Pass,
    outcomes: list[RecordedOutcome],
    unchanged: list[str],
    failed: list[SkippedExport],
) -> None:
    """One export: skip it, run it, or record why it could not be run."""
    try:
        recorded = _considered(export, run)
    except OperationFailed as failure:
        failed.append(SkippedExport(export=export, reason=failure.message))
        return
    if recorded is None:
        unchanged.append(export)
        return
    outcomes.append(recorded)


def _considered(export: str, run: _Pass) -> RecordedOutcome | None:
    """The outcome for this export, or ``None`` when nothing needed doing.

    The digests are taken before the mesh is touched, which is the whole of G1's
    *"when the working copy fetches a **changed** export"*: an export whose bytes
    and whose governing specification are the ones the recorded outcome was
    taken of costs two reads of small files and no mesh load at all.
    """
    spec_path = run.spec_store.discover(export)
    if spec_path is None:
        return None
    digest = digest_at(
        run.project, export, repository_host=run.repository_host, revision=run.revision
    )
    spec_digest = digest_at(
        run.project, spec_path, repository_host=run.repository_host, revision=run.revision
    )
    if digest is None:
        return None
    recorded = recorded_validation(
        run.project, spec_path, repository_host=run.repository_host, revision=run.revision
    )
    if not needs_validation(
        recorded, export=export, export_hash=digest.value, spec_hash=_value(spec_digest)
    ):
        return None
    return _validated(export, spec_path, digest, _value(spec_digest), recorded, run)


def _value(digest: ContentHash | None) -> str:
    return digest.value if digest is not None else ""


def _validated(
    export: str,
    spec_path: str,
    digest: ContentHash,
    spec_hash: str,
    recorded: ValidationRecord | None,
    run: _Pass,
) -> RecordedOutcome:
    """Run the one validation, then commit its outcome only if it moved (G1, G2)."""
    outcome = validate_export.raising(
        export,
        spec_store=run.spec_store,
        mesh_inspector=run.mesh_inspector,
        blob_store=run.blob_store,
        emit_preview=run.blob_store is not None,
        source_digest=digest,
    )
    record = _record_of(outcome, export, digest, spec_hash, run)
    written = RecordedOutcome(record=record, spec_path=spec_path, preview=outcome.preview)
    if not needs_commit(recorded, record):
        return written
    return _committed(written, recorded, run)


def _record_of(
    outcome: ValidationOutcome,
    export: str,
    digest: ContentHash,
    spec_hash: str,
    run: _Pass,
) -> ValidationRecord:
    """The run, as the file beside the asset states it. Nothing is decided here."""
    report = outcome.report
    return ValidationRecord(
        asset_id=outcome.asset_id,
        export=export,
        export_hash=digest.value,
        passed=outcome.passed,
        validated_at=run.clock(),
        spec_hash=spec_hash,
        attributed_to=run.attributed_to,
        performed_by=run.agent,
        errors=len(report.errors),
        warnings=len(report.warnings),
    )


def _committed(
    written: RecordedOutcome, recorded: ValidationRecord | None, run: _Pass
) -> RecordedOutcome:
    """One outcome, written back as one commit naming the export it concerns."""
    path = path_for(written.spec_path)
    based_on = digest_at(
        run.project, path, repository_host=run.repository_host, revision=run.revision
    )
    outcome = write_back.raising(
        run.project,
        [Edit(path=path, content=to_document(written.record), based_on=based_on)],
        repository_host=run.repository_host,
        author=run.author,
        message=_message(written.record),
        subject=run.attributed_to,
        agent=run.agent,
    )
    _index(written.record, run)
    return replace(written, committed=True, revision=outcome.revision.value)


def _message(record: ValidationRecord) -> str:
    """*"Its commit message SHALL name the asset and describe what changed."*

    It names the export as well, because `where_is` answers *which export was
    validated* and a history that did not say would make the file the only place
    that knows.
    """
    return edit_message(record.asset_id, f"validation of {record.export} {record.verdict}")


def _index(record: ValidationRecord, run: _Pass) -> None:
    """Carry the answer into the index too, so `where_is` need not wait for a rebuild.

    Never *instead of* the commit — the commit has already landed by the time
    this runs, and a failure here loses a row a rebuild reproduces from the file
    that is now in the repository. That ordering is the whole of *"no write
    reaches only the index"*.
    """
    if run.search_index is None:
        return
    entry = run.search_index.get(record.asset_id)
    if entry is None:
        return
    run.search_index.upsert(
        replace(
            entry,
            validated_export=record.export,
            validated_at=record.validated_at.isoformat(),
        )
    )


__all__ = [
    "AUTOMATION_AUTHOR",
    "EXPORT_SUFFIXES",
    "RecordedOutcome",
    "SkippedExport",
    "WorkerReport",
    "exports_at",
    "validate_changed_exports",
]
