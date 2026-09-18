"""Task 4.9 — validation and compilation complete with every remote port raising.

The validator SHALL never require identity and SHALL never require the network
(openspec/project.md): the day auth is down or the artist is off-VPN she still
has to be able to commit, or the tool becomes the enemy. The layering contract
(D10) makes it structural — the validation path cannot even import an identity
or network adapter — and this is the behavioural half of the same promise.

Every port that will one day speak to something remote is configured to raise on
every call, and the assertion is that nothing in these two use cases notices.
"""

from __future__ import annotations

import pytest

from cybercanon.application.ports.preview import PreviewUnavailable
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.compile_spec import compile_project_briefing, compile_spec
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.rules import budgets

SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
UNREACHABLE = ConnectionError("the network is unreachable")


@pytest.fixture
def spec_store() -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.add(
        SPEC_PATH,
        Asset(
            id=AssetId("mech_scout"),
            name="Scout Mech",
            constraints=Constraints(tri_budget=12000),
        ),
    )
    store.set_project(ProjectConfig(name="Ironwood", defaults=Constraints(up_axis="Z")))
    return store


@pytest.fixture
def severed_blobs() -> InMemoryBlobStore:
    """The one port in this path that will be a remote service. Down, on purpose."""
    blobs = InMemoryBlobStore()
    blobs.fail_with(UNREACHABLE)
    return blobs


@pytest.fixture
def inspector() -> InMemoryMeshInspector:
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, facts_for(MeshFormat.GLB, triangles=14310, up_axis="Y"))
    return inspector


def test_validation_completes_and_reports_normally_while_everything_remote_is_down(
    spec_store: InMemorySpecStore,
    inspector: InMemoryMeshInspector,
    severed_blobs: InMemoryBlobStore,
) -> None:
    inspector.fail_preview(EXPORT, PreviewUnavailable("no compressor on this machine"))

    outcome = validate_export(
        EXPORT,
        spec_store=spec_store,
        mesh_inspector=inspector,
        blob_store=severed_blobs,
        emit_preview=True,
    )

    assert outcome.report.violations_of(budgets.TRI_BUDGET)
    assert not outcome.passed
    assert outcome.preview_failure is not None


def test_the_verdict_is_the_same_with_the_remote_ports_up_and_down(
    spec_store: InMemorySpecStore,
    inspector: InMemoryMeshInspector,
    severed_blobs: InMemoryBlobStore,
) -> None:
    """Offline is not a degraded mode: it is the same decision, byte for byte."""
    offline = validate_export(
        EXPORT,
        spec_store=spec_store,
        mesh_inspector=inspector,
        blob_store=severed_blobs,
        emit_preview=True,
    )
    online = validate_export(EXPORT, spec_store=spec_store, mesh_inspector=inspector)

    assert offline.report == online.report


def test_compilation_succeeds_and_is_identical_with_every_remote_port_raising(
    spec_store: InMemorySpecStore, severed_blobs: InMemoryBlobStore
) -> None:
    """compile_spec never touches a blob store, an identity or a model — by design."""
    with pytest.raises(ConnectionError):
        severed_blobs.preview_for("mech_scout")

    first = compile_spec(SPEC_PATH, spec_store=spec_store)
    second = compile_spec(SPEC_PATH, spec_store=spec_store)

    assert first.text == second.text
    assert "Scout Mech" in first.text


def test_the_project_briefing_compiles_offline_too(spec_store: InMemorySpecStore) -> None:
    briefing = compile_project_briefing("", spec_store=spec_store)

    assert briefing.project == "Ironwood"
    assert "- **Up axis**: Z" in briefing.text
