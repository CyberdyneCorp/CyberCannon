"""`SqliteSearchIndex` — the rebuildable lookup as one git-ignored file (D7).

Standard library, a single file, no server and no credential: the MCP server is
a long-lived local process, so a full rescan per call would be waste, and a
database service would be a dependency a laptop off the VPN cannot satisfy. The
file lives under `.canon/` and is git-ignored, because it is **derived**: git is
the source of truth, and deleting this and running a rebuild is always a
complete recovery.

Two stores, deliberately, and the split is the one `.gitignore` already names:

* `.canon/index.sqlite` — the rows, plus an FTS5 index over identifiers, names,
  aliases, tags and descriptions;
* `.canon/queries.log` — zero-result search terms, appended as plain lines
  (D11). A person reads that file to decide which aliases to add, so it stays
  something a person can read without this tool, and nothing in it ever leaves
  the machine.

**Ranking is not reimplemented here.** :func:`~cybercanon.application.ports.search_index.rank`
is the cascade (D9) and this adapter sorts with it, exactly as the in-memory
fake does; the conformance suite runs both through one contract, so a query that
ordered results its own way would fail the build rather than the product. What
SQL does is *narrow*: the FTS5 table answers the ordinary token query without a
scan, and a substring scan completes it for the passes whose definition is a
substring a token index cannot express — a name *prefix* and a description
*substring*. Candidates are a superset; `rank` decides.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path

from cybercanon.application.ports.search_index import (
    FileFingerprint,
    IndexedAsset,
    RecordedMiss,
    SearchHit,
    rank,
)

CANON_DIRECTORY = ".canon"
INDEX_FILENAME = "index.sqlite"
QUERY_LOG_FILENAME = "queries.log"

INDEX_PATH = f"{CANON_DIRECTORY}/{INDEX_FILENAME}"
QUERY_LOG_PATH = f"{CANON_DIRECTORY}/{QUERY_LOG_FILENAME}"
"""Both are git-ignored: derived state never enters a review (task 4.3)."""

LIST_SEPARATOR = "\n"
"""How an ordered list of aliases or tags is stored in one column."""

FIELD_SEPARATOR = "\t"
"""How the query log separates a miss's project from its term."""

