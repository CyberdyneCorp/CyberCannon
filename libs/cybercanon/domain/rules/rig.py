"""The skeleton contract: how many bones, and whether the mesh is skinned at all.

`rig.bone_budget_exceeded` is a budget like the triangle budget and behaves like
one — at or below the budget is silence, above it is an `error` stating both
numbers.

`rig.not_skinned` fires when the **asset** declares a rig and the export carries
no skinning. It reads `rig_declared` rather than the merged rig, because a
project-wide `max_bones` default must not turn every static prop into an asset
that owes a skeleton. `rig.skinned: false` is the explicit opt-out for an asset
with a skeleton it deliberately does not skin to.
"""

from __future__ import annotations

from collections.abc import Iterable

from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.mesh_facts import FactKind, MeshFacts
from cybercanon.domain.violations import Severity, Violation

BONE_BUDGET = "rig.bone_budget_exceeded"
BONE_BUDGET_SEVERITY = Severity.ERROR
BONE_BUDGET_CONSUMES = frozenset({FactKind.BONE_COUNT})

NOT_SKINNED = "rig.not_skinned"
NOT_SKINNED_SEVERITY = Severity.ERROR
NOT_SKINNED_CONSUMES = frozenset({FactKind.SKINNING})

UNNAMED_SKELETON = "the declared skeleton"


def check_bone_budget(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """The export's bone count against the effective `rig.max_bones`."""
    allowed = spec.max_bones
    if allowed is None or facts.bone_count is None or facts.bone_count <= allowed:
        return ()
    return (
        Violation(
            rule_id=BONE_BUDGET,
            severity=BONE_BUDGET_SEVERITY,
            subject="rig.max_bones",
            message=(
                f"{spec.asset_id}: skeleton has {facts.bone_count} bones, "
                f"above the max_bones of {allowed}"
            ),
            observed=str(facts.bone_count),
            expected=str(allowed),
        ),
    )


def check_skinning(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """A declared rig with an unskinned export is a violation naming the skeleton."""
    if not spec.expects_skinning or facts.is_skinned is not False:
        return ()
    skeleton = spec.skeleton or UNNAMED_SKELETON
    return (
        Violation(
            rule_id=NOT_SKINNED,
            severity=NOT_SKINNED_SEVERITY,
            subject=skeleton,
            message=(
                f"{spec.asset_id}: declares the rig {skeleton} and the export carries no skinning"
            ),
            observed="not skinned",
            expected=f"skinned to {skeleton}",
        ),
    )


__all__ = [
    "BONE_BUDGET",
    "BONE_BUDGET_CONSUMES",
    "BONE_BUDGET_SEVERITY",
    "NOT_SKINNED",
    "NOT_SKINNED_CONSUMES",
    "NOT_SKINNED_SEVERITY",
    "UNNAMED_SKELETON",
    "check_bone_budget",
    "check_skinning",
]
