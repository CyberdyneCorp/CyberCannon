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
    ContentKind,
    UnsupportedExportFormat,
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
    """D13's honest move: a fact we cannot read is NOT EVALUATED, never fabricated."""
    absent = unavailable_for(MeshFormat.FBX)

    assert absent == {FactKind.CLIP_LOOP, FactKind.CLIP_ROOT_MOTION}


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
