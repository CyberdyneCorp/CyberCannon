"""What every `MeshInspector` SHALL do, whoever implements it (task 4.2).

The port is the D1 boundary: reading is here, rules are domain. So the contract
asserts the properties the domain depends on and deliberately asserts nothing
about geometry — a triangle count is the adapter's business and a fixture's, not
the port's.

What every implementation owes its caller:

* facts whose `available` mask is **exactly** the per-format matrix row, because
  that mask is the only basis for NOT EVALUATED (D13);
* a `source_format` matching the export it was handed;
* the same answer twice for the same file — a validator that drifts between runs
  is worse than no validator;
* a named failure for a file it cannot read, never empty facts;
* a preview derived from that same read, smaller than the source and carrying
  the source's named parts (D7, and `asset-preview`).

`TrimeshInspector` joins this suite in task 5.5 with fixture files standing in
for the corpus below.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.mesh_inspector import MeshInspector, MeshUnreadable
from cybercanon.domain.format_matrix import available_for
from cybercanon.domain.mesh_facts import MeshFormat


@dataclass(frozen=True)
class ExportFixture:
    """One export every implementation of the port is seeded with."""

    path: str
    source_format: MeshFormat
    objects: tuple[str, ...]
    triangles: int


SKINNED_GLB = ExportFixture(
    path="characters/mech_scout/exports/SM_mech_scout_LOD0.glb",
    source_format=MeshFormat.GLB,
    objects=("SM_mech_scout_LOD0",),
    triangles=14310,
)

STATIC_OBJ = ExportFixture(
    path="props/crate/exports/SM_crate_LOD0.obj",
    source_format=MeshFormat.OBJ,
    objects=("SM_crate_LOD0",),
    triangles=880,
)

CORPUS = (SKINNED_GLB, STATIC_OBJ)

UNREADABLE = "characters/mech_scout/exports/truncated.glb"
"""A file that exists and is not the mesh its extension claims."""

MISSING = "characters/mech_scout/exports/never_exported.glb"


class MeshInspectorContract:
    """The behaviour every mesh inspector shares."""

    def test_the_facts_name_the_format_they_came_from(self, implementation: MeshInspector) -> None:
        facts = implementation.inspect(SKINNED_GLB.path).facts

        assert facts.source_format is SKINNED_GLB.source_format

    @pytest.mark.parametrize("fixture", CORPUS, ids=lambda fixture: fixture.source_format.value)
    def test_the_available_mask_is_the_matrix_row(
        self, implementation: MeshInspector, fixture: ExportFixture
    ) -> None:
        """D13 — an adapter never widens or narrows its format's row by hand."""
        facts = implementation.inspect(fixture.path).facts

        assert facts.available == available_for(fixture.source_format)

    def test_reading_the_same_export_twice_gives_the_same_facts(
        self, implementation: MeshInspector
    ) -> None:
        first = implementation.inspect(SKINNED_GLB.path).facts
        second = implementation.inspect(SKINNED_GLB.path).facts

        assert first == second

    def test_an_unreadable_export_is_named_not_assumed(self, implementation: MeshInspector) -> None:
        with pytest.raises(MeshUnreadable) as raised:
            implementation.inspect(UNREADABLE)

        assert UNREADABLE in raised.value.message

    def test_a_missing_export_fails_the_operation(self, implementation: MeshInspector) -> None:
        with pytest.raises(OperationFailed):
            implementation.inspect(MISSING)

    def test_a_preview_comes_from_the_read_it_was_given(
        self, implementation: MeshInspector
    ) -> None:
        inspected = implementation.inspect(SKINNED_GLB.path)

        preview = implementation.emit_preview(inspected)

        assert preview.triangles < inspected.facts.triangles
        assert preview.content

    def test_a_preview_keeps_the_names_annotations_anchor_to(
        self, implementation: MeshInspector
    ) -> None:
        inspected = implementation.inspect(SKINNED_GLB.path)

        preview = implementation.emit_preview(inspected)

        assert set(SKINNED_GLB.objects) <= set(preview.parts)
