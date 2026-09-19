"""Decimated previews that keep everything an annotation or a viewer anchors to.

`asset-preview` asks for a small mesh, and then spends most of its requirements
saying what a preview may **not** lose: object and attachment point names, every
clip with its name and duration, the skeleton and the skinning. A preview that
loads but cannot animate sends the viewer back to the 200 MB working export,
which defeats the point — so an emitter that cannot carry those reports a
*failure* rather than writing a degraded preview, and this module verifies that
by reading back what it just wrote rather than by trusting itself.

**How it decimates.** Triangles are dropped from each primitive's index list; no
vertex, attribute, joint binding, skin or animation sampler is touched. That is
"deliberately dumb" by design (D7) — preview quality is not a hill worth tuning
before a viewer exists to show what is actually needed — and it is what makes
"clips and skinning survive" true by construction rather than by luck. Textures
are dropped (material names are kept), which is where most of the size goes.

**On Draco.** D7 specifies a Draco-compressed preview, and `gltf_draco` provides
one: each primitive's vertices and its surviving triangles are encoded into a
`KHR_draco_mesh_compression` payload, which is what deletes the original vertex
buffers from the file. The encoder is a declared dependency with wheels for every
platform this runs on, but D7's recorded risk is a native dependency failing to
install, so compression stays a *choice made per document*: a machine without an
encoder, or a document the encoder cannot carry honestly, gets the uncompressed
decimated GLB instead. That is larger and still a browser-deliverable form, and
it loses nothing — which is the only property a preview is judged on.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Any

from pygltflib import GLTF2, Accessor, Buffer, BufferView

from cybercanon.adapters.outbound.mesh import gltf_draco, gltf_facts
from cybercanon.adapters.outbound.mesh.gltf_document import (
    TRIANGLES_MODE,
    GltfDocument,
    GltfUnreadable,
)
from cybercanon.application.ports.preview import PreviewMesh, PreviewUnavailable
from cybercanon.domain.mesh_facts import MeshFormat

DECIMATION_RATIO = 0.25
"""Keep roughly one triangle in four — a fixed fraction, per D7."""

TRIANGLE_CEILING = 20_000
"""And never more than this, however large the source."""

UNSIGNED_SHORT = 5123
UNSIGNED_INT = 5125
ELEMENT_ARRAY_BUFFER = 34963
_USHORT_MAX = 65535


@dataclass(frozen=True)
class PreviewSettings:
    """What decimation aims for. Configurable per project when a viewer asks."""

    ratio: float = DECIMATION_RATIO
    ceiling: int = TRIANGLE_CEILING


def emit_preview(document: GltfDocument, settings: PreviewSettings | None = None) -> PreviewMesh:
    """A decimated preview of an already-read glTF, verified against its source.

    Raises :class:`PreviewUnavailable` — never
    :class:`~cybercanon.application.errors.OperationFailed` — when the preview
    would lose a clip, a bone or a named part, or when the document uses
    something this emitter cannot rewrite honestly.
    """
    source = describe(document)
    try:
        content = _decimated_glb(document, settings or PreviewSettings())
        emitted = GltfDocument.from_bytes(content, source="preview")
        if gltf_draco.is_compressed(emitted):
            gltf_draco.verify(emitted)
        preview = describe(emitted)
    except (GltfUnreadable, ValueError, KeyError, IndexError) as error:
        raise PreviewUnavailable(f"the preview could not be built: {error}") from error
    verify_carried(source, preview)
    return PreviewMesh(
        content=content,
        triangles=preview.triangles,
        parts=preview.parts,
        clips=preview.clip_names,
        bones=preview.bones,
    )


# --------------------------------------------------------------------------
# What a preview must carry over
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Carried:
    """The properties a preview is judged on, read the same way from either side.

    Public because the refusal is the requirement, not an implementation detail:
    `asset-preview` makes a preview that dropped clips, bones or named parts a
    *failure*, and :func:`verify_carried` is where that decision is made and
    where it is tested.
    """

    triangles: int
    parts: tuple[str, ...]
    clip_names: tuple[str, ...]
    durations: tuple[float, ...]
    bones: tuple[str, ...]


def describe(document: GltfDocument) -> Carried:
    """What one glTF document carries, as the comparison sees it."""
    facts = gltf_facts.read_facts(document, MeshFormat.GLB)
    return Carried(
        triangles=facts.triangles or 0,
        parts=tuple(facts.objects) + tuple(facts.empties),
        clip_names=facts.clip_names,
        durations=tuple(round(clip.duration_s or 0.0, 4) for clip in facts.clips),
        bones=tuple(document.node_name(index) for index in sorted(document.joint_indices())),
    )


def verify_carried(source: Carried, preview: Carried) -> None:
    """Refuse a preview that lost what annotations and the viewer depend on.

    Raises :class:`PreviewUnavailable` — a preview that loads but cannot animate
    would send the viewer back to the working export, so a degraded preview is
    worse than none and is never written.
    """
    _refuse_missing("named parts", source.parts, preview.parts)
    _refuse_missing("animation clips", source.clip_names, preview.clip_names)
    _refuse_missing("bones", source.bones, preview.bones)
    if source.durations != preview.durations:
        raise PreviewUnavailable(
            f"clip durations changed in the preview: {source.durations} -> {preview.durations}"
        )
    if source.triangles and preview.triangles >= source.triangles:
        raise PreviewUnavailable(
            f"the preview is not smaller than its source "
            f"({preview.triangles} vs {source.triangles} triangles)"
        )


def _refuse_missing(what: str, source: tuple[str, ...], preview: tuple[str, ...]) -> None:
    lost = tuple(name for name in source if name not in preview)
    if lost:
        raise PreviewUnavailable(f"the preview would lose {what}: {', '.join(lost)}")


# --------------------------------------------------------------------------
# Decimation
# --------------------------------------------------------------------------


def _decimated_glb(document: GltfDocument, settings: PreviewSettings) -> bytes:
    """Drop triangles, compress what is left if it can be, and repack the buffer."""
    gltf = GLTF2.from_dict(document.gltf.to_dict())
    views = [_view_bytes(document, view) for view in document.gltf.bufferViews or []]
    keep = _keep_every(_triangle_total(document), settings)
    _write_geometry(document, gltf, views, _reductions(document, gltf, keep))
    _drop_textures(gltf)
    _repack(gltf, views)
    return b"".join(gltf.save_to_bytes())


def _keep_every(total: int, settings: PreviewSettings) -> int:
    """Keep one triangle in `n`, where `n` is what the target asks for."""
    target = max(1, min(int(total * settings.ratio), settings.ceiling))
    return max(2, math.ceil(total / target)) if total > target else 1


def _triangle_primitives(gltf: GLTF2) -> tuple[Any, ...]:
    return tuple(
        primitive
        for mesh in (gltf.meshes or [])
        for primitive in (mesh.primitives or [])
        if (primitive.mode if primitive.mode is not None else TRIANGLES_MODE) == TRIANGLES_MODE
    )


def _triangle_total(document: GltfDocument) -> int:
    return gltf_facts.read_facts(document, MeshFormat.GLB).triangles or 0


@dataclass(frozen=True)
class _Reduction:
    """One primitive and the triangles of its own index list that survive."""

    primitive: Any
    triangles: tuple[tuple[int, ...], ...]


def _reductions(document: GltfDocument, gltf: GLTF2, keep: int) -> tuple[_Reduction, ...]:
    """Every `keep`-th triangle of every triangle primitive, decided before anything moves.

    Deciding first and writing after is what lets compression be attempted and
    abandoned without leaving a half-rewritten document behind. An index accessor
    shared by two primitives is reduced once, exactly as before.
    """
    seen: set[int] = set()
    reductions: list[_Reduction] = []
    for primitive in _triangle_primitives(gltf):
        if primitive.indices is not None and primitive.indices in seen:
            continue
        triangles = _indices(document, primitive)[::keep]
        if triangles:
            reductions.append(_Reduction(primitive=primitive, triangles=triangles))
        if primitive.indices is not None:
            seen.add(primitive.indices)
    return tuple(reductions)


def _write_geometry(
    document: GltfDocument, gltf: GLTF2, views: list[bytes], reductions: tuple[_Reduction, ...]
) -> None:
    """Write the reduced geometry back, Draco-compressed when this document allows it."""
    compressed = _compressed(document, reductions)
    if compressed is None:
        for reduction in reductions:
            _write_indices(gltf, views, reduction)
        return
    for reduction, block in zip(reductions, compressed, strict=True):
        _write_draco(gltf, views, reduction, block)
    _declare_draco(gltf)


def _compressed(
    document: GltfDocument, reductions: tuple[_Reduction, ...]
) -> tuple[gltf_draco.Compressed, ...] | None:
    """Every reduction as a Draco buffer, or `None` when this document cannot be.

    All or nothing, deliberately: a file where one triangle primitive is
    compressed and its neighbour is not is harder to reason about than either
    whole form, and the uncompressed form loses nothing (D7).
    """
    if not reductions or not gltf_draco.available() or gltf_draco.shares_accessors(document):
        return None
    try:
        return tuple(
            gltf_draco.compress(document, reduction.primitive, reduction.triangles)
            for reduction in reductions
        )
    except Exception:  # compression is optional by construction (D7)
        return None


def _write_indices(gltf: GLTF2, views: list[bytes], reduction: _Reduction) -> None:
    """Point this primitive at the triangles it kept, in a freshly appended view.

    The accessor is *moved* to that new view rather than a second accessor being
    added beside it, so the original index data ends up referenced by nothing and
    :func:`_repack` drops it — which is part of why the preview is smaller.
    """
    kept = [index for triangle in reduction.triangles for index in triangle]
    view = _append_view(gltf, views, _packed(kept), target=ELEMENT_ARRAY_BUFFER)
    _point_at(gltf, reduction.primitive, view=view, count=len(kept), maximum=max(kept))


def _write_draco(
    gltf: GLTF2, views: list[bytes], reduction: _Reduction, block: gltf_draco.Compressed
) -> None:
    """Hand this primitive's geometry over to one Draco buffer.

    Every attribute accessor keeps its `count`, its type and its `min`/`max` and
    loses only its buffer view: that is what the extension means, and it is why
    the original vertex data becomes unreferenced and :func:`_repack` drops it.
    """
    view = _append_view(gltf, views, block.buffer, target=None)
    primitive = reduction.primitive
    _point_at(gltf, primitive, view=None, count=block.triangles * 3, maximum=block.vertices - 1)
    for accessor in vars(primitive.attributes).values():
        if accessor is not None:
            gltf.accessors[accessor].bufferView = None
            gltf.accessors[accessor].byteOffset = None
    primitive.extensions = {
        **(primitive.extensions or {}),
        gltf_draco.DRACO_EXTENSION: {"bufferView": view, "attributes": dict(block.attributes)},
    }


def _declare_draco(gltf: GLTF2) -> None:
    """A reader that cannot decode Draco must be told, not left to guess."""
    for declared in (gltf.extensionsUsed, gltf.extensionsRequired):
        if gltf_draco.DRACO_EXTENSION not in declared:
            declared.append(gltf_draco.DRACO_EXTENSION)


def _append_view(gltf: GLTF2, views: list[bytes], payload: bytes, *, target: int | None) -> int:
    views.append(payload)
    gltf.bufferViews.append(
        BufferView(buffer=0, byteOffset=0, byteLength=len(payload), target=target)
    )
    return len(gltf.bufferViews) - 1


def _point_at(gltf: GLTF2, primitive: Any, *, view: int | None, count: int, maximum: int) -> None:
    """Re-aim the primitive's index accessor, adding one when it had none.

    A compressed primitive's accessor has no buffer view, and glTF then forbids a
    `byteOffset` as well — an offset into nothing. The Khronos validator rejects
    it outright, so the two are set together and never independently.
    """
    accessor = Accessor(
        bufferView=view,
        byteOffset=None if view is None else 0,
        componentType=UNSIGNED_SHORT if maximum <= _USHORT_MAX else UNSIGNED_INT,
        count=count,
        type="SCALAR",
    )
    if primitive.indices is None:
        gltf.accessors.append(accessor)
        primitive.indices = len(gltf.accessors) - 1
        return
    gltf.accessors[primitive.indices] = accessor


def _indices(document: GltfDocument, primitive: Any) -> tuple[tuple[int, ...], ...]:
    """The primitive's triangles, indexed or not — a non-indexed one gets indices."""
    if primitive.indices is None:
        positions = getattr(primitive.attributes, "POSITION", None)
        if positions is None:
            return ()
        count = document.gltf.accessors[positions].count
        flat: tuple[int, ...] = tuple(range(count))
    else:
        flat = _scalar_indices(document, primitive.indices)
    return tuple(tuple(flat[start : start + 3]) for start in range(0, len(flat) - 2, 3))


