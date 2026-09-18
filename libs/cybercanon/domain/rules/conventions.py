"""The mechanical conventions: scale, axis, transforms, object names.

These are the defects the product exists to stop being fixed by hand,
downstream, by the wrong person. Each violation names the specific object or
property at fault, because "naming is wrong somewhere in this file" is not
actionable.

`transforms.unapplied` is a whole-export fact (D1 fixes `transforms_applied` as
one boolean), so the violation names every object in the export rather than
pretending to know which one carries the transform. The alternative — a
per-object list — is a change to the port and the fact set, and belongs to the
change that needs it.
"""

from __future__ import annotations

from collections.abc import Iterable

from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.mesh_facts import FactKind, MeshFacts
from cybercanon.domain.naming import matches
from cybercanon.domain.violations import Severity, Violation

UNIT_SCALE = "unit_scale.mismatch"
UNIT_SCALE_SEVERITY = Severity.ERROR
UNIT_SCALE_CONSUMES = frozenset({FactKind.UNIT_SCALE})

UP_AXIS = "up_axis.mismatch"
UP_AXIS_SEVERITY = Severity.ERROR
UP_AXIS_CONSUMES = frozenset({FactKind.UP_AXIS})

TRANSFORMS = "transforms.unapplied"
TRANSFORMS_SEVERITY = Severity.ERROR
TRANSFORMS_CONSUMES = frozenset({FactKind.TRANSFORMS_APPLIED, FactKind.OBJECTS})

NAMING = "naming.pattern_mismatch"
NAMING_SEVERITY = Severity.WARNING
NAMING_CONSUMES = frozenset({FactKind.OBJECTS})

UNIT_SCALE_TOLERANCE = 1e-6
"""Floating point slack. A scale differing in the seventh decimal is the same scale."""


def check_unit_scale(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """The export's unit scale against the effective `unit_scale`."""
    if spec.unit_scale is None or facts.unit_scale is None:
        return ()
    if abs(facts.unit_scale - spec.unit_scale) <= UNIT_SCALE_TOLERANCE:
        return ()
    return (
        Violation(
            rule_id=UNIT_SCALE,
            severity=UNIT_SCALE_SEVERITY,
            subject="unit_scale",
            message=(
                f"{spec.asset_id}: export unit scale is {facts.unit_scale}, "
                f"expected {spec.unit_scale}"
            ),
            observed=str(facts.unit_scale),
            expected=str(spec.unit_scale),
        ),
    )


def check_up_axis(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """The export's up axis against the effective `up_axis`."""
    if spec.up_axis is None or facts.up_axis is None:
        return ()
    if facts.up_axis.upper() == spec.up_axis.upper():
        return ()
    return (
        Violation(
            rule_id=UP_AXIS,
            severity=UP_AXIS_SEVERITY,
            subject="up_axis",
            message=(
                f"{spec.asset_id}: export up axis is {facts.up_axis}, expected {spec.up_axis}"
            ),
            observed=facts.up_axis,
            expected=spec.up_axis,
        ),
    )


def check_transforms_applied(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """Object transforms must be applied before export."""
    if facts.transforms_applied is not False:
        return ()
    listed = ", ".join(facts.objects) if facts.objects else "the export"
    return (
        Violation(
            rule_id=TRANSFORMS,
            severity=TRANSFORMS_SEVERITY,
            subject=listed,
            message=(
                f"{spec.asset_id}: object transforms are not applied on {listed}; "
                "apply scale and rotation before exporting"
            ),
            observed="transforms not applied",
            expected="transforms applied",
        ),
    )


def check_naming(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """Every object name against the effective naming template (D8)."""
    if not spec.naming:
        return ()
    return tuple(
        _naming_violation(spec, name)
        for name in facts.objects
        if not matches(spec.naming, name, {"asset": spec.asset_id})
    )


def _naming_violation(spec: EffectiveSpec, name: str) -> Violation:
    return Violation(
        rule_id=NAMING,
        severity=NAMING_SEVERITY,
        subject=name,
        message=(
            f"{spec.asset_id}: object {name!r} does not match the naming pattern {spec.naming!r}"
        ),
        observed=name,
        expected=spec.naming,
    )


__all__ = [
    "NAMING",
    "NAMING_CONSUMES",
    "NAMING_SEVERITY",
    "TRANSFORMS",
    "TRANSFORMS_CONSUMES",
    "TRANSFORMS_SEVERITY",
    "UNIT_SCALE",
    "UNIT_SCALE_CONSUMES",
    "UNIT_SCALE_SEVERITY",
    "UNIT_SCALE_TOLERANCE",
    "UP_AXIS",
    "UP_AXIS_CONSUMES",
    "UP_AXIS_SEVERITY",
    "check_naming",
    "check_transforms_applied",
    "check_unit_scale",
    "check_up_axis",
]
