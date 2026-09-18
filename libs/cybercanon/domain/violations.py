"""What a check reports, and how loudly.

A check is a pure function returning zero or more :class:`SpecViolation`. The
value object carries everything a human or a machine needs to act — the stable
`rule_id` a project configures severity against, the `subject` naming the
offending field, and the observed and expected values — so no renderer has to
re-derive any of it.

This module holds both violation kinds, sharing :class:`Severity` because a
project tunes rule severity in one vocabulary:

* :class:`SpecViolation` — a structural problem in an `asset.yaml`, produced by
  :mod:`cybercanon.domain.spec_checks` over the file alone;
* :class:`Violation` — a mesh rule's finding, produced by
  :mod:`cybercanon.domain.rules` over an
  :class:`~cybercanon.domain.effective_spec.EffectiveSpec` and hand-built
  :class:`~cybercanon.domain.mesh_facts.MeshFacts`.

They are deliberately two types rather than one: a spec violation is a defect of
a file a person edits, a mesh violation is a defect of an export a person
re-exports, and the surfaces that render them differ. What they must share is
the severity vocabulary and the rule-identifier discipline, and they do.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    """How a violation is treated. Only `error` fails a run."""

    ERROR = "error"
    WARNING = "warning"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SpecViolation:
    """One structural problem found in a specification file.

    `subject` names the offending field in dotted form (``constraints.lods``,
    ``design.states[fire]``) so a message never has to be parsed to find out
    what to edit.
    """

    rule_id: str
    severity: Severity
    subject: str
    message: str
    observed: str | None = None
    expected: str | None = None

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR


@dataclass(frozen=True)
class Violation:
    """One mesh rule's finding about an export.

    Every field exists because a renderer would otherwise have to re-derive it:
    `rule_id` is what a project configures severity against and what two runs of
    the same rule must agree on; `subject` names the offending object, socket,
    clip or property; `observed` and `expected` are what a person needs in order
    to know what to change. `message` states all of it in one line, naming the
    asset, so a report line is actionable on its own.

    `severity` is stamped by the rule registry, so a project can lower a rule to
    a warning without editing the rule.
    """

    rule_id: str
    severity: Severity
    subject: str
    message: str
    observed: str | None = None
    expected: str | None = None

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR


def errors(violations: tuple[SpecViolation, ...]) -> tuple[SpecViolation, ...]:
    """Only the violations that fail a run — the rest are advisory."""
    return tuple(violation for violation in violations if violation.is_error)


__all__ = ["Severity", "SpecViolation", "Violation", "errors"]