def _scalar_indices(document: GltfDocument, accessor_index: int) -> tuple[int, ...]:
    accessor = document.gltf.accessors[accessor_index]
    size = document.element_size(accessor)
    unpack = {1: "<B", 2: "<H", 4: "<I"}.get(size)
    if unpack is None:
        raise GltfUnreadable(f"an index accessor of {size} bytes is not readable")
    return tuple(struct.unpack(unpack, element)[0] for element in document.elements(accessor_index))


def _packed(indices: list[int]) -> bytes:
    width = "H" if max(indices) <= _USHORT_MAX else "I"
    return struct.pack(f"<{len(indices)}{width}", *indices)


def _view_bytes(document: GltfDocument, view: Any) -> bytes:
    start = view.byteOffset or 0
    return document.blob[start : start + view.byteLength]


def _drop_textures(gltf: GLTF2) -> None:
    """Images are most of a preview's weight and nothing anchors to them."""
    gltf.images = []
    gltf.textures = []
    gltf.samplers = []
    for material in gltf.materials or []:
        _strip_texture_references(material)


def _strip_texture_references(material: Any) -> None:
    for name in ("normalTexture", "occlusionTexture", "emissiveTexture"):
        setattr(material, name, None)
    pbr = getattr(material, "pbrMetallicRoughness", None)
    if pbr is not None:
        pbr.baseColorTexture = None
        pbr.metallicRoughnessTexture = None


