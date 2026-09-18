"""The per-format capability matrix — one table, two questions (D13).

A validator that silently passes every rule it could not run is worse than one
that refuses the format, because the team stops looking. So this module answers,
in one place, the two questions that are constantly confused:

* **Can the format *record* this fact?** :data:`FACTS_BY_FORMAT`. `OBJ` records
  no unit scale, so an `OBJ` export may well be correctly scaled and the honest
  outcome is NOT EVALUATED, never a pass and never a failure.
* **Can the format *contain* this thing at all?** :data:`CONTENT_BY_FORMAT`.
  `OBJ` cannot hold an animation clip, so an asset that requires one can never
  be satisfied by an `OBJ` export — an ordinary `error`, with an obvious fix.

Both tables are exhaustive by construction: `tests/unit/test_domain_format_matrix.py`
asserts every :class:`~cybercanon.domain.mesh_facts.FactKind` is classified
present or absent for every format, so adding a fact without classifying it
fails the build rather than producing a quiet wrong NOT EVALUATED.

**On the FBX row.** `FBX` carries clips, skinning and sockets, but the facts a
reader can be *trusted* for are narrower: clip loop closure and root motion are
conventions rather than recorded properties there, so they are marked
unavailable and their rules report NOT EVALUATED instead of a fabricated
mismatch. Group 5 owns tightening this row against real fixtures (task 5.6);
this is the honest starting position, not a measurement.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType

from cybercanon.domain.mesh_facts import ALWAYS_AVAILABLE, FactKind, MeshFacts, MeshFormat


class ContentKind(Enum):
    """Something a specification can demand that a container format may lack."""

    ANIMATION_CLIPS = "animation clips"
    SKELETON = "a skeleton"
    ATTACHMENT_POINTS = "attachment points"

    def __str__(self) -> str:
        return self.value


class UnsupportedExportFormat(Exception):
    """A format the matrix does not cover. Named, never assumed."""

    def __init__(self, name: object) -> None:
        super().__init__(
            f"{name} is not a supported export format; supported formats are "
            + ", ".join(fmt.value for fmt in MeshFormat)
        )
        self.name = name


_GLTF_FACTS = frozenset(FactKind)
"""glTF records every fact: clips, durations, frame rates, scale and axis are explicit."""

_FBX_FACTS = frozenset(FactKind) - {FactKind.CLIP_LOOP, FactKind.CLIP_ROOT_MOTION}

_OBJ_FACTS = (
    frozenset(
        {
            FactKind.TRIANGLES,
            FactKind.OBJECTS,
            FactKind.MATERIALS,
            FactKind.UV_SETS,
        }
    )
    | ALWAYS_AVAILABLE
)

FACTS_BY_FORMAT: Mapping[MeshFormat, frozenset[FactKind]] = MappingProxyType(
    {
        MeshFormat.GLB: _GLTF_FACTS,
        MeshFormat.GLTF: _GLTF_FACTS,
        MeshFormat.FBX: _FBX_FACTS,
        MeshFormat.OBJ: _OBJ_FACTS,
    }
)
"""Which facts each format can be read for. The only basis for NOT EVALUATED."""

_EVERYTHING = frozenset(ContentKind)

CONTENT_BY_FORMAT: Mapping[MeshFormat, frozenset[ContentKind]] = MappingProxyType(
    {
        MeshFormat.GLB: _EVERYTHING,
        MeshFormat.GLTF: _EVERYTHING,
        MeshFormat.FBX: _EVERYTHING,
        MeshFormat.OBJ: frozenset(),
    }
)
"""What each format can carry at all. The only basis for `format.unsuitable_for_asset`."""


def available_for(source_format: MeshFormat) -> frozenset[FactKind]:
    """The facts this format can yield.

    Raises :class:`UnsupportedExportFormat` for a format with no row, so a
    missing row can never be read as "nothing is checkable, everything passes".
    """
    facts = FACTS_BY_FORMAT.get(source_format)
    if facts is None:
        raise UnsupportedExportFormat(source_format)
    return facts


def can_contain(source_format: MeshFormat, content: ContentKind) -> bool:
    """Whether an export in this format could hold that thing at all."""
    carried = CONTENT_BY_FORMAT.get(source_format)
    if carried is None:
        raise UnsupportedExportFormat(source_format)
    return content in carried


def unavailable_for(source_format: MeshFormat) -> frozenset[FactKind]:
    """The facts this format cannot yield — what a report lists as suppressed."""
    return frozenset(FactKind) - available_for(source_format)


def facts_for(source_format: MeshFormat, **observed: object) -> MeshFacts:
    """Build :class:`MeshFacts` whose mask is this format's row.

    The one constructor an adapter — or a test that wants a realistic export —
    should use: values for facts the format cannot yield are refused rather than
    quietly dropped (:class:`~cybercanon.domain.mesh_facts.FabricatedFact`).
    """
    return MeshFacts(
        source_format=source_format,
        available=available_for(source_format),
        **observed,  # type: ignore[arg-type]
    )


__all__ = [
    "CONTENT_BY_FORMAT",
    "FACTS_BY_FORMAT",
    "ContentKind",
    "UnsupportedExportFormat",
    "available_for",
    "can_contain",
    "facts_for",
    "unavailable_for",
]
