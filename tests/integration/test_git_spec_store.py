"""Tasks 5.1-5.4 — `GitSpecStore` against real files in a real working copy.

The port conformance suite already proves this adapter answers the port the same
way the fake does. What is asserted here is what only a file can show: that a
commented specification survives a load-and-dump byte for byte (D4), that a
newer major `schema_version` is refused by name (D6), that an unrecognised field
is a warning and the mesh still gets validated (D5), and that discovery walks
upward and stops (D9).

Marked `integration` because it touches the filesystem: the domain suite runs
with zero files on disk and stays that way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
from cybercanon.adapters.outbound.git import yaml_io
from cybercanon.adapters.outbound.git.discovery import GIT_DIR
from cybercanon.adapters.outbound.git.schema import RULE_UNKNOWN_FIELD, SCHEMA_VERSION
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.ports.spec_store import SpecNotFound, SpecUnreadable
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.status import Status

pytestmark = pytest.mark.integration

SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
NESTED = "characters/mech_scout/exports/lod/SM_mech_scout_LOD2.glb"

COMMENTED_SPEC = """\
# Scout mech — the canon for this asset.
#
# Art owns `concept`, design owns `design`, engineering owns `constraints`.
schema_version: 1
id: mech_scout
name: "Scout Mech"          # the human-readable name; the id never changes
status: modeling
owner_art: rafa

design:
  role: light recon walker
  # A declared socket becomes an export gate.
  sockets:
    - name: SOCKET_muzzle_l
      purpose: muzzle flash
  states:
    - name: walk
    - name: destroyed
      animated: false

constraints:
  tri_budget: 12000
  lods: [12000, 6000, 2000]
  naming: "SM_{asset}_LOD{n}"
  animation:
    frame_rate: 30
    clip_naming: "A_{asset}_{state}"
