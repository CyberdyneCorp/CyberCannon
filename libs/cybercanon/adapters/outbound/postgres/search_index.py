"""`PostgresSearchIndex` — the same rebuildable index, for a hosted surface (D7).

`SqliteSearchIndex` is one file on an artist's laptop; this is the same port
over a database several people share. Nothing above the port changes, and that
is the whole claim: `tests/conformance/test_search_index.py` runs one contract
body against the in-memory fake, SQLite **and** this adapter, so an ordering a
`ts_rank` produced differently, a filter that widened instead of combining, or a
fingerprint that did not survive a round trip through a column each fail the
build rather than the product.

**Ranking is not reimplemented here, and there is no third copy of it.**
:func:`~cybercanon.application.ports.search_index.rank` is the cascade (D9) and
this adapter sorts with it, exactly as the fake and SQLite do. What SQL does is
*narrow*: a GIN index over a generated `tsvector` answers the ordinary token
query without a scan, and a substring scan completes it for the two passes whose
definition is a substring a token index cannot express — a name *prefix* and a
description *substring*. Candidates are a superset; `rank` decides. A
`ts_rank_cd` ordering would be a second search engine with results that move
under people for reasons nobody can explain, which is precisely what the fixed
cascade exists to prevent.

**The schema is not created here.** It is applied by
:mod:`cybercanon.adapters.outbound.postgres.migrations` as a release step, for
the reason `project.md` gives: *"Database migrations run as a release step, and
the index schema is droppable-and-rebuildable by definition."* An adapter that
created its tables on connect would make that guarantee unobservable and would
let two deployments quietly diverge.

**Nothing here is authoritative.** Every row is a projection of an `asset.yaml`
in the working copy; dropping the schema and rebuilding is always a complete
recovery, and `tests/integration/test_postgres_index.py` is what turns that
sentence into a test.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from cybercanon.application.ports.search_index import (
    FileFingerprint,
    IndexedAsset,
    RecordedMiss,
    SearchHit,
    joined,
    pending_suggestions,
    rank,
    searchable_text,
    suggesting,
    tag_needle,
    tags_key,
    unjoined,
)
from cybercanon.domain.derived import (
    DerivedRecord,
    Provenance,
    SuggestionDecision,
    SuggestionState,
)

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
"""Every written column, in the order the insert lists them.

`document` is absent on purpose: it is a generated column, derived by the
database from `searchable`, so there is no way for it to disagree with the text
it indexes.
"""

SELECT_ROW = f"SELECT {', '.join(COLUMNS)} FROM assets"
"""Every statement selects the same columns, so one row shape reads back."""

FTS_CONFIGURATION = "simple"
"""No stemming and no stop words.

