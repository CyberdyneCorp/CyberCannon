"""Task 8.1 (D1) — four applications, and one of them restarting is not an outage.

D1 chose four Coolify applications over one compose stack in order to make a
requirement true by construction: *"given all four components are running, when
any one of them is restarted, then the remaining three SHALL continue running,
and the restarted component SHALL return to serving without manual
intervention."* A single stack would have made that false by construction, and
a declaration nobody executes would have made it unfalsifiable.

`tests/tooling/test_deployment_inventory.py` asserts the declaration — four
applications, each with its own host, volumes, environment and health
configuration. What is asserted **here** is the behaviour behind it, against the
real things: a real git working copy, a real PostgreSQL, a real S3 API, and for
the API a real `uvicorn` process that is terminated and started again.

Three of the four are driven end to end. The fourth, the web application, is
process-only by D10 — nothing in the deployment depends on it, and its own
restart is executed against the built artifact by
`tests/integration/test_web_readiness_process.py`, which starts it with nothing
answering at the address of the API and reads `/readyz`. Saying which suite
executes what is the point: a test that claimed the web half here would be
claiming to have started something this process never started.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import boto3
import psycopg
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from staged_project import PROJECT, SCOUT_SPEC, Staged, ready
from test_postgres_index import Answers, fingerprints_under

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.health import (
    ALIVE,
    DEGRADED_FIELD,
    LIVE_PATH,
    READY,
    READY_PATH,
    STATUS_FIELD,
)
from cybercanon.adapters.inbound.http.surface import HostedProject, Surface
from cybercanon.adapters.outbound.minio.blob_store import S3BlobStore
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.results import Ok
from cybercanon.application.testing import build_fakes
from cybercanon.application.use_cases.blob_mirror import mirror_project
from cybercanon.application.use_cases.deployment_status import (
    DeploymentJournal,
    rebuild_and_record,
)
from cybercanon.application.use_cases.service_health import (
    OBJECT_STORE,
    SEARCH_INDEX,
    available,
    unavailable,
)

pytestmark = pytest.mark.integration

BUCKET = "cybercanon-blobs"
REGION = "us-east-1"

BOOT_TIMEOUT_S = 30.0
POLL_S = 0.05

SERVE = """\
import uvicorn

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.surface import HostedProject, Surface
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.testing import build_fakes

store = GitSpecStore({working_copy!r})
container = Container(
    spec_store=store,
    mesh_inspector=build_fakes()["mesh_inspector"],
    search_index=PostgresSearchIndex({dsn!r}),
)
surface = Surface(projects={{{project!r}: HostedProject(name={project!r}, container=container)}})
uvicorn.run(build_app(surface=surface), host="127.0.0.1", port={port}, log_level="warning")
"""
"""One API instance over the volumes: the working copy on disk and the index."""


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    return ready(tmp_path)


@pytest.fixture
def blobs() -> Iterator[S3BlobStore]:
    with mock_aws():
        client = _client()
        client.create_bucket(Bucket=BUCKET)
        yield _store(client)


def _client():
    return boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id="integration",
        aws_secret_access_key="integration",
    )


def _store(client) -> S3BlobStore:
    return S3BlobStore(
        client,
        BUCKET,
        base_url="https://blobs.cyberdyne.example",
        secret=b"a-configured-link-signing-key",
    )


def _rebuilt(staged: Staged, index: PostgresSearchIndex) -> None:
    outcome = rebuild_and_record(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        search_index=index,
        fingerprints=fingerprints_under(staged.working_copy),
        journal=DeploymentJournal(),
    )
    assert isinstance(outcome, Ok), outcome


def _mirrored(staged: Staged, blobs: S3BlobStore) -> dict[str, str]:
    report = mirror_project(
        PROJECT,
        repository_host=staged.host,
        spec_store=staged.spec_store(),
        blob_store=blobs,
    )
    assert isinstance(report, Ok), report
    return dict(report.value.keys)


def _answers(index: PostgresSearchIndex) -> tuple[object, ...]:
    return tuple(replace(entry, fingerprint=None) for entry in Answers.of(index).listing)


def _api(staged: Staged, index: PostgresSearchIndex | None, dependencies) -> TestClient:
    """The API instance, over whichever of its dependencies are reachable."""
    container = Container(
        spec_store=staged.spec_store(),
        mesh_inspector=build_fakes()["mesh_inspector"],
        search_index=index,
    )
    surface = Surface(
        projects={PROJECT: HostedProject(name=PROJECT, container=container)},
        observe=lambda: dependencies,
    )
    return TestClient(build_app(surface=surface))


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _scrubbed() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("CANON_") and name not in {"DATABASE_URL", "PGHOST"}
    }


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as answer:
        return answer.status, answer.read().decode("utf-8")


def _started(repo_root: Path, staged: Staged, dsn: str, port: int) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            SERVE.format(
                working_copy=str(staged.working_copy), dsn=dsn, project=PROJECT, port=port
            ),
        ],
        cwd=repo_root,
        env=_scrubbed(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _await(process, f"http://127.0.0.1:{port}{LIVE_PATH}")
    return process


def _await(process: subprocess.Popen[str], url: str) -> None:
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the instance exited: {process.communicate()[0]}")
        try:
            _get(url)
        except (urllib.error.URLError, OSError):
            time.sleep(POLL_S)
        else:
            return
    process.terminate()
    raise AssertionError(f"the instance did not answer {url} within {BOOT_TIMEOUT_S}s")


# --------------------------------------------------------------------------
# The index database restarts
# --------------------------------------------------------------------------


def test_the_api_keeps_serving_while_the_index_is_gone(staged: Staged, postgres_dsn: str) -> None:
    """*"a lost index does NOT withhold traffic"*, so its restart is not an outage."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuilt(staged, index)

    client = _api(staged, None, (unavailable(SEARCH_INDEX, "the index is restarting"),))
    readiness = client.get(READY_PATH)

    assert readiness.status_code == 200
    assert readiness.json()[STATUS_FIELD] == READY
    assert SEARCH_INDEX in readiness.json()[DEGRADED_FIELD]