COLUMNS = (
    "project",
    "asset_id",
    "name",
    "status",
    "aliases",
    "tags",
    "description",
    "spec_path",
    "directory",
    "source_file",
    "engine_path",
    "discussion",
    "design_doc",
    "owner_art",
    "owner_design",
    "owner_code",
    "validated_export",
    "validated_at",
    "fingerprint_path",
    "fingerprint_size",
    "fingerprint_mtime_ns",
    "tags_key",
    "searchable",
)
"""Every stored column. `tags_key` and `searchable` are normalised copies.

Neither is information: they are the lower-cased forms the filters and the
substring scan compare against, kept beside the verbatim values so a row still
reads back exactly as it was written.
"""

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS assets (
        project TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        status TEXT,
        aliases TEXT NOT NULL DEFAULT '',
        tags TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        spec_path TEXT NOT NULL DEFAULT '',
        directory TEXT NOT NULL DEFAULT '',
        source_file TEXT,
        engine_path TEXT,
        discussion TEXT,
        design_doc TEXT,
        owner_art TEXT,
        owner_design TEXT,
        owner_code TEXT,
        validated_export TEXT,
        validated_at TEXT,
        fingerprint_path TEXT,
        fingerprint_size INTEGER,
        fingerprint_mtime_ns INTEGER,
        tags_key TEXT NOT NULL DEFAULT '',
        searchable TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (project, asset_id)
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(
        asset_id,
        name,
        aliases,
        tags,
        description,
        project UNINDEXED,
        tokenize = 'unicode61'
    )
    """,
)

SELECT_ROW = f"SELECT {', '.join(COLUMNS)} FROM assets"
"""Every statement selects the same columns, so one row shape reads back."""


class SqliteSearchIndex:
    """A project's indexed assets in one SQLite file, with FTS5 over their text."""

    def __init__(
        self,
        root: str | Path,
        *,
        database: str | Path | None = None,
        query_log: str | Path | None = None,
    ) -> None:
        """Open (and create, if needed) the index for the repository at `root`.

        The two paths are overridable so a test can point them somewhere else,
        but the default is the only one anything ships with: `.canon/` beside
        the working copy, which is where `.gitignore` expects them.
        """
        self._root = Path(root)
        self._database = Path(database) if database else self._root / INDEX_PATH
        self._query_log = Path(query_log) if query_log else self._root / QUERY_LOG_PATH
        self._database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._database, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        for statement in SCHEMA:
            self._connection.execute(statement)

    @property
    def database(self) -> Path:
        """Where the rows live — one file, deletable, rebuildable."""
        return self._database

    @property
    def query_log(self) -> Path:
        """Where zero-result terms are appended (D11). Never transmitted."""
        return self._query_log

    def close(self) -> None:
        """Release the file. A long-lived server closes on shutdown."""
        self._connection.close()

    def __enter__(self) -> SqliteSearchIndex:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- writing ---------------------------------------------------------

    def upsert(self, entry: IndexedAsset) -> None:
        """Write one asset's row, replacing whatever was there for that id."""
        values = _values(entry)
        placeholders = ", ".join("?" * len(COLUMNS))
        self._connection.execute(
            f"INSERT OR REPLACE INTO assets ({', '.join(COLUMNS)}) VALUES ({placeholders})",
            [values[column] for column in COLUMNS],
        )
        self._index_text(entry)

    def forget(self, asset_id: str, project: str | None = None) -> None:
        """Drop one row — a specification that was deleted or renamed."""
        clause, parameters = _scope(project)
        self._connection.execute(
            f"DELETE FROM assets WHERE asset_id = ?{clause}", [asset_id, *parameters]
        )
        self._connection.execute(
            f"DELETE FROM assets_fts WHERE asset_id = ?{clause}", [asset_id, *parameters]
        )

    def clear(self) -> None:
        """Drop everything, rows and recorded misses alike.

        The index is disposable by specification, and a `clear` that left the
        query log behind would make "deleting the index loses nothing" true in
        one direction only.
        """
        self._connection.execute("DELETE FROM assets")
        self._connection.execute("DELETE FROM assets_fts")
        self._query_log.unlink(missing_ok=True)

    # -- reading ---------------------------------------------------------

    def get(self, asset_id: str, project: str | None = None) -> IndexedAsset | None:
        """The row for that identifier, or ``None`` when nothing is indexed for it."""
        clause, parameters = _scope(project)
        found = self._connection.execute(
            f"{SELECT_ROW} WHERE asset_id = ?{clause} ORDER BY project, asset_id LIMIT 1",
            [asset_id, *parameters],
        ).fetchone()
        return _entry(found) if found is not None else None

    def list_assets(
        self,
        project: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
    ) -> tuple[IndexedAsset, ...]:
        """The project's assets matching every filter given, ordered by identifier.

        Filters combine rather than widen: every clause is `AND`-ed, because
        asking for status `modeling` *and* an art owner means both.
        """
        clauses, parameters = _filters(project, status, owner, tag)
        return tuple(self._rows(f"{SELECT_ROW}{_where(clauses)} ORDER BY asset_id", parameters))

    def search(self, term: str, project: str | None = None) -> tuple[SearchHit, ...]:
        """The ranked cascade of D9 over everything that could possibly match.

        The SQL narrows and :func:`rank` decides, so this adapter and the fake
        cannot order results differently.
        """
        if not term.strip():
            return ()
        return rank(self._candidates(term, project), term)

    def is_stale(self, asset_id: str, current: FileFingerprint | None) -> bool:
        """Whether the row for that asset no longer matches the file on disk (D8)."""
        entry = self.get(asset_id)
        return entry is None or entry.fingerprint != current

    # -- misses (D11) ----------------------------------------------------

    def record_miss(self, term: str, project: str | None = None) -> None:
        """Append a term that matched nothing to the local query log.

        Appended rather than counted in the database, so the file stays
        something a person can read with `cat` — the log's whole value is
        somebody reading it and deciding which aliases to add.
        """
        self._query_log.parent.mkdir(parents=True, exist_ok=True)
        line = f"{project or ''}{FIELD_SEPARATOR}{term}\n"
        with self._query_log.open("a", encoding="utf-8") as log:
            log.write(line)

    def misses(self, project: str | None = None) -> tuple[RecordedMiss, ...]:
        """Every recorded miss, ordered by term, with how often each was asked."""
        counted: dict[tuple[str, str], RecordedMiss] = {}
        for scope, term in self._logged():
            if project is not None and scope != project:
                continue
            key = (scope, term.strip().lower())
            recorded = counted.get(key)
            counted[key] = RecordedMiss(
                term=recorded.term if recorded else term,
                project=scope,
                count=recorded.count + 1 if recorded else 1,
            )
        return tuple(sorted(counted.values(), key=lambda miss: (miss.project, miss.term)))

    # -- internals -------------------------------------------------------

    def _rows(self, statement: str, parameters: list[object]) -> Iterator[IndexedAsset]:
        for row in self._connection.execute(statement, parameters):
            yield _entry(row)

    def _index_text(self, entry: IndexedAsset) -> None:
        """Keep the FTS5 table in step with the row it describes."""
        self._connection.execute(
            "DELETE FROM assets_fts WHERE asset_id = ? AND project = ?",
            [entry.asset_id, entry.project],
        )
        self._connection.execute(
            "INSERT INTO assets_fts (asset_id, name, aliases, tags, description, project) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                entry.asset_id,
                entry.name,
                _join(entry.aliases),
                _join(entry.tags),
                entry.description,
                entry.project,
            ],
        )

    def _candidates(self, term: str, project: str | None) -> tuple[IndexedAsset, ...]:
        """Everything that could match, from the token index and the substring scan."""
        found: dict[tuple[str, str], IndexedAsset] = {}
        for entry in (*self._matching(term, project), *self._containing(term, project)):
            found[(entry.project, entry.asset_id)] = entry
        return tuple(found.values())

    def _matching(self, term: str, project: str | None) -> tuple[IndexedAsset, ...]:
        """The FTS5 pass: whole tokens of an identifier, name, alias, tag or description."""
        clause, parameters = _scope(project)
        statement = (
            f"{SELECT_ROW} WHERE (project, asset_id) IN "
            "(SELECT project, asset_id FROM assets_fts WHERE assets_fts MATCH ?)"
            f"{clause}"
        )
        try:
            return tuple(self._rows(statement, [_phrase(term), *parameters]))
        except sqlite3.OperationalError:
            return ()

    def _containing(self, term: str, project: str | None) -> tuple[IndexedAsset, ...]:
        """The substring pass, for what a token index cannot express."""
        clause, parameters = _scope(project)
        statement = f"{SELECT_ROW} WHERE instr(searchable, ?) > 0{clause}"
        return tuple(self._rows(statement, [term.strip().lower(), *parameters]))

    def _logged(self) -> Iterator[tuple[str, str]]:
        """Every line of the query log, as a project and the term that missed."""
        if not self._query_log.is_file():
            return
        for line in self._query_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            scope, _, term = line.partition(FIELD_SEPARATOR)
            yield scope, term


