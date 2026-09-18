"""What an export *is*, as facts — the boundary between reading and ruling (D1).

`MeshInspector` reads a file and returns one of these. Nothing here knows how a
`.glb` is laid out, and nothing here touches a file: the whole validation suite
runs over hand-built :class:`MeshFacts`, which is the single decision that makes
the rules cheap to write and impossible to break silently.

Two properties are structural rather than documented:

* **Every value is optional, and `available` is the authority.** A fact a format
  cannot carry has no substitute value — not ``0``, not ``1.0``, not ``"Y"``.
  :meth:`MeshFacts.__post_init__` refuses facts that carry a value the mask says
  is unavailable, so an adapter cannot quietly invent one (`asset-validation`:
  "An unavailable fact is not defaulted").
* **`available` is a set of :class:`FactKind`, not a bag of booleans.** A rule
  declares the kinds it consumes and the dispatcher compares the two sets, which
  is what makes NOT EVALUATED structural instead of an ``if`` inside every rule
  (D13).

The per-format table that populates `available` lives in
:mod:`cybercanon.domain.format_matrix`, so the value object stays a value object.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class MeshFormat(Enum):
    """An export format the validator knows how to reason about."""

    GLB = "GLB"
    GLTF = "GLTF"
    FBX = "FBX"
    OBJ = "OBJ"

    @classmethod
    def from_name(cls, text: str) -> MeshFormat | None:
        """The format this name or extension denotes, or ``None`` for an unknown one.

        ``None`` rather than an exception: an unrecognised format is an
        *operation failure* the caller reports naming the format, never a
        validation that quietly assumes facts it does not have.
        """
        return _FORMAT_BY_NAME.get(text.strip().lstrip(".").upper())

    def __str__(self) -> str:
        return self.value


class FactKind(Enum):
    """One fact an export may or may not be able to yield.

    The value is the phrase a report uses — "OBJ carries no unit scale" — so a
    renderer never has to keep its own table of English names.
    """

    SOURCE_FORMAT = "source format"
    TRIANGLES = "triangle count"
    OBJECTS = "object names"
    TRANSFORMS_APPLIED = "applied transforms"
    UNIT_SCALE = "unit scale"
    UP_AXIS = "up axis"
    UV_SETS = "UV sets"
    MATERIALS = "material names"
    EMPTIES = "attachment points"
    CLIPS = "animation clips"
    CLIP_FRAME_RATE = "clip frame rate"
    CLIP_DURATION = "clip duration"
    CLIP_ROOT_MOTION = "clip root motion"
    CLIP_LOOP = "clip loop closure"
    FRAME_RATE = "frame rate"
    SKINNING = "skinning"
    BONE_COUNT = "bone count"

    @property
    def label(self) -> str:
        """The phrase a message uses for this fact."""
        return self.value

    @property
    def order(self) -> int:
        """Declaration order — the only stable way to sort an unordered enum."""
        return list(type(self)).index(self)

    def __str__(self) -> str:
        return self.value


ALWAYS_AVAILABLE = frozenset({FactKind.SOURCE_FORMAT})
"""The one fact every export carries: the format it is written in.

It is a `FactKind` so that `format.unsuitable_for_asset` — the rule that fires
precisely *because* a format carries nothing — declares what it consumes like
every other rule, and so the dispatcher needs no special case.
"""


@dataclass(frozen=True)
class ClipFacts:
    """One animation clip as the export describes it.

    Every field but the name is optional because formats differ in what they
    record, and a value invented here would be a lie the domain cannot detect.
    Which of these a format can be trusted for is the matrix's business, not
    this object's.
    """

    name: str
    frames: int | None = None
    duration_s: float | None = None
    frame_rate: float | None = None
    has_root_motion: bool | None = None
    loop_closed: bool | None = None

    @property
    def seconds(self) -> float | None:
        """The clip's length in seconds, however the export expressed it."""
        if self.duration_s is not None:
            return self.duration_s
        if self.frames is None or not self.frame_rate:
            return None
        return self.frames / self.frame_rate