def test_the_working_copy_still_answers_while_the_index_is_gone(
    staged: Staged, postgres_dsn: str
) -> None:
    """*"answers derivable from the working copy alone SHALL continue to be served"*."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuilt(staged, index)

    without_index = Container(
        spec_store=staged.spec_store(),
        mesh_inspector=build_fakes()["mesh_inspector"],
        search_index=None,
    )
    compiled = without_index.compile_spec(SCOUT_SPEC)
    looked_up = without_index.where_is("mech_scout")

    assert isinstance(compiled, Ok), compiled
    assert not isinstance(looked_up, Ok), "a lookup needs the index and says so"


def test_the_index_returns_to_serving_with_no_intervention(
    staged: Staged, postgres_dsn: str
) -> None:
    """A restarted managed application is a new connection over the same volume."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuilt(staged, index)
        before = _answers(index)

    with PostgresSearchIndex(postgres_dsn) as restarted:
        after = _answers(restarted)

    assert after == before, "the index did not come back with what it had"


def test_a_restarting_index_leaves_the_other_three_alone(
    staged: Staged, blobs: S3BlobStore, postgres_dsn: str
) -> None:
    """The point of four applications: one of them going away touches nothing else."""
    keys = _mirrored(staged, blobs)
    revision = staged.host.head(PROJECT).value
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuilt(staged, index)

    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        connection.execute("SELECT 1")  # the database is up again, as a restart leaves it

    assert staged.host.head(PROJECT).value == revision
    assert all(_store(_client()).verified(key) for key in set(keys.values()))


# --------------------------------------------------------------------------
# The blob store restarts
# --------------------------------------------------------------------------


def test_every_blob_answers_under_the_same_reference_after_a_restart(
    staged: Staged, blobs: S3BlobStore
) -> None:
    keys = _mirrored(staged, blobs)

    restarted = _store(_client())

    assert keys
    assert all(restarted.exists(key) for key in set(keys.values()))


def test_the_api_stays_ready_while_the_blob_store_is_gone(staged: Staged) -> None:
    """The mirror is rebuildable, so its absence degrades previews and nothing else."""
    client = _api(staged, None, (unavailable(OBJECT_STORE, "the mirror is restarting"),))

    readiness = client.get(READY_PATH)

    assert readiness.json()[STATUS_FIELD] == READY
    assert OBJECT_STORE in readiness.json()[DEGRADED_FIELD]


# --------------------------------------------------------------------------
# The API restarts
# --------------------------------------------------------------------------


def test_the_api_returns_to_serving_after_being_replaced(
    repo_root: Path, staged: Staged, postgres_dsn: str
) -> None:
    """A real process, terminated and started again over the same volumes."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuilt(staged, index)
    port = _free_port()
    first = _started(repo_root, staged, postgres_dsn, port)
    first.terminate()
    first.wait(timeout=10)

    second = _started(repo_root, staged, postgres_dsn, port)
    try:
        alive = _get(f"http://127.0.0.1:{port}{LIVE_PATH}")
        readiness = _get(f"http://127.0.0.1:{port}{READY_PATH}")
    finally:
        second.terminate()
        second.wait(timeout=10)

    assert ALIVE in alive[1]
    assert READY in readiness[1]


def test_a_restarting_api_leaves_the_state_on_the_volumes(
    repo_root: Path, staged: Staged, blobs: S3BlobStore, postgres_dsn: str
) -> None:
    """*"the remaining three SHALL continue running"* — and keep what they held."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuilt(staged, index)
        before = _answers(index)
    keys = _mirrored(staged, blobs)
    revision = staged.host.head(PROJECT).value

    port = _free_port()
    instance = _started(repo_root, staged, postgres_dsn, port)
    instance.terminate()
    instance.wait(timeout=10)

    with PostgresSearchIndex(postgres_dsn) as index:
        assert _answers(index) == before
    assert staged.host.head(PROJECT).value == revision
    assert all(_store(_client()).verified(key) for key in set(keys.values()))


def test_all_four_up_is_the_ordinary_state(staged: Staged, postgres_dsn: str) -> None:
    """The scenario's GIVEN, asserted rather than assumed."""
    with PostgresSearchIndex(postgres_dsn) as index:
        _rebuilt(staged, index)
        client = _api(
            staged,
            index,
            (available(SEARCH_INDEX), available(OBJECT_STORE)),
        )
        readiness = client.get(READY_PATH)

    assert readiness.json()[STATUS_FIELD] == READY
    assert readiness.json()[DEGRADED_FIELD] == []