An asset identifier is not English. `simple` means a token is a token, which is
what keeps `mech_scout` findable and stops `a` from being discarded out of a
name somebody chose deliberately.
"""


class PostgresSearchIndex:
    """A project's indexed assets in PostgreSQL, narrowed by full text and scan."""

    def __init__(self, dsn: str | None = None, *, connection: psycopg.Connection | None = None):
        """Open the index over that database, or adopt a connection already open.

        `connection` exists for the composition root and for the conformance
        suite, which run several stores against one server; `dsn` is what a
        deployable passes. Autocommit, because every operation here is one
        statement and the transaction that matters — a write reaching the
        repository — is not this store's.
        """
        if connection is None and not dsn:
            raise ValueError("a PostgresSearchIndex needs a dsn or an open connection")
        self._owned = connection is None
        self._connection = connection or psycopg.connect(str(dsn), autocommit=True)
        self._connection.autocommit = True

    @property
    def connection(self) -> psycopg.Connection:
        return self._connection

    def close(self) -> None:
        """Release the connection, when this store opened one."""
        if self._owned:
            self._connection.close()

    def __enter__(self) -> PostgresSearchIndex:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- writing ---------------------------------------------------------

    def upsert(self, entry: IndexedAsset) -> None:
        """Write one asset's row, replacing whatever was there for that id."""
        values = _values(entry)
        placeholders = ", ".join(["%s"] * len(COLUMNS))
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}" for column in COLUMNS if column not in _KEY
        )
        self._connection.execute(
            f"INSERT INTO assets ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT (project, asset_id) DO UPDATE SET {assignments}",
            [values[column] for column in COLUMNS],
        )

    def forget(self, asset_id: str, project: str | None = None) -> None:
        """Drop one row — a specification that was deleted or renamed."""
        clause, parameters = _scope(project)
        self._connection.execute(
            f"DELETE FROM assets WHERE asset_id = %s{clause}", [asset_id, *parameters]
        )

    def clear(self) -> None:
        """Drop everything, rows and recorded misses alike.

        The index is disposable by specification, and a `clear` that left the
        recorded misses behind would make "deleting the index loses nothing"
        true in one direction only.
        """
        self._connection.execute("DELETE FROM assets")
        self._connection.execute("DELETE FROM search_misses")
        self._connection.execute("DELETE FROM derived_records")
        self._connection.execute("DELETE FROM suggestion_decisions")

    # -- reading ---------------------------------------------------------

    def get(self, asset_id: str, project: str | None = None) -> IndexedAsset | None:
        """The row for that identifier, or ``None`` when nothing is indexed for it."""
        clause, parameters = _scope(project)
        rows = self._rows(
            f"{SELECT_ROW} WHERE asset_id = %s{clause} ORDER BY project, asset_id LIMIT 1",
            [asset_id, *parameters],
        )
        return next(iter(rows), None)

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
        """The ranked cascade of D9 over everything that could possibly match."""
        if not term.strip():
            return ()
        suggestions = self._suggestions(project)
        return rank(self._candidates(term, project, suggestions), term, suggestions)

    def is_stale(self, asset_id: str, current: FileFingerprint | None) -> bool:
        """Whether the row for that asset no longer matches the file on disk (D8)."""
        entry = self.get(asset_id)
        return entry is None or entry.fingerprint != current

    # -- misses (D11) ----------------------------------------------------

    def record_miss(self, term: str, project: str | None = None) -> None:
        """Count a term that matched nothing. Local to the deployment, never sent."""
        scope = project or ""
        self._connection.execute(
            "INSERT INTO search_misses (project, term_key, term, count) "
            "VALUES (%s, %s, %s, 1) "
            "ON CONFLICT (project, term_key) DO UPDATE SET count = search_misses.count + 1",
            [scope, term.strip().lower(), term],
        )

    def misses(self, project: str | None = None) -> tuple[RecordedMiss, ...]:
        """Every recorded miss, ordered by term, with how often each was asked."""
        clause, parameters = ("", []) if project is None else (" WHERE project = %s", [project])
        with self._connection.cursor(row_factory=dict_row) as cursor:
            rows = cursor.execute(
                "SELECT project, term, count FROM search_misses"
                f"{clause} ORDER BY project, term_key",
                parameters,
            ).fetchall()
        return tuple(
            RecordedMiss(term=row["term"], project=row["project"], count=int(row["count"]))
            for row in rows
        )

    # -- derived metadata (add-derived-metadata, D5 and D6) ---------------

    def put_derived(self, record: DerivedRecord, project: str = "") -> None:
        """One derived record, keyed by the content hash of the image it saw (D5)."""
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in DERIVED_COLUMNS
            if column not in _DERIVED_KEY
        )
        placeholders = ", ".join(["%s"] * len(DERIVED_COLUMNS))
        self._connection.execute(
            f"INSERT INTO derived_records ({', '.join(DERIVED_COLUMNS)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (project, source_hash) DO UPDATE SET {assignments}",
            [
                project,
                record.source_hash,
                record.asset_id,
                record.source_path,
                record.model,
                record.generated_at.isoformat(),
                record.description,
                joined(record.tags),
                joined(record.suggested_aliases),
            ],
        )

    def derived(self, source_hash: str, project: str | None = None) -> DerivedRecord | None:
        clause, parameters = _scope(project)
        rows = self._derived_rows(
            f"{SELECT_DERIVED} WHERE source_hash = %s{clause} ORDER BY project LIMIT 1",
            [source_hash, *parameters],
        )
        return next(iter(rows), None)

    def derived_records(
        self, project: str | None = None, asset_id: str | None = None
    ) -> tuple[DerivedRecord, ...]:
        clauses, parameters = _named_filters(("project", project), ("asset_id", asset_id))
        statement = f"{SELECT_DERIVED}{_where(clauses)} ORDER BY project, source_hash"
        return tuple(self._derived_rows(statement, parameters))

    def record_decision(self, decision: SuggestionDecision, project: str = "") -> None:
        """A person's answer about one suggested value, for one image (D6)."""
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in DECISION_COLUMNS
            if column not in _DECISION_KEY
        )
        placeholders = ", ".join(["%s"] * len(DECISION_COLUMNS))
        self._connection.execute(
            f"INSERT INTO suggestion_decisions ({', '.join(DECISION_COLUMNS)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (project, source_hash, value) DO UPDATE SET {assignments}",
            [
                project,
                decision.source_hash,
                decision.value,
                str(decision.state),
                decision.actor,
                decision.at.isoformat() if decision.at else "",
                decision.written,
            ],
        )

    def decisions(
        self, source_hash: str | None = None, project: str | None = None
    ) -> tuple[SuggestionDecision, ...]:
        clauses, parameters = _named_filters(("project", project), ("source_hash", source_hash))
        statement = f"{SELECT_DECISION}{_where(clauses)} ORDER BY project, source_hash, value"
        with self._connection.cursor(row_factory=dict_row) as cursor:
            rows = cursor.execute(statement, list(parameters)).fetchall()
        return tuple(_decision(row) for row in rows)

    def clear_derived(self, project: str | None = None) -> None:
        """Drop the generated half and every decision about it, and nothing else."""
        clause, parameters = _scope(project)
        where = f" WHERE true{clause}"
        self._connection.execute(f"DELETE FROM derived_records{where}", parameters)
        self._connection.execute(f"DELETE FROM suggestion_decisions{where}", parameters)

    # -- internals -------------------------------------------------------

    def _suggestions(self, project: str | None) -> Mapping[str, tuple[str, ...]]:
        """The sixth pass's input, joined by the domain rather than by SQL (D9)."""
        return pending_suggestions(self.derived_records(project), self.decisions(project=project))

    def _derived_rows(self, statement: str, parameters: Sequence[Any]) -> Iterator[DerivedRecord]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            for row in cursor.execute(statement, list(parameters)).fetchall():
                yield _record(row)

    def _rows(self, statement: str, parameters: Sequence[Any]) -> Iterator[IndexedAsset]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            for row in cursor.execute(statement, list(parameters)).fetchall():
                yield _entry(row)

    def _candidates(
        self,
        term: str,
        project: str | None,
        suggestions: Mapping[str, tuple[str, ...]],
    ) -> tuple[IndexedAsset, ...]:
        """The text index, the substring scan, and the rows the sixth pass rescues.

        The third source is not optional: a suggested alias is stored beside the
        row rather than in it, so a candidate set built only from `searchable`
        would never hold the asset the sixth pass exists to find.
        """
        found: dict[tuple[str, str], IndexedAsset] = {}
        narrowed = (
            *self._matching(term, project),
            *self._containing(term, project),
            *self._named(suggesting(suggestions, term), project),
        )
        for entry in narrowed:
            found[(entry.project, entry.asset_id)] = entry
        return tuple(found.values())

    def _named(self, asset_ids: tuple[str, ...], project: str | None) -> tuple[IndexedAsset, ...]:
        """The rows for these identifiers — what the sixth pass has to rank."""
        if not asset_ids:
            return ()
        clause, parameters = _scope(project)
        statement = f"{SELECT_ROW} WHERE asset_id = ANY(%s){clause}"
        return tuple(self._rows(statement, [list(asset_ids), *parameters]))

    def _matching(self, term: str, project: str | None) -> tuple[IndexedAsset, ...]:
        """The full-text pass: whole tokens of an identifier, name, alias, tag or text."""
        clause, parameters = _scope(project)
        statement = f"{SELECT_ROW} WHERE document @@ plainto_tsquery(%s, %s){clause}"
        return tuple(self._rows(statement, [FTS_CONFIGURATION, term.strip(), *parameters]))

    def _containing(self, term: str, project: str | None) -> tuple[IndexedAsset, ...]:
        """The substring pass, for what a token index cannot express."""
        clause, parameters = _scope(project)
        statement = f"{SELECT_ROW} WHERE position(%s in searchable) > 0{clause}"
        return tuple(self._rows(statement, [term.strip().lower(), *parameters]))


