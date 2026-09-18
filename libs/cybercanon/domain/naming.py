"""Naming templates — `SM_{asset}_LOD{n}`, not a regular expression (D8).

Artists and designers author `asset.yaml`. A regex in that file is a literacy
tax on exactly the people the tool most needs to keep, so the authored form is a
template with named placeholders and the domain expands it into a matcher here.

Two placeholder shapes, and the difference matters:

* **bound** — `{asset}` and `{state}` are substituted with a known value, so
  they become literal text in the matcher;
* **numeric** — `{n}` (and its alias `{lod}`) stands for a level index. When
  matching it accepts any run of digits, and :func:`lod_index` reads the index
  back out, which is how a per-LOD triangle budget knows which LOD it is looking
  at without the file name being parsed anywhere.

Matching is case-insensitive: `SM_MechScout_LOD0` satisfies an asset id of
`mech_scout`. Teams capitalise object names and asset ids differently and a
rejection over a capital letter is noise, not a defect.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
"""One `{name}` placeholder in an authored template."""

NUMERIC_PLACEHOLDERS = frozenset({"n", "lod", "level"})
"""Placeholders that stand for a level index rather than a name."""

LOD_GROUP = "lod_index"
_NUMERIC_PATTERN = rf"(?P<{LOD_GROUP}>\d+)"
_FREE_PATTERN = r"[^\s]+"


def placeholders(template: str) -> tuple[str, ...]:
    """Every placeholder the template declares, in the order it declares them."""
    return tuple(match.group(1) for match in PLACEHOLDER.finditer(template))


def expand(template: str, values: Mapping[str, object] | None = None) -> str:
    """The template with its bound placeholders substituted.

    An unbound placeholder is left standing — `SM_{asset}_LOD{n}` expanded with
    only `asset` is still a template, and saying so is more useful than
    inventing an index.
    """
    bound = _text_values(values)
    return PLACEHOLDER.sub(lambda match: bound.get(match.group(1), match.group(0)), template)


def matcher(template: str, values: Mapping[str, object] | None = None) -> re.Pattern[str]:
    """The compiled matcher this template denotes, with `values` bound as literals."""
    bound = _text_values(values)
    pattern = "".join(_segment(part, bound) for part in _split(template))
    return re.compile(rf"^{pattern}$", re.IGNORECASE)


def matches(template: str, name: str, values: Mapping[str, object] | None = None) -> bool:
    """Whether `name` satisfies the template."""
    return matcher(template, values).match(name) is not None


def lod_index(template: str, name: str, values: Mapping[str, object] | None = None) -> int | None:
    """The level index `name` declares under this template, if it declares one."""
    found = matcher(template, values).match(name)
    if found is None:
        return None
    captured = found.groupdict().get(LOD_GROUP)
    return int(captured) if captured is not None else None


def _split(template: str) -> tuple[tuple[bool, str], ...]:
    """The template as `(is_placeholder, text)` parts, in order."""
    parts: list[tuple[bool, str]] = []
    cursor = 0
    for match in PLACEHOLDER.finditer(template):
        if match.start() > cursor:
            parts.append((False, template[cursor : match.start()]))
        parts.append((True, match.group(1)))
        cursor = match.end()
    if cursor < len(template):
        parts.append((False, template[cursor:]))
    return tuple(parts)


def _segment(part: tuple[bool, str], bound: Mapping[str, str]) -> str:
    is_placeholder, text = part
    if not is_placeholder:
        return re.escape(text)
    if text in bound:
        return re.escape(bound[text])
    return _NUMERIC_PATTERN if text in NUMERIC_PLACEHOLDERS else _FREE_PATTERN


def _text_values(values: Mapping[str, object] | None) -> Mapping[str, str]:
    return {key: str(value) for key, value in (values or {}).items() if value is not None}


__all__ = [
    "LOD_GROUP",
    "NUMERIC_PLACEHOLDERS",
    "PLACEHOLDER",
    "expand",
    "lod_index",
    "matcher",
    "matches",
    "placeholders",
]
