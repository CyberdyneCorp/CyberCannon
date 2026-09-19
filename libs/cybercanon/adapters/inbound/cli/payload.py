"""The machine-readable result — the same report, as data.

`canon-cli` requires a mode whose standard output carries *only* the structured
result, and `asset-validation` requires that the structured rendering and the
prose agree: the same violations, the same severities, the same overall outcome
and the same not-evaluated rules with their reasons. Both renderings are built
from one report, here and in
:mod:`cybercanon.adapters.inbound.cli.rendering`, so agreement is a property of
the input rather than a discipline two functions have to keep.

Three fields are distinct at the top of every validation result because a
consumer needs them apart: `violations`, `not_evaluated` and `export_format`.
Folding the second into the first would tell a script that a rule failed when it
never ran, and dropping it would hide exactly the suppression D13 exists to make
visible.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cybercanon.application.ports.search_index import RecordedMiss
from cybercanon.application.results import Refusal
from cybercanon.application.use_cases.compile_spec import CompiledSpec
from cybercanon.application.use_cases.index_assets import RebuildReport
from cybercanon.application.use_cases.lint_spec import LintFinding, LintReport
from cybercanon.application.use_cases.resolve_actor import UnmappedAuthors
from cybercanon.application.use_cases.sign_in import SignedIn, SignedOut, SignInStatus
from cybercanon.application.use_cases.validate_export import ValidationOutcome
from cybercanon.domain.report import NotEvaluated, Report
from cybercanon.domain.violations import SpecViolation, Violation

SCHEMA = "cybercanon.cli/v1"
"""The shape of this document, so a consumer can refuse one it does not know."""


def validation_payload(outcomes: Sequence[ValidationOutcome]) -> dict[str, Any]:
    """Every export validated in one run."""
    return _document(
        "validate",
        passed=all(outcome.passed for outcome in outcomes),
        results=[_validation(outcome) for outcome in outcomes],
    )


def lint_payload(report: LintReport, project_notes: Sequence[SpecViolation] = ()) -> dict[str, Any]:
    """Structural findings over specification files, plus the project's own.

    A `.canon/project.yaml` that declares a severity level nobody has heard of
    is not a defect of any asset, so it travels beside the findings rather than
    among them — visible, and never able to fail somebody else's file.
    """
    return _document(
        "check",
        passed=report.passed,
        checked=list(report.checked),
        findings=[_finding(finding) for finding in report.findings],
        mapping=[_finding(finding) for finding in report.mapping],
        project_notes=[_spec_violation(note) for note in project_notes],
    )


def rebuild_payload(report: RebuildReport) -> dict[str, Any]:
    """What a rebuild indexed, and the files it named as unreadable."""
    return _document(
        "index rebuild",
        passed=report.is_complete,
        project=report.project,
        indexed=list(report.indexed),
        forgotten=list(report.forgotten),
        unreadable=[{"path": spec.path, "reason": spec.reason} for spec in report.unreadable],
    )


def misses_payload(misses: Sequence[RecordedMiss]) -> dict[str, Any]:
    """The locally recorded zero-result terms (D11) — never transmitted anywhere."""
    return _document(
        "index misses",
        passed=True,
        misses=[_miss(miss) for miss in misses],
    )


def unmapped_payload(unmapped: UnmappedAuthors) -> dict[str, Any]:
    """The addresses `.canon/actors.yaml` does not bind, and why it could not be read."""
    return _document(
        "actors unmapped",
        passed=not unmapped.violations,
        authors=list(unmapped.emails),
        findings=[_spec_violation(violation) for violation in unmapped.violations],
    )


def sign_in_payload(signed_in: SignedIn) -> dict[str, Any]:
    """A completed sign-in. It names where the credential went and never what it is."""
    return _document(
        "auth login",
        passed=True,
        approved_at=signed_in.verification_uri,
        stored_in=signed_in.stored_in,
    )


def sign_out_payload(signed_out: SignedOut) -> dict[str, Any]:
    """A sign-out, and whether there was anything to remove."""
    return _document(
        "auth logout",
        passed=True,
        removed=signed_out.removed,
        stored_in=signed_out.stored_in,
    )


def sign_in_status_payload(status: SignInStatus) -> dict[str, Any]:
    """Whether this machine holds a credential. Never the credential."""
    return _document(
        "auth status",
        passed=True,
        signed_in=status.signed_in,
        stored_in=status.stored_in,
    )


def changed_payload(
    specs: Sequence[str], outcomes: Sequence[ValidationOutcome], lint: LintReport
) -> dict[str, Any]:
    """The pre-commit run: which assets were touched, and what they produced."""
    passed = lint.passed and all(outcome.passed for outcome in outcomes)
    return _document(
        "changed",
        passed=passed,
        assets=list(specs),
        results=[_validation(outcome) for outcome in outcomes],
        findings=[_finding(finding) for finding in lint.findings],
    )


def nothing_changed_payload() -> dict[str, Any]:
    """No changed file belonged to an asset: the hook's ordinary case."""
    return _document("changed", passed=True, assets=[], results=[], findings=[])


