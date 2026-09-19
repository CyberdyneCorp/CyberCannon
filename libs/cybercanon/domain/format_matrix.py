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

A row can be narrow for two different reasons, and a report says which:
:data:`UNTRUSTED_BY_FORMAT` names the facts a format *does* record but which no
reader here can be trusted with. Both outcomes are NOT EVALUATED — the
difference is what the line tells the person reading it, because "`OBJ` carries
no unit scale" and "`FBX` carries no unit scale this reader can trust" invite
different fixes.

Both tables are exhaustive by construction: `tests/unit/test_domain_format_matrix.py`
asserts every :class:`~cybercanon.domain.mesh_facts.FactKind` is classified
present or absent for every format, so adding a fact without classifying it
fails the build rather than producing a quiet wrong NOT EVALUATED.

**On the FBX row.** `FBX` carries clips, skinning and sockets, but the facts a
reader can be *trusted* for are narrower, and this row is now a measurement
rather than a starting position (task 5.6, verified against a Blender export in
`tests/integration/`). Five facts are marked unavailable, so their rules report
NOT EVALUATED instead of a fabricated mismatch:

* **unit scale** — Blender writes `UnitScaleFactor: 1.0` into a file whose
  vertices are in metres, while the FBX convention reads that factor as
  centimetres per unit. The value is recorded and *actively unreliable*, which
  is worse than absent;
* **applied transforms** — spread across `Lcl *` properties, geometric
  transforms and a pivot system, none of which is the question the rule asks;
* **frame rate** (whole export and per clip) — a `TimeMode` enum, with a real
  number only when the exporter chose to write `CustomFrameRate`;
* **clip root motion** and **loop closure** — conventions in FBX, not recorded
  properties.
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

FBX_UNTRUSTED = frozenset(
    {
        FactKind.UNIT_SCALE,
        FactKind.TRANSFORMS_APPLIED,
        FactKind.FRAME_RATE,
        FactKind.CLIP_FRAME_RATE,
        FactKind.CLIP_ROOT_MOTION,
        FactKind.CLIP_LOOP,
    }
)
"""What an FBX records but no reader here can be trusted for. See the module docstring."""

_FBX_FACTS = frozenset(FactKind) - FBX_UNTRUSTED

UNTRUSTED_BY_FORMAT: Mapping[MeshFormat, frozenset[FactKind]] = MappingProxyType(
    {MeshFormat.FBX: FBX_UNTRUSTED}
)
"""Facts a format records but no reader here can be trusted with. Phrasing only.

A fact listed here is unavailable for the same reason as one the format cannot
record at all — the rule does not run either way — so this table never decides
an outcome. It decides the sentence.
"""

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


def absence_phrase(source_format: MeshFormat, kind: FactKind) -> str:
    """Why this format cannot yield that fact, in the words a report prints."""
    if kind in UNTRUSTED_BY_FORMAT.get(source_format, frozenset()):
        return f"{source_format} carries no {kind.label} this reader can trust"
    return f"{source_format} carries no {kind.label}"


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
    "FBX_UNTRUSTED",
    "UNTRUSTED_BY_FORMAT",
    "ContentKind",
    "UnsupportedExportFormat",
    "absence_phrase",
    "available_for",
    "can_contain",
    "facts_for",
    "unavailable_for",
]
