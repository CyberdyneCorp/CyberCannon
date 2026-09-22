"""The in-memory `ViewIndex` — the hash-to-view mapping, in a dictionary.

The real store is a table the index owns; this is the same behaviour a unit test
can hold. Both are rebuildable by definition (D3), and both are keyed the same
way — `(project, digest)` — so a fake that answered a hash it was never given
would make every fallback-to-the-repository test green over a lookup that cannot
happen.
"""

from __future__ import annotations

from cybercanon.application.ports.view_index import ViewRow
from cybercanon.domain.revisions import ContentHash


class InMemoryViewIndex:
    """What each mirrored blob is, per project."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], ViewRow] = {}

    def record(self, row: ViewRow) -> None:
        self._rows[(row.project, row.digest.value)] = row

    def row_for(self, project: str, digest: ContentHash) -> ViewRow | None:
        return self._rows.get((project, digest.value))

    def rows_for(self, project: str, asset_id: str) -> tuple[ViewRow, ...]:
        found = (
            row
            for (held, _), row in self._rows.items()
            if held == project and row.asset_id == asset_id
        )
        return tuple(sorted(found, key=lambda row: (row.slot, row.revision)))

    def forget_project(self, project: str) -> None:
        for key in [key for key in self._rows if key[0] == project]:
            del self._rows[key]

    def clear(self) -> None:
        """Forget everything — what dropping the index does (D3)."""
        self._rows.clear()


__all__ = ["InMemoryViewIndex"]