_KEY = ("project", "asset_id")
"""The primary key, which an upsert matches on rather than assigns."""

DERIVED_COLUMNS = (
    "project",
    "source_hash",
    "asset_id",
    "source_path",
    "model",
    "generated_at",
    "description",
    "tags",
    "suggested_aliases",
)

DECISION_COLUMNS = (
    "project",
    "source_hash",
    "value",
    "state",
    "actor",
    "decided_at",
    "written",
)

SELECT_DERIVED = f"SELECT {', '.join(DERIVED_COLUMNS)} FROM derived_records"
SELECT_DECISION = f"SELECT {', '.join(DECISION_COLUMNS)} FROM suggestion_decisions"

_DERIVED_KEY = ("project", "source_hash")
_DECISION_KEY = ("project", "source_hash", "value")


def _record(row: dict[str, Any]) -> DerivedRecord:
    """One stored derived record back as the domain value it was written from."""
    return DerivedRecord(
        provenance=Provenance(
            model=row["model"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
            source_hash=row["source_hash"],
        ),
        asset_id=row["asset_id"],
        source_path=row["source_path"],
        description=row["description"],
        tags=unjoined(row["tags"]),
        suggested_aliases=unjoined(row["suggested_aliases"]),
    )


def _decision(row: dict[str, Any]) -> SuggestionDecision:
    """One stored decision back as the domain value. A state it cannot read raises."""
    return SuggestionDecision(
        source_hash=row["source_hash"],
        value=row["value"],
        state=SuggestionState(row["state"]),
        actor=row["actor"],
        at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
        written=row["written"],
    )


def _named_filters(*pairs: tuple[str, str | None]) -> tuple[tuple[str, ...], list[object]]:
    """Every `column = value` a caller gave, as clauses and their parameters."""
    clauses: list[str] = []
    parameters: list[object] = []
    for column, value in pairs:
        if value is not None:
            clauses.append(f"{column} = %s")
            parameters.append(value)
    return tuple(clauses), parameters


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
        "aliases": joined(entry.aliases),
        "tags": joined(entry.tags),
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
        "tags_key": tags_key(entry.tags),
        "searchable": searchable_text(entry),
    }