# --------------------------------------------------------------------------
# Rows in and out
# --------------------------------------------------------------------------


def _values(entry: IndexedAsset) -> dict[str, object]:
    """One indexed asset as stored columns — verbatim, plus the normalised copies."""
    fingerprint = entry.fingerprint
    return {
        "project": entry.project,
        "asset_id": entry.asset_id,
        "name": entry.name,
        "status": entry.status,
        "aliases": _join(entry.aliases),
        "tags": _join(entry.tags),
        "description": entry.description,
        "spec_path": entry.spec_path,
        "directory": entry.directory,
        "source_file": entry.source_file,
        "engine_path": entry.engine_path,
        "discussion": entry.discussion,
        "design_doc": entry.design_doc,
        "owner_art": entry.owner_art,
        "owner_design": entry.owner_design,
        "owner_code": entry.owner_code,
        "validated_export": entry.validated_export,
        "validated_at": entry.validated_at,
        "fingerprint_path": fingerprint.path if fingerprint else None,
        "fingerprint_size": fingerprint.size if fingerprint else None,
        "fingerprint_mtime_ns": fingerprint.mtime_ns if fingerprint else None,
        "tags_key": _tags_key(entry.tags),
        "searchable": _searchable(entry),
    }


def _entry(row: sqlite3.Row) -> IndexedAsset:
    """One stored row as the port's value object, exactly as it was written."""
    return IndexedAsset(
        asset_id=row["asset_id"],
        name=row["name"],
        project=row["project"],
        status=row["status"],
        aliases=_split(row["aliases"]),
        tags=_split(row["tags"]),
        description=row["description"],
        spec_path=row["spec_path"],
        directory=row["directory"],
        source_file=row["source_file"],
        engine_path=row["engine_path"],
        discussion=row["discussion"],
        design_doc=row["design_doc"],
        owner_art=row["owner_art"],
        owner_design=row["owner_design"],
        owner_code=row["owner_code"],
        validated_export=row["validated_export"],
        validated_at=row["validated_at"],
        fingerprint=_fingerprint(row),
    )


