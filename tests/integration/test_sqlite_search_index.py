"""Task 4.1 — `SqliteSearchIndex` as a real file under `.canon/` (D7).

The port conformance suite proves this adapter answers the port exactly as the
in-memory fake does. What only a file can show is asserted here:

* the index lands where `.gitignore` expects it, and so does the query log;
* the rows **survive the process** — which is the entire reason a long-lived MCP
  server keeps an index instead of rescanning per call;
* the searchable text is really in an **FTS5** table, not a column somebody
  scans, because D7 named the mechanism and a scan would pass every behavioural
  test while quietly being the alternative that was rejected;
* deleting the file loses nothing: a rebuild from the same rows answers
  identically, which is the specification's disposability claim exercised
  against a real file rather than a dictionary.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cybercanon.adapters.outbound.sqlite.search_index import (
    INDEX_PATH,
    QUERY_LOG_PATH,
    SqliteSearchIndex,
)
from cybercanon.application.ports.search_index import (
    FileFingerprint,
    IndexedAsset,
    MatchKind,
)

pytestmark = pytest.mark.integration

PROJECT = "ironwood"

MECH_SCOUT = IndexedAsset(
    asset_id="mech_scout",
    name="Scout Mech",
    project=PROJECT,
    status="modeling",
    aliases=("drone",),
    tags=("character", "robot"),
    description="A light reconnaissance walker.",
    spec_path="characters/mech_scout/asset.yaml",
    directory="characters/mech_scout",
    owner_art="rafa@cyberdyne.com",
    fingerprint=FileFingerprint(path="characters/mech_scout/asset.yaml", size=812, mtime_ns=7),
)

MULE = IndexedAsset(
    asset_id="mule",
    name="Mule Hauler",
    project=PROJECT,
    status="concept",
    tags=("vehicle",),
    description="A six-wheeled supply mech carrier.",
    spec_path="vehicles/mule/asset.yaml",
    directory="vehicles/mule",
)


def _index(root: Path) -> SqliteSearchIndex:
    index = SqliteSearchIndex(root)
    index.upsert(MECH_SCOUT)
    index.upsert(MULE)
    return index


# --------------------------------------------------------------------------
# Where it lives
# --------------------------------------------------------------------------


def test_the_index_and_the_query_log_live_under_canon(tmp_path: Path) -> None:
    """Exactly the two paths `.gitignore` names — derived state never reaches a diff."""
    index = _index(tmp_path)
    index.record_miss("hovercraft", project=PROJECT)

    assert index.database == tmp_path / INDEX_PATH
    assert index.query_log == tmp_path / QUERY_LOG_PATH
    assert index.database.is_file()
    assert index.query_log.is_file()


def test_the_query_log_is_text_a_person_can_read(tmp_path: Path) -> None:
    """The log's whole value is somebody reading it to decide which aliases to add."""
    index = _index(tmp_path)
    index.record_miss("hovercraft", project=PROJECT)

    assert "hovercraft" in index.query_log.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# It is a file, and it is an FTS5 index
# --------------------------------------------------------------------------


def test_rows_survive_the_process_that_wrote_them(tmp_path: Path) -> None:
    """The reason a long-lived server keeps an index rather than rescanning."""
    _index(tmp_path).close()

    reopened = SqliteSearchIndex(tmp_path)

    found = reopened.get("mech_scout")
    assert found is not None
    assert found.name == "Scout Mech"
    assert found.aliases == ("drone",)
    assert found.fingerprint == MECH_SCOUT.fingerprint


def test_recorded_misses_survive_the_process_that_wrote_them(tmp_path: Path) -> None:
    index = _index(tmp_path)
    index.record_miss("hovercraft", project=PROJECT)
    index.record_miss("hovercraft", project=PROJECT)
    index.close()

    (miss,) = SqliteSearchIndex(tmp_path).misses()

    assert miss.term == "hovercraft"
    assert miss.count == 2


def test_the_searchable_text_is_indexed_with_fts5(tmp_path: Path) -> None:
    """D7 named the mechanism; a scan would pass every behavioural test without it."""
    _index(tmp_path).close()

    with sqlite3.connect(tmp_path / INDEX_PATH) as connection:
        (declaration,) = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'assets_fts'"
        ).fetchone()
        matched = connection.execute(
            "SELECT asset_id FROM assets_fts WHERE assets_fts MATCH ?", ['"walker"']
        ).fetchall()

    assert "fts5" in declaration.lower()
    for column in ("asset_id", "name", "aliases", "tags", "description"):
        assert column in declaration
    assert matched == [("mech_scout",)]


def test_a_search_is_answered_from_the_reopened_file(tmp_path: Path) -> None:
    _index(tmp_path).close()

    hits = SqliteSearchIndex(tmp_path).search("drone", project=PROJECT)

    assert [hit.asset_id for hit in hits] == ["mech_scout"]
    assert hits[0].kind is MatchKind.ALIAS


# --------------------------------------------------------------------------
# Disposable by specification
# --------------------------------------------------------------------------


def test_deleting_the_file_and_rebuilding_restores_every_answer(tmp_path: Path) -> None:
    """Deleting the index loses nothing the repository does not still hold."""
    index = _index(tmp_path)
    before = (index.list_assets(project=PROJECT), index.search("mech", project=PROJECT))
    index.close()
    (tmp_path / INDEX_PATH).unlink()

    rebuilt = _index(tmp_path)

    assert (rebuilt.list_assets(project=PROJECT), rebuilt.search("mech", project=PROJECT)) == before


def test_an_index_with_no_file_yet_builds_one(tmp_path: Path) -> None:
    """A repository that never ran the server gets its index on first use."""
    root = tmp_path / "game"
    root.mkdir()

    index = SqliteSearchIndex(root)

    assert index.database.is_file()
    assert index.list_assets() == ()
    assert index.misses() == ()
