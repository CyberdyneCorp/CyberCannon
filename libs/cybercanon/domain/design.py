"""The `design` block — authored by game design.

Every field here constrains art, constrains code, or is checkable, and two of
them close the loop the product exists for:

* a declared :class:`Socket` becomes `socket.missing` against the export's
  attachment points;
* a :class:`State` resolves to a required animation clip (D12), which becomes
  `animation.clip_missing` against the export's clips.

Resolution of states into required clips happens once, in the effective-spec
merge (task 3.3). What lives here is the state's own contract and the single
question the structural checks ask of it: does it constrain anything at all?
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Socket:
    """An attachment point art must place and code may rely on."""

    name: str
    purpose: str


@dataclass(frozen=True)
class State:
    """One entry of `design.states`, and the animation contract it declares.

    A state either resolves to a required clip — through its own `clip` or
    through the project's clip naming convention — or declares itself
    unanimated with ``animated=False``. A state that does neither constrains
    nothing and is reported by `spec.state_constrains_nothing` (D12).
    """

    name: str
    clip: str | None = None
    loop: bool | None = None
    frame_rate: float | None = None
    root_motion: bool | None = None
    min_duration_s: float | None = None
    min_duration_frames: int | None = None
    animated: bool = True

    @property
    def is_unanimated(self) -> bool:
        """The explicit declaration that this state has no animation."""
        return not self.animated

    def resolves_to_a_clip(self, clip_naming: str | None) -> bool:
        """Whether a required clip name can be derived for this state.

        The name itself is derived in the effective-spec merge; all this answers
        is whether anything is there to derive it from.
        """
        if self.is_unanimated:
            return False
        return self.clip is not None or bool(clip_naming)

    def constrains_nothing(self, clip_naming: str | None) -> bool:
        """The condition `spec.state_constrains_nothing` reports."""
        return not self.is_unanimated and not self.resolves_to_a_clip(clip_naming)

    def minimum_duration_seconds(self, default_frame_rate: float | None = None) -> float | None:
        """The minimum duration in seconds, whichever way it was authored.

        Seconds win when both are declared. Frames need a frame rate: the
        state's own, otherwise the project default; with neither, the minimum is
        not expressible and this answers ``None`` rather than guessing.
        """
        if self.min_duration_s is not None:
            return self.min_duration_s
        rate = self.frame_rate if self.frame_rate is not None else default_frame_rate
        if self.min_duration_frames is None or not rate:
            return None
        return self.min_duration_frames / rate


@dataclass(frozen=True)
class Design:
    """What the asset does, in terms art and code can both be held to."""

    role: str | None = None
    read_distance_m: float | None = None
    silhouette_priority: str | None = None
    states: tuple[State, ...] = ()
    scale_ref: str | None = None
    team_color_regions: tuple[str, ...] = ()
    sockets: tuple[Socket, ...] = ()

    @property
    def socket_names(self) -> tuple[str, ...]:
        """The attachment point names an export must carry."""
        return tuple(socket.name for socket in self.sockets)

    def state(self, name: str) -> State | None:
        """The state with this name, or ``None``."""
        return next((state for state in self.states if state.name == name), None)


__all__ = ["Design", "Socket", "State"]
