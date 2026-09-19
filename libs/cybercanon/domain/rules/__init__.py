"""The rule registry and the three-way dispatch (D2, D13).

A rule is a pure function with a stable identifier, a default severity, and an
explicit declaration of the facts it consumes:

```python
Rule = Callable[[EffectiveSpec, MeshFacts], Iterable[Violation]]
```

There is no `Rule` base class and no shared state between rules — a flat
registry keyed by `rule_id` is auditable (you can print the inventory), keeps
each rule's cognitive complexity near one, and makes severity a property of the
registration rather than of the code that detects the defect.

**The dispatch is what makes NOT EVALUATED structural.** Every rule declares
`consumes`; :func:`evaluate` compares that set against
:attr:`MeshFacts.available` *before* calling the rule, so a rule whose facts the
format cannot yield is reported as not evaluated, naming the rule and the fact,
without a single `if format is OBJ` anywhere in a rule body. A rule cannot
accidentally pass on a fact it never saw, because it is never called.

Severity is stamped here from the registration, so a project lowering a rule to
a warning never edits the rule.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.format_matrix import absence_phrase
from cybercanon.domain.mesh_facts import FactKind, MeshFacts
from cybercanon.domain.report import (
    NotEvaluated,
    Passed,
    Report,
    RuleOutcome,
    Violated,
    build_report,
)
from cybercanon.domain.rules import animation, budgets, conventions, format_fitness, rig, sockets
from cybercanon.domain.violations import Severity, Violation

RuleFn = Callable[[EffectiveSpec, MeshFacts], Iterable[Violation]]
"""A rule: effective spec plus facts in, zero or more violations out. Nothing else."""


@dataclass(frozen=True)
class Rule:
    """One registered rule: its identity, its default severity, and what it reads."""

    rule_id: str
    severity: Severity
    consumes: frozenset[FactKind]
    check: RuleFn

    def __post_init__(self) -> None:
        if not self.consumes:
            raise ValueError(
                f"rule {self.rule_id!r} declares no facts; a rule that consumes nothing "
                "cannot be reported as not evaluated and would pass in silence"
            )


REGISTRY: tuple[Rule, ...] = (
    Rule(
        budgets.TRI_BUDGET,
        budgets.TRI_BUDGET_SEVERITY,
        budgets.TRI_BUDGET_CONSUMES,
        budgets.check_tri_budget,
    ),
    Rule(
        budgets.LOD_BUDGET,
        budgets.LOD_BUDGET_SEVERITY,
        budgets.LOD_BUDGET_CONSUMES,
        budgets.check_lod_budget,
    ),
    Rule(
        conventions.UNIT_SCALE,
        conventions.UNIT_SCALE_SEVERITY,
        conventions.UNIT_SCALE_CONSUMES,
        conventions.check_unit_scale,
    ),
    Rule(
        conventions.UP_AXIS,
        conventions.UP_AXIS_SEVERITY,
        conventions.UP_AXIS_CONSUMES,
        conventions.check_up_axis,
    ),
    Rule(
        conventions.TRANSFORMS,
        conventions.TRANSFORMS_SEVERITY,
        conventions.TRANSFORMS_CONSUMES,
        conventions.check_transforms_applied,
    ),
    Rule(
        conventions.NAMING,
        conventions.NAMING_SEVERITY,
        conventions.NAMING_CONSUMES,
        conventions.check_naming,
    ),
    Rule(
        sockets.SOCKET_MISSING,
        sockets.SOCKET_MISSING_SEVERITY,
        sockets.SOCKET_MISSING_CONSUMES,
        sockets.check_sockets,
    ),
    Rule(
        animation.CLIP_MISSING,
        animation.CLIP_MISSING_SEVERITY,
        animation.CLIP_MISSING_CONSUMES,
        animation.check_clips_present,
    ),
    Rule(
        animation.FRAME_RATE,
        animation.FRAME_RATE_SEVERITY,
        animation.FRAME_RATE_CONSUMES,
        animation.check_clip_frame_rate,
    ),
    Rule(
        animation.DURATION,
        animation.DURATION_SEVERITY,
        animation.DURATION_CONSUMES,
        animation.check_clip_duration,
    ),
    Rule(
        animation.ROOT_MOTION,
        animation.ROOT_MOTION_SEVERITY,
        animation.ROOT_MOTION_CONSUMES,
        animation.check_clip_root_motion,
    ),
    Rule(
        animation.LOOP,
        animation.LOOP_SEVERITY,
        animation.LOOP_CONSUMES,
        animation.check_clip_loop,
    ),
    Rule(
        rig.BONE_BUDGET,
        rig.BONE_BUDGET_SEVERITY,
        rig.BONE_BUDGET_CONSUMES,
        rig.check_bone_budget,
    ),
    Rule(
        rig.NOT_SKINNED,
        rig.NOT_SKINNED_SEVERITY,
        rig.NOT_SKINNED_CONSUMES,
        rig.check_skinning,
    ),
    Rule(
        format_fitness.UNSUITABLE_FORMAT,
        format_fitness.UNSUITABLE_FORMAT_SEVERITY,
        format_fitness.UNSUITABLE_FORMAT_CONSUMES,
        format_fitness.check_format_fitness,
    ),
)
"""Every mesh rule, in report order. The inventory is printable, so it is auditable."""

RULE_IDS: tuple[str, ...] = tuple(rule.rule_id for rule in REGISTRY)

BY_ID: Mapping[str, Rule] = {rule.rule_id: rule for rule in REGISTRY}


def reason_for(missing: FactKind, facts: MeshFacts) -> str:
    """Why a rule could not run, in the words a report prints.

    The matrix owns the sentence because it owns the distinction: a format that
    cannot record a fact and one that records it unreliably both produce NOT
    EVALUATED, and only the wording tells the two apart.
    """
    return absence_phrase(facts.source_format, missing)


def evaluate(rule: Rule, spec: EffectiveSpec, facts: MeshFacts) -> tuple[RuleOutcome, ...]:
    """One rule against one export: passed, violated, or not evaluated."""
    missing = facts.missing(rule.consumes)
    if missing is not None:
        return (NotEvaluated(rule.rule_id, missing, reason_for(missing, facts)),)
    violations = tuple(rule.check(spec, facts))
    if not violations:
        return (Passed(rule.rule_id),)
    return tuple(Violated(replace(found, severity=rule.severity)) for found in violations)


def with_severities(
    overrides: Mapping[str, Severity], rules: tuple[Rule, ...] = REGISTRY
) -> tuple[Rule, ...]:
    """The registry with a project's per-rule severities applied.

    Severity is a property of the registration, never of the code that detects
    the defect, so a project lowering a noisy rule to a warning re-registers it
    and edits nothing else. The rule bodies, the facts they consume and the
    report they produce are untouched.
    """
    if not overrides:
        return rules
    return tuple(
        replace(rule, severity=overrides.get(rule.rule_id, rule.severity)) for rule in rules
    )


def run(
    spec: EffectiveSpec,
    facts: MeshFacts,
    export: str | None = None,
    rules: tuple[Rule, ...] = REGISTRY,
) -> Report:
    """Every rule against one export, as one report.

    The pure decision the whole product rests on: the same facts and the same
    effective spec produce the same report, whatever surface asked and whatever
    file the facts were read from.
    """
    outcomes = tuple(outcome for rule in rules for outcome in evaluate(rule, spec, facts))
    return build_report(spec.asset_id, facts.source_format, outcomes, export=export)


__all__ = [
    "BY_ID",
    "REGISTRY",
    "RULE_IDS",
    "Rule",
    "RuleFn",
    "evaluate",
    "reason_for",
    "run",
    "with_severities",
]
