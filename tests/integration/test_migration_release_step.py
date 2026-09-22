"""Group 4 — migrations as a release step, against a real PostgreSQL.

`deployment-operations` asks for four things from the schema step, and every one
of them is about *when* and *what happens when it fails* rather than about SQL:

* **4.2** a migration that fails leaves the schema at a **recorded version** the
  runner reports, and the runner exits non-zero. PostgreSQL's transactional DDL
  gives the first half; the ledger gives the second, and the pair is what makes
  the operator's next decision — retry, or drop and rebuild — a decision against
  a number rather than a guess;
* **4.3** that non-zero exit is the **release gate**. The pre-deploy command is
  `python -m cybercanon.api.migrate`, and the image's start command runs it
  before the server with `&&`, so a failed migration starts no server at all and
  the previous version keeps serving. Both halves are asserted here with real
  processes and a real socket: the release attempt is run exactly as the
  container runs it, and the previous version is a `uvicorn` that is still
  answering afterwards;
* **4.4** an instance **never migrates at start** — neither the deployable's
  application factory nor anything it starts touches the schema, checked by
  bringing two instances up against an empty database and finding it still
  empty;
* **4.5** the recovery for a schema no migration can advance is `drop → migrate
  → rebuild` (D5) and **no backup appears anywhere in it**: the index is
  discarded entirely, recreated at the target version and rebuilt from the
  working copy, and every lookup answers exactly as it did before the loss.

The database is the real one every other integration suite uses; the working
copy is a real git clone of a real remote. A drill over fakes would be a drill
over the assumptions being tested.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from staged_project import PROJECT, Staged, ready
from test_postgres_index import Answers, fingerprints_under

from cybercanon.adapters.inbound.http.health import (
    ALIVE,
    LIVE_PATH,
    READY,
    READY_PATH,
    STATUS_FIELD,
)
from cybercanon.adapters.outbound.postgres.migrations import (
    LEDGER_TABLE,
    MigrationFailed,
    apply_migrations,
    migrations_in,
    recorded_version,
    schema_version,
    tables_in,
)
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.api import main as api_main
from cybercanon.api import migrate, recover

pytestmark = pytest.mark.integration

MIGRATIONS = Path("db/migrations")

BROKEN = "0999_broken.sql"
BROKEN_SQL = "CREATE TABLE assets (this is not sql);"
"""A file the database refuses, numbered last so everything before it applies."""

BOOT_TIMEOUT_S = 30.0
POLL_S = 0.1

SERVE = """\
import uvicorn

from cybercanon.adapters.inbound.http.app import build_app

uvicorn.run(build_app(), host="127.0.0.1", port={port}, log_level="warning")
"""

RELEASE = "{python} -m cybercanon.api.migrate {directory} && {python} -c {serve}"
"""The image's command, shell and all: migrate, and only then serve."""


def environment_for(dsn: str) -> dict[str, str]:
    """A complete service environment pointed at this database."""
    return {
        "CANON_PROJECT": "ronin",
        "CANON_REPOSITORY_URL": "git@github.com:cyberdynecorp/ronin.git",
        "CANON_REPOSITORY_BRANCH": "main",
        "CANON_REPOSITORY_CREDENTIAL": "a-deploy-key",
        "CANON_FETCH_INTERVAL_S": "300",
        "CANON_WEBHOOK_SECRET": "a-webhook-secret",
        "CANON_AUTH_ISSUER": "https://auth.cyberdynecorp.ai/",
        "CANON_AUTH_AUDIENCE": "cybercanon",
        "CANON_AUTH_KEY_SET_URL": "https://auth.cyberdynecorp.ai/.well-known/jwks.json",
        "CANON_AUTH_GROUP_ROLES": "art-leads=ART_DIRECTOR",
        "CANON_DATABASE_URL": dsn,
        "CANON_OBJECT_STORE_URL": "https://minio.cyberdynecorp.ai",
        "CANON_LINK_EXPIRY_S": "120",
        "CANON_WRITE_BACK_TIMEOUT_S": "30",
        "CANON_DRAIN_WINDOW_S": "90",
    }


@pytest.fixture
def broken_set(tmp_path: Path, repo_root: Path) -> Path:
    """The real migration set, with one file the database will refuse at the end."""
    directory = tmp_path / "migrations"
    shutil.copytree(repo_root / MIGRATIONS, directory)
    (directory / BROKEN).write_text(BROKEN_SQL, encoding="utf-8")
    return directory


@pytest.fixture
def empty_dsn(postgres_server) -> Iterator[str]:
    """A database with no schema at all — not even the ledger."""
    name = "release_step"
    postgres_server.psql(f"DROP DATABASE IF EXISTS {name}")
    postgres_server.psql(f"CREATE DATABASE {name}")
    yield postgres_server.get_uri(database=name)


