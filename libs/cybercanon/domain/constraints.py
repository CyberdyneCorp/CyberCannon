"""The `constraints` block — authored by engineering.

Every field is a technical fact an export is measured against. An asset's own
constraints take precedence over the project defaults, field by field; that
merge is one pure function (D3, task 3.2) and does not live here. What lives
here is the shape of what gets merged, with every field optional, because an
asset that declares nothing inherits everything.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Texture:
    """Texture budget: resolution, how many sets, and which channels are packed."""

    size: int | None = None
    sets: int | None = None
    channels: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rig:
    """The skeleton contract: which skeleton, how many bones, skinned or not.

    `skinned` is a declaration, not an observation: ``True`` means the export is
    expected to carry skinning, which is what makes `rig.not_skinned` checkable
    (task 3.11).
    """

    skeleton: str | None = None
    max_bones: int | None = None
    skinned: bool | None = None


@dataclass(frozen=True)
class AnimationDefaults:
    """Animation defaults: the frame rate clips are expected at, and how they are named.

    `clip_naming` is a template with `{asset}` and `{state}` placeholders (D8),
    never a regular expression — artists and designers author these files.
    """

    frame_rate: float | None = None
    clip_naming: str | None = None


@dataclass(frozen=True)
class Constraints:
    """What the export must respect technically."""

    tri_budget: int | None = None
    lods: tuple[int, ...] = ()
    texture: Texture | None = None
    rig: Rig | None = None
    animation: AnimationDefaults | None = None
    collider: str | None = None
    pivot: str | None = None
    up_axis: str | None = None
    unit_scale: float | None = None
    naming: str | None = None

    @property
    def clip_naming(self) -> str | None:
        """The clip naming convention this block declares, if any."""
        return self.animation.clip_naming if self.animation else None


__all__ = ["AnimationDefaults", "Constraints", "Rig", "Texture"]
