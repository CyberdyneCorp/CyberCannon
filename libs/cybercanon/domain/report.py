"""Three outcomes, and the report that keeps them apart (D13).

A rule is not a boolean. It passed, it was violated, or **it could not be
evaluated** because the export's format does not record the fact it consumes.
Collapsing the third into the first is how a validator starts lying about its
coverage; collapsing it into the second is how a team learns to ignore it.

So :class:`Report` carries three lists, and the overall outcome is failing **if
and only if** at least one violation has severity `error` — not-evaluated rules
never change it, and warnings never change it. Every rendering (CLI prose,
`--json`, and every later surface) shows the not-evaluated list in full, never
as a count, because a wrong matrix row is only ever visible there.
"""

from __future__ import annotations

from dataclasses import dataclass

from cybercanon.domain.mesh_facts import FactKind, MeshFormat
from cybercanon.domain.violations import Severity, Violation


@dataclass(frozen=True)
class Passed:
    """The rule ran and found nothing."""

    rule_id: str


@dataclass(frozen=True)
class Violated:
    """The rule ran and found something."""

    violation: Violation

    @property
    def rule_id(self) -> str:
        return self.violation.rule_id


@dataclass(frozen=True)
class NotEvaluated:
    """The rule did not run, and this is exactly why.

    `missing_fact` is the first fact the format cannot yield and `reason` states
    it in the words a report prints — "OBJ carries no unit scale".
    """

    rule_id: str
    missing_fact: FactKind
    reason: str


RuleOutcome = Passed | Violated | NotEvaluated
"""What evaluating one rule against one export produced."""


@dataclass(frozen=True)
class Report:
    """One export, measured against one effective specification."""

    asset_id: str
    export_format: MeshFormat
    export: str | None = None
    violations: tuple[Violation, ...] = ()
    not_evaluated: tuple[NotEvaluated, ...] = ()
    passed_rules: tuple[str, ...] = ()

    @property
    def errors(self) -> tuple[Violation, ...]:
        """The violations that fail the run."""
        return tuple(violation for violation in self.violations if violation.is_error)

    @property
    def warnings(self) -> tuple[Violation, ...]:
        """The violations that are advisory — listed, never fatal."""
        return tuple(violation for violation in self.violations if not violation.is_error)

    @property
    def passed(self) -> bool:
        """Failing if and only if an `error`-severity violation exists."""
        return not self.errors

    @property
    def outcome(self) -> str:
        """The overall outcome as one word, for a renderer that wants it."""
        return PASSING if self.passed else FAILING

    def violations_of(self, rule_id: str) -> tuple[Violation, ...]:
        """Every violation of one rule — what a test asserting a rule fired reads."""
        return tuple(violation for violation in self.violations if violation.rule_id == rule_id)

    def not_evaluated_rule(self, rule_id: str) -> NotEvaluated | None:
        """The suppression record for one rule, or ``None`` when it ran."""
        return next((entry for entry in self.not_evaluated if entry.rule_id == rule_id), None)

    def evaluated(self, rule_id: str) -> bool:
        """Whether the rule ran at all — the question NOT EVALUATED exists to answer."""
        return self.not_evaluated_rule(rule_id) is None


PASSING = "passing"
FAILING = "failing"


def build_report(
    asset_id: str,
    export_format: MeshFormat,
    outcomes: tuple[RuleOutcome, ...],
    export: str | None = None,
) -> Report:
    """Sort evaluated outcomes into the three lists a report keeps apart."""
    return Report(
        asset_id=asset_id,
        export_format=export_format,
        export=export,
        violations=tuple(o.violation for o in outcomes if isinstance(o, Violated)),
        not_evaluated=tuple(o for o in outcomes if isinstance(o, NotEvaluated)),
        passed_rules=tuple(o.rule_id for o in outcomes if isinstance(o, Passed)),
    )


__all__ = [
    "FAILING",
    "PASSING",
    "NotEvaluated",
    "Passed",
    "Report",
    "RuleOutcome",
    "Severity",
    "Violated",
    "build_report",
]
