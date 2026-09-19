"""Task 1.3 — the HTTP adapter is a translator, asserted over the syntax tree.

The MCP adapter has the same guard (`test_mcp_adapter_is_a_formatter.py`) and
for the same reason, but this is the surface with the most to lose. A "Validate"
button that disagrees with `canon validate` is *visible to artists*, and it is
the exact failure this product exists to prevent — the design says so in one
line: *"if it grows logic, the product acquires the exact bug it was built to
prevent, and this time the disagreement is visible to artists."*

Five halves now, and the last two are task 9.2's structural half — D10's single
mapping, asserted rather than reviewed:

* **it imports nothing from `adapters/outbound/`** — import-linter enforces it
  for the package (D10) and again for this one by name; asserted here per
  module, so the failure names the file;
* **it contains no conditional on specification content** — a walk of every
  `if`, `while`, ternary, comprehension guard and `assert` for a word from the
  specification's vocabulary. Branching on whether a *page of results* exists is
  translation; branching on whether a *socket* exists is deciding;
* **no route handler catches an exception** — the one `except` in this package
  is the middleware in `outcomes.py`, and D10 says why: *"a per-router
  `try/except` satisfies that on the day it is written and stops doing so at the
  fourth endpoint"*;
* **no route handler writes a status code** — every status comes from
  `outcomes.STATUSES`, so two endpoints producing the same outcome cannot
  disagree about what it is;
* **the guard bites** — the same checks run over modules that do branch on a
  triangle budget, swallow an exception and answer with a hand-written number.
  A guard nobody has seen fail is a guard nobody knows works.
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

A_HANDLER_THAT_DECIDES_FOR_ITSELF = '''\
"""A handler that grew its own error handling and its own status code."""


@router.get("/projects/{project}/assets")
async def assets(project):
    try:
        return JSONResponse(status_code=200, content=listing(project))
    except Exception:
        return JSONResponse(status_code=500, content={"error": "oops"})
'''
"""Both halves of task 9.2's structural claim, in the smallest module that has them."""

ROUTE_DECORATORS = frozenset({"get", "post", "put", "patch", "delete", "head", "api_route"})
"""The decorators that make a function a route handler, whatever it is called."""

STATUS_RANGE = range(100, 600)
"""What an integer literal has to be in before it is plausibly a status code."""


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


def _handlers(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function registered as a route, found by how it is decorated."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _is_route(node):
            yield node


def _is_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in ROUTE_DECORATORS
        for decorator in node.decorator_list
    )


def _catches(node: ast.AST) -> list[int]:
    """The lines at which this function catches something."""
    return [child.lineno for child in ast.walk(node) if isinstance(child, ast.Try)]


def _status_literals(node: ast.AST) -> list[int]:
    """Integer literals inside this function that look like status codes."""
    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant)
        and isinstance(child.value, int)
        and not isinstance(child.value, bool)
        and child.value in STATUS_RANGE
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


def test_no_route_handler_catches_an_exception(http_modules: list[Path]) -> None:
    """Task 9.2: the only `except` in this package is the one middleware (D10)."""
    offences = [
        f"{module}:{handler.name} catches at line {line}"
        for module in http_modules
        for handler in _handlers(_tree(module))
        for line in _catches(handler)
    ]

    assert not offences, (
        "a router that catches an exception is a router deciding what kind of "
        "failure it was. That decision belongs to the outcome vocabulary and its "
        f"one middleware — {offences}"
    )


def test_no_route_handler_constructs_a_status_code(http_modules: list[Path]) -> None:
    """Task 9.2: every status comes from the one mapping, so two cannot disagree."""
    offences = [
        f"{module}:{handler.name} writes {sorted(set(literals))}"
        for module in http_modules
        for handler in _handlers(_tree(module))
        if (literals := _status_literals(handler))
    ]

    assert not offences, (
        "status codes are chosen in `outcomes.STATUSES` and nowhere else, so the "
        f"same outcome maps identically on every endpoint — {offences}"
    )


def test_the_guard_catches_a_handler_that_decides_for_itself() -> None:
    """Task 9.2: verify both halves fail when a handler grows them."""
    tree = ast.parse(A_HANDLER_THAT_DECIDES_FOR_ITSELF)
    (handler,) = _handlers(tree)

    assert _catches(handler)
    assert sorted(set(_status_literals(handler))) == [200, 500]


def test_the_adapter_has_route_handlers_to_check(http_modules: list[Path]) -> None:
    """A guard over no handlers is a guard that passes for the wrong reason."""
    found = [handler.name for module in http_modules for handler in _handlers(_tree(module))]

    assert len(found) > 5


def test_the_guard_catches_an_outbound_import() -> None:
    """The other half of the same proof, over the same staged module."""
    reaching = ast.parse(f"from {OUTBOUND}.postgres import rows\n")

    assert {name for name in _imported(reaching) if name.startswith(OUTBOUND)}
