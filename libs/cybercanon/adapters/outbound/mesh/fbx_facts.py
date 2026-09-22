"""FBX, read into `MeshFacts` — and the four facts it deliberately refuses to state.

glTF is the format the matrix marks as recording everything; FBX is the format
that shows why the matrix exists. It carries clips, a skeleton and attachment
points, so an asset requiring them *can* be satisfied by an FBX — but several
facts an exporter writes into one cannot be trusted, and a fact that is
sometimes right is a fact that silently passes a rule when it is wrong.

**What this reader answers for**, each verified against a real Blender export
(`tests/integration/test_fbx_inspection.py`, and the opt-in Blender
cross-check in `tests/integration/test_fbx_against_blender.py`):

| Fact | Where it comes from |
|---|---|
| triangles | `PolygonVertexIndex`, whose last index per polygon is negated |
| object names | `Model`/`Mesh` records |
| material names | `Material` records |
| UV sets | `LayerElementUV` layers on the geometry that has most |
| attachment points | `Model`/`Null` records that do not parent a bone |
| up axis | `GlobalSettings` `UpAxis` and `UpAxisSign` |
| clips and durations | `AnimationStack` `LocalStart`/`LocalStop`, in FBX time units |
| skinning, bone count | a `Deformer`/`Skin`, and the `Model`/`LimbNode` records |

**What it refuses to answer for, and why** — these are the matrix rows
`format_matrix` marks unavailable for FBX, so their rules report NOT EVALUATED:

* **Unit scale.** Measured, not assumed: Blender 5.2 writes
  `UnitScaleFactor: 1.0` into a file whose vertices are in metres, while the FBX
  convention reads that factor as centimetres per unit. Either reading is wrong
  for some exporter, and a wrong unit scale is the one fact a validator must
  never state confidently — it is the defect the product exists to catch.
* **Applied transforms.** FBX spreads a node's placement across `Lcl *`
  properties, *geometric* translation/rotation/scaling and a pivot system. "The
  artist applied transforms before exporting" is not any one of them.
* **Frame rate.** `GlobalSettings` records a `TimeMode` enum, and a real value in
  `CustomFrameRate` only when the exporter chose to; recovering the rate from key
  spacing instead assumes every clip was baked per frame, which is an export
  option, not a property of the format.
* **Root motion and loop closure.** Conventions in FBX rather than recorded
  properties, as `design.md` already records for this format.

**What it refuses outright.** A file whose up axis or whose clip length is not
recorded raises, naming what is missing. The mask is per *format*, so a fact
marked available must be answerable for every file of that format; answering
``None`` instead would leave the rule looking satisfied.
"""

from __future__ import annotations

from cybercanon.adapters.outbound.mesh.fbx_document import (
    KTIME_PER_SECOND,
    FbxDocument,
    FbxNode,
    FbxUnreadable,
    object_property,
)
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import ClipFacts, MeshFacts, MeshFormat

AXIS_NAMES = ("X", "Y", "Z")
"""`GlobalSettings.UpAxis` is an index into this, and `UpAxisSign` its direction."""

CLIP_NAME_SEPARATOR = "|"
"""FBX takes are commonly named ``<object>|<clip>``; see :func:`clip_name`."""


def read_facts(document: FbxDocument) -> MeshFacts:
    """Everything the rules are allowed to know about one FBX export."""
    return facts_for(
        MeshFormat.FBX,
        triangles=_triangles(document),
        objects=tuple(node.object_name for node in document.objects("Model", "Mesh")),
        up_axis=_up_axis(document),
        uv_sets=_uv_sets(document),
        materials=tuple(node.object_name for node in document.objects("Material")),
        empties=_empties(document),
        clips=_clips(document),
        is_skinned=bool(document.objects("Deformer", "Skin")),
        bone_count=len(document.objects("Model", "LimbNode")),
    )


def _up_axis(document: FbxDocument) -> str:
    """The axis the file declares as up. Absent is a refusal, never an assumption."""
    axis = document.global_setting("UpAxis")
    if not isinstance(axis, int) or not 0 <= axis < len(AXIS_NAMES):
        raise FbxUnreadable(
            "this FBX records no up axis in GlobalSettings, and an assumed axis would "
            "be the defect the up-axis rule exists to catch"
        )
    sign = document.global_setting("UpAxisSign")
    prefix = "-" if isinstance(sign, int | float) and sign < 0 else ""
    return f"{prefix}{AXIS_NAMES[axis]}"