def last_version(repo_root: Path) -> str:
    """The version the real migration set ends at."""
    return migrations_in(repo_root / MIGRATIONS)[-1].version


def tables_of(dsn: str) -> set[str]:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    return {str(row[0]) for row in rows}


# --------------------------------------------------------------------------
# 4.2 — a failure leaves a recorded version, and the runner reports it
# --------------------------------------------------------------------------


def test_a_failing_migration_leaves_the_schema_at_the_last_completed_version(
    empty_dsn: str, broken_set: Path, repo_root: Path
) -> None:
    with pytest.raises(MigrationFailed) as refused:
        apply_migrations(empty_dsn, broken_set)

    assert refused.value.version == BROKEN
    assert refused.value.at_version == last_version(repo_root)
    assert schema_version(empty_dsn) == last_version(repo_root)


def test_the_file_that_failed_left_nothing_of_itself_behind(
    empty_dsn: str, broken_set: Path
) -> None:
    """One transaction per file: a refused file is not half applied."""
    with pytest.raises(MigrationFailed):
        apply_migrations(empty_dsn, broken_set)

    with psycopg.connect(empty_dsn) as connection:
        assert BROKEN not in {
            str(row[0])
            for row in connection.execute(f"SELECT version FROM {LEDGER_TABLE}").fetchall()
        }


