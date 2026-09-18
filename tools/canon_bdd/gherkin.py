"""Render a parsed spec delta as Gherkin.

Three things are preserved verbatim, because they are the traceability: the
requirement name (a Gherkin ``Rule:``), the scenario name, and the text of every
GIVEN/WHEN/THEN line. Everything else in the file is generated scaffolding.

D5 — each feature carries its change, its capability and its spec path as tags,
so ``just test-bdd --tag asset-validation`` runs one capability and a failure
names where the requirement lives.
"""

from __future__ import annotations

from canon_bdd.specs import CapabilitySpec, Requirement, Scenario, Step

GHERKIN_KEYWORDS = {"GIVEN": "Given", "WHEN": "When", "THEN": "Then", "AND": "And"}

CHANGE_TAG = "change"
CAPABILITY_TAG = "capability"
SPEC_TAG = "spec"

_INDENT = "  "


def render(spec: CapabilitySpec) -> str:
    """The complete text of one ``.feature`` file."""
    lines = [*_header(spec), *_tags(spec), f"Feature: {spec.capability}"]
    for requirement in spec.requirements:
        lines.extend(_requirement_lines(requirement))
    return "\n".join(lines) + "\n"


def tags(spec: CapabilitySpec) -> tuple[str, ...]:
    """The tags carried by every scenario in this capability's feature."""
    return (
        f"{CHANGE_TAG}:{spec.change}",
        f"{CAPABILITY_TAG}:{spec.capability}",
        f"{SPEC_TAG}:{spec.path.as_posix()}",
    )


def _header(spec: CapabilitySpec) -> tuple[str, ...]:
    return (
        f"# Generated from {spec.path.as_posix()} by scripts/gen_features.py.",
        "# Do not edit: run `just gen-features`. A hand edit fails `just features`.",
        "",
    )


def _tags(spec: CapabilitySpec) -> tuple[str, ...]:
    return (" ".join(f"@{tag}" for tag in tags(spec)),)


def _requirement_lines(requirement: Requirement) -> tuple[str, ...]:
    lines = ["", f"{_INDENT}Rule: {requirement.name}"]
    for scenario in requirement.scenarios:
        lines.extend(_scenario_lines(scenario))
    return tuple(lines)


def _scenario_lines(scenario: Scenario) -> tuple[str, ...]:
    return (
        "",
        f"{_INDENT * 2}Scenario: {scenario.name}",
        *(_step_line(step) for step in scenario.steps),
    )


def _step_line(step: Step) -> str:
    return f"{_INDENT * 3}{GHERKIN_KEYWORDS[step.keyword]} {step.text}"
