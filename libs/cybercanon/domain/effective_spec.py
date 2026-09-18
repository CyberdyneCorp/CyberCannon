"""The merged contract every rule is measured against (D3, D12).

Project defaults merge with the asset's own `constraints`, field by field, and
the asset wins wherever it declares something. The merge happens **once**,
before any rule runs, so no rule ever contains an
``asset.tri_budget or project.tri_budget`` smear and the compiled `art-spec.md`
can state effective values without re-deriving them — the briefing a human reads
and the contract the validator enforces are the same object.

Two derivations happen here rather than in a rule, and for the same reason:

* **`required_sockets`** comes from `design.sockets` (the golden loop: design
  declares, art places, the validator gates);
* **`required_clips`** comes from `design.states` (D12): the state's explicit
  `clip` wins, otherwise the clip naming template is expanded with the asset id
  and the state name. A state that declares itself unanimated contributes
  nothing, and a state that resolves to neither is a *specification-file*
  violation reported by `spec.state_constrains_nothing`, not a mesh violation.

The consequence is that "what does design require" is computed in one place, so
the compiler, the validator and the lenses cannot disagree about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cybercanon.domain.asset import Asset
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig, Texture
from cybercanon.domain.design import Design, State
from cybercanon.domain.naming import expand

ASSET_PLACEHOLDER = "asset"
STATE_PLACEHOLDER = "state"


@dataclass(frozen=True)
class RequiredClip:
    """One animation clip the specification demands, and what it demands of it.

    `state` is carried so a violation can name the state that required the clip,
    which is the difference between "a clip is missing" and "the `fire` state has
    no animation".
    """

    state: str
    clip_name: str
    frame_rate: float | None = None
    min_duration_s: float | None = None
    root_motion: bool | None = None
    loop: bool | None = None


@dataclass(frozen=True)
class EffectiveSpec:
    """Project defaults and asset constraints, already merged, plus what design requires."""

    asset_id: str
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
    rig_declared: bool = False
    required_sockets: tuple[str, ...] = ()
    required_clips: tuple[RequiredClip, ...] = ()

    @property
    def max_bones(self) -> int | None:
        """The effective bone budget, wherever it was declared."""
        return self.rig.max_bones if self.rig else None

    @property
    def skeleton(self) -> str | None:
        """The declared skeleton, which a `rig.not_skinned` violation names."""
        return self.rig.skeleton if self.rig else None

    @property
    def expects_skinning(self) -> bool:
        """Whether this asset's export is expected to carry skinning.

        A declared rig implies it; ``rig.skinned: false`` is the explicit opt-out
        for an asset that has a skeleton it does not skin to.
        """
        if not self.rig_declared:
            return False
        return self.rig is None or self.rig.skinned is not False

    @property
    def clip_naming(self) -> str | None:
        """The effective clip naming convention."""
        return self.animation.clip_naming if self.animation else None

    @property
    def frame_rate(self) -> float | None:
        """The frame rate clips are expected at, unless a state overrides it."""
        return self.animation.frame_rate if self.animation else None

    def required_clip(self, name: str) -> RequiredClip | None:
        """The requirement for that clip name, or ``None`` when nothing requires it."""
        return next((clip for clip in self.required_clips if clip.clip_name == name), None)


def merge(asset: Asset, project_defaults: Constraints | None = None) -> EffectiveSpec:
    """The one merge (D3): project defaults ← asset constraints, asset wins per field."""
    own = asset.constraints
    animation = _merge_animation(own, project_defaults)
    return EffectiveSpec(
        asset_id=asset.id.value,
        tri_budget=_first(own, project_defaults, "tri_budget"),
        lods=_first_sequence(own, project_defaults, "lods"),
        texture=_merge_texture(own, project_defaults),
        rig=_merge_rig(own, project_defaults),
        animation=animation,
        collider=_first(own, project_defaults, "collider"),
        pivot=_first(own, project_defaults, "pivot"),
        up_axis=_first(own, project_defaults, "up_axis"),
        unit_scale=_first(own, project_defaults, "unit_scale"),
        naming=_first(own, project_defaults, "naming"),
        rig_declared=own is not None and own.rig is not None,
        required_sockets=asset.design.socket_names if asset.design else (),
        required_clips=resolve_required_clips(
            asset.id.value,
            asset.design,
            clip_naming=animation.clip_naming if animation else None,
            default_frame_rate=animation.frame_rate if animation else None,
        ),
    )


def resolve_required_clips(
    asset_id: str,
    design: Design | None,
    clip_naming: str | None = None,
    default_frame_rate: float | None = None,
) -> tuple[RequiredClip, ...]:
    """Design states resolved into the clips an export must contain (D12)."""
    states = design.states if design else ()
    resolved = (
        _required_clip(asset_id, state, clip_naming, default_frame_rate) for state in states
    )
    return tuple(clip for clip in resolved if clip is not None)


def clip_name_for(asset_id: str, state: State, clip_naming: str | None) -> str | None:
    """The clip name a state resolves to: its own `clip`, else the expanded template."""
    if state.is_unanimated:
        return None
    if state.clip is not None:
        return state.clip
    if not clip_naming:
        return None
    return expand(clip_naming, {ASSET_PLACEHOLDER: asset_id, STATE_PLACEHOLDER: state.name})


def _required_clip(
    asset_id: str, state: State, clip_naming: str | None, default_frame_rate: float | None
) -> RequiredClip | None:
    name = clip_name_for(asset_id, state, clip_naming)
    if name is None:
        return None
    frame_rate = state.frame_rate if state.frame_rate is not None else default_frame_rate
    return RequiredClip(
        state=state.name,
        clip_name=name,
        frame_rate=frame_rate,
        min_duration_s=state.minimum_duration_seconds(default_frame_rate),
        root_motion=state.root_motion,
        loop=state.loop,
    )


def _first(own: Constraints | None, fallback: Constraints | None, field: str) -> Any:
    """The asset's value for a field, else the project's, else ``None``."""
    mine = getattr(own, field, None) if own else None
    return mine if mine is not None else (getattr(fallback, field, None) if fallback else None)


def _first_sequence(
    own: Constraints | None, fallback: Constraints | None, field: str
) -> tuple[int, ...]:
    """Sequences merge whole: a declared list replaces the default, it does not extend it."""
    mine = getattr(own, field, ()) if own else ()
    if mine:
        return tuple(mine)
    return tuple(getattr(fallback, field, ()) if fallback else ())


def _merge_rig(own: Constraints | None, fallback: Constraints | None) -> Rig | None:
    mine = own.rig if own else None
    theirs = fallback.rig if fallback else None
    if mine is None and theirs is None:
        return None
    return Rig(
        skeleton=_pick(mine, theirs, "skeleton"),
        max_bones=_pick(mine, theirs, "max_bones"),
        skinned=_pick(mine, theirs, "skinned"),
    )


def _merge_texture(own: Constraints | None, fallback: Constraints | None) -> Texture | None:
    mine = own.texture if own else None
    theirs = fallback.texture if fallback else None
    if mine is None and theirs is None:
        return None
    channels = (mine.channels if mine else ()) or (theirs.channels if theirs else ())
    return Texture(
        size=_pick(mine, theirs, "size"),
        sets=_pick(mine, theirs, "sets"),
        channels=tuple(channels),
    )


def _merge_animation(
    own: Constraints | None, fallback: Constraints | None
) -> AnimationDefaults | None:
    mine = own.animation if own else None
    theirs = fallback.animation if fallback else None
    if mine is None and theirs is None:
        return None
    return AnimationDefaults(
        frame_rate=_pick(mine, theirs, "frame_rate"),
        clip_naming=_pick(mine, theirs, "clip_naming"),
    )


def _pick(mine: object, theirs: object, field: str) -> Any:
    own = getattr(mine, field, None)
    return own if own is not None else getattr(theirs, field, None)


__all__ = [
    "EffectiveSpec",
    "RequiredClip",
    "clip_name_for",
    "merge",
    "resolve_required_clips",
]
