"""`validate_export` — the one validation, reachable from every surface.

The pre-commit hook the artist runs, the `validate_export` tool the Blender
agent calls and the "Validate" button in the web app are **this function**.
Anything else produces "it passed on my machine but the site says it failed",
which is precisely the trust-destroying bug this product exists to prevent, so
no rule logic is permitted in an adapter.

The run is five steps and every one of them is somebody else's code:

1. **discover** the governing specification by walking upward (`SpecStore`, D9);
2. **merge** project defaults with the asset's constraints into one
   `EffectiveSpec` (domain, D3) — rules never see the merge;
3. **extract** facts, once, through `MeshInspector` (D1);
4. **decide**, purely, in the domain rule registry (D2, D13);
5. **optionally emit a preview** from that same read, guarded (D7).

Two properties are load-bearing and are asserted in
`tests/unit/test_use_case_validate_export.py`:

* **The verdict depends only on the facts and the effective spec.** Identical
  facts from different formats produce identical violations.
* **Preview emission cannot change the verdict.** Step 5 is wrapped so that any
  failure — an emitter that would drop clips, a blob store that is down, a Draco
  binary that never installed — is reported as its own condition and the report
  is returned untouched.

No identity, no network, no token: nothing here calls anything but the spec
store and the inspector, and the layering contract (D10) makes that structural
rather than a promise.
"""

from __future__ import annotations

from dataclasses import dataclass

from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.mesh_inspector import (
    InspectedMesh,
    MeshInspector,
    UnsupportedExport,
)
from cybercanon.application.ports.preview import StoredPreview
from cybercanon.application.ports.spec_store import (
    LoadedSpec,
    ProjectConfig,
    SpecNotFound,
    SpecStore,
)
from cybercanon.domain.effective_spec import EffectiveSpec, merge
from cybercanon.domain.format_matrix import UnsupportedExportFormat, available_for
from cybercanon.domain.mesh_facts import MeshFacts
from cybercanon.domain.report import Report
from cybercanon.domain.rules import run, with_severities
from cybercanon.domain.violations import SpecViolation


@dataclass(frozen=True)
class PreviewFailure:
    """A preview that was not produced, and why. Never part of the verdict (D7)."""

    export: str
    reason: str


@dataclass(frozen=True)
class ValidationOutcome:
    """Everything one validation run produced, with the verdict kept apart.

    `report` is the verdict and nothing else touches it: `spec_warnings` (an
    unrecognised field, D5) and `preview_failure` are separate conditions,
    reported alongside, never folded in.
    """

    report: Report
    spec_path: str
    spec_warnings: tuple[SpecViolation, ...] = ()
    preview: StoredPreview | None = None
    preview_failure: PreviewFailure | None = None

    @property
    def passed(self) -> bool:
        """The verdict: failing if and only if an `error`-severity violation exists."""
        return self.report.passed

    @property
    def asset_id(self) -> str:
        return self.report.asset_id


def validate_export(
    export: str,
    *,
    spec_store: SpecStore,
    mesh_inspector: MeshInspector,
    blob_store: BlobStore | None = None,
    emit_preview: bool = False,
) -> ValidationOutcome:
    """Validate one export against its governing specification.

    Raises :class:`~cybercanon.application.errors.OperationFailed` — and only
    that — when the run could not happen at all: no governing specification, an
    unreadable export, or a format the matrix does not cover. A caller therefore
    never has to distinguish "clean" from "could not tell", which is the whole
    reason the CLI can have one exit-code seam (D11).
    """
    loaded, project = _governing_spec(export, spec_store)
    spec = merge(loaded.asset, project.defaults)
    inspected = mesh_inspector.inspect(export)
    facts = _supported(export, inspected.facts)
    report = run(spec, facts, export=export, rules=with_severities(project.severities))
    preview, failure = _preview(
        export, spec, inspected, mesh_inspector, blob_store if emit_preview else None
    )
    return ValidationOutcome(
        report=report,
        spec_path=loaded.path,
        spec_warnings=loaded.warnings,
        preview=preview,
        preview_failure=failure,
    )


def _governing_spec(export: str, spec_store: SpecStore) -> tuple[LoadedSpec, ProjectConfig]:
    """Step 1 and the defaults for step 2 — the only path arithmetic in the run (D9)."""
    spec_path = spec_store.discover(export)
    if spec_path is None:
        raise SpecNotFound(export)
    return spec_store.load(spec_path), spec_store.load_project(spec_path)


def _supported(export: str, facts: MeshFacts) -> MeshFacts:
    """Refuse a format the matrix does not cover, by name, before any rule runs.

    The inspector is expected to refuse it first; this is the use case's own
    guard, so an adapter that forgot cannot turn an unknown format into a
    passing report full of assumed facts (D13).
    """
    try:
        available_for(facts.source_format)
    except UnsupportedExportFormat as error:
        raise UnsupportedExport(export, str(facts.source_format)) from error
    return facts


def _preview(
    export: str,
    spec: EffectiveSpec,
    inspected: InspectedMesh,
    mesh_inspector: MeshInspector,
    blob_store: BlobStore | None,
) -> tuple[StoredPreview | None, PreviewFailure | None]:
    """Step 5, guarded (D7).

    The broad `except` is the decision, not laziness: *any* failure below this
    line — emitter, compressor, blob store, a port raising something nobody
    anticipated — is a preview failure and never a validation failure. The
    verdict has already been computed and is not in scope here.
    """
    if blob_store is None:
        return None, None
    try:
        preview = mesh_inspector.emit_preview(inspected)
        return blob_store.put_preview(spec.asset_id, export, preview), None
    except Exception as error:  # D7: any preview failure, and only the preview fails
        return None, PreviewFailure(export=export, reason=_reason(error))


def _reason(error: Exception) -> str:
    return str(error) or type(error).__name__


__all__ = [
    "PreviewFailure",
    "ValidationOutcome",
    "validate_export",
]
