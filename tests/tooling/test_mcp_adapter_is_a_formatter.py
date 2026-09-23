"""Task 5.5 — D1, asserted over the syntax tree rather than trusted to review.

The MCP adapter has two jobs: map tool arguments onto a use case call, and
render the result as prose. Nothing else. This is the change where drift starts,
because prose rendering *feels* like a good place to "just add" a fallback — a
default triangle budget when none is declared, a status when the file omits one,
a severity when the report seems harsh — and each of those would be the CLI and
the agent quietly disagreeing about what the specification says.

Two halves, deliberately different in kind, because either alone is evadable:

* **it imports nothing from `adapters/outbound/`** — `import-linter` enforces
  this for the whole inbound package (D10); asserted here too, per module, so
  the failure names the file rather than a contract;
* **it contains no conditional on specification content** — a grep over the
  parsed tree for any `if`, `while`, ternary, comprehension guard or `assert`
  whose test mentions a word from the specification's vocabulary. Branching on
  whether a *table row* exists is formatting; branching on whether a *socket*
  exists is deciding, and the second is the domain's.

The adapter is also covered by `tests/tooling/test_rule_logic_stays_in_the_domain.py`,
which catches a rule copied into any surface. This module is the part of D1 that
is specific to the formatter claim.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

MCP = Path("libs/cybercanon/adapters/inbound/mcp")
OUTBOUND = "cybercanon.adapters.outbound"

SPEC_VOCABULARY = frozenset(
    {
        # the authored blocks
        "concept",
        "design",
        "constraints",
        "annotations",
        "links",
        "silhouette_rules",
        "views",
        "palette",
        "role",
        "states",
        "sockets",
        "required_sockets",
        "socket",
        "aliases",
        "status",
        "read_distance_m",
        "silhouette_priority",
        "scale_ref",
        # the engineering values a fallback would invent
        "tri_budget",
        "lods",
        "max_bones",
        "bone_count",
        "triangles",
        "unit_scale",
        "up_axis",
        "uv_sets",
        "materials",
        "empties",
        "clips",
        "frame_rate",
        "naming",
        "pivot",
        "expects_skinning",
        "transforms_applied",
        "required_clips",
        # the verdict
        "severity",
        "passed",
        "violations",
        "rule_id",
    }
)
"""Words that make a branch a decision about an asset rather than about layout."""

CONDITIONALS = (ast.If, ast.IfExp, ast.While, ast.Assert)


def _modules(repo_root: Path) -> Iterator[Path]:
    yield from sorted((repo_root / MCP).rglob("*.py"))


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


@pytest.fixture(scope="module")
def mcp_modules(repo_root: Path) -> list[Path]:
    return list(_modules(repo_root))


def test_the_adapter_exists_to_be_checked(mcp_modules: list[Path]) -> None:
    """A guard over nothing is a guard that passes for the wrong reason.

    `writes.py` is named here for task 4.7: the write tools have the most to
    gain from a shortcut — *"just check whether the budget is actually
    reachable before recording this"* — so the guard has to be known to cover
    them rather than assumed to.
    """
    assert len(mcp_modules) >= 4
    assert {path.name for path in mcp_modules} >= {"tools.py", "rendering.py", "writes.py"}


def test_the_adapter_imports_nothing_from_an_outbound_adapter(mcp_modules: list[Path]) -> None:
    """An inbound adapter that reached an outbound one would be wiring, not formatting."""
    for module in mcp_modules:
        reached = {name for name in _imported(_tree(module)) if name.startswith(OUTBOUND)}
        assert not reached, f"{module} imports {sorted(reached)}"


def test_the_adapter_contains_no_conditional_on_specification_content(
    mcp_modules: list[Path],
) -> None:
    """Branch on a table row all you like; branching on a socket is deciding."""
    offences = [
        f"{module}:{line} branches on {sorted(named)}"
        for module in mcp_modules
        for line, test in _tests(_tree(module))
        if (named := _mentioned(test) & SPEC_VOCABULARY)
    ]
    assert not offences, (
        "the MCP adapter is a formatter (D1): it maps tool arguments onto a use "
        "case call and renders prose. A decision about specification content "
        f"belongs in the domain, not here — {offences}"
    )


def test_the_vocabulary_is_real(repo_root: Path) -> None:
    """The guard is only worth anything if these words appear in the core at all."""
    core = (repo_root / "libs" / "cybercanon" / "domain").rglob("*.py")
    spelled = {
        node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
        for module in core
        for node in ast.walk(_tree(module))
        if isinstance(node, ast.Name | ast.Attribute)
    }
    assert len(SPEC_VOCABULARY & spelled) > 20
