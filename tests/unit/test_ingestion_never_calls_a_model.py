"""Task 7.1 — ingestion consults no language or vision model, and a test says so (D12).

*"Ingestion must not call a model"* is an **absence**, and `add-mcp-read-server`'s
D6 already established what happens to an absence enforced by absence: it lasts
until the first person who thinks auto-describing on upload would be a nice
touch. So there are three halves here rather than one:

* **structural** — a walk of the ingestion package's syntax tree, asserting it
  names no model port and imports nothing that could be one;
* **behavioural** — a full ingestion run with every port that *could* be a model
  wired to something that raises on any access at all, so a call added through a
  route the syntax tree cannot see still fails;
* **the guard bites** — the same structural check run over a staged module that
  *does* import a model port, because a guard nobody has seen fail is a guard
  nobody knows works.

The model ports themselves arrive with `add-derived-metadata` in M4. Until they
do, the check is written against the names they will have and against the
package that would hold them, which is exactly the point: the day somebody adds
`from cybercanon.application.ports.llm import LLMPort` to this package, this
test fails and names the file.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases import ingest_views, view_mirror, view_revisions
from views_world import SCOUT_SPEC, a_spec, a_world

pytestmark = pytest.mark.unit

MODEL_NAMES = frozenset(
    {
        "LLMPort",
        "VisionPort",
        "llm",
        "vision",
        "describe",
        "completion",
        "chat_completion",
        "embedding",
        "suggest_aliases",
    }
)
"""Every name a model call would arrive under. Checked as names, not as strings."""

INGESTION_MODULES = (ingest_views, view_revisions, view_mirror)
"""The package `concept-ingestion` is implemented in. All of it, not one file."""

A_MODULE_THAT_ASKS_A_MODEL = '''\
"""A use case that grew a nice touch."""

from cybercanon.application.ports.llm import LLMPort


def ingest(content, llm: LLMPort):
    return llm.describe(content)
'''
"""What the guard has to catch. Staged as text, never written into the package."""


def _imported(tree: ast.Module) -> set[str]:
    """Every module and every imported name in one tree."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found |= {alias.name for alias in node.names}
    return found


def _named(tree: ast.Module) -> set[str]:
    """Every identifier and attribute this module mentions."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
    return found


def _offences(source: str) -> set[str]:
    """Every model name this source imports or mentions."""
    tree = ast.parse(source)
    parts = {part for module in _imported(tree) for part in module.split(".")}
    return (parts | _named(tree)) & MODEL_NAMES


@pytest.mark.parametrize("module", INGESTION_MODULES, ids=lambda module: module.__name__)
def test_the_ingestion_package_names_no_model_port(module: Any) -> None:
    offences = _offences(Path(module.__file__).read_text(encoding="utf-8"))

    assert not offences, (
        f"{module.__name__} names {sorted(offences)}. Ingestion SHALL complete with "
        "model access disabled; generated descriptions, tags and aliases are "
        "`derived-metadata`, invoked explicitly after the view exists."
    )


def test_the_guard_catches_a_module_that_asks_a_model() -> None:
    """A guard over nothing passes for the wrong reason."""
    assert _offences(A_MODULE_THAT_ASKS_A_MODEL) == {"llm", "LLMPort", "describe"}


class RaisesOnAnything:
    """A port that fails on any access at all — a model wired and unusable.

    Deliberately not a mock recording calls: a mock that was never called proves
    the same thing only if somebody remembers to assert it, and this cannot be
    used at all without the test failing on the spot.
    """

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"ingestion reached a model port: {name}")


def test_a_full_ingestion_completes_with_model_ports_wired_to_raise() -> None:
    """The behavioural half: run it with a model that explodes if it is touched."""
    world = a_world({SCOUT_SPEC: a_spec()})
    world.notes["llm"] = RaisesOnAnything()
    world.notes["vision"] = RaisesOnAnything()

    outcome = ran(world.ingest(uploads=(world.upload(),)))

    assert outcome.committed
    assert outcome.views[0].mirrored


def test_uploading_generates_no_description_tag_or_alias() -> None:
    """Task 7.2: the specification contains only what was uploaded or authored."""
    world = a_world()

    ran(world.ingest(uploads=(world.upload(),), name="Scout Mech"))

    written = next(
        content.decode() for path, content in world.files().items() if path.endswith("asset.yaml")
    )
    assert written.splitlines() == [
        "schema_version: 1",
        "id: mech_scout",
        "name: Scout Mech",
        "status: concept",
    ]
