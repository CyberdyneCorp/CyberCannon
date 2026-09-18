"""What a step module declares, read from its source.

D4 scopes step definitions per capability, and a scoping rule is only worth
something if something checks it. The checks (``tests/tooling/test_step_scoping.py``,
``tests/tooling/test_shared_steps.py``) need the step phrases a module declares,
so this module reads them out of the AST — the same choice, for the same reason,
as :mod:`canon_bdd.implemented`: a gate that imports test code to decide what
test code declares can be talked out of its answer, and the gates must also run
outside a pytest session.

A pattern written as a module-level constant is resolved, because a regex is
unreadable inline. Anything else — a computed phrase, an imported constant —
reads as *unknown* and is reported as such rather than silently ignored.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

KEYWORDS = ("given", "when", "then")
PARSER_FUNCTIONS = ("parse", "re", "cfparse", "string")
UNKNOWN = None


@dataclass(frozen=True)
class StepDeclaration:
    """One ``@given``/``@when``/``@then`` decorator found in a step module."""

    module: Path
    keyword: str
    parser: str
    pattern: str | None
    line: int

    @property
    def is_readable(self) -> bool:
        """False when the phrase is computed, so no gate can read it."""
        return self.pattern is not None


def declarations_under(steps_dir: Path) -> tuple[StepDeclaration, ...]:
    """Every step declaration under ``steps_dir``, in a deterministic order."""
    if not steps_dir.is_dir():
        return ()
    return tuple(
        declaration
        for path in sorted(steps_dir.rglob("*.py"))
        for declaration in declarations_in(path)
    )


def declarations_in(path: Path) -> tuple[StepDeclaration, ...]:
    """The step declarations one module makes."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = _module_constants(tree)
    return tuple(
        declaration
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        for decorator in node.decorator_list
        for declaration in _declaration(path, decorator, constants)
    )


def _declaration(
    path: Path, decorator: ast.expr, constants: dict[str, str]
) -> tuple[StepDeclaration, ...]:
    """The one declaration this decorator makes, or nothing if it is not a step."""
    keyword = _keyword(decorator)
    if keyword is None or not isinstance(decorator, ast.Call):
        return ()
    parser, pattern = _pattern(decorator.args[0] if decorator.args else None, constants)
    return (
        StepDeclaration(
            module=path,
            keyword=keyword,
            parser=parser,
            pattern=pattern,
            line=decorator.lineno,
        ),
    )


def _keyword(decorator: ast.expr) -> str | None:
    """``given``/``when``/``then``, however the module imported it."""
    if not isinstance(decorator, ast.Call):
        return None
    name = _called_name(decorator.func)
    return name if name in KEYWORDS else None


def _pattern(argument: ast.expr | None, constants: dict[str, str]) -> tuple[str, str | None]:
    """The parser name (``""`` for a plain phrase) and the phrase itself."""
    if isinstance(argument, ast.Call) and _called_name(argument.func) in PARSER_FUNCTIONS:
        parser = _called_name(argument.func) or ""
        inner = argument.args[0] if argument.args else None
        return parser, _text(inner, constants)
    return "", _text(argument, constants)


def _text(node: ast.expr | None, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, UNKNOWN)
    return UNKNOWN


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "..."`` assignments, so a pattern can be named."""
    return {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None