def _fingerprint(row: sqlite3.Row) -> FileFingerprint | None:
    """What the specification file looked like when it was indexed, or nothing."""
    path = row["fingerprint_path"]
    if path is None:
        return None
    return FileFingerprint(
        path=path, size=row["fingerprint_size"], mtime_ns=row["fingerprint_mtime_ns"]
    )


def _join(values: tuple[str, ...]) -> str:
    return LIST_SEPARATOR.join(values)


def _split(stored: str) -> tuple[str, ...]:
    return tuple(stored.split(LIST_SEPARATOR)) if stored else ()


def _tags_key(tags: tuple[str, ...]) -> str:
    """The tags in comparison form, delimited so a filter matches whole tags only."""
    if not tags:
        return ""
    inner = LIST_SEPARATOR.join(tag.strip().lower() for tag in tags)
    return f"{LIST_SEPARATOR}{inner}{LIST_SEPARATOR}"


def _searchable(entry: IndexedAsset) -> str:
    """Every searchable field lower-cased, for the substring pass."""
    fields = (
        entry.asset_id,
        entry.name,
        _join(entry.aliases),
        _join(entry.tags),
        entry.description,
    )
    return LIST_SEPARATOR.join(fields).lower()


# --------------------------------------------------------------------------
# Clauses
# --------------------------------------------------------------------------


def _scope(project: str | None) -> tuple[str, list[object]]:
    """The project clause, appended to a statement that already has a `WHERE`."""
    return (" AND project = ?", [project]) if project is not None else ("", [])


def _filters(
    project: str | None, status: str | None, owner: str | None, tag: str | None
) -> tuple[tuple[str, ...], list[object]]:
    """Every filter that was given, as clauses and their parameters."""
    clauses: list[str] = []
    parameters: list[object] = []
    for clause, values in (
        _equals("project", project),
        _status(status),
        _owner(owner),
        _tag(tag),
    ):
        if clause:
            clauses.append(clause)
            parameters.extend(values)
    return tuple(clauses), parameters


def _equals(column: str, value: str | None) -> tuple[str, list[object]]:
    return (f"{column} = ?", [value]) if value is not None else ("", [])


def _status(status: str | None) -> tuple[str, list[object]]:
    """Compared case-insensitively; an unrecorded status is the empty string."""
    if status is None:
        return "", []
    return "lower(coalesce(status, '')) = lower(?)", [status]


def _owner(owner: str | None) -> tuple[str, list[object]]:
    """A person matches whichever of the three seats they hold."""
    if owner is None:
        return "", []
    held = " OR ".join(
        f"(coalesce({column}, '') <> '' AND lower(trim({column})) = ?)"
        for column in ("owner_art", "owner_design", "owner_code")
    )
    wanted = owner.strip().lower()
    return f"({held})", [wanted, wanted, wanted]


def _tag(tag: str | None) -> tuple[str, list[object]]:
    """Whole tags only: `vehicle` never matches an asset tagged `vehicles`."""
    if tag is None:
        return "", []
    return "instr(tags_key, ?) > 0", [f"{LIST_SEPARATOR}{tag.strip().lower()}{LIST_SEPARATOR}"]


def _where(clauses: Iterable[str]) -> str:
    joined = " AND ".join(clauses)
    return f" WHERE {joined}" if joined else ""


def _phrase(term: str) -> str:
    """The term as an FTS5 phrase, so punctuation cannot become query syntax."""
    escaped = term.strip().replace('"', '""')
    return f'"{escaped}"'


__all__ = [
    "CANON_DIRECTORY",
    "INDEX_FILENAME",
    "INDEX_PATH",
    "QUERY_LOG_FILENAME",
    "QUERY_LOG_PATH",
    "SqliteSearchIndex",
]