def test_the_runner_exits_non_zero_naming_the_file_and_the_recorded_version(
    empty_dsn: str, broken_set: Path, repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = migrate.main([str(broken_set)], environment_for(empty_dsn))

    assert code == migrate.FAILED
    complained = capsys.readouterr().err
    assert BROKEN in complained
    assert last_version(repo_root) in complained


def test_the_schema_version_is_reportable_after_a_failure(
    empty_dsn: str, broken_set: Path, repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """*"It SHALL report a recorded version identifying which migrations applied."*"""
    migrate.main([str(broken_set)], environment_for(empty_dsn))
    capsys.readouterr()

    assert migrate.main([migrate.VERSION_FLAG], environment_for(empty_dsn)) == 0
    assert capsys.readouterr().out.strip() == last_version(repo_root)


def test_a_successful_release_step_exits_zero_and_says_what_it_applied(
    empty_dsn: str, repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = migrate.main([str(repo_root / MIGRATIONS)], environment_for(empty_dsn))

    assert code == 0
    assert last_version(repo_root) in capsys.readouterr().out


# --------------------------------------------------------------------------
# 4.3 — the exit code is the release gate
# --------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def _answers(url: str) -> bool:
    try:
        _get(url)
    except (urllib.error.URLError, OSError):
        return False
    return True


def _await(process: subprocess.Popen[str], url: str) -> None:
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the server exited: {process.communicate()[0]}")
        if _answers(url):
            return
        time.sleep(POLL_S)
    process.terminate()
    raise AssertionError(f"the server did not answer {url} within {BOOT_TIMEOUT_S}s")


def _scrubbed() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("CANON_") and name not in {"DATABASE_URL", "PGHOST"}
    }


@pytest.fixture
def previous_version(repo_root: Path) -> Iterator[str]:
    """The version that is already serving when the next release is attempted."""
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-c", SERVE.format(port=port)],
        cwd=repo_root,
        env=_scrubbed(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _await(process, f"{base}{LIVE_PATH}")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_a_failed_migration_aborts_the_release_and_the_previous_version_keeps_serving(
    previous_version: str, empty_dsn: str, broken_set: Path, repo_root: Path
) -> None:
    """The release attempt is the container's own command: migrate, `&&`, serve."""
    port = _free_port()
    attempt = subprocess.run(
        RELEASE.format(
            python=sys.executable,
            directory=str(broken_set),
            serve=repr(SERVE.format(port=port)),
        ),
        shell=True,
        cwd=repo_root,
        env={**_scrubbed(), **environment_for(empty_dsn)},
        capture_output=True,
        text=True,
        timeout=BOOT_TIMEOUT_S,
    )

    assert attempt.returncode != 0, "a failed migration must abort the release"
    assert BROKEN in attempt.stderr
    assert not _answers(f"http://127.0.0.1:{port}{LIVE_PATH}"), (
        "no instance of the new version may serve a request"
    )
    status, body = _get(f"{previous_version}{LIVE_PATH}")
    assert status == 200 and ALIVE in body
    assert _get(f"{previous_version}{READY_PATH}")[0] == 200


def test_the_release_step_is_a_pre_deploy_command_and_not_the_image_start(
    repo_root: Path,
) -> None:
    """Where the gate is wired: before the container, never inside it (D4).

    The image serves and nothing else — an entry point that migrated would
    migrate once per instance, which is the behaviour the test above forbids.
    The release step is Coolify's pre-deploy command, and `deploy/README.md` is
    where a deployment reads what to configure it as.
    """
    image = (repo_root / "deploy" / "api.Dockerfile").read_text(encoding="utf-8")
    document = (repo_root / "deploy" / "README.md").read_text(encoding="utf-8")

    assert "cybercanon.api.migrate" not in image[image.index("CMD") :]
    assert "python -m cybercanon.api.migrate" in document
    assert "pre-deploy" in document.lower()


# --------------------------------------------------------------------------
# 4.4 — instances never migrate at start
# --------------------------------------------------------------------------


def test_two_instances_started_against_an_empty_database_migrate_nothing(
    empty_dsn: str,
) -> None:
    """*"Given a release that starts more than one instance, no instance SHALL
    attempt a migration."* Two are started, and the database is still empty."""
    environment = environment_for(empty_dsn)

    for _ in range(2):
        with TestClient(api_main.application(environment)) as instance:
            assert instance.get(LIVE_PATH).json()[STATUS_FIELD] == ALIVE
            assert instance.get(READY_PATH).json()[STATUS_FIELD] == READY

    assert tables_of(empty_dsn) == set(), "starting an instance created a schema"


def test_no_start_path_reaches_the_migration_runner() -> None:
    """The structural half: the deployable's boot does not import the runner."""
    source = Path(api_main.__file__).read_text(encoding="utf-8")

    assert "apply_migrations" not in source
    assert "migrate" not in source.replace("migration", "")


# --------------------------------------------------------------------------
# 4.5 — drop → migrate → rebuild, with no backup anywhere in it
# --------------------------------------------------------------------------


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    return ready(tmp_path)


def _indexed(dsn: str) -> Answers:
    with PostgresSearchIndex(dsn) as index:
        return Answers.of(index)


def test_the_recovery_from_a_broken_schema_rebuilds_an_identical_index(
    staged: Staged, postgres_dsn: str
) -> None:
    recover.rebuild_from(staged.working_copy, dsn=postgres_dsn)
    before = _indexed(postgres_dsn)
    assert before.listing, "the fixture project has assets to lose"

    # A schema no migration can advance: the ledger says applied, the tables are gone.
    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        connection.execute("DROP TABLE assets CASCADE")
        assert recorded_version(connection), "the ledger still claims the schema is current"

    report = recover.recover([staged.working_copy], dsn=postgres_dsn)

    assert set(report.dropped) >= {"assets", LEDGER_TABLE}
    assert report.applied, "the schema is recreated at the target version, not patched"
    assert _indexed(postgres_dsn) == before


def test_the_recovery_needs_no_backup_of_the_index(staged: Staged, postgres_dsn: str) -> None:
    """Nothing is dumped, and nothing is restored: the working copy is the source."""
    recover.rebuild_from(staged.working_copy, dsn=postgres_dsn)
    before = _indexed(postgres_dsn)

    report = recover.recover([staged.working_copy], dsn=postgres_dsn)

    assert _indexed(postgres_dsn) == before
    assert report.indexed == len(before.listing)
    source = Path(recover.__file__).read_text(encoding="utf-8").lower()
    assert "pg_dump" not in source and "pg_restore" not in source


def test_the_drop_removes_every_table_the_migration_set_creates(repo_root: Path) -> None:
    """A table nobody listed would survive a drop and outlive the loss it caused."""
    created = set(tables_in(migrations_in(repo_root / MIGRATIONS)))

    assert created == {
        "assets",
        "search_misses",
        "idempotency_keys",
        "dismissals",
        "concept_views",
        LEDGER_TABLE,
    }


def test_a_rebuild_reports_progress_so_a_long_recovery_is_watchable(
    staged: Staged, postgres_dsn: str
) -> None:
    seen: list[tuple[int, int]] = []
    recover.rebuild_from(
        staged.working_copy,
        dsn=postgres_dsn,
        progress=lambda step: seen.append((step.done, step.total)),
    )

    assert seen, "a recovery that reports nothing is indistinguishable from a hang"
    assert seen[-1][0] == seen[-1][1]
    assert [done for done, _ in seen] == sorted(done for done, _ in seen)


def test_the_fingerprints_the_recovery_writes_are_the_files_it_read(
    staged: Staged, postgres_dsn: str
) -> None:
    """The rebuild is over the working copy, so its rows point at real files."""
    recover.rebuild_from(staged.working_copy, dsn=postgres_dsn)
    fingerprints = fingerprints_under(staged.working_copy)

    with PostgresSearchIndex(postgres_dsn) as index:
        for entry in index.list_assets(project=PROJECT):
            assert entry.fingerprint == fingerprints(entry.spec_path)
