"""Task 6.2 — no rule logic outside the domain, asserted rather than trusted.

The pre-commit validator the artist runs, the `validate_export` the Blender
agent calls and the "Validate" button in the web app are the *same use case*.
The way that stops being true is not a rewrite; it is one `if triangles >
budget` appearing in a command, a router or a tool handler because it was
quicker than adding a rule. Then the product has the bug it exists to
prevent — "it passed on my machine but the site says it failed".

Two mechanical halves, because either alone is evadable:

* **import-linter** (D10) keeps the layering honest — the domain imports nothing
  third-party, and inbound adapters never reach an outbound one. It cannot see
  a rule *copied* into an adapter, because a copy imports nothing.
* **This grep**, over the syntax tree rather than the text, catches the copy: a
  stable `rule_id`, a constraint field or a severity decision appearing in a
  surface module. Docstrings are excluded deliberately — an adapter is allowed
  to *explain* the rule it delegates to, and every module here does.

Adding a rule therefore has exactly one place to go, and a shortcut through an
adapter fails the build with the file and the token that gave it away.
"""

from __future__ import annotations

import ast
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

from cybercanon.domain.rules import RULE_IDS

DOMAIN = Path("libs/cybercanon/domain")

SURFACES = (
    Path("libs/cybercanon/adapters/inbound"),
    Path("libs/cybercanon/adapters/wiring"),
    Path("services"),
)
"""Where a rule would be re-implemented if it were going to be: the surfaces."""

OUTSIDE_THE_DOMAIN = (
    Path("libs/cybercanon/application"),
    Path("libs/cybercanon/adapters"),
    Path("services"),
)

CONSTRAINT_FIELDS = (
    "tri_budget",
    "lods",
    "max_bones",
    "bone_count",
    "triangles",
    "unit_scale",
    "up_axis",
    "required_sockets",
    "required_clips",
    "expects_skinning",
    "transforms_applied",
)
"""Reading one of these in a surface module means deciding something in it."""

VERDICT_TYPES = ("Violation", "Violated", "NotEvaluated", "Passed")
"""A surface renders a verdict; it never constructs one."""


def _modules(repo_root: Path, directory: Path) -> Iterator[Path]:
    yield from sorted((repo_root / directory).rglob("*.py"))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _code_strings(tree: ast.Module) -> set[str]:
    """Every string literal except the docstrings, which are prose about the rules."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def _names(tree: ast.Module) -> set[str]:
    """Identifiers and attribute names the module actually uses in code."""
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            used.add(node.arg)
    return used


def _called(tree: ast.Module) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _paths(repo_root: Path, directories: tuple[Path, ...]) -> list[Path]:
    return [module for directory in directories for module in _modules(repo_root, directory)]


@pytest.fixture(scope="module")
def surface_modules(repo_root: Path) -> list[Path]:
    return _paths(repo_root, SURFACES)


@pytest.fixture(scope="module")
def modules_outside_the_domain(repo_root: Path) -> list[Path]:
    return _paths(repo_root, OUTSIDE_THE_DOMAIN)


# --------------------------------------------------------------------------
# The grep half
# --------------------------------------------------------------------------


def test_the_surfaces_exist_to_be_checked(surface_modules: list[Path]) -> None:
    """A guard over nothing is a guard that passes for the wrong reason."""
    assert len(surface_modules) > 5


def test_no_rule_identifier_is_spelled_outside_the_domain(
    modules_outside_the_domain: list[Path],
) -> None:
    """A stable `rule_id` in code outside the domain is a rule decided there."""
    for module in modules_outside_the_domain:
        leaked = _code_strings(_tree(module)) & set(RULE_IDS)
        assert not leaked, f"{module} spells rule identifiers {sorted(leaked)} in code"


def test_no_surface_reads_a_constraint_field(surface_modules: list[Path]) -> None:
    """Comparing a budget requires naming it; no surface names one."""
    for module in surface_modules:
        named = _names(_tree(module)) & set(CONSTRAINT_FIELDS)
        assert not named, f"{module} reads constraint fields {sorted(named)}"


def test_no_surface_constructs_a_verdict(surface_modules: list[Path]) -> None:
    """Rendering a violation is fine; manufacturing one is the rule moving."""
    for module in surface_modules:
        built = _called(_tree(module)) & set(VERDICT_TYPES)
        assert not built, f"{module} constructs {sorted(built)}"


def test_no_surface_decides_a_severity(surface_modules: list[Path]) -> None:
    """Severity is stamped by the registry and configured per project — never here."""
    for module in surface_modules:
        assert "Severity" not in _names(_tree(module)), f"{module} decides a severity"


def test_the_rules_themselves_all_live_in_one_package(repo_root: Path) -> None:
    """The positive half: every registered rule identifier is spelled in the domain."""
    spelled: set[str] = set()
    for module in _modules(repo_root, DOMAIN):
        spelled |= _code_strings(_tree(module))
    assert set(RULE_IDS) <= spelled


# --------------------------------------------------------------------------
# The import-linter half
# --------------------------------------------------------------------------


def test_the_layering_contracts_back_the_grep(repo_root: Path) -> None:
    """The grep catches a copy; these contracts catch a reach (D10)."""
    config = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    types = {contract["type"] for contract in config["tool"]["importlinter"]["contracts"]}
    assert {"layers", "forbidden", "stdlib_only"} <= types
