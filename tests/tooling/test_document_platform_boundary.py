"""Tasks 1.5 and 5.6 — the two boundaries that can only be checked structurally.

Both are rules about what the code **cannot express**, so neither can be checked
by exercising anything:

* **The naming boundary (5.6).** No domain or application module mentions
  CyberArche by name. `DocumentPlatform` is the port and `adapters/outbound/arche`
  is the only place the product knows which document platform it is talking to —
  which is what makes D11's split real rather than aspirational, and what keeps
  a second platform a new adapter instead of a rewrite.
* **The one-way content boundary (1.5, D9).** No domain or application signature
  accepts a document body. *"The design block is never generated from the
  document"* is enforced by nothing if the body is reachable — somebody
  eventually adds a helpful "pre-fill from doc" button — so the temptation is
  made unimplementable without a port change that shows up in review.

A grep and an AST walk rather than a convention, because a convention is exactly
what the next person will not know about.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.tooling

PLATFORM_NAME = re.compile(r"\bcyber\s?arche\b|\barche\b", re.IGNORECASE)
"""How the document platform would be named if it leaked out of its adapter.

Word-bounded on purpose: `searches` contains those five letters, and a guard
that fired on it would be deleted by the second person who hit it.
"""

BODY_PARAMETERS = frozenset(
    {"body", "document_body", "contents", "blocks", "prose", "markdown", "html"}
)
"""Parameter names that would mean a document's text had crossed the boundary."""

ALLOWED_BODY_PARAMETERS = frozenset({"content", "contents"})
"""`content` is the repository's own file bytes and predates this change.

It is named here rather than removed from the set above so that the exception is
visible: what D9 forbids is a *document's* body reaching a signature, and the
bytes of an `asset.yaml` are the thing this product is made of.
"""


CORE = ("domain", "application")

SIGNATURE_LAYERS = (
    "domain",
    "application/ports",
    "application/use_cases",
)
"""Where D9's signature rule applies: the core, minus the in-memory fakes.

`application/testing` is excluded deliberately. A fake **is** a document
platform, so it holds the bodies a real one holds — that is what makes a search
fake answer anything. What D9 forbids is a *CyberCanon* use case accepting one.
"""


def _modules(root: Path, layer: str) -> tuple[Path, ...]:
    return tuple(sorted((root / "libs" / "cybercanon" / layer).rglob("*.py")))


def test_no_domain_or_application_module_names_cyberarche(repo_root: Path) -> None:
    offenders = [
        f"{path.relative_to(repo_root)} mentions {PLATFORM_NAME.search(text).group()!r}"
        for layer in CORE
        for path in _modules(repo_root, layer)
        if PLATFORM_NAME.search(text := path.read_text(encoding="utf-8"))
    ]

    assert not offenders, (
        "the core must not know which document platform it talks to (D11): " + "; ".join(offenders)
    )


def test_the_naming_guard_is_over_something_that_could_fail(repo_root: Path) -> None:
    """A guard over nothing passes for the wrong reason: the adapter *does* name it."""
    adapter = repo_root / "libs" / "cybercanon" / "adapters" / "outbound" / "arche" / "platform.py"

    assert PLATFORM_NAME.search(adapter.read_text(encoding="utf-8"))


def test_no_domain_or_application_signature_accepts_a_document_body(
    repo_root: Path,
) -> None:
    """D9, as an AST walk over every function the core defines."""
    offenders = [
        f"{path.relative_to(repo_root)}:{name} takes {parameter!r}"
        for layer in SIGNATURE_LAYERS
        for path in _modules(repo_root, layer)
        for name, parameter in _body_parameters(path)
    ]

    assert not offenders, "no use case may accept a document's body (D9): " + "; ".join(offenders)


def _body_parameters(path: Path) -> Iterator[tuple[str, str]]:
    """Every public function in this module that names a document's body."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name.startswith("_"):
            continue
        named = {argument.arg for argument in _arguments(node)}
        for parameter in sorted((named & BODY_PARAMETERS) - ALLOWED_BODY_PARAMETERS):
            yield node.name, parameter


def test_the_port_declares_no_method_that_returns_a_document(repo_root: Path) -> None:
    """The port is the door, so the absence is asserted on the port itself."""
    port = repo_root / "libs" / "cybercanon" / "application" / "ports" / "document_platform.py"
    tree = ast.parse(port.read_text(encoding="utf-8"))
    protocol = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "DocumentPlatform"
    )

    methods = {
        node.name
        for node in protocol.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }

    assert methods == {"resolve", "create", "search", "revisions"}


def _arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[ast.arg, ...]:
    arguments = node.args
    return (
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
        *([arguments.vararg] if arguments.vararg else []),
        *([arguments.kwarg] if arguments.kwarg else []),
    )
