"""Tasks 4.2 and 5.5 — the `MeshInspector` contract against every implementation.

The fake is seeded with facts; `TrimeshInspector` is seeded with *files*, written
into the temporary directory by `canon_fixtures.mesh` so nothing binary lives in
git. Running both through one body is what catches the divergence that matters:
a fake whose `available` mask is generous where the real reader's is not would
make every not-evaluated test green and every real report wrong.

The richer questions a real file can answer — that clip names and durations match
what was authored, that OBJ behaves end to end, that a preview keeps its bones —
belong to the opt-in integration suite (`tests/integration`), not here. This
suite asserts only what the *port* promises.
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from mesh_inspector_contract import (
    CORPUS,
    SKINNED_GLB,
    STATIC_OBJ,
    UNREADABLE,
    MeshInspectorContract,
)

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.domain.format_matrix import facts_for


def in_memory(directory: Path) -> InMemoryMeshInspector:
    """The fake, holding exactly the exports the contract asks about."""
    inspector = InMemoryMeshInspector()
    for fixture in CORPUS:
        inspector.add(
            fixture.path,
            facts_for(
                fixture.source_format,
                triangles=fixture.triangles,
                objects=fixture.objects,
            ),
        )
    inspector.add_unreadable(UNREADABLE, "unexpected end of file")
    return inspector


def real(directory: Path) -> TrimeshInspector:
    """The real adapter, over exports written into `directory` for this test."""
    fixtures.write_skinned_glb(directory / SKINNED_GLB.path, asset="mech_scout")
    fixtures.write_static_obj(directory / STATIC_OBJ.path, name=STATIC_OBJ.objects[0])
    fixtures.write_unreadable_glb(directory / UNREADABLE)
    return TrimeshInspector(root=directory)


implementation = implementation_fixture(fake=in_memory, real=real)


class TestMeshInspector(MeshInspectorContract):
    """The `MeshInspector` contract, against the fake and `TrimeshInspector`."""
