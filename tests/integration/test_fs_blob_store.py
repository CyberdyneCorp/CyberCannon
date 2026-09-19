"""Task 5.10 — `FsBlobStore`, and the association a preview is useless without.

The port conformance suite already runs the shared contract against this
adapter. What is asserted here is what only the filesystem can show: that the
association survives the process — a store opened fresh over the same directory
reads back which asset and which export a preview came from — and that a preview
produced by a real validation run lands where the record says it does.

A preview nobody can trace back to an export is a preview nobody can trust to be
current, and "current" is the only question a consumer will ever ask of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
from cybercanon.adapters.outbound.git.discovery import GIT_DIR
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.ports.preview import PreviewMesh
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.revisions import ContentHash, blob_key

pytestmark = pytest.mark.integration

ASSET = "mech_scout"
SPEC = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
LATER = "characters/mech_scout/exports/SM_mech_scout_LOD0.v2.glb"

SPEC_YAML = """\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
constraints:
  tri_budget: 12000
  naming: "SM_{asset}_LOD{n}"
"""

PREVIEW = PreviewMesh(content=b"glTF-preview-bytes", triangles=3577, parts=("SM_mech_scout_LOD0",))


def test_the_association_survives_a_freshly_opened_store(tmp_path: Path) -> None:
    FsBlobStore(tmp_path).put_preview(ASSET, EXPORT, PREVIEW)

    stored = FsBlobStore(tmp_path).preview_for(ASSET)

    assert stored is not None
    assert stored.asset_id == ASSET
    assert stored.source_export == EXPORT
    assert FsBlobStore(tmp_path).read(stored.key) == PREVIEW.content


def test_two_exports_of_one_asset_do_not_overwrite_each_other(tmp_path: Path) -> None:
    store = FsBlobStore(tmp_path)
    first = store.put_preview(ASSET, EXPORT, PREVIEW)
    second = store.put_preview(ASSET, LATER, PreviewMesh(content=b"v2", triangles=3000))

    assert first.key != second.key
    assert store.read(first.key) == PREVIEW.content
    assert store.preview_for(ASSET) == second, "the newest export is the current preview"


def test_a_validation_run_writes_a_traceable_preview(tmp_path: Path) -> None:
    """The whole path: read once, validate, emit, store — with the source recorded."""
    (tmp_path / GIT_DIR).mkdir(parents=True, exist_ok=True)
    (tmp_path / SPEC).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / SPEC).write_text(SPEC_YAML, encoding="utf-8")
    fixtures.write_skinned_glb(tmp_path / EXPORT)
    blobs = FsBlobStore(tmp_path / ".canon/cache")

    outcome = ran(
        validate_export(
            EXPORT,
            spec_store=GitSpecStore(tmp_path),
            mesh_inspector=TrimeshInspector(root=tmp_path),
            blob_store=blobs,
            emit_preview=True,
        )
    )

    assert outcome.preview_failure is None
    assert outcome.preview is not None
    assert outcome.preview.asset_id == ASSET
    assert outcome.preview.source_export == EXPORT
    assert blobs.read(outcome.preview.key)
    assert blobs.preview_for(ASSET) == outcome.preview


# --------------------------------------------------------------------------
# Task 7.2 — an interrupted upload leaves nothing readable at its key
# --------------------------------------------------------------------------


VIEW = b"\x89PNG\r\n\x1a\nthe scout mech, three-quarter"


def test_an_upload_in_flight_is_not_readable_at_its_key(tmp_path: Path) -> None:
    """The half-written file is beside the key, never at it.

    `blob-storage`: *"An upload that fails or is interrupted SHALL leave no
    readable object at its key."* `FsBlobStore` writes to a `.partial` name in
    the same directory and renames, so what an interruption leaves behind is
    exactly what is staged here — and the key still does not resolve.
    """
    store = FsBlobStore(tmp_path / "blobs")
    key = blob_key(ContentHash.of(VIEW))
    partial = store.root / key
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.with_name(partial.name + ".partial").write_bytes(VIEW[:8])

    assert not store.exists(key)
    assert store.read(key) is None


def test_the_completed_upload_replaces_the_partial_atomically(tmp_path: Path) -> None:
    """And the interrupted attempt leaves nothing behind once the real one lands."""
    store = FsBlobStore(tmp_path / "blobs")
    key = blob_key(ContentHash.of(VIEW))
    partial = (store.root / key).with_name((store.root / key).name + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_bytes(VIEW[:8])

    stored = store.put(VIEW)

    assert stored.key == key
    assert store.verified(key) == VIEW
    assert not partial.exists()
