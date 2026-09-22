"""The `ViewIndex` port — which asset, slot and revision a content hash belongs to (D3).

D3 splits one question in two, and the split is the whole of this port:

* **the bytes** live in blob storage under their content hash, which is what
  makes mirroring idempotent, an identical image uploaded to two assets cost one
  object, and orphan collection a set difference against the repository;
* **what that hash *is*** — which asset, which slot, which revision — is a row
  here, written when the commit is observed and **reconstructible by walking the
  repository**.

That second half is why this is an index and not a record: *"a bucket full of
hash-named objects is unreadable without the index — acceptable precisely
because the index is rebuildable and the repository is the truth."* Every read
that cannot find a mapping falls back to the repository rather than reporting
the view as missing, so a dropped index costs a rebuild and never an answer.

It is deliberately **not** part of :class:`~cybercanon.application.ports.search_index.SearchIndex`.
That port answers *which asset does a person mean*; this one answers *what are
these bytes*, and a port that did both would be a port nobody could drop half of.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cybercanon.domain.revisions import ContentHash


@dataclass(frozen=True)
class ViewRow:
    """One mirrored view revision, as the index knows it.

    `digest` is the key the bytes are stored under; everything else is what the
    repository said about them at the revision the mirror observed. `path` is
    kept because it is the fallback: a read that finds no row asks the
    repository for this path, and a row whose path is wrong is a row that can be
    rebuilt.
    """

    project: str
    asset_id: str
    slot: str
    revision: str
    path: str
    digest: ContentHash
    byte_size: int = 0


class ViewIndex(Protocol):
    """Remembers what a mirrored blob is, so a hash can be read backwards."""

    def record(self, row: ViewRow) -> None:
        """Write this mapping. Recording the same row twice is the same fact.

        Idempotent for the reason the mirror itself is: a second mirroring pass
        over an unchanged repository must write nothing new, or *"re-running it
        is a no-op"* would be false one layer up.
        """
        ...

    def row_for(self, project: str, digest: ContentHash) -> ViewRow | None:
        """What those bytes are in this project, or ``None`` — never a guess."""
        ...

    def rows_for(self, project: str, asset_id: str) -> tuple[ViewRow, ...]:
        """Every recorded view revision of one asset, in a deterministic order."""
        ...

    def forget_project(self, project: str) -> None:
        """Drop this project's rows — what a rebuild does before it runs."""
        ...


__all__ = ["ViewIndex", "ViewRow"]
