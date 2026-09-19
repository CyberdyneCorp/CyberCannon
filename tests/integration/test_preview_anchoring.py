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
| OBJ, several objects | yes | **no** — see the xfail below; a reader defect |
| FBX | **no** | nothing to resolve against — see the last test |

`anchor-resolution` itself belongs to `add-viewer-3d` and is not implemented, so
:func:`resolves` below is not production code being tested: it is the resolution
rule the specification states, written in one line, applied to the artifact the
viewer will load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canon_fixtures import fbx as fbx_fixtures
from canon_fixtures import mesh as fixtures
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.application.ports.preview import PreviewMesh, PreviewUnavailable
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
    """The resolution rule, stated: an anchor resolves iff its part is present.

    Deliberately one line and deliberately here rather than in `libs/` —
    `anchor-resolution` is `add-viewer-3d`'s capability and does not exist yet.
    What this file tests is the *preview*, against the rule the viewer will use.
    """
    return anchor.durable_key in preview.parts


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
# OBJ — yes for one object, and a reader defect for more than one
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
    over — and it is what would catch a conversion that renamed a part. It does
    **not** catch the defect below, because both readings share one loader and
    therefore share its merge; that one needs the authored names, and the xfail
    below is where they are.
    """
    inspected = inspector.inspect(MULTIPART_OBJ)

    preview = inspector.emit_preview(inspected)

    assert set(inspected.facts.objects or ()) <= set(preview.parts)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT (M0, this run): trimesh's OBJ loader defaults to group_material=True / "
        "split_objects=False, so every `o` group sharing a material is merged into one "
        "geometry named after the first. obj_facts._load and trimesh_inspector._as_gltf "
        "both take that default, so a multi-object OBJ loses every part name but one — "
        "in the facts the rules run over AND in the preview the viewer loads. An "
        "annotation anchored to the lost name cannot resolve, and its geometry now sits "
        "inside a part carrying another name. Fix: pass split_objects=True at both "
        "trimesh.load call sites. Not applied here: reporting, not rewriting."
    ),
)
def test_every_named_object_in_a_multi_object_obj_can_be_anchored_to(
    repository: Path, inspector: TrimeshInspector
) -> None:
    """An artist's OBJ has a body and a shoulder, and both must be anchorable."""
    authored = fixtures.write_multipart_obj(repository / MULTIPART_OBJ)

    preview = _preview(inspector, MULTIPART_OBJ)

    assert all(resolves(Anchor3D(part=part), preview) for part in authored.objects)


# --------------------------------------------------------------------------
# FBX — there is no preview to resolve against
# --------------------------------------------------------------------------


def test_an_fbx_export_yields_no_preview_at_all(inspector: TrimeshInspector) -> None:
    """The gap this run found, asserted as the contract it currently is.

    `test_fbx_inspection.py` already records that an FBX yields no preview and
    that this never moves the verdict. What it does not record is what that
    costs the anchoring scheme, which is the question here. An FBX *is* read for
    validation — object names, the socket, the skeleton and the clips all reach
    the report — and then nothing converts it into a previewable document, so
    `emit_preview` refuses. In order: an FBX-only asset has no preview, the 3D
    viewer has nothing to load for it, and no annotation can be anchored to it
    at all. The refusal is explicit and never touches the verdict (D7), so this
    is a missing capability rather than a silent one — but it is a whole format,
    and FBX is what a DCC exports.
    """
    inspected = inspector.inspect(QUAD_FBX)

    assert inspected.facts.objects
    assert inspected.handle is None
    with pytest.raises(PreviewUnavailable, match="not read into a previewable document"):
        inspector.emit_preview(inspected)
