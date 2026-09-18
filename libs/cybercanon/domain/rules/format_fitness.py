"""`format.unsuitable_for_asset` — cannot *contain*, as opposed to cannot *record*.

This is the other half of D13, and the distinction is the whole decision:

* `OBJ` records no unit scale, so an `OBJ` export may well be correctly scaled.
  The unit scale rule is **not evaluated** and we say so.
* `OBJ` cannot hold an animation clip, so an asset whose states require one can
  **never** be satisfied by an `OBJ` export. That is an export mistake with an
  obvious fix — re-export — and saying it now is strictly kinder than saying it
  at integration.

So this rule is an ordinary `error` violation, and it is the one rule that must
never be suppressed by the availability gate: it consumes
:attr:`~cybercanon.domain.mesh_facts.FactKind.SOURCE_FORMAT`, which every export
carries by definition, so it runs on every format including the ones that can
answer nothing else.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from cybercanon.domain.effective_spec import EffectiveSpec
from cybercanon.domain.format_matrix import ContentKind, can_contain
from cybercanon.domain.mesh_facts import FactKind, MeshFacts
from cybercanon.domain.violations import Severity, Violation

UNSUITABLE_FORMAT = "format.unsuitable_for_asset"
UNSUITABLE_FORMAT_SEVERITY = Severity.ERROR
UNSUITABLE_FORMAT_CONSUMES = frozenset({FactKind.SOURCE_FORMAT})

Requirement = tuple[ContentKind, Callable[[EffectiveSpec], bool], str]

REQUIREMENTS: tuple[Requirement, ...] = (
    (
        ContentKind.ANIMATION_CLIPS,
        lambda spec: bool(spec.required_clips),
        "its design states require animation clips",
    ),
    (
        ContentKind.SKELETON,
        lambda spec: spec.rig_declared,
        "it declares a rig",
    ),
    (
        ContentKind.ATTACHMENT_POINTS,
        lambda spec: bool(spec.required_sockets),
        "its design declares sockets",
    ),
)
"""What a specification can demand, and the phrase a violation uses to name it."""


def check_format_fitness(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """One violation per declared requirement this export's format cannot contain."""
    return tuple(
        _unsuitable(spec, facts, content, because)
        for content, demands, because in REQUIREMENTS
        if demands(spec) and not can_contain(facts.source_format, content)
    )


def _unsuitable(
    spec: EffectiveSpec, facts: MeshFacts, content: ContentKind, because: str
) -> Violation:
    fmt = facts.source_format
    return Violation(
        rule_id=UNSUITABLE_FORMAT,
        severity=UNSUITABLE_FORMAT_SEVERITY,
        subject=str(content),
        message=(
            f"{spec.asset_id}: {fmt} is an unsuitable export format for this asset — "
            f"{because}, and {fmt} cannot contain {content}"
        ),
        observed=f"{fmt} export",
        expected=f"a format that can contain {content}",
    )


__all__ = [
    "REQUIREMENTS",
    "UNSUITABLE_FORMAT",
    "UNSUITABLE_FORMAT_CONSUMES",
    "UNSUITABLE_FORMAT_SEVERITY",
    "Requirement",
    "check_format_fitness",
]
