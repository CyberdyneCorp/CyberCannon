"""What a 3D viewer test has on the table: a repository, an export and a preview.

Built on `tests/annotations_world.py` rather than beside it, because the viewer's
whole claim is that it reuses the annotation half unchanged — a world of its own
would be the first place that claim quietly stopped being true.

Everything is in memory and none of it is geometry: the export is a
:class:`~cybercanon.domain.mesh_facts.MeshFacts` built by hand, the preview is
bytes with a key, and the validation outcome is the JSON document G2 writes
beside the specification. That is the whole of D6 — every question this layer
answers is a question about *names*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from annotations_world import PROJECT, SCOUT, SCOUT_SPEC, Threads, a_world
from cybercanon.application.ports.preview import PreviewMesh
from cybercanon.application.ports.repository_host import FileChange
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.use_cases.validation_records import path_for, to_document
from cybercanon.application.use_cases.validation_worker import AUTOMATION_AUTHOR
from cybercanon.application.use_cases.viewer import (
    annotation_resolutions,
    get_preview_descriptor,
    read_preview,
)
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import ClipFacts, MeshFacts, MeshFormat
from cybercanon.domain.validation_outcome import ValidationRecord

EXPORT = "characters/mech_scout/exports/mech_scout.glb"
OLDER_EXPORT = "characters/mech_scout/exports/mech_scout_v1.glb"

SHOULDER = "SM_MechScout_Shoulder_L"
PAULDRON = "SM_MechScout_Pauldron_L"
TORSO = "SM_MechScout_Torso"
ARM = "SM_MechScout_Arm_L"

PARTS = (SHOULDER, TORSO, ARM)
MATERIALS = ("M_MechScout_Body", "M_MechScout_Glass")

WALK = "A_mech_scout_walk"
FIRE = "A_mech_scout_fire"

PREVIEW_BYTES = b"glTF\x02\x00\x00\x00decimated-preview"

VALIDATED_AT = datetime(2026, 9, 22, 9, 0, tzinfo=UTC)


def an_export(
    triangles: int | None = 14310,
    parts: tuple[str, ...] = PARTS,
    materials: tuple[str, ...] = MATERIALS,
    clips: tuple[str, ...] = (WALK,),
) -> MeshFacts:
    """One export as its validation run measured it. Names and counts, no geometry."""
    return facts_for(
        MeshFormat.GLB,
        triangles=triangles,
        objects=parts,
        materials=materials,
        clips=tuple(ClipFacts(name=name, duration_s=1.2) for name in clips),
    )


def a_validation(export: str = EXPORT, *, passed: bool = True, asset_id: str = SCOUT) -> bytes:
    """The outcome document G2 commits beside the specification."""
    return to_document(
        ValidationRecord(
            asset_id=asset_id,
            export=export,
            export_hash="sha256:" + "0" * 64,
            passed=passed,
            validated_at=VALIDATED_AT,
        )
    )


def a_spec_with_states(
    *states: str,
    unanimated: tuple[str, ...] = (),
    clip_naming: str = "A_{asset}_{state}",
) -> bytes:
    """A specification declaring design states, so clip coverage has something to cover.

    `unanimated` names the states declared with ``animated: false`` — the ones
    `animation-playback` requires to be shown as *declared unanimated* and never
    as a gap.
    """
    declared = [f"    - name: {state}" for state in states]
    declared += [f"    - name: {state}\n      animated: false" for state in unanimated]
    lines = [
        "schema_version: 1",
        f"id: {SCOUT}",
        "name: Scout Mech",
        "status: modeling",
        "constraints:",
        "  animation:",
        f"    clip_naming: {clip_naming}",
        "design:",
        "  states:" if declared else "  role: scout",
        *declared,
        "concept:",
        "  views: [front, side, back]",
    ]
    return ("\n".join(lines) + "\n").encode()


@dataclass
class Viewer:
    """A project with an asset, an export, an outcome and (usually) a preview."""

    threads: Threads
    mesh: InMemoryMeshInspector = field(default_factory=InMemoryMeshInspector)
    blobs: InMemoryBlobStore = field(default_factory=InMemoryBlobStore)

    # -- arranging -------------------------------------------------------

    def record_export(self, export: str = EXPORT, facts: MeshFacts | None = None) -> None:
        """This export exists and the inspector can read it."""
        self.mesh.add(export, facts or an_export())

    def record_validation(self, export: str = EXPORT, *, passed: bool = True) -> None:
        """The outcome file G2 writes, committed beside the specification."""
        self.threads.host.commit(
            PROJECT,
            [FileChange(path=path_for(SCOUT_SPEC), content=a_validation(export, passed=passed))],
            author=AUTOMATION_AUTHOR,
            message="validation outcome",
        )
        self.threads.host.push(PROJECT)

    def store_preview(
        self, export: str = EXPORT, content: bytes = PREVIEW_BYTES, asset_id: str = SCOUT
    ) -> None:
        self.blobs.put_preview(
            asset_id,
            export,
            PreviewMesh(content=content, triangles=4200, parts=PARTS, clips=(WALK,)),
        )

    # -- asking ----------------------------------------------------------

    def descriptor(self, asset_id: str = SCOUT, *, blobs: bool = True):
        return get_preview_descriptor(
            PROJECT,
            asset_id,
            repository_host=self.threads.host,
            spec_store=self.threads.spec_store,
            mesh_inspector=self.mesh,
            blob_store=self.blobs if blobs else None,
        )

    def preview_bytes(self, asset_id: str = SCOUT):
        return read_preview(
            PROJECT,
            asset_id,
            repository_host=self.threads.host,
            spec_store=self.threads.spec_store,
            blob_store=self.blobs,
        )

    def resolutions(self, parts: tuple[str, ...] = PARTS, bones=None, **workspace):
        return annotation_resolutions(
            self.threads.workspace(**workspace), export=EXPORT, parts=parts, bones=bones
        )


def a_viewer(spec: bytes | None = None, **files: bytes) -> Viewer:
    """The ordinary arrangement: an asset, a validated export and its preview."""
    viewer = Viewer(threads=a_world({SCOUT_SPEC: spec or a_spec_with_states(), **files}))
    viewer.record_export()
    viewer.record_validation()
    viewer.store_preview()
    return viewer


__all__ = [
    "ARM",
    "EXPORT",
    "FIRE",
    "MATERIALS",
    "OLDER_EXPORT",
    "PARTS",
    "PAULDRON",
    "PREVIEW_BYTES",
    "SHOULDER",
    "TORSO",
    "WALK",
    "Viewer",
    "a_spec_with_states",
    "a_validation",
    "a_viewer",
    "an_export",
]
