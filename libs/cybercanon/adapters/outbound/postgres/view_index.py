"""`PostgresViewIndex` — the hash-to-view mapping, in the rebuildable index (D3).

Index state on purpose and losable on purpose. Everything that makes a view a
view — the file, its path, its history, who committed it — is repository
content; what lives here is only *which view a digest belongs to*, so that a
bucket of hash-named objects can be read backwards without walking the
repository for every request.

Recording the same row twice is the same fact, so the write is an upsert keyed
by (project, digest). A store that raised on the second mirroring pass would
make *"re-running it is a no-op"* false one layer up.
"""

from __future__ import annotations

import psycopg

from cybercanon.application.ports.view_index import ViewRow
from cybercanon.domain.revisions import ContentHash


class PostgresViewIndex:
    """View rows in PostgreSQL, keyed by project and content digest."""

    def __init__(self, dsn: str | None = None, *, connection: psycopg.Connection | None = None):
        if connection is None and not dsn:
            raise ValueError("a PostgresViewIndex needs a dsn or an open connection")
        self._owned = connection is None
        self._connection = connection or psycopg.connect(str(dsn), autocommit=True)
        self._connection.autocommit = True

    def close(self) -> None:
        if self._owned:
            self._connection.close()

    def __enter__(self) -> PostgresViewIndex:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def record(self, row: ViewRow) -> None:
        """Write the mapping, replacing whatever that digest was last said to be."""
        self._connection.execute(
            "INSERT INTO concept_views (project, digest, asset_id, slot, revision, path, "
            "byte_size) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (project, digest) DO UPDATE SET asset_id = EXCLUDED.asset_id, "
            "slot = EXCLUDED.slot, revision = EXCLUDED.revision, path = EXCLUDED.path, "
            "byte_size = EXCLUDED.byte_size",
            [
                row.project,
                row.digest.value,
                row.asset_id,
                row.slot,
                row.revision,
                row.path,
                row.byte_size,
            ],
        )

    def row_for(self, project: str, digest: ContentHash) -> ViewRow | None:
        """What those bytes are in this project, or ``None`` — never a guess."""
        found = self._connection.execute(
            "SELECT asset_id, slot, revision, path, byte_size FROM concept_views "
            "WHERE project = %s AND digest = %s",
            [project, digest.value],
        ).fetchone()
        return _row(project, digest, found) if found else None

    def rows_for(self, project: str, asset_id: str) -> tuple[ViewRow, ...]:
        """Every recorded view revision of one asset, ordered by slot then revision."""
        found = self._connection.execute(
            "SELECT digest, asset_id, slot, revision, path, byte_size FROM concept_views "
            "WHERE project = %s AND asset_id = %s ORDER BY slot, revision",
            [project, asset_id],
        ).fetchall()
        return tuple(_row(project, ContentHash(str(row[0])), row[1:]) for row in found)

    def forget_project(self, project: str) -> None:
        """Drop this project's rows — what a rebuild does before it runs."""
        self._connection.execute("DELETE FROM concept_views WHERE project = %s", [project])


def _row(project: str, digest: ContentHash, values) -> ViewRow:
    asset_id, slot, revision, path, byte_size = values
    return ViewRow(
        project=project,
        asset_id=str(asset_id),
        slot=str(slot),
        revision=str(revision),
        path=str(path),
        digest=digest,
        byte_size=int(byte_size),
    )


__all__ = ["PostgresViewIndex"]