def _triangles(document: FbxDocument) -> int:
    """Triangles across every mesh geometry, fanning each polygon."""
    return sum(_geometry_triangles(node) for node in document.objects("Geometry", "Mesh"))


def _geometry_triangles(geometry: FbxNode) -> int:
    """Every polygon fanned into triangles — the same fan a preview is built from."""
    return sum(max(len(polygon) - 2, 0) for polygon in polygons(geometry))


def polygons(geometry: FbxNode) -> tuple[tuple[int, ...], ...]:
    """One `Geometry`'s polygons, each as its control point indices.

    A polygon's last index is stored negated, which is how FBX marks where a
    polygon ends. A non-empty list with no negated index is not a polygon list
    this reader understands, and reading it anyway would report every index as
    its own triangle — a triangle budget is the rule artists feel first, so it
    is refused instead.

    Public because the preview converter has to fan exactly the polygons the
    triangle count was taken over: two readings of one list disagree eventually,
    and the report and the viewer disagreeing is the failure this codebase
    refuses everywhere else.
    """
    indices = _polygon_indices(geometry)
    if indices and not any(index < 0 for index in indices):
        raise FbxUnreadable(
            f"geometry {geometry.object_name!r} has a polygon list with no polygon ends"
        )
    found: list[tuple[int, ...]] = []
    current: list[int] = []
    for index in indices:
        current.append(index if index >= 0 else ~index)
        if index < 0:
            found.append(tuple(current))
            current = []
    return tuple(found)


def _polygon_indices(geometry: FbxNode) -> list[int]:
    node = geometry.child("PolygonVertexIndex")
    payload = node.properties[0] if node and node.properties else None
    if not isinstance(payload, list):
        return []
    return [index for index in payload if isinstance(index, int)]


def _uv_sets(document: FbxDocument) -> int:
    """UV layers on the geometry that carries most — the export's UV set count."""
    return max(
        (len(node.children_named("LayerElementUV")) for node in document.objects("Geometry")),
        default=0,
    )


def _empties(document: FbxDocument) -> tuple[str, ...]:
    """Attachment points: a `Null` that is not the holder an armature hangs from.

    An exporter writes the armature object itself as a `Null` too (Blender does),
    and reporting that as a socket would be an attachment point nobody authored.
    A `Null` that parents a bone is a skeleton holder; anything else is a socket.
    """
    holders = _skeleton_holders(document)
    return tuple(
        node.object_name
        for node in document.objects("Model", "Null")
        if node.object_id not in holders
    )


def _skeleton_holders(document: FbxDocument) -> frozenset[int]:
    parents = document.parents_of()
    return frozenset(
        parent
        for bone in document.objects("Model", "LimbNode")
        for parent in parents.get(bone.object_id or -1, ())
    )


# --------------------------------------------------------------------------
# Clips
# --------------------------------------------------------------------------


def _clips(document: FbxDocument) -> tuple[ClipFacts, ...]:
    """One clip per animation stack, named and timed as the file records it."""
    names = frozenset(node.object_name for node in document.objects("Model"))
    return tuple(
        ClipFacts(name=clip_name(stack.object_name, names), duration_s=_duration(stack))
        for stack in document.objects("AnimationStack")
    )


def clip_name(recorded: str, model_names: frozenset[str]) -> str:
    """``Armature|A_scout_walk`` is the clip ``A_scout_walk`` on object `Armature`.

    The prefix is stripped only when it is the name of an object in this very
    file, so a clip an artist genuinely named with a ``|`` keeps its name and a
    Blender export stops reporting its armature's name as part of every clip.
    """
    prefix, separator, remainder = recorded.partition(CLIP_NAME_SEPARATOR)
    return remainder if separator and remainder and prefix in model_names else recorded


def _duration(stack: FbxNode) -> float:
    """The stack's length in seconds. A stack that records none is a refusal."""
    stop = object_property(stack, "LocalStop")
    if not isinstance(stop, int):
        raise FbxUnreadable(
            f"animation stack {stack.object_name!r} records no length, and a clip "
            "duration this reader invented would be compared against the specification"
        )
    start = object_property(stack, "LocalStart")
    begins = start if isinstance(start, int) else 0
    return (stop - begins) / KTIME_PER_SECOND


__all__ = ["AXIS_NAMES", "CLIP_NAME_SEPARATOR", "clip_name", "polygons", "read_facts"]
