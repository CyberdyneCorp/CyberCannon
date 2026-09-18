"""Which generated scenarios actually execute.

D4 scopes step definitions per capability: ``tests/bdd/steps/<capability>.py``
holds one capability's steps and binds the scenarios it satisfies with
``@scenario("../features/<change>/<capability>.feature", "<scenario name>")`` —
or with ``scenarios(...)`` once every scenario in a feature is covered.

Those bindings are read **statically, from the source**, never by importing the
module: the gates must be answerable outside a pytest session (the pending-list
bootstrap runs from the command line), and a gate that executes arbitrary test
code to decide whether tests exist is a gate that can be talked out of its
answer. The cost is that a binding must use literal strings — a computed feature
name reads as *not executing*, which fails the build loudly rather than quietly
claiming coverage.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

STEPS_DIR = Path("tests/bdd/steps")
FEATURE_SUFFIX = ".feature"
SCENARIO_FUNCTIONS = ("scenario", "scenarios")


@dataclass(frozen=True)
class Binding:
    """One ``@scenario``/``scenarios()`` binding found in a step module."""

    module: Path
    feature: Path
    scenario: str | None
    line: int

    @property
    def capability(self) -> str:
        """Generated features are ``<capability>.feature``; that is the capability."""
        return self.feature.stem

    @property
    def binds_every_scenario(self) -> bool:
        return self.scenario is None


class StepModuleError(Exception):
    """A step module could not be read, so its scenarios cannot be trusted."""


def discover(steps_dir: Path) -> tuple[Binding, ...]:
    """Every scenario binding under ``steps_dir``, in a deterministic order."""
    if not steps_dir.is_dir():
        return ()
    return tuple(
        binding
        for path in sorted(steps_dir.rglob("*.py"))
        if not path.name.startswith("_")
        for binding in bindings_in(path)
    )


def bindings_in(path: Path) -> tuple[Binding, ...]:
    """The bindings one step module declares."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        raise StepModuleError(f"{path}:{error.lineno}: {error.msg}") from error
    return tuple(
        binding
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for binding in _binding(path, node)
    )


def _binding(path: Path, node: ast.Call) -> tuple[Binding, ...]:
    name = _called_name(node.func)
    if name not in SCENARIO_FUNCTIONS or not node.args:
        return ()
    if name == "scenario":
        return _single_binding(path, node)
    return tuple(
        Binding(module=path, feature=feature, scenario=None, line=node.lineno)
        for argument in node.args
        for feature in _features(path, _literal(argument))
    )


def _single_binding(path: Path, node: ast.Call) -> tuple[Binding, ...]:
    scenario = _literal(node.args[1]) if len(node.args) > 1 else None
    if scenario is None:
        return ()
    return tuple(
        Binding(module=path, feature=feature, scenario=scenario, line=node.lineno)
        for feature in _features(path, _literal(node.args[0]))
    )


def _features(module: Path, reference: str | None) -> tuple[Path, ...]:
    """A binding names one feature file, or a directory holding several."""
    if reference is None:
        return ()
    target = (module.parent / reference).resolve()
    if reference.endswith(FEATURE_SUFFIX):
        return (target,)
    return tuple(sorted(target.rglob(f"*{FEATURE_SUFFIX}"))) if target.is_dir() else ()


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def _literal(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def executing_keys(
    bindings: tuple[Binding, ...], scenarios_by_capability: dict[str, tuple[str, ...]]
) -> set[tuple[str, str]]:
    """The ``(capability, scenario)`` keys these bindings make executable."""
    keys: set[tuple[str, str]] = set()
    for binding in bindings:
        names = scenarios_by_capability.get(binding.capability, ())
        bound = names if binding.binds_every_scenario else (binding.scenario,)
        keys.update((binding.capability, name) for name in bound if name in names)
    return keys
