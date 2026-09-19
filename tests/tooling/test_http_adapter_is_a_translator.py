"""Task 1.3 — the HTTP adapter is a translator, asserted over the syntax tree.

The MCP adapter has the same guard (`test_mcp_adapter_is_a_formatter.py`) and
for the same reason, but this is the surface with the most to lose. A "Validate"
button that disagrees with `canon validate` is *visible to artists*, and it is
the exact failure this product exists to prevent — the design says so in one
line: *"if it grows logic, the product acquires the exact bug it was built to
prevent, and this time the disagreement is visible to artists."*

Three halves, and the third is what task 1.3 asks for beyond the MCP test:

* **it imports nothing from `adapters/outbound/`** — import-linter enforces it
  for the package (D10) and again for this one by name; asserted here per
  module, so the failure names the file;
* **it contains no conditional on specification content** — a walk of every
  `if`, `while`, ternary, comprehension guard and `assert` for a word from the
  specification's vocabulary. Branching on whether a *page of results* exists is
  translation; branching on whether a *socket* exists is deciding;
* **the guard bites** — the same check run over a module that does branch on a
  triangle budget, which fails. A guard nobody has seen fail is a guard nobody
  knows works.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_mcp_adapter_is_a_formatter import SPEC_VOCABULARY

HTTP = Path("libs/cybercanon/adapters/inbound/http")
OUTBOUND = "cybercanon.adapters.outbound"

CONDITIONALS = (ast.If, ast.IfExp, ast.While, ast.Assert)

A_ROUTER_THAT_DECIDES = '''\
"""A router that took a shortcut instead of adding a rule."""


def budget_report(asset):
    if asset.constraints.tri_budget < 12000:
        return "fine"
    return "too heavy"
'''
"""What the guard has to catch. Staged as text, never written into the package."""


def _modules(repo_root: Path) -> Iterator[Path]:
    yield from sorted((repo_root / HTTP).rglob("*.py"))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _tests(tree: ast.Module) -> Iterator[tuple[int, ast.expr]]:
    """Every expression the module branches on, with the line it is written at."""
    for node in ast.walk(tree):
        if isinstance(node, CONDITIONALS):
            yield node.lineno, node.test
        elif isinstance(node, ast.comprehension):
            for guard in node.ifs:
                yield guard.lineno, guard


def _mentioned(expression: ast.expr) -> set[str]:
    """Identifiers, attribute names and string literals inside one test."""
    words: set[str] = set()
    for node in ast.walk(expression):
        if isinstance(node, ast.Name):
            words.add(node.id)
        elif isinstance(node, ast.Attribute):
            words.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            words.add(node.value)
    return words


def _imported(tree: ast.Module) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _decisions(tree: ast.Module) -> list[str]:
    """Every branch in this tree that is about specification content."""
    return [
        f"{line} branches on {sorted(named)}"
        for line, test in _tests(tree)
        if (named := _mentioned(test) & SPEC_VOCABULARY)
    ]


@pytest.fixture(scope="module")
def http_modules(repo_root: Path) -> list[Path]:
    return list(_modules(repo_root))


def test_the_adapter_exists_to_be_checked(http_modules: list[Path]) -> None:
    """A guard over nothing is a guard that passes for the wrong reason."""
    assert {path.name for path in http_modules} >= {"app.py", "health.py"}


def test_the_adapter_imports_nothing_from_an_outbound_adapter(
    http_modules: list[Path],
) -> None:
    """An inbound adapter that reached an outbound one would be wiring, not translating."""
    for module in http_modules:
        reached = {name for name in _imported(_tree(module)) if name.startswith(OUTBOUND)}
        assert not reached, f"{module} imports {sorted(reached)}"


def test_the_adapter_contains_no_conditional_on_specification_content(
    http_modules: list[Path],
) -> None:
    """Branch on a page of results all you like; branching on a socket is deciding."""
    offences = [
        f"{module}:{offence}" for module in http_modules for offence in _decisions(_tree(module))
    ]
    assert not offences, (
        "the HTTP adapter is a thin translator (`http-api`): it maps a request "
        "onto a use case call and renders the outcome. A decision about "
        f"specification content belongs in the domain, not here — {offences}"
    )


def test_the_guard_catches_a_router_that_decides() -> None:
    """Task 1.3: verify it fails when such a conditional is introduced."""
    offences = _decisions(ast.parse(A_ROUTER_THAT_DECIDES))

    assert offences, "the guard did not notice a router branching on a triangle budget"
    assert "tri_budget" in offences[0]


def test_the_guard_catches_an_outbound_import() -> None:
    """The other half of the same proof, over the same staged module."""
    reaching = ast.parse(f"from {OUTBOUND}.postgres import rows\n")

    assert {name for name in _imported(reaching) if name.startswith(OUTBOUND)}