def compile_payload(compiled: CompiledSpec, destination: str | None) -> dict[str, Any]:
    """A compiled briefing, and where it was written."""
    return _document(
        "compile",
        passed=True,
        asset=compiled.asset_id,
        source=compiled.source,
        written_to=destination,
        text=compiled.text,
    )


def failure_payload(command: str, refusal: Refusal) -> dict[str, Any]:
    """An operation that could not run, as data — never a report with no violations.

    `id` is the stable machine-readable identifier the outcome carries (D10), so
    a script reading this document branches on the same token an HTTP client
    would. `message` and `subject` keep the shape they have always had.
    """
    return _document(
        command,
        passed=False,
        ran=False,
        error={
            "id": refusal.identifier,
            "message": refusal.message,
            "subject": refusal.subject or None,
        },
    )


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------


def _miss(miss: RecordedMiss) -> dict[str, Any]:
    return {"term": miss.term, "project": miss.project, "count": miss.count}


def _document(command: str, *, passed: bool, ran: bool = True, **body: Any) -> dict[str, Any]:
    return {"schema": SCHEMA, "command": command, "ran": ran, "passed": passed, **body}


def _validation(outcome: ValidationOutcome) -> dict[str, Any]:
    report = outcome.report
    return {
        "asset": report.asset_id,
        "export": report.export,
        "export_format": str(report.export_format),
        "spec": outcome.spec_path,
        "passed": outcome.passed,
        "outcome": report.outcome,
        "violations": [_violation(violation) for violation in report.violations],
        "not_evaluated": [_not_evaluated(entry) for entry in report.not_evaluated],
        "passed_rules": list(report.passed_rules),
        "spec_warnings": [_spec_violation(warning) for warning in outcome.spec_warnings],
        "preview": _preview(outcome),
    }


def _violation(violation: Violation) -> dict[str, Any]:
    return {
        "rule_id": violation.rule_id,
        "severity": str(violation.severity),
        "subject": violation.subject,
        "observed": violation.observed,
        "expected": violation.expected,
        "message": violation.message,
    }


def _spec_violation(violation: SpecViolation) -> dict[str, Any]:
    return {
        "rule_id": violation.rule_id,
        "severity": str(violation.severity),
        "subject": violation.subject,
        "observed": violation.observed,
        "expected": violation.expected,
        "message": violation.message,
    }


def _not_evaluated(entry: NotEvaluated) -> dict[str, Any]:
    return {
        "rule_id": entry.rule_id,
        "missing_fact": entry.missing_fact.label,
        "reason": entry.reason,
    }


def _finding(finding: LintFinding) -> dict[str, Any]:
    return {"path": finding.path, **_spec_violation(finding.violation)}


def _preview(outcome: ValidationOutcome) -> dict[str, Any] | None:
    """Preview emission, reported apart from the verdict it cannot change (D7)."""
    if outcome.preview_failure is not None:
        return {"stored": False, "reason": outcome.preview_failure.reason}
    if outcome.preview is None:
        return None
    return {
        "stored": True,
        "key": outcome.preview.key,
        "size_bytes": outcome.preview.size_bytes,
        "source_export": outcome.preview.source_export,
    }


def report_payload(report: Report) -> dict[str, Any]:
    """One report on its own — what a surface with no use-case wrapper renders."""
    return {
        "asset": report.asset_id,
        "export": report.export,
        "export_format": str(report.export_format),
        "outcome": report.outcome,
        "passed": report.passed,
        "violations": [_violation(violation) for violation in report.violations],
        "not_evaluated": [_not_evaluated(entry) for entry in report.not_evaluated],
        "passed_rules": list(report.passed_rules),
    }


__all__ = [
    "SCHEMA",
    "changed_payload",
    "compile_payload",
    "failure_payload",
    "lint_payload",
    "nothing_changed_payload",
    "report_payload",
    "validation_payload",
]
