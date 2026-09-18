"""Human-readable output — prose over a report, and nothing else.

Two requirements shape every line here, and both are about a person reading a
terminal at the moment a commit was blocked:

* **A violation states the fix** (`canon-cli`). Each line names the **asset**,
  the **subject** at fault, the **observed** value and the **expected** value,
  so the reader acts without opening `asset.yaml`. The rule's own message
  follows underneath, already phrased in those terms by the domain.
* **Not-evaluated rules are printed in full, never as a count** (D13). A wrong
  matrix row suppresses a real rule, and this listing is the only place that
  suppression is ever visible. Collapsing it into "5 rules skipped" is how a
  validator starts lying about its coverage.

Nothing in this module decides anything. It receives a report the domain
produced and turns it into text; the severities, the verdict and the reasons
were all settled before it was called.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from cybercanon.application.errors import OperationFailed
from cybercanon.application.use_cases.lint_spec import LintFinding, LintReport
from cybercanon.application.use_cases.validate_export import ValidationOutcome
from cybercanon.domain.report import NotEvaluated, Report
from cybercanon.domain.violations import SpecViolation, Violation

INDENT = "  "
NOT_EVALUATED_NOTE = "the export's format does not record the fact each rule reads"
NO_VIOLATIONS = "no violations"
NO_FINDINGS = "no findings"


def render_validations(outcomes: Sequence[ValidationOutcome]) -> str:
    """Every export validated in one run, then the verdict for the run as a whole."""
    blocks = [render_validation(outcome) for outcome in outcomes]
    return "\n\n".join((*blocks, _verdict(all(outcome.passed for outcome in outcomes))))


def render_validation(outcome: ValidationOutcome) -> str:
    """One export: where it came from, what failed, and what was never checked."""
    report = outcome.report
    return "\n".join(
        (
            _header(report, outcome.spec_path),
            *_violations(report),
            *_not_evaluated(report),
            *_spec_warnings(outcome.spec_warnings),
            *_preview(outcome),
            f"{INDENT}{len(report.passed_rules)} rules passed",
        )
    )


def render_lint(report: LintReport) -> str:
    """Structural findings, grouped by the file they are in."""
    blocks = [_lint_file(report, path) for path in report.checked]
    checked = _plural(len(report.checked), "specification file")
    summary = f"{checked} checked, {_count(report.findings)}"
    return "\n\n".join((*blocks, summary, _verdict(report.passed)))


def render_project_notes(notes: Sequence[SpecViolation]) -> str:
    """What the project configuration itself got wrong — beside the findings, never among them."""
    return "\n".join((".canon/project.yaml", *(_spec_warning(note) for note in notes)))


def render_failure(error: OperationFailed) -> str:
    """An operation that could not run — never a verdict, never a passing report."""
    return f"canon: {error.message}"


def render_compiled(source: str, destination: str | None) -> str:
    """Where a compiled briefing went, for the person who asked for it."""
    if destination is None:
        return f"canon: compiled {source}"
    return f"canon: compiled {source} -> {destination}"


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def _header(report: Report, spec_path: str) -> str:
    export = report.export or "(export)"
    return f"{export}\n{INDENT}asset {report.asset_id} | spec {spec_path} | {report.export_format}"


def _violations(report: Report) -> tuple[str, ...]:
    if not report.violations:
        return (f"{INDENT}{NO_VIOLATIONS}",)
    lines = (_violation(report.asset_id, violation) for violation in report.violations)
    header = f"{INDENT}{_plural(len(report.violations), 'violation')} ({_count(report.violations)})"
    return (header, *_flatten(lines))


def _violation(asset_id: str, violation: Violation) -> tuple[str, ...]:
    """The four things a reader needs, on one line, then the rule's own sentence."""
    return (
        f"{INDENT * 2}{violation.severity}  {violation.rule_id}  "
        f"asset {asset_id}  subject {violation.subject}  "
        f"observed {_value(violation.observed)}  expected {_value(violation.expected)}",
        f"{INDENT * 3}{violation.message}",
    )


def _not_evaluated(report: Report) -> tuple[str, ...]:
    """Every suppressed rule by name — never a count (D13)."""
    if not report.not_evaluated:
        return ()
    header = f"{INDENT}not evaluated ({len(report.not_evaluated)}) — {NOT_EVALUATED_NOTE}"
    return (header, *(_suppressed(entry) for entry in report.not_evaluated))


def _suppressed(entry: NotEvaluated) -> str:
    return f"{INDENT * 2}{entry.rule_id}  needs {entry.missing_fact.label}  — {entry.reason}"


def _spec_warnings(warnings: Sequence[SpecViolation]) -> tuple[str, ...]:
    if not warnings:
        return ()
    return (
        f"{INDENT}specification notes ({len(warnings)})",
        *(_spec_warning(warning) for warning in warnings),
    )


def _spec_warning(warning: SpecViolation) -> str:
    return f"{INDENT * 2}{warning.severity}  {warning.rule_id}  {warning.message}"


def _preview(outcome: ValidationOutcome) -> tuple[str, ...]:
    """Preview emission is reported apart from the verdict, because it is (D7)."""
    if outcome.preview_failure is not None:
        return (f"{INDENT}preview not produced: {outcome.preview_failure.reason}",)
    if outcome.preview is not None:
        return (f"{INDENT}preview stored at {outcome.preview.key}",)
    return ()


def _lint_file(report: LintReport, path: str) -> str:
    findings = report.findings_in(path)
    if not findings:
        return f"{path}\n{INDENT}{NO_FINDINGS}"
    return "\n".join((path, *(_finding(finding) for finding in findings)))


def _finding(finding: LintFinding) -> str:
    violation = finding.violation
    return (
        f"{INDENT}{finding.severity}  {finding.rule_id}  subject {finding.subject}"
        f"\n{INDENT * 2}{violation.message}"
    )


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _verdict(passed: bool) -> str:
    return "PASSING" if passed else "FAILING"


def _count(items: Sequence[Violation] | Sequence[LintFinding]) -> str:
    errors = sum(1 for item in items if item.is_error)
    return f"{errors} error, {len(items) - errors} warning"


def _value(value: str | None) -> str:
    return "—" if value is None else value


def _flatten(groups: Iterable[Sequence[str]]) -> tuple[str, ...]:
    return tuple(line for group in groups for line in group)


__all__ = [
    "render_compiled",
    "render_failure",
    "render_lint",
    "render_project_notes",
    "render_validation",
    "render_validations",
]