def _repack(gltf: GLTF2, views: list[bytes]) -> None:
    """Rebuild the binary chunk from the views still referenced, and only those.

    A Draco payload is referenced by its primitive's extension rather than by an
    accessor, so both kinds of reference are collected and both are remapped —
    a view dropped here is a preview that decodes to nothing.
    """
    payloads = _draco_payloads(gltf)
    referenced = sorted(_accessor_views(gltf) | {payload["bufferView"] for payload in payloads})
    blob = bytearray()
    remapped: dict[int, int] = {}
    kept: list[BufferView] = []
    for index in referenced:
        while len(blob) % 4:
            blob.append(0)
        view = gltf.bufferViews[index]
        remapped[index] = len(kept)
        kept.append(
            BufferView(
                buffer=0,
                byteOffset=len(blob),
                byteLength=len(views[index]),
                byteStride=view.byteStride,
                target=view.target,
            )
        )
        blob.extend(views[index])
    for accessor in gltf.accessors or []:
        if accessor.bufferView is not None:
            accessor.bufferView = remapped[accessor.bufferView]
    for payload in payloads:
        payload["bufferView"] = remapped[payload["bufferView"]]
    gltf.bufferViews = kept
    gltf.buffers = [Buffer(byteLength=len(blob))]
    gltf.set_binary_blob(bytes(blob))


def _accessor_views(gltf: GLTF2) -> set[int]:
    return {
        accessor.bufferView for accessor in gltf.accessors or [] if accessor.bufferView is not None
    }


def _draco_payloads(gltf: GLTF2) -> tuple[dict[str, Any], ...]:
    """The extension object of every compressed primitive, to remap in place."""
    return tuple(
        primitive.extensions[gltf_draco.DRACO_EXTENSION]
        for mesh in (gltf.meshes or [])
        for primitive in (mesh.primitives or [])
        if gltf_draco.DRACO_EXTENSION in (primitive.extensions or {})
    )


__all__ = [
    "DECIMATION_RATIO",
    "TRIANGLE_CEILING",
    "Carried",
    "PreviewSettings",
    "describe",
    "emit_preview",
    "verify_carried",
]