"""


def _repository(root: Path, spec: str = COMMENTED_SPEC) -> GitSpecStore:
    (root / GIT_DIR).mkdir(parents=True, exist_ok=True)
    written = root / SPEC_PATH
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(spec, encoding="utf-8")
    return GitSpecStore(root)


# --------------------------------------------------------------------------
# 5.1 — round-trip parse, and the newer-major refusal (D6)
# --------------------------------------------------------------------------


def test_a_specification_parses_into_its_declared_asset(tmp_path: Path) -> None:
    loaded = _repository(tmp_path).load(SPEC_PATH)

    assert loaded.asset.id.value == "mech_scout"
    assert loaded.asset.status is Status.MODELING
    assert loaded.asset.design is not None
    assert loaded.asset.design.socket_names == ("SOCKET_muzzle_l",)
    assert loaded.asset.constraints is not None
    assert loaded.asset.constraints.lods == (12000, 6000, 2000)
    assert loaded.asset.clip_naming == "A_{asset}_{state}"


def test_a_newer_major_schema_version_is_refused_by_name(tmp_path: Path) -> None:
    """D6 — and only a *newer* one: an older file must keep working."""
    future = COMMENTED_SPEC.replace("schema_version: 1", f"schema_version: {SCHEMA_VERSION + 1}")
    store = _repository(tmp_path, future)

    with pytest.raises(SpecUnreadable) as raised:
        store.load(SPEC_PATH)

    assert str(SCHEMA_VERSION + 1) in raised.value.message
    assert "upgrade canon" in raised.value.message


def test_a_same_major_minor_version_is_read(tmp_path: Path) -> None:
    minor = COMMENTED_SPEC.replace("schema_version: 1", "schema_version: 1.4")
    store = _repository(tmp_path, minor)

    assert store.load(SPEC_PATH).asset.id.value == "mech_scout"


def test_a_file_that_is_not_yaml_names_the_file(tmp_path: Path) -> None:
    store = _repository(tmp_path, "id: [unclosed\n")

    with pytest.raises(SpecUnreadable) as raised:
        store.load(SPEC_PATH)

    assert SPEC_PATH in raised.value.message


# --------------------------------------------------------------------------
# 5.2 — an unknown field is a warning, and the mesh is still validated (D5)
# --------------------------------------------------------------------------


def test_an_unrecognised_field_is_reported_with_its_location(tmp_path: Path) -> None:
    store = _repository(tmp_path, COMMENTED_SPEC + "  shinyness: 3\n")

    warnings = store.load(SPEC_PATH).warnings

    assert [warning.subject for warning in warnings] == ["constraints.shinyness"]
    assert warnings[0].rule_id == RULE_UNKNOWN_FIELD
    assert "shinyness" in warnings[0].message


def test_a_spec_with_an_unrecognised_field_still_validates_its_mesh(tmp_path: Path) -> None:
    """Version skew must never block a commit — the whole point of D5."""
    store = _repository(tmp_path, COMMENTED_SPEC + "  shinyness: 3\n")
    fixtures.write_skinned_glb(tmp_path / EXPORT)

    outcome = validate_export(
        EXPORT,
        spec_store=store,
        mesh_inspector=TrimeshInspector(root=tmp_path),
        blob_store=FsBlobStore(tmp_path / ".canon/cache"),
    )

    assert outcome.report.export_format is not None
    assert [warning.subject for warning in outcome.spec_warnings] == ["constraints.shinyness"]
    assert outcome.report.violations_of("spec.unknown_field") == ()


# --------------------------------------------------------------------------
# 5.3 — round-trip YAML (D4)
# --------------------------------------------------------------------------


def test_load_then_dump_preserves_comments_and_key_order_byte_for_byte() -> None:
    """The property that keeps `asset.yaml` diffs reviewable when writing lands."""
    assert yaml_io.dump(yaml_io.load(COMMENTED_SPEC)) == COMMENTED_SPEC


def test_the_round_trip_keeps_comments_attached_to_their_field() -> None:
    dumped = yaml_io.dump(yaml_io.load(COMMENTED_SPEC))

    assert "# the human-readable name; the id never changes" in dumped
    assert "# A declared socket becomes an export gate." in dumped


# --------------------------------------------------------------------------
# 5.4 — upward discovery, bounded by the git root (D9)
# --------------------------------------------------------------------------


def test_discovery_from_an_export_path_finds_the_governing_spec(tmp_path: Path) -> None:
    assert _repository(tmp_path).discover(EXPORT) == SPEC_PATH


def test_discovery_from_a_nested_path_walks_all_the_way_up(tmp_path: Path) -> None:
    assert _repository(tmp_path).discover(NESTED) == SPEC_PATH


def test_discovery_finds_nothing_for_a_path_belonging_to_no_asset(tmp_path: Path) -> None:
    """An answer, not an error: most touched files belong to no asset."""
    assert _repository(tmp_path).discover("docs/pipeline.md") is None


def test_discovery_is_bounded_by_the_repository_root(tmp_path: Path) -> None:
    """A specification above the repository governs a different project."""
    outside = tmp_path / "elsewhere"
    repository = outside / "game"
    (outside / "asset.yaml").parent.mkdir(parents=True, exist_ok=True)
    _repository(repository)
    (outside / "asset.yaml").write_text("id: not_ours\nname: Not Ours\n", encoding="utf-8")

    assert GitSpecStore(repository).discover("docs/pipeline.md") is None


def test_an_absolute_path_inside_the_repository_is_accepted(tmp_path: Path) -> None:
    store = _repository(tmp_path)

    assert store.discover(str(tmp_path / EXPORT)) == SPEC_PATH


def test_a_path_outside_the_repository_discovers_nothing(tmp_path: Path) -> None:
    store = _repository(tmp_path / "game")

    assert store.discover(str(tmp_path / "elsewhere/thing.glb")) is None


def test_loading_a_spec_that_is_not_there_is_reported(tmp_path: Path) -> None:
    with pytest.raises(SpecNotFound):
        _repository(tmp_path).load("characters/nobody/asset.yaml")