def _entry(row: dict[str, Any]) -> IndexedAsset:
    """One stored row as the port's value object, exactly as it was written."""
    return IndexedAsset(
        asset_id=row["asset_id"],
        name=row["name"],
        project=row["project"],
        status=row["status"],
        aliases=unjoined(row["aliases"]),
        tags=unjoined(row["tags"]),
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


def _fingerprint(row: dict[str, Any]) -> FileFingerprint | None:
    """What the specification file looked like when it was indexed, or nothing."""
    path = row["fingerprint_path"]
    if path is None:
        return None
    return FileFingerprint(
        path=path,
        size=int(row["fingerprint_size"]),
        mtime_ns=int(row["fingerprint_mtime_ns"]),
    )


# --------------------------------------------------------------------------
# Clauses
# --------------------------------------------------------------------------


def _scope(project: str | None) -> tuple[str, list[object]]:
    """The project clause, appended to a statement that already has a `WHERE`."""
    return (" AND project = %s", [project]) if project is not None else ("", [])


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
    return (f"{column} = %s", [value]) if value is not None else ("", [])


def _status(status: str | None) -> tuple[str, list[object]]:
    """Compared case-insensitively; an unrecorded status is the empty string."""
    if status is None:
        return "", []
    return "lower(coalesce(status, '')) = lower(%s)", [status]


def _owner(owner: str | None) -> tuple[str, list[object]]:
    """A person matches whichever of the three seats they hold."""
    if owner is None:
        return "", []
    held = " OR ".join(
        f"(coalesce({column}, '') <> '' AND lower(btrim({column})) = %s)"
        for column in ("owner_art", "owner_design", "owner_code")
    )
    wanted = owner.strip().lower()
    return f"({held})", [wanted, wanted, wanted]


def _tag(tag: str | None) -> tuple[str, list[object]]:
    """Whole tags only: `vehicle` never matches an asset tagged `vehicles`."""
    if tag is None:
        return "", []
    return "position(%s in tags_key) > 0", [tag_needle(tag)]


def _where(clauses: Iterable[str]) -> str:
    joined_clauses = " AND ".join(clauses)
    return f" WHERE {joined_clauses}" if joined_clauses else ""


__all__ = [
    "COLUMNS",
    "DECISION_COLUMNS",
    "DERIVED_COLUMNS",
    "FTS_CONFIGURATION",
    "SELECT_ROW",
    "PostgresSearchIndex",
]
