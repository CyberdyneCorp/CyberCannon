"""Task 12.2 — the worker runs outside the request path, proved with a slow read.

G1: *"Not in the request path. Mesh loading is unbounded work; an HTTP handler
that waits on it is a timeout with extra steps."* A property about *where* work
happens cannot be asserted by reading the code, so it is asserted the only way
it can be: a mesh inspector that deliberately takes a second, a notification
posted over a real transport, and a response that comes back long before the
inspection finishes — and an outcome that is nevertheless committed afterwards.

The runner is
:class:`~cybercanon.adapters.wiring.background.BackgroundWork`, which is what
the composition root hands the notification endpoint as its `refresh`. It has
nothing in it but a queue, which is the point: the decision about *what* to do
with a project is the use case's, and this is only the seam that keeps it off
the event loop.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.webhooks import (
    ACCEPTED,
    SIGNATURE_HEADER,
    WEBHOOK_PATH,
    RepositoryNotifications,
    signature_for,
)
from cybercanon.adapters.wiring.background import BackgroundWork
from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.ports.mesh_inspector import InspectedMesh
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.validation_records import RECORD_NAME
from cybercanon.application.use_cases.validation_worker import validate_changed_exports
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat

PROJECT = "cyberdyne-game"
BRANCH = "main"
SECRET = "a-shared-secret-nobody-commits"

SPEC = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
RECORD = f"characters/mech_scout/{RECORD_NAME}"

SPEC_BYTES = b"schema_version: 1\nid: mech_scout\n"
MESH = b"glTF-ish bytes nothing here parses"

NOON = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

SLOW_S = 1.0
"""How long the deliberately slow inspector takes to read one export."""

RESPONSE_BUDGET_S = SLOW_S / 4
"""What the notification response must beat. A quarter is not a close call."""

PATIENCE_S = 20.0
"""How long the test waits for the background pass, on a loaded machine."""


class SlowInspector:
    """An inspector that takes :data:`SLOW_S` to read an export, then answers.

    Wrapping the fake rather than replacing it, so the facts, the preview and
    the failure modes are the ones every other test uses and the only difference
    is the one this test is about: reading a mesh is slow.
    """

    def __init__(self, inner: InMemoryMeshInspector) -> None:
        self._inner = inner
        self.started = threading.Event()

    def inspect(self, export: str) -> InspectedMesh:
        self.started.set()
        time.sleep(SLOW_S)
        return self._inner.inspect(export)

    def emit_preview(self, mesh: InspectedMesh):
        return self._inner.emit_preview(mesh)


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC: SPEC_BYTES, EXPORT: MESH})
    built.clone(PROJECT)
    return built


@pytest.fixture
def store(host: InMemoryRepositoryHost) -> InMemorySpecStore:
    built = InMemorySpecStore()
    built.add(
        SPEC,
        Asset(
            id=AssetId("mech_scout"), name="Scout Mech", constraints=Constraints(tri_budget=12000)
        ),
    )
    built.snapshot(host.head(PROJECT).value)
    return built


def a_slow_job(host: InMemoryRepositoryHost, store: InMemorySpecStore) -> SlowInspector:
    inner = InMemoryMeshInspector()
    inner.add(EXPORT, facts_for(MeshFormat.GLB, triangles=11840))
    return SlowInspector(inner)


def notify(client: TestClient) -> float:
    """Post one authenticated notification and answer how long it took."""
    body = f'{{"project": "{PROJECT}", "ref": "refs/heads/{BRANCH}"}}'.encode()
    started = time.perf_counter()
    response = client.post(
        WEBHOOK_PATH,
        content=body,
        headers={SIGNATURE_HEADER: signature_for(SECRET, body)},
    )
    elapsed = time.perf_counter() - started
    assert response.status_code == ACCEPTED
    return elapsed


def test_a_notification_does_not_block_on_mesh_loading(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """The request returns while the inspector is still reading the export."""
    inspector = a_slow_job(host, store)

    def job(project: str) -> None:
        validate_changed_exports(
            project,
            repository_host=host,
            spec_store=store,
            mesh_inspector=inspector,
            clock=fixed_clock(NOON),
        )

    with BackgroundWork(job) as work:
        client = TestClient(
            build_app(
                notifications=RepositoryNotifications(
                    secret=SECRET, branches={PROJECT: BRANCH}, refresh=work.submit
                )
            )
        )
        elapsed = notify(client)
        assert inspector.started.wait(PATIENCE_S)
        assert RECORD not in host.remote_files(PROJECT)

        assert work.wait(PATIENCE_S)

    assert elapsed < RESPONSE_BUDGET_S
    assert RECORD in host.remote_files(PROJECT)


def test_an_unauthenticated_notification_queues_no_work(
    host: InMemoryRepositoryHost, store: InMemorySpecStore
) -> None:
    """D4's refusal is unchanged by there being a worker behind the endpoint."""
    asked: list[str] = []

    with BackgroundWork(asked.append) as work:
        client = TestClient(
            build_app(
                notifications=RepositoryNotifications(
                    secret=SECRET, branches={PROJECT: BRANCH}, refresh=work.submit
                )
            )
        )
        response = client.post(WEBHOOK_PATH, content=b'{"project": "cyberdyne-game"}')
        assert work.wait(PATIENCE_S)

    assert response.status_code != ACCEPTED
    assert asked == []


def test_a_failing_pass_does_not_end_the_runner() -> None:
    """One project's failure must not silently stop background work for the rest."""
    seen: list[str] = []
    failures: list[str] = []

    def job(project: str) -> None:
        seen.append(project)
        if project == "broken":
            raise RuntimeError("the export is truncated")

    with BackgroundWork(job, on_error=lambda project, _: failures.append(project)) as work:
        work.submit("broken")
        assert work.wait(PATIENCE_S)
        work.submit("healthy")
        assert work.wait(PATIENCE_S)

    assert seen == ["broken", "healthy"]
    assert failures == ["broken"]
