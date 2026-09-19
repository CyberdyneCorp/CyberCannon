"""`PostgresDismissals` — the per-person dismissal flag, in the index (D9).

Index state on purpose and losable on purpose. Everything a person needs to see
an unread item — the request, its assignee, its state, its attribution — is
repository content and is rebuilt from the working copy; what lives here is only
*whether they have looked at it yet*, and D9 accepts that a rebuild forgets it.

Dismissing twice is the same fact rather than a second one, so the write is an
upsert keyed by (project, actor, subject). A store that raised on the second
dismissal would turn a double-click into an error.
"""

from __future__ import annotations

import psycopg

from cybercanon.application.ports.dismissals import Dismissal
from cybercanon.domain.identity import ActorId


class PostgresDismissals:
    """Dismissal flags in PostgreSQL, keyed by project, person and subject."""

    def __init__(self, dsn: str | None = None, *, connection: psycopg.Connection | None = None):
        if connection is None and not dsn:
            raise ValueError("a PostgresDismissals needs a dsn or an open connection")
        self._owned = connection is None
        self._connection = connection or psycopg.connect(str(dsn), autocommit=True)
        self._connection.autocommit = True

    def close(self) -> None:
        if self._owned:
            self._connection.close()

    def __enter__(self) -> PostgresDismissals:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def dismiss(self, dismissal: Dismissal) -> None:
        """Record it, keeping the first moment it was dismissed."""
        self._connection.execute(
            "INSERT INTO dismissals (project, actor, subject, dismissed_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (project, actor, subject) DO NOTHING",
            [dismissal.project, str(dismissal.actor), dismissal.subject, dismissal.at],
        )

    def dismissed_by(self, actor: ActorId, project: str) -> frozenset[str]:
        """Every subject this person has dismissed in this project."""
        rows = self._connection.execute(
            "SELECT subject FROM dismissals WHERE actor = %s AND project = %s",
            [str(actor), project],
        ).fetchall()
        return frozenset(str(row[0]) for row in rows)


__all__ = ["PostgresDismissals"]
