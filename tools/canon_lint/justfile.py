"""A small justfile reader, so the project's conventions can be tested as data.

`just check` is the contract between a developer's machine and CI. Tests that
assert things about it need to read recipe names, dependencies and bodies, and
shelling out to `just --summary` would only tell them the names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RECIPE_HEADER = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_-]*)(?P<params>[^:=\n]*):(?!=)(?P<deps>.*)$"
)


@dataclass(frozen=True)
class Recipe:
    """One justfile recipe: the recipes it depends on, and the lines it runs."""

    name: str
    dependencies: tuple[str, ...] = ()
    body: tuple[str, ...] = ()


def parse_justfile(text: str) -> dict[str, Recipe]:
    """Parse recipe names, dependencies and bodies out of a justfile."""
    recipes: dict[str, Recipe] = {}
    current: str | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0].isspace():
            if current is not None:
                recipes[current] = _with_body_line(recipes[current], line.strip())
            continue
        header = _RECIPE_HEADER.match(line)
        current = header.group("name") if header else None
        if header is not None and current is not None:
            recipes[current] = Recipe(current, tuple(header.group("deps").split()))
    return recipes


def _with_body_line(recipe: Recipe, line: str) -> Recipe:
    return Recipe(recipe.name, recipe.dependencies, (*recipe.body, line))
