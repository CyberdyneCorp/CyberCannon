"""Can an annotation anchored to a named part be resolved against the preview?

The 3D viewer loads the **preview**, never the working export, and an
`Anchor3D`'s durable key is the part name (`openspec/project.md` — "Annotations:
durable anchoring"). So the whole dual-anchor scheme rests on one property that
nothing else in this repository states as a test: *the part names an annotation
can be anchored to in the source export are present, unchanged, in the preview
the viewer will actually load.* If they are not, a pin does not report itself
orphaned — it resolves against whatever part did survive, and lands on the wrong
geometry. That is the silent failure the design exists to prevent, so it is
asserted here per format rather than assumed.

The answers this file records, one per supported format:

| format | preview emitted | anchor resolves |
|---|---|---|
| GLB | yes | **yes** — every object and every attachment point |
| glTF | yes | **yes** — same export, same code path |
| OBJ, one object | yes, via an in-memory glTF conversion | **yes** |
| OBJ, several objects | yes | **yes** — every `o` group, since the loader stopped merging them |
| FBX | yes, via an in-memory glTF conversion | **yes** — objects, sockets and bones |
| FBX whose clips carry no curves | **no**, refused by name | nothing to resolve against |

Both of the two defects this file was written to record are fixed, and the
tests that recorded them are still here, now asserting the capability: the
multi-object OBJ was one merged part and is now two, and an FBX had no preview
at all and now has one. The last case is the honest remainder — a clip this
reader cannot carry is refused rather than emitted without its motion — and it
is a refusal that names itself, not a silence.

`anchor-resolution` belongs to `add-viewer-3d`, and since that change landed the
rule is production code: :func:`resolves` below calls
:func:`cybercanon.domain.anchor_resolution.resolve`, the same pure function the
viewer's own surfaces answer orphan counts with. It used to be a one-line
restatement of the specification, which was right while nothing implemented it
and would now be a second implementation of exactly the rule this project
refuses to have twice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures import fbx as fbx_fixtures
from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.ports.preview import PreviewMesh, PreviewUnavailable
from cybercanon.domain.anchor_resolution import resolve
from cybercanon.domain.annotations import Anchor3D

pytestmark = pytest.mark.integration

RIGGED = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
RIGGED_GLTF = "characters/mech_scout/exports/SM_mech_scout_LOD0.gltf"
CRATE_OBJ = "props/crate/exports/SM_crate_LOD0.obj"
MULTIPART_OBJ = "characters/mech_scout/exports/SM_mech_scout_parts_LOD0.obj"
QUAD_FBX = "characters/quad_scout/exports/SM_quad_scout_LOD0.fbx"

CRATE_PART = "SM_crate_LOD0"
SOCKET = "SOCKET_muzzle_l"


@pytest.fixture(scope="module")
def repository(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("anchoring")
    fixtures.write_rigged_glb(root / RIGGED)
    fixtures.write_skinned_gltf(root / RIGGED_GLTF)
    fixtures.write_static_obj(root / CRATE_OBJ, name=CRATE_PART)
    fixtures.write_multipart_obj(root / MULTIPART_OBJ)
    fbx_fixtures.write_skinned_fbx(root / QUAD_FBX)
    return root


@pytest.fixture(scope="module")
def inspector(repository: Path) -> TrimeshInspector:
    return TrimeshInspector(root=repository)


def resolves(anchor: Anchor3D, preview: PreviewMesh) -> bool:
    """The resolution rule, asked of the domain rather than restated here.

    What this file tests is the *preview* — whether the names an anchor can key
    on survive emission, per format — so the rule it is held against has to be
    the one the viewer and the read surfaces use, not a paraphrase of it that
    could drift.
    """
    return resolve(anchor, preview.parts, preview.bones).is_resolved


def _preview(inspector: TrimeshInspector, export: str) -> PreviewMesh:
    return inspector.emit_preview(inspector.inspect(export))


# --------------------------------------------------------------------------
# glTF — the answer is yes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("part", [fixtures.SHOULDER, SOCKET])
def test_an_anchor_to_a_named_part_resolves_against_the_preview(
    inspector: TrimeshInspector, part: str
) -> None:
    """The question this run exists to answer, for the format the viewer gets."""
    assert resolves(Anchor3D(part=part), _preview(inspector, RIGGED))


def test_every_anchorable_name_in_the_source_survives_into_the_preview(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """Not "a part" but *every* part — resolution has to be total, not typical.

    A preview that kept the body and dropped the shoulder would orphan exactly
    the annotations about the shoulder, which is where the feedback lives.
    """
    authored = fixtures.write_rigged_glb(repository / RIGGED)
    anchorable = tuple(authored.objects) + tuple(authored.empties)

    preview = _preview(inspector, RIGGED)

    assert anchorable
    assert all(resolves(Anchor3D(part=part), preview) for part in anchorable)


def test_the_bone_of_an_anchor_also_survives(repository: Path, inspector: TrimeshInspector) -> None:
    """`Anchor3D.bone` is optional and not the durable key, but a viewer that
    cannot find the bone cannot follow the pin through an animation."""
    authored = fixtures.write_rigged_glb(repository / RIGGED)

    preview = _preview(inspector, RIGGED)

    assert set(authored.bones) <= set(preview.bones)


def test_an_anchor_to_a_part_the_export_does_not_contain_does_not_resolve(
    inspector: TrimeshInspector,
) -> None:
    """The negative direction, so the assertions above discriminate at all.

    A renamed part must orphan. If this resolved, every test in this file would
    pass against a preview containing nothing.
    """
    assert not resolves(Anchor3D(part="SM_MechScout_Shoulder_R"), _preview(inspector, RIGGED))


def test_the_gltf_container_answers_the_same_way(inspector: TrimeshInspector) -> None:
    """GLB and glTF are one code path; an anchor cannot resolve in only one."""
    preview = _preview(inspector, RIGGED_GLTF)

    assert resolves(Anchor3D(part=SOCKET), preview)
    assert resolves(Anchor3D(part="SM_mech_scout_LOD0"), preview)


# --------------------------------------------------------------------------
# OBJ — yes for one object, and yes for every object
# --------------------------------------------------------------------------


def test_an_obj_with_one_object_resolves(inspector: TrimeshInspector) -> None:
    """OBJ has no previewable form of its own; it is converted in memory first."""
    assert resolves(Anchor3D(part=CRATE_PART), _preview(inspector, CRATE_OBJ))


def test_an_obj_part_list_read_for_validation_matches_the_one_in_the_preview(
    inspector: TrimeshInspector,
) -> None:
    """The two readings must agree, or the report and the viewer disagree.

    `verify_carried` only ever compares the preview against the *converted*
    document, so it cannot see a name that conversion never had. This is the
    other comparison — preview against the facts the rules were actually run
    over — and it is what would catch a conversion that renamed a part. It did
    **not** catch the defect below, because both readings shared one loader and
    therefore shared its merge; catching that one needs the authored names, and
    the test below is where they are.
    """
    inspected = inspector.inspect(MULTIPART_OBJ)

    preview = inspector.emit_preview(inspected)

    assert set(inspected.facts.objects or ()) <= set(preview.parts)


def test_every_named_object_in_a_multi_object_obj_can_be_anchored_to(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """An artist's OBJ has a body and a shoulder, and both must be anchorable.

    This was the first of the two defects recorded here, as a strict xfail:
    `trimesh`'s OBJ loader defaults to `split_objects=False`, so every `o` group
    was merged into one geometry named after the first, and a pin anchored to
    the lost name did not orphan — it resolved against the part that survived
    and landed on the wrong geometry. Both call sites now read the file once,
    through `obj_facts.load_scene`, which keeps every group.
    """
    authored = fixtures.write_multipart_obj(repository / MULTIPART_OBJ)

    preview = _preview(inspector, MULTIPART_OBJ)

    assert len(authored.objects) > 1
    assert all(resolves(Anchor3D(part=part), preview) for part in authored.objects)


def test_a_part_a_multi_object_obj_does_not_contain_still_does_not_resolve(
    inspector: TrimeshInspector,
) -> None:
    """The negative direction for the same file: splitting did not invent parts."""
    assert not resolves(
        Anchor3D(part="SM_MechScout_Shoulder_R"), _preview(inspector, MULTIPART_OBJ)
    )


# --------------------------------------------------------------------------
# FBX — a preview, and an anchor that resolves against it
# --------------------------------------------------------------------------


def test_every_anchorable_name_in_an_fbx_survives_into_its_preview(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """The second defect this file recorded, now asserted as the capability.

    An FBX *was* read for validation — object names, the socket, the skeleton
    and the clips all reached the report — and then nothing converted it into a
    previewable document, so an FBX-only asset had no preview, the 3D viewer had
    nothing to load for it, and no annotation could be anchored to it at all.
    `fbx_gltf` converts it, and the question this file asks is answered the same
    way for FBX as for glTF: every name the report offers to anchor to is a name
    the preview carries.
    """
    authored = fbx_fixtures.write_skinned_fbx(repository / QUAD_FBX)
    anchorable = tuple(authored.objects) + tuple(authored.empties)

    preview = _preview(inspector, QUAD_FBX)

    assert anchorable
    assert all(resolves(Anchor3D(part=part), preview) for part in anchorable)


def test_an_fbx_part_list_read_for_validation_matches_the_one_in_the_preview(
    inspector: TrimeshInspector,
) -> None:
    """The two readings must agree, or the report and the viewer disagree.

    `verify_carried` only compares the preview against the *converted* document,
    so it cannot see a name the conversion never had. This is the other
    comparison — the preview against the facts the rules were actually run over.
    """
    inspected = inspector.inspect(QUAD_FBX)

    preview = inspector.emit_preview(inspected)

    anchorable = tuple(inspected.facts.objects or ()) + tuple(inspected.facts.empties or ())
    assert set(anchorable) <= set(preview.parts)


def test_the_bones_of_an_fbx_survive_into_its_preview(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """A bone is not the durable key, but a pin follows it through an animation."""
    authored = fbx_fixtures.write_skinned_fbx(repository / QUAD_FBX)

    preview = _preview(inspector, QUAD_FBX)

    assert set(authored.bones) <= set(preview.bones)
    assert preview.clips == authored.clip_names


def test_an_anchor_to_a_part_the_fbx_does_not_contain_does_not_resolve(
    inspector: TrimeshInspector,
) -> None:
    """The negative direction again, so the three assertions above discriminate."""
    assert not resolves(Anchor3D(part="SM_quad_scout_LOD1"), _preview(inspector, QUAD_FBX))


def test_an_fbx_clip_that_cannot_be_carried_is_refused_rather_than_emptied(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """The honest remainder, and the shape of every refusal this converter makes.

    A clip whose motion this reader cannot carry is not emitted as a clip of the
    right name and length that holds a pose — `asset-preview` makes a preview
    that lost its clips a failure, and a preview nobody can tell is degraded is
    the worse of the two outcomes. The export still validates: the refusal is a
    `PreviewUnavailable`, which never moves a verdict (D7).
    """
    export = "props/curveless/exports/SM_curveless_LOD0.fbx"
    authored = fbx_fixtures.write_curveless_fbx(repository / export)

    inspected = inspector.inspect(export)

    assert inspected.facts.clip_names == authored.clip_names
    with pytest.raises(PreviewUnavailable, match="carries no curve"):
        inspector.emit_preview(inspected)
