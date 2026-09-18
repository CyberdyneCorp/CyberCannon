"""Triangle budgets — the whole export, and the LOD level it claims to be.

`tri_budget.exceeded` is the rule the pre-commit hook blocks a commit over, so
it is an `error` by default. `lod.exceeded` is the same comparison against the
budget declared for the level the export's object names claim, which is why it
consumes object names as well as the triangle count: nothing else in
:class:`~cybercanon.domain.mesh_facts.MeshFacts` says which LOD this file is.

When the objects claim more than one level — an export holding LOD0 and LOD1
together — the level cannot be attributed, because the triangle count is for the
whole export. The rule then reports nothing rather than guessing, and the plain
`tri_budget` rule still applies.
"""

from __future__ import annotations

from collections.abc import Iterable

from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.mesh_facts import FactKind, MeshFacts
from cybercanon.domain.naming import lod_index
from cybercanon.domain.violations import Severity, Violation

TRI_BUDGET = "tri_budget.exceeded"
TRI_BUDGET_SEVERITY = Severity.ERROR
TRI_BUDGET_CONSUMES = frozenset({FactKind.TRIANGLES})

LOD_BUDGET = "lod.exceeded"
LOD_BUDGET_SEVERITY = Severity.ERROR
LOD_BUDGET_CONSUMES = frozenset({FactKind.TRIANGLES, FactKind.OBJECTS})


def check_tri_budget(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """The export's triangle count against the effective `tri_budget`."""
    if spec.tri_budget is None or facts.triangles is None:
        return ()
    if facts.triangles <= spec.tri_budget:
        return ()
    return (
        Violation(
            rule_id=TRI_BUDGET,
            severity=TRI_BUDGET_SEVERITY,
            subject="triangles",
            message=(
                f"{spec.asset_id}: export has {facts.triangles} triangles, "
                f"above the tri_budget of {spec.tri_budget}"
            ),
            observed=str(facts.triangles),
            expected=str(spec.tri_budget),
        ),
    )


def check_lod_budget(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """The export's triangle count against the budget for the LOD it claims to be."""
    level = _claimed_level(spec, facts)
    if level is None or facts.triangles is None or level >= len(spec.lods):
        return ()
    allowed = spec.lods[level]
    if facts.triangles <= allowed:
        return ()
    return (
        Violation(
            rule_id=LOD_BUDGET,
            severity=LOD_BUDGET_SEVERITY,
            subject=f"LOD{level}",
            message=(
                f"{spec.asset_id}: LOD{level} has {facts.triangles} triangles, "
                f"above the {allowed} declared for that level"
            ),
            observed=str(facts.triangles),
            expected=str(allowed),
        ),
    )


def claimed_lod_levels(spec: EffectiveSpec, facts: MeshFacts) -> frozenset[int]:
    """The LOD levels this export's object names claim under the naming template."""
    if not spec.naming:
        return frozenset()
    found = (lod_index(spec.naming, name, {"asset": spec.asset_id}) for name in facts.objects)
    return frozenset(level for level in found if level is not None)


def _claimed_level(spec: EffectiveSpec, facts: MeshFacts) -> int | None:
    if not spec.lods:
        return None
    levels = claimed_lod_levels(spec, facts)
    return next(iter(levels)) if len(levels) == 1 else None


__all__ = [
    "LOD_BUDGET",
    "LOD_BUDGET_CONSUMES",
    "LOD_BUDGET_SEVERITY",
    "TRI_BUDGET",
    "TRI_BUDGET_CONSUMES",
    "TRI_BUDGET_SEVERITY",
    "check_lod_budget",
    "check_tri_budget",
    "claimed_lod_levels",
]