_MESH_FIELD_BY_FACT: dict[FactKind, str] = {
    FactKind.TRIANGLES: "triangles",
    FactKind.OBJECTS: "objects",
    FactKind.TRANSFORMS_APPLIED: "transforms_applied",
    FactKind.UNIT_SCALE: "unit_scale",
    FactKind.UP_AXIS: "up_axis",
    FactKind.UV_SETS: "uv_sets",
    FactKind.MATERIALS: "materials",
    FactKind.EMPTIES: "empties",
    FactKind.CLIPS: "clips",
    FactKind.FRAME_RATE: "frame_rate",
    FactKind.SKINNING: "is_skinned",
    FactKind.BONE_COUNT: "bone_count",
}
MESH_FIELD_BY_FACT = MappingProxyType(_MESH_FIELD_BY_FACT)
"""Which `MeshFacts` field each whole-export fact lives in."""

_CLIP_FIELDS_BY_FACT: dict[FactKind, tuple[str, ...]] = {
    FactKind.CLIP_FRAME_RATE: ("frame_rate",),
    FactKind.CLIP_DURATION: ("duration_s", "frames"),
    FactKind.CLIP_ROOT_MOTION: ("has_root_motion",),
    FactKind.CLIP_LOOP: ("loop_closed",),
}
CLIP_FIELDS_BY_FACT = MappingProxyType(_CLIP_FIELDS_BY_FACT)
"""Which `ClipFacts` fields each per-clip fact lives in."""


class FabricatedFact(ValueError):
    """A value was supplied for a fact the export's mask says is unavailable.

    Raised rather than dropped: silently discarding it would hide the adapter
    bug, and silently keeping it is the "validator that lies about its coverage"
    D13 exists to prevent.
    """


@dataclass(frozen=True)
class MeshFacts:
    """Everything the rules are allowed to know about one export.

    Build these through :func:`cybercanon.domain.format_matrix.facts_for`, which
    fills `available` from the per-format matrix. The bare constructor is for the
    one case the matrix cannot serve: a test proving the not-evaluated path with
    a deliberately narrow mask.
    """

    source_format: MeshFormat
    available: frozenset[FactKind] = frozenset()
    triangles: int | None = None
    objects: tuple[str, ...] = ()
    transforms_applied: bool | None = None
    unit_scale: float | None = None
    up_axis: str | None = None
    uv_sets: int | None = None
    materials: tuple[str, ...] = ()
    empties: tuple[str, ...] = ()
    clips: tuple[ClipFacts, ...] = ()
    frame_rate: float | None = None
    is_skinned: bool | None = None
    bone_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "available", frozenset(self.available) | ALWAYS_AVAILABLE)
        fabricated = self._fabricated()
        if fabricated:
            listed = ", ".join(sorted(fabricated))
            raise FabricatedFact(
                f"{self.source_format} facts carry a value for unavailable fact(s): {listed}. "
                "An unavailable fact has no substitute value."
            )

    def has(self, kind: FactKind) -> bool:
        """Whether this export can answer for that fact at all."""
        return kind in self.available

    def missing(self, kinds: frozenset[FactKind]) -> FactKind | None:
        """The first fact of `kinds` this export cannot yield, in declaration order."""
        absent = kinds - self.available
        return min(absent, key=lambda kind: kind.order) if absent else None

    def value(self, kind: FactKind) -> object:
        """The observed value of a whole-export fact, or ``None`` when unavailable."""
        field = MESH_FIELD_BY_FACT.get(kind)
        return getattr(self, field) if field and self.has(kind) else None

    @property
    def clip_names(self) -> tuple[str, ...]:
        """The names of the clips this export carries, in export order."""
        return tuple(clip.name for clip in self.clips)

    def clip(self, name: str) -> ClipFacts | None:
        """The clip of that exact name, or ``None`` when the export has none."""
        return next((clip for clip in self.clips if clip.name == name), None)

    def _fabricated(self) -> tuple[str, ...]:
        return tuple(
            kind.name for kind in FactKind if not self.has(kind) and self._carries_a_value(kind)
        )

    def _carries_a_value(self, kind: FactKind) -> bool:
        field = MESH_FIELD_BY_FACT.get(kind)
        if field is not None:
            observed = getattr(self, field)
            return observed is not None and observed != ()
        return any(
            getattr(clip, clip_field) is not None
            for clip in self.clips
            for clip_field in CLIP_FIELDS_BY_FACT.get(kind, ())
        )


_FORMAT_BY_NAME = {member.value: member for member in MeshFormat}

__all__ = [
    "ALWAYS_AVAILABLE",
    "CLIP_FIELDS_BY_FACT",
    "MESH_FIELD_BY_FACT",
    "ClipFacts",
    "FabricatedFact",
    "FactKind",
    "MeshFacts",
    "MeshFormat",
]
