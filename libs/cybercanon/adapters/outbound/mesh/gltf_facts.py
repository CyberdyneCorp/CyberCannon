"""glTF and GLB, read into `MeshFacts`.

glTF is the format the matrix marks as recording everything (D13), and it earns
that row: units are metres by definition, the up axis is `+Y` by definition, and
clips, skins, sockets and materials are all explicit objects rather than
conventions. So this is the reader the other formats are measured against.

Two normalisations are worth naming, because they are interpretations rather
than lookups:

* **Frame rate is derived, not stored.** glTF records sample *times* in seconds
  and has no notion of a frame rate, so the rate is recovered from the sampling
  interval. A clip sampled every 1/30 s reports 30, which is what the spec's
  `frame_rate` means to the person who authored it in Blender.
* **Root motion is a question about the skeleton root.** A clip has root motion
  when it translates the skin's root bone and that translation actually changes.
  A clip that pins the root in place has none, which is the distinction an engine
  cares about.

Everything this reader cannot answer honestly it does not answer at all: a fact
is left ``None`` rather than defaulted, because `MeshFacts` refuses a value for
an unavailable fact and a fabricated one is worse than an absent one.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from cybercanon.adapters.outbound.mesh.gltf_document import TRIANGLES_MODE, GltfDocument
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import ClipFacts, MeshFacts, MeshFormat

GLTF_UP_AXIS = "Y"
"""glTF fixes `+Y` up; a reader that reported anything else would be guessing."""

GLTF_UNIT_SCALE = 1.0
"""glTF distances are metres by definition."""

_IDENTITY_ROTATION = (0.0, 0.0, 0.0, 1.0)


def read_facts(document: GltfDocument, source_format: MeshFormat) -> MeshFacts:
    """Everything the rules are allowed to know about one glTF export."""
    mesh_nodes = _mesh_nodes(document)
    clips = tuple(_clip(document, animation) for animation in document.gltf.animations or [])
    return facts_for(
        source_format,
        triangles=_triangles(document),
        objects=tuple(document.node_name(index) for index in mesh_nodes),
        transforms_applied=all(_is_applied(document.nodes[index]) for index in mesh_nodes),
        unit_scale=GLTF_UNIT_SCALE,
        up_axis=GLTF_UP_AXIS,
        uv_sets=_uv_sets(document),
        materials=tuple(material.name or "" for material in document.gltf.materials or []),
        empties=_empties(document),
        clips=clips,
        frame_rate=_export_frame_rate(clips),
        is_skinned=any(node.skin is not None for node in document.nodes),
        bone_count=len(document.joint_indices()),
    )


def _mesh_nodes(document: GltfDocument) -> tuple[int, ...]:
    return tuple(index for index, node in enumerate(document.nodes) if node.mesh is not None)


def _empties(document: GltfDocument) -> tuple[str, ...]:
    """Attachment points: a node that is neither geometry, nor bone, nor camera."""
    joints = document.joint_indices()
    return tuple(
        document.node_name(index)
        for index, node in enumerate(document.nodes)
        if node.mesh is None and node.camera is None and index not in joints
    )


def _triangles(document: GltfDocument) -> int:
    """Triangles across every primitive the document draws as triangles."""
    return sum(_primitive_triangles(document, primitive) for primitive in document.primitives())


def _primitive_triangles(document: GltfDocument, primitive: Any) -> int:
    if (primitive.mode if primitive.mode is not None else TRIANGLES_MODE) != TRIANGLES_MODE:
        return 0
    accessor = primitive.indices
    if accessor is None:
        accessor = getattr(primitive.attributes, "POSITION", None)
    return 0 if accessor is None else document.gltf.accessors[accessor].count // 3


def _uv_sets(document: GltfDocument) -> int:
    """How many UV sets the export carries, counted on the primitive that has most."""
    return max(
        (_texcoord_count(primitive.attributes) for primitive in document.primitives()),
        default=0,
    )


def _texcoord_count(attributes: Any) -> int:
    return sum(
        1
        for name, accessor in vars(attributes).items()
        if name.startswith("TEXCOORD_") and accessor is not None
    )


def _is_applied(node: Any) -> bool:
    """A mesh node with no transform of its own: the export baked it in."""
    return (
        node.matrix is None
        and _is_zero(node.translation)
        and _is_identity_rotation(node.rotation)
        and _is_one(node.scale)
    )


def _is_zero(values: list[float] | None) -> bool:
    return values is None or all(value == 0.0 for value in values)


def _is_one(values: list[float] | None) -> bool:
    return values is None or all(value == 1.0 for value in values)


def _is_identity_rotation(values: list[float] | None) -> bool:
    return values is None or tuple(values) == _IDENTITY_ROTATION


# --------------------------------------------------------------------------
# Clips
# --------------------------------------------------------------------------


def _clip(document: GltfDocument, animation: Any) -> ClipFacts:
    times = _sample_times(document, animation)
    frame_rate = _frame_rate(times)
    duration = max(times[-1], 0.0) if times else 0.0
    return ClipFacts(
        name=animation.name or "",
        frames=round(duration * frame_rate) if frame_rate else None,
        duration_s=duration,
        frame_rate=frame_rate,
        has_root_motion=_has_root_motion(document, animation),
        loop_closed=_loop_closed(document, animation),
    )


def _sample_times(document: GltfDocument, animation: Any) -> tuple[float, ...]:
    """Every sample time in the clip, sorted — the clip's own timeline."""
    return tuple(
        sorted(
            time for sampler in animation.samplers or [] for time in document.scalars(sampler.input)
        )
    )


def _frame_rate(times: tuple[float, ...]) -> float | None:
    """The rate the clip was sampled at, recovered from its smallest interval."""
    intervals = [round(later - earlier, 6) for earlier, later in pairwise(times) if later > earlier]
    return round(1.0 / min(intervals), 3) if intervals else None


def _export_frame_rate(clips: tuple[ClipFacts, ...]) -> float | None:
    """The export's own rate: the one its clips agree on, or nothing."""
    rates = {clip.frame_rate for clip in clips if clip.frame_rate is not None}
    return rates.pop() if len(rates) == 1 else None


def _loop_closed(document: GltfDocument, animation: Any) -> bool | None:
    """A loop is closed when every channel ends where it started."""
    samplers = animation.samplers or []
    if not samplers:
        return None
    return all(_ends_where_it_started(document, sampler) for sampler in samplers)


def _ends_where_it_started(document: GltfDocument, sampler: Any) -> bool:
    values = document.elements(sampler.output)
    return bool(values) and values[0] == values[-1]


def _has_root_motion(document: GltfDocument, animation: Any) -> bool | None:
    """Root motion is the skeleton root actually translating, not merely being keyed."""
    roots = document.skeleton_roots()
    if not roots:
        return None
    samplers = animation.samplers or []
    return any(
        _moves(document, samplers[channel.sampler])
        for channel in animation.channels or []
        if channel.target.node in roots and channel.target.path == "translation"
    )


def _moves(document: GltfDocument, sampler: Any) -> bool:
    values = document.elements(sampler.output)
    return len(set(values)) > 1


__all__ = ["GLTF_UNIT_SCALE", "GLTF_UP_AXIS", "read_facts"]
