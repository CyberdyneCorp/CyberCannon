"""The animation gates — the socket loop, applied to `design.states` (D12).

`animation.clip_missing` is `socket.missing` with a different fact list: one
derived requirement compared against one export fact. Both read what **design**
declared, resolved into :class:`~cybercanon.domain.effective_spec.RequiredClip`
by the effective-spec merge, so a declared state becomes an export gate without
engineering restating it and the two lists cannot drift.

The four expectation rules judge a clip that *is* present. They are separate
rules rather than one `animation.clip_mismatch` because severity is per rule and
a team tunes them differently: a missing clip blocks, a frame rate 29.97 against
a declared 30 should not. Frame-rate comparison is exact and the rule is a
warning until a real engine import says otherwise.

A clip the specification does not require is never a violation. Artists export
test clips.
"""

from __future__ import annotations

from collections.abc import Iterable

from cybercanon.domain.effective_spec import EffectiveSpec, RequiredClip
from cybercanon.domain.mesh_facts import ClipFacts, FactKind, MeshFacts
from cybercanon.domain.violations import Severity, Violation

CLIP_MISSING = "animation.clip_missing"
CLIP_MISSING_SEVERITY = Severity.ERROR
CLIP_MISSING_CONSUMES = frozenset({FactKind.CLIPS})

FRAME_RATE = "animation.frame_rate_mismatch"
FRAME_RATE_SEVERITY = Severity.WARNING
FRAME_RATE_CONSUMES = frozenset({FactKind.CLIPS, FactKind.CLIP_FRAME_RATE})

DURATION = "animation.duration_too_short"
DURATION_SEVERITY = Severity.WARNING
DURATION_CONSUMES = frozenset({FactKind.CLIPS, FactKind.CLIP_DURATION})

ROOT_MOTION = "animation.root_motion_missing"
ROOT_MOTION_SEVERITY = Severity.WARNING
ROOT_MOTION_CONSUMES = frozenset({FactKind.CLIPS, FactKind.CLIP_ROOT_MOTION})

LOOP = "animation.loop_not_closed"
LOOP_SEVERITY = Severity.WARNING
LOOP_CONSUMES = frozenset({FactKind.CLIPS, FactKind.CLIP_LOOP})


def check_clips_present(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """One violation per required clip the export does not contain."""
    present = set(facts.clip_names)
    return tuple(
        _missing(spec, required)
        for required in spec.required_clips
        if required.clip_name not in present
    )


def check_clip_frame_rate(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """A present clip's frame rate against the one its state declares."""
    return tuple(
        _violation(
            FRAME_RATE,
            FRAME_RATE_SEVERITY,
            spec,
            required,
            observed=str(clip.frame_rate),
            expected=str(required.frame_rate),
            detail=(f"is exported at {clip.frame_rate} fps, expected {required.frame_rate} fps"),
        )
        for required, clip in _present(spec, facts)
        if required.frame_rate is not None
        and clip.frame_rate is not None
        and clip.frame_rate != required.frame_rate
    )


def check_clip_duration(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """A present clip's length against the minimum duration its state declares."""
    return tuple(
        _violation(
            DURATION,
            DURATION_SEVERITY,
            spec,
            required,
            observed=str(clip.seconds),
            expected=str(required.min_duration_s),
            detail=(
                f"is {clip.seconds} s long, below the declared minimum of "
                f"{required.min_duration_s} s"
            ),
        )
        for required, clip in _present(spec, facts)
        if required.min_duration_s is not None
        and clip.seconds is not None
        and clip.seconds < required.min_duration_s
    )


def check_clip_root_motion(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """A present clip that must carry root motion and does not."""
    return tuple(
        _violation(
            ROOT_MOTION,
            ROOT_MOTION_SEVERITY,
            spec,
            required,
            observed="no root motion",
            expected="root motion",
            detail="animates no translation of the root, and its state declares root_motion",
        )
        for required, clip in _present(spec, facts)
        if required.root_motion is True and clip.has_root_motion is False
    )


def check_clip_loop(spec: EffectiveSpec, facts: MeshFacts) -> Iterable[Violation]:
    """A present clip that must loop and whose last pose does not return to its first."""
    return tuple(
        _violation(
            LOOP,
            LOOP_SEVERITY,
            spec,
            required,
            observed="loop not closed",
            expected="a closed loop",
            detail="does not return to its first pose, and its state declares loop",
        )
        for required, clip in _present(spec, facts)
        if required.loop is True and clip.loop_closed is False
    )


def _present(spec: EffectiveSpec, facts: MeshFacts) -> tuple[tuple[RequiredClip, ClipFacts], ...]:
    """Required clips the export actually contains, paired with their facts."""
    pairs = ((required, facts.clip(required.clip_name)) for required in spec.required_clips)
    return tuple((required, clip) for required, clip in pairs if clip is not None)


def _missing(spec: EffectiveSpec, required: RequiredClip) -> Violation:
    return Violation(
        rule_id=CLIP_MISSING,
        severity=CLIP_MISSING_SEVERITY,
        subject=required.clip_name,
        message=(
            f"{spec.asset_id}: state {required.state!r} requires the animation clip "
            f"{required.clip_name!r} and the export contains no clip of that name"
        ),
        observed="absent",
        expected=f"a clip named {required.clip_name}",
    )


def _violation(
    rule_id: str,
    severity: Severity,
    spec: EffectiveSpec,
    required: RequiredClip,
    observed: str,
    expected: str,
    detail: str,
) -> Violation:
    return Violation(
        rule_id=rule_id,
        severity=severity,
        subject=required.clip_name,
        message=(
            f"{spec.asset_id}: clip {required.clip_name!r} (state {required.state!r}) {detail}"
        ),
        observed=observed,
        expected=expected,
    )


__all__ = [
    "CLIP_MISSING",
    "CLIP_MISSING_CONSUMES",
    "CLIP_MISSING_SEVERITY",
    "DURATION",
    "DURATION_CONSUMES",
    "DURATION_SEVERITY",
    "FRAME_RATE",
    "FRAME_RATE_CONSUMES",
    "FRAME_RATE_SEVERITY",
    "LOOP",
    "LOOP_CONSUMES",
    "LOOP_SEVERITY",
    "ROOT_MOTION",
    "ROOT_MOTION_CONSUMES",
    "ROOT_MOTION_SEVERITY",
    "check_clip_duration",
    "check_clip_frame_rate",
    "check_clip_loop",
    "check_clip_root_motion",
    "check_clips_present",
]
