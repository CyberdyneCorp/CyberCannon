"""The single explicitly-marked pending list — the only escape from gate two.

D3 accepts that adding a requirement to a spec breaks the build until someone
implements its step. The escape hatch is this one file, reviewed like any other
exception: a scenario listed here is *pending*, never silently skipped, and it is
counted in the traceability report on every ``just check`` so the number is a
live progress measure rather than a place to hide.

Format — one scenario per line, ``<capability> :: <scenario name>``. ``#``
introduces a comment; blank lines are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PENDING_PATH = Path("tests/bdd/pending.txt")
SEPARATOR = " :: "

HEADER = """\
# Pending scenarios — the single explicitly-marked escape from the step-definition
# gate (add-test-strategy, D3). A line here says: this generated scenario has no
# step definition yet, and that is a reviewed exception rather than an accident.
#
# Format: <capability> :: <scenario name>, exactly as the spec delta names them.
#
# Rules the build enforces (tests/bdd/test_traceability.py):
#   * a generated scenario that is neither executing nor listed here FAILS;
#   * a line naming a scenario that now executes FAILS — delete the line;
#   * a line naming a scenario no spec contains FAILS — the spec moved.
#
# This list only ever shrinks. Regenerate it from scratch with
# `python scripts/gen_features.py --bootstrap-pending`, which is a one-time
# bootstrap, never part of `just check`.
"""


@dataclass(frozen=True)
class PendingEntry:
    """One reviewed exception: a scenario with no step definition yet."""

    capability: str
    scenario: str
    line: int

    @property
    def key(self) -> tuple[str, str]:
        return (self.capability, self.scenario)


class PendingListError(Exception):
    """The pending list itself is malformed. It is data the gates trust."""


def load(path: Path) -> tuple[PendingEntry, ...]:
    """Parse the pending list. A missing file means nothing is pending."""
    if not path.is_file():
        return ()
    entries: list[PendingEntry] = []
    seen: dict[tuple[str, str], int] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        entry = _parse_line(path, raw, number)
        if entry is None:
            continue
        if (first := seen.get(entry.key)) is not None:
            raise PendingListError(f"{path}:{number}: duplicate entry (first seen at line {first})")
        seen[entry.key] = number
        entries.append(entry)
    return tuple(entries)


def _parse_line(path: Path, raw: str, number: int) -> PendingEntry | None:
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    if SEPARATOR not in line:
        raise PendingListError(
            f"{path}:{number}: expected '<capability>{SEPARATOR}<scenario name>', got {line!r}"
        )
    capability, scenario = line.split(SEPARATOR, 1)
    return PendingEntry(capability=capability.strip(), scenario=scenario.strip(), line=number)


def render(keys: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> str:
    """The text of a pending list holding exactly these scenarios."""
    lines = [f"{capability}{SEPARATOR}{scenario}" for capability, scenario in sorted(set(keys))]
    return HEADER + "\n" + "\n".join(lines) + ("\n" if lines else "")
