"""Tasks 3.12 and 3.14 — the capability matrix, and what it decides.

The matrix is a maintenance item with a quiet failure mode: a wrong row produces
a *wrong* NOT EVALUATED, which is quieter than a wrong violation. The mitigation
D13 names is exactly the first test here — every fact is classified present or
absent for every format, so adding a fact without classifying it fails the build.
"""

from __future__ import annotations

import pytest

from cybercanon.domain.format_matrix import (
    CONTENT_BY_FORMAT,
    FACTS_BY_FORMAT,
    FBX_UNTRUSTED,
    UNTRUSTED_BY_FORMAT,
    ContentKind,
    UnsupportedExportFormat,
    absence_phrase,
    available_for,
    can_contain,
    unavailable_for,
)
from cybercanon.domain.mesh_facts import FactKind, MeshFormat

OBJ_CANNOT_YIELD = (
    FactKind.CLIPS,
    FactKind.CLIP_DURATION,
    FactKind.CLIP_FRAME_RATE,
    FactKind.CLIP_LOOP,
    FactKind.CLIP_ROOT_MOTION,
    FactKind.FRAME_RATE,
    FactKind.BONE_COUNT,
    FactKind.SKINNING,
    FactKind.EMPTIES,
    FactKind.UNIT_SCALE,
    FactKind.UP_AXIS,
)

OBJ_YIELDS = (FactKind.TRIANGLES, FactKind.OBJECTS, FactKind.MATERIALS)


@pytest.mark.parametrize("source_format", list(MeshFormat))
@pytest.mark.parametrize("kind", list(FactKind))
def test_every_fact_is_classified_for_every_format(
    source_format: MeshFormat, kind: FactKind
) -> None:
    """Adding a `FactKind` without deciding each format's row fails the build."""
    row = FACTS_BY_FORMAT[source_format]

    assert (kind in row) or (kind in unavailable_for(source_format))


@pytest.mark.parametrize("source_format", list(MeshFormat))
def test_every_format_has_a_row_in_both_tables(source_format: MeshFormat) -> None:
    assert source_format in FACTS_BY_FORMAT
    assert source_format in CONTENT_BY_FORMAT


@pytest.mark.parametrize("kind", OBJ_CANNOT_YIELD)
def test_the_matrix_governs_obj_absences(kind: FactKind) -> None:
    assert kind not in available_for(MeshFormat.OBJ)


@pytest.mark.parametrize("kind", OBJ_YIELDS)
def test_the_matrix_governs_what_obj_does_yield(kind: FactKind) -> None:
    assert kind in available_for(MeshFormat.OBJ)


def test_gltf_and_glb_are_read_identically() -> None:
    assert available_for(MeshFormat.GLB) == available_for(MeshFormat.GLTF) == frozenset(FactKind)


def test_fbx_is_marked_unavailable_for_the_facts_it_cannot_be_trusted_for() -> None:
    """D13's honest move: a fact we cannot read is NOT EVALUATED, never fabricated.

    This row is a measurement (task 5.6): every entry was checked against a real
    Blender export. Unit scale is the one that proves the point — Blender writes
    `UnitScaleFactor: 1.0` into a file whose vertices are in metres, so the
    recorded value is worse than no value.
    """
    absent = unavailable_for(MeshFormat.FBX)

    assert absent == {
        FactKind.UNIT_SCALE,
        FactKind.TRANSFORMS_APPLIED,
        FactKind.FRAME_RATE,
        FactKind.CLIP_FRAME_RATE,
        FactKind.CLIP_ROOT_MOTION,
        FactKind.CLIP_LOOP,
    }
    assert absent == FBX_UNTRUSTED


def test_fbx_can_still_be_read_for_everything_a_rig_needs() -> None:
    """The row is narrowed, not abandoned: sockets, clips and bones still count."""
    row = available_for(MeshFormat.FBX)

    assert {
        FactKind.TRIANGLES,
        FactKind.OBJECTS,
        FactKind.MATERIALS,
        FactKind.UV_SETS,
        FactKind.UP_AXIS,
        FactKind.EMPTIES,
        FactKind.CLIPS,
        FactKind.CLIP_DURATION,
        FactKind.SKINNING,
        FactKind.BONE_COUNT,
    } <= row


def test_a_format_that_records_nothing_and_one_that_records_it_badly_read_differently() -> None:
    """Both are NOT EVALUATED; only the sentence tells the person which fix applies."""
    assert absence_phrase(MeshFormat.OBJ, FactKind.UNIT_SCALE) == "OBJ carries no unit scale"
    assert absence_phrase(MeshFormat.FBX, FactKind.UNIT_SCALE) == (
        "FBX carries no unit scale this reader can trust"
    )


@pytest.mark.parametrize("source_format", list(MeshFormat))
@pytest.mark.parametrize("kind", list(FactKind))
def test_an_untrusted_fact_is_always_an_unavailable_one(
    source_format: MeshFormat, kind: FactKind
) -> None:
    """A fact marked untrusted but left available would be a silent pass."""
    if kind in UNTRUSTED_BY_FORMAT.get(source_format, frozenset()):
        assert kind not in available_for(source_format)


@pytest.mark.parametrize("content", list(ContentKind))
def test_obj_can_contain_none_of_the_things_a_spec_can_demand(content: ContentKind) -> None:
    assert not can_contain(MeshFormat.OBJ, content)


@pytest.mark.parametrize("source_format", [MeshFormat.GLB, MeshFormat.GLTF, MeshFormat.FBX])
@pytest.mark.parametrize("content", list(ContentKind))
def test_the_rigged_formats_can_contain_everything(
    source_format: MeshFormat, content: ContentKind
) -> None:
    assert can_contain(source_format, content)


def test_a_format_with_no_row_is_refused_by_name_not_assumed() -> None:
    """A missing row must never read as 'nothing is checkable, everything passes'."""
    with pytest.raises(UnsupportedExportFormat) as raised:
        available_for("USD")  # type: ignore[arg-type]

    assert "USD" in str(raised.value)

    with pytest.raises(UnsupportedExportFormat):
        can_contain("USD", ContentKind.SKELETON)  # type: ignore[arg-type]
