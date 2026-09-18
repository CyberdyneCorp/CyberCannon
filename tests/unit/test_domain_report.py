"""Task 3.4 — `Violation`, the three-way outcome, and the report that keeps them apart.

The property the whole design rests on: the outcome is failing **if and only if**
an `error`-severity violation exists. Warnings are listed and pass; not-evaluated
rules are listed and pass, and are never presentable as satisfied.
"""

from __future__ import annotations

from cybercanon.domain.mesh_facts import FactKind, MeshFormat
from cybercanon.domain.report import (
    FAILING,
    PASSING,
    NotEvaluated,
    Passed,
    Report,
    Violated,
    build_report,
)
from cybercanon.domain.violations import Severity, Violation

ASSET = "mech_scout"


def a_violation(rule_id: str, severity: Severity) -> Violation:
    return Violation(
        rule_id=rule_id,
        severity=severity,
        subject="triangles",
        message="something to fix",
        observed="14310",
        expected="12000",
    )


def a_report(*outcomes: object) -> Report:
    return build_report(ASSET, MeshFormat.GLB, tuple(outcomes), export="exports/mech.glb")  # type: ignore[arg-type]


def test_an_error_violation_fails_the_run() -> None:
    report = a_report(Violated(a_violation("tri_budget.exceeded", Severity.ERROR)))

    assert not report.passed
    assert report.outcome == FAILING
    assert len(report.errors) == 1
    assert report.warnings == ()


def test_warnings_alone_pass_and_are_still_listed() -> None:
    report = a_report(Violated(a_violation("naming.pattern_mismatch", Severity.WARNING)))

    assert report.passed
    assert report.outcome == PASSING
    assert len(report.violations) == 1
    assert len(report.warnings) == 1


def test_not_evaluated_alone_passes_and_is_still_listed() -> None:
    report = a_report(
        NotEvaluated("unit_scale.mismatch", FactKind.UNIT_SCALE, "OBJ carries no unit scale"),
        NotEvaluated("rig.not_skinned", FactKind.SKINNING, "OBJ carries no skinning"),
    )

    assert report.passed
    assert len(report.not_evaluated) == 2
    assert report.violations == ()


def test_a_not_evaluated_rule_is_distinguishable_from_a_passed_one() -> None:
    report = a_report(
        Passed("tri_budget.exceeded"),
        NotEvaluated("unit_scale.mismatch", FactKind.UNIT_SCALE, "OBJ carries no unit scale"),
    )

    assert report.evaluated("tri_budget.exceeded")
    assert not report.evaluated("unit_scale.mismatch")
    assert "unit_scale.mismatch" not in report.passed_rules
    assert report.passed_rules == ("tri_budget.exceeded",)


def test_a_not_evaluated_rule_carries_the_fact_and_the_reason() -> None:
    report = a_report(
        NotEvaluated("unit_scale.mismatch", FactKind.UNIT_SCALE, "OBJ carries no unit scale")
    )

    entry = report.not_evaluated_rule("unit_scale.mismatch")
    assert entry is not None
    assert entry.missing_fact is FactKind.UNIT_SCALE
    assert entry.reason == "OBJ carries no unit scale"
    assert report.not_evaluated_rule("tri_budget.exceeded") is None


def test_the_report_states_the_asset_the_export_and_its_format() -> None:
    report = a_report(Passed("tri_budget.exceeded"))

    assert report.asset_id == ASSET
    assert report.export == "exports/mech.glb"
    assert report.export_format is MeshFormat.GLB


def test_violations_are_addressable_by_rule() -> None:
    report = a_report(
        Violated(a_violation("tri_budget.exceeded", Severity.ERROR)),
        Violated(a_violation("naming.pattern_mismatch", Severity.WARNING)),
    )

    assert len(report.violations_of("tri_budget.exceeded")) == 1
    assert report.violations_of("socket.missing") == ()


def test_a_violated_outcome_reports_its_rule() -> None:
    outcome = Violated(a_violation("tri_budget.exceeded", Severity.ERROR))

    assert outcome.rule_id == "tri_budget.exceeded"


def test_an_empty_report_passes() -> None:
    assert a_report().passed
