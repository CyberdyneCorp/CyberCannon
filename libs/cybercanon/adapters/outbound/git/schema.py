"""The `asset.yaml` schema, as pydantic models — and the one place pydantic lives.

D4 splits two jobs between two libraries: `ruamel.yaml` owns the *file* (comments,
key order, quoting), pydantic owns the *shape* (fields, types, enums). Both are
adapter concerns and neither is ever imported by `libs/cybercanon/domain`, which
import-linter enforces (D10) — the domain speaks only in its own value objects,
and this module is the translation.

Three rules of the format are implemented here rather than described:

* **`schema_version` is read first** (D6). A file whose *major* version is newer
  than this binary understands is refused with a message naming the tool version
  the author needs. An older or equal one is read.
* **An unknown field is a warning, never a parse failure** (D5). Version skew
  must not block a commit: a newer CyberCanon writes a field this binary has
  never heard of, and this binary still validates the mesh. The warning names the
  field and its location so a typo stays visible.
* **A field of the wrong type is a reported violation, not an exception.** One
  bad value would otherwise deny the artist every other finding in the same run,
  so the offending field is dropped, reported by its dotted location, and the
  rest of the file loads.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from cybercanon.application.ports.spec_store import PreviewDefaults
from cybercanon.domain.actors import ActorBinding, ActorMapping
from cybercanon.domain.annotations import (
    Anchor,
    Anchor2D,
    Anchor3D,
    Annotation,
    AnnotationKind,
    AnnotationState,
    Camera,
    Point,
)
from cybercanon.domain.asset import Asset, AssetId, Links
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import AnimationDefaults, Constraints, Rig, Texture
from cybercanon.domain.design import Design, Socket, State
from cybercanon.domain.spec_checks import check_declared_status
from cybercanon.domain.status import Status
from cybercanon.domain.violations import Severity, SpecViolation

SCHEMA_VERSION = 1
"""The major version of `asset.yaml` this binary writes and fully understands."""

TOOL_VERSION = "0.1"
"""What a refusal tells the author to upgrade to; bumped with the major version."""

RULE_UNKNOWN_FIELD = "spec.unknown_field"
RULE_INVALID_VALUE = "spec.invalid_value"
RULE_UNKNOWN_ENUM = "spec.unknown_value"

_MAX_REPAIRS = 32
"""A ceiling on the drop-and-retry loop, so a pathological file still terminates."""


class SchemaTooNew(ValueError):
    """The file's major version is newer than this binary understands (D6)."""

    def __init__(self, declared: object) -> None:
        super().__init__(
            f"schema_version {declared} is newer than this build of canon understands "
            f"(schema version {SCHEMA_VERSION}); upgrade canon to {TOOL_VERSION}+ to read it"
        )
        self.declared = declared


class _Block(BaseModel):
    """Every block tolerates fields it has never heard of, and remembers them (D5)."""

    model_config = ConfigDict(extra="allow")


class TextureFile(_Block):
    size: int | None = None
    sets: int | None = None
    channels: tuple[str, ...] = ()


class RigFile(_Block):
    skeleton: str | None = None
    max_bones: int | None = None
    skinned: bool | None = None


class AnimationFile(_Block):
    frame_rate: float | None = None
    clip_naming: str | None = None


class ConstraintsFile(_Block):
    tri_budget: int | None = None
    lods: tuple[int, ...] = ()
    texture: TextureFile | None = None
    rig: RigFile | None = None
    animation: AnimationFile | None = None
    collider: str | None = None
    pivot: str | None = None
    up_axis: str | None = None
    unit_scale: float | None = None
    naming: str | None = None


class SocketFile(_Block):
    name: str
    purpose: str = ""


class StateFile(_Block):
    name: str
    clip: str | None = None
    loop: bool | None = None
    frame_rate: float | None = None
    root_motion: bool | None = None
    min_duration_s: float | None = None
    min_duration_frames: int | None = None
    animated: bool = True


class DesignFile(_Block):
    role: str | None = None
    read_distance_m: float | None = None
    silhouette_priority: str | None = None
    states: tuple[StateFile, ...] = ()
    scale_ref: str | None = None
    team_color_regions: tuple[str, ...] = ()
    sockets: tuple[SocketFile, ...] = ()


class ConceptFile(_Block):
    views: tuple[str, ...] = ()
    silhouette_rules: tuple[str, ...] = ()


class LinksFile(_Block):
    source: str | None = None
    engine: str | None = None
    discussion: str | None = None
    design_doc: str | None = None


class CameraFile(_Block):
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    fov_deg: float


class AnchorFile(_Block):
    """Both anchor forms in one shape — `view` names a 2D anchor, `part` a 3D one.

    There is deliberately no field for a triangle index or a barycentric
    coordinate: the format must not be able to express an anchor that dies on
    the next re-export (`asset-spec`).
    """

    view: str | None = None
    u: float | None = None
    v: float | None = None
    part: str | None = None
    bone: str | None = None
    point: tuple[float, float, float] | None = None
    normal: tuple[float, float, float] | None = None
    camera: CameraFile | None = None


class AnnotationFile(_Block):
    id: str
    author: str = ""
    kind: str = "technical"
    text: str = ""
    state: str = "open"
    target: AnchorFile | None = None


class AssetFile(_Block):
    """One `asset.yaml`, before it becomes an :class:`Asset`."""

    schema_version: int | float | str | None = None
    id: str
    name: str = ""
    status: str = Status.CONCEPT.value
    aliases: tuple[str, ...] = ()
    owner_art: str | None = None
    owner_design: str | None = None
    owner_code: str | None = None
    concept: ConceptFile | None = None
    design: DesignFile | None = None
    constraints: ConstraintsFile | None = None
    links: LinksFile | None = None
    annotations: tuple[AnnotationFile, ...] = ()


class PreviewFile(_Block):
    """`preview:` — what decimation aims for, deliberately dumb numbers (D7)."""

    ratio: float | None = None
    ceiling: int | None = None


class ProjectFile(_Block):
    """`.canon/project.yaml` — the defaults half of the merge (D3), and the knobs.

    `defaults` is an ordinary `constraints` block, so the naming pattern, the
    clip naming convention, the default frame rate, the rig bone budget, the up
    axis and the unit scale are declared in exactly the vocabulary an
    `asset.yaml` uses and merge without a second code path. The three fields
    that are *not* constraints live beside it: where the engine keeps its
    content, what severity each rule carries in this project, and what preview
    emission aims for.
    """

    schema_version: int | float | str | None = None
    name: str | None = None
    defaults: ConstraintsFile | None = None
    golden_rules: tuple[str, ...] = ()
    engine_content_root: str | None = None
    severity: dict[str, str] = {}
    preview: PreviewFile | None = None


class ActorEntryFile(_Block):
    """One entry of `.canon/actors.yaml` — a person's two identities, bound.

    Every field but the subject is optional *on purpose*, and the tolerance is
    the requirement rather than politeness: an entry with no email and an entry
    whose `default_role` names no known role are both defects the mapping's
    structural checks report by name
    (:mod:`cybercanon.domain.actor_checks`). A model that refused them would
    turn each into an unparseable file, and a reader would lose every other
    finding in the same run — the failure D12 keeps the mapping out of.
    """

    subject: str
    display_name: str = ""
    emails: tuple[str, ...] = ()
    chat_handle: str | None = None
    default_role: str | None = None


class ActorsFile(_Block):
    """`.canon/actors.yaml` — the project's identity-subject to git-author mapping.

    Repository content like `asset.yaml`, so it is versioned, diffable and
    reviewed in a pull request (D12). It is read at the same revision as the
    specifications it explains, which is what makes an entry added today
    explain a commit authored last year.
    """

    schema_version: int | float | str | None = None
    actors: tuple[ActorEntryFile, ...] = ()


# --------------------------------------------------------------------------
# schema_version (D6)
# --------------------------------------------------------------------------


def check_schema_version(declared: object) -> None:
    """Refuse a *newer major* version, and only that.

    An older file is readable by construction — fields are optional and unknown
    ones are warnings — so the only unreadable file is one written by a binary
    that knows more about the format than this one does.
    """
    if declared is None:
        return
    major = _major(declared)
    if major is not None and major > SCHEMA_VERSION:
        raise SchemaTooNew(declared)


def _major(declared: object) -> int | None:
    """The major component of `1`, `1.3` or `"2.0"`; ``None`` when it is not a version."""
    text = str(declared).strip()
    head = text.split(".", 1)[0]
    return int(head) if head.isdigit() else None


# --------------------------------------------------------------------------
# Parsing (D5 — tolerant, and never silent)
# --------------------------------------------------------------------------


def parse_asset_file(data: Mapping[str, Any]) -> tuple[AssetFile, tuple[SpecViolation, ...]]:
    """Read one specification file, reporting rather than raising wherever it can."""
    check_schema_version(data.get("schema_version"))
    return _parse(AssetFile, data)


def parse_project_file(data: Mapping[str, Any]) -> tuple[ProjectFile, tuple[SpecViolation, ...]]:
    """Read `.canon/project.yaml` under the same tolerance as a specification."""
    check_schema_version(data.get("schema_version"))
    return _parse(ProjectFile, data)


def parse_actors_file(data: Mapping[str, Any]) -> ActorsFile:
    """Read `.canon/actors.yaml`, or refuse the whole file.

    Deliberately *not* the tolerant drop-and-report loop the specification files
    get. A specification with one bad field still describes an asset, so
    dropping the field keeps the rest useful; a mapping whose shape is wrong
    describes nobody, and half a mapping would bind some commits to people and
    silently leave others unmapped — which looks exactly like a complete mapping
    with missing entries. So a shape failure raises here and the store turns it
    into the one violation D12 specifies, naming the file.
    """
    check_schema_version(data.get("schema_version"))
    return ActorsFile.model_validate(dict(data))


def to_actor_mapping(parsed: ActorsFile) -> ActorMapping:
    """The parsed file as the domain value object resolution is a function over."""
    return ActorMapping(
        bindings=tuple(
            ActorBinding(
                subject=entry.subject,
                display_name=entry.display_name or entry.subject,
                emails=tuple(entry.emails),
                chat_handle=entry.chat_handle,
                default_role=entry.default_role,
            )
            for entry in parsed.actors
        )
    )


def _parse(model: type[Any], data: Mapping[str, Any]) -> tuple[Any, tuple[SpecViolation, ...]]:
    """Validate, dropping each unusable value and reporting it, until it parses."""
    payload: Any = dict(data)
    invalid: list[SpecViolation] = []
    for _ in range(_MAX_REPAIRS):
        try:
            parsed = model.model_validate(payload)
        except ValidationError as error:
            payload, reported = _drop_invalid(payload, error)
            invalid.extend(reported)
            if not reported:
                raise
            continue
        return parsed, (*invalid, *unknown_fields(parsed))
    return model.model_validate(payload), tuple(invalid)


def _drop_invalid(payload: Any, error: ValidationError) -> tuple[Any, tuple[SpecViolation, ...]]:
    """Remove every value pydantic refused, keeping the rest of the file readable."""
    reported: list[SpecViolation] = []
    for detail in error.errors():
        location = tuple(detail["loc"])
        if not location or not _drop(payload, location):
            continue
        reported.append(_invalid_value(_dotted(location), detail.get("msg", "invalid value")))
    return payload, tuple(reported)


def _drop(payload: Any, location: Sequence[Any]) -> bool:
    """Delete the value at a pydantic error location. ``False`` when it is not there."""
    container = payload
    for step in location[:-1]:
        container = _child(container, step)
        if container is None:
            return False
    last = location[-1]
    if isinstance(container, dict) and last in container:
        del container[last]
        return True
    if isinstance(container, list) and isinstance(last, int) and last < len(container):
        del container[last]
        return True
    return False


def _child(container: Any, step: Any) -> Any:
    if isinstance(container, dict):
        return container.get(step)
    if isinstance(container, list) and isinstance(step, int) and step < len(container):
        return container[step]
    return None


def _invalid_value(subject: str, message: str) -> SpecViolation:
    return SpecViolation(
        rule_id=RULE_INVALID_VALUE,
        severity=Severity.ERROR,
        subject=subject,
        message=f"{subject} could not be read: {message}",
        observed=message,
    )


def _dotted(location: Sequence[Any]) -> str:
    """`('constraints', 'lods', 0)` -> `constraints.lods[0]`."""
    rendered = ""
    for step in location:
        if isinstance(step, int):
            rendered += f"[{step}]"
        else:
            rendered += f".{step}" if rendered else str(step)
    return rendered


# --------------------------------------------------------------------------
# Unknown fields (D5)
# --------------------------------------------------------------------------


def unknown_fields(model: BaseModel) -> tuple[SpecViolation, ...]:
    """Every field the schema does not define, named with its location in the file."""
    return tuple(_walk_unknown(model, ""))


def _walk_unknown(model: BaseModel, prefix: str) -> Iterator[SpecViolation]:
    for name in sorted(model.model_extra or {}):
        yield _unknown_field(_path(prefix, name))
    for name, value in model:
        if name in (model.model_extra or {}):
            continue
        yield from _walk_value(value, _path(prefix, name))


def _walk_value(value: Any, location: str) -> Iterator[SpecViolation]:
    if isinstance(value, BaseModel):
        yield from _walk_unknown(value, location)
    elif isinstance(value, tuple | list):
        for index, item in enumerate(value):
            yield from _walk_value(item, f"{location}[{index}]")


def _path(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def _unknown_field(location: str) -> SpecViolation:
    field = location.rsplit(".", 1)[-1]
    return SpecViolation(
        rule_id=RULE_UNKNOWN_FIELD,
        severity=Severity.WARNING,
        subject=location,
        message=(
            f"unrecognised field {field!r} at {location}; it is ignored. "
            "This is either a typo or a file written by a newer canon."
        ),
        observed=field,
    )


# --------------------------------------------------------------------------
# File -> domain
# --------------------------------------------------------------------------


def to_asset(parsed: AssetFile) -> tuple[Asset, tuple[SpecViolation, ...]]:
    """Turn a parsed file into the domain object, reporting what would not map."""
    status, violations = _status(parsed.status)
    annotations, annotation_violations = _annotations(parsed.annotations)
    asset = Asset(
        id=AssetId(parsed.id),
        name=parsed.name or parsed.id,
        status=status,
        aliases=tuple(parsed.aliases),
        owner_art=parsed.owner_art,
        owner_design=parsed.owner_design,
        owner_code=parsed.owner_code,
        concept=_concept(parsed.concept),
        design=_design(parsed.design),
        constraints=to_constraints(parsed.constraints),
        links=_links(parsed.links),
        annotations=annotations,
    )
    return asset, (*violations, *annotation_violations)


def _status(declared: str) -> tuple[Status, tuple[SpecViolation, ...]]:
    """An unknown status is reported and the asset still loads (`asset-spec`)."""
    known = Status.from_value(declared)
    if known is not None:
        return known, ()
    return Status.CONCEPT, check_declared_status(declared)


def _concept(parsed: ConceptFile | None) -> Concept | None:
    if parsed is None:
        return None
    return Concept(
        views=tuple(parsed.views),
        silhouette_rules=tuple(parsed.silhouette_rules),
    )


def _design(parsed: DesignFile | None) -> Design | None:
    if parsed is None:
        return None
    return Design(
        role=parsed.role,
        read_distance_m=parsed.read_distance_m,
        silhouette_priority=parsed.silhouette_priority,
        states=tuple(_state(state) for state in parsed.states),
        scale_ref=parsed.scale_ref,
        team_color_regions=tuple(parsed.team_color_regions),
        sockets=tuple(Socket(name=s.name, purpose=s.purpose) for s in parsed.sockets),
    )


def _state(parsed: StateFile) -> State:
    return State(
        name=parsed.name,
        clip=parsed.clip,
        loop=parsed.loop,
        frame_rate=parsed.frame_rate,
        root_motion=parsed.root_motion,
        min_duration_s=parsed.min_duration_s,
        min_duration_frames=parsed.min_duration_frames,
        animated=parsed.animated,
    )


def to_constraints(parsed: ConstraintsFile | None) -> Constraints | None:
    """The `constraints` block, shared by an asset file and the project defaults."""
    if parsed is None:
        return None
    return Constraints(
        tri_budget=parsed.tri_budget,
        lods=tuple(parsed.lods),
        texture=_texture(parsed.texture),
        rig=_rig(parsed.rig),
        animation=_animation(parsed.animation),
        collider=parsed.collider,
        pivot=parsed.pivot,
        up_axis=parsed.up_axis,
        unit_scale=parsed.unit_scale,
        naming=parsed.naming,
    )


def to_severities(
    declared: Mapping[str, str],
) -> tuple[dict[str, Severity], tuple[SpecViolation, ...]]:
    """`severity:` — the per-rule severity table, with unusable levels reported.

    A project lowering `naming.pattern_mismatch` to a warning is the design's
    answer to a strict-but-wrong rule; a level that is not a level is a typo,
    and a typo that silently kept a rule at `error` would be indistinguishable
    from the rule working.
    """
    known: dict[str, Severity] = {}
    violations: list[SpecViolation] = []
    for rule_id in sorted(declared):
        level, reported = _enum(Severity, str(declared[rule_id]), f"severity.{rule_id}")
        violations.extend(reported)
        if level is not None:
            known[rule_id] = level
    return known, tuple(violations)


def to_preview(parsed: PreviewFile | None) -> PreviewDefaults | None:
    """`preview:` — the decimation settings, as the neutral numbers the port holds."""
    if parsed is None:
        return None
    return PreviewDefaults(ratio=parsed.ratio, ceiling=parsed.ceiling)


def _texture(parsed: TextureFile | None) -> Texture | None:
    if parsed is None:
        return None
    return Texture(size=parsed.size, sets=parsed.sets, channels=tuple(parsed.channels))


def _rig(parsed: RigFile | None) -> Rig | None:
    if parsed is None:
        return None
    return Rig(skeleton=parsed.skeleton, max_bones=parsed.max_bones, skinned=parsed.skinned)


def _animation(parsed: AnimationFile | None) -> AnimationDefaults | None:
    if parsed is None:
        return None
    return AnimationDefaults(frame_rate=parsed.frame_rate, clip_naming=parsed.clip_naming)


def _links(parsed: LinksFile | None) -> Links | None:
    if parsed is None:
        return None
    return Links(
        source=parsed.source,
        engine=parsed.engine,
        discussion=parsed.discussion,
        design_doc=parsed.design_doc,
    )


def _annotations(
    parsed: Sequence[AnnotationFile],
) -> tuple[tuple[Annotation, ...], tuple[SpecViolation, ...]]:
    annotations: list[Annotation] = []
    violations: list[SpecViolation] = []
    for index, entry in enumerate(parsed):
        location = f"annotations[{index}]"
        anchor = _anchor(entry.target)
        if anchor is None:
            violations.append(_unanchored(location, entry.id))
            continue
        kind, kind_violations = _enum(AnnotationKind, entry.kind, f"{location}.kind")
        state, state_violations = _enum(AnnotationState, entry.state, f"{location}.state")
        violations.extend((*kind_violations, *state_violations))
        annotations.append(
            Annotation(
                id=entry.id,
                author=entry.author,
                kind=kind or AnnotationKind.TECHNICAL,
                text=entry.text,
                target=anchor,
                state=state or AnnotationState.OPEN,
            )
        )
    return tuple(annotations), tuple(violations)


def _anchor(parsed: AnchorFile | None) -> Anchor | None:
    """The durable key decides the form: a `view` is 2D, a `part` is 3D."""
    if parsed is None:
        return None
    if parsed.part:
        return Anchor3D(
            part=parsed.part,
            bone=parsed.bone,
            point=_point(parsed.point),
            normal=_point(parsed.normal),
            camera=_camera(parsed.camera),
        )
    if parsed.view and parsed.u is not None and parsed.v is not None:
        return Anchor2D(view=parsed.view, u=parsed.u, v=parsed.v)
    return None


def _point(values: tuple[float, float, float] | None) -> Point | None:
    return None if values is None else (float(values[0]), float(values[1]), float(values[2]))


def _camera(parsed: CameraFile | None) -> Camera | None:
    if parsed is None:
        return None
    position = _point(parsed.position)
    target = _point(parsed.target)
    if position is None or target is None:
        return None
    return Camera(position=position, target=target, fov_deg=parsed.fov_deg)


def _enum(enum: type[Any], declared: str, location: str) -> tuple[Any, tuple[SpecViolation, ...]]:
    """A value outside an enumerated set is reported, never fatal."""
    for member in enum:
        if member.value == declared:
            return member, ()
    allowed = ", ".join(member.value for member in enum)
    return None, (
        SpecViolation(
            rule_id=RULE_UNKNOWN_ENUM,
            severity=Severity.WARNING,
            subject=location,
            message=f"{location} is {declared!r}, which is not one of: {allowed}",
            observed=declared,
            expected=allowed,
        ),
    )


def _unanchored(location: str, annotation_id: str) -> SpecViolation:
    return SpecViolation(
        rule_id=RULE_INVALID_VALUE,
        severity=Severity.ERROR,
        subject=f"{location}.target",
        message=(
            f"annotation {annotation_id!r} has no usable anchor: a 2D anchor names a "
            "view with u and v, a 3D anchor names a part"
        ),
    )


__all__ = [
    "RULE_INVALID_VALUE",
    "RULE_UNKNOWN_ENUM",
    "RULE_UNKNOWN_FIELD",
    "SCHEMA_VERSION",
    "TOOL_VERSION",
    "ActorEntryFile",
    "ActorsFile",
    "AssetFile",
    "PreviewFile",
    "ProjectFile",
    "SchemaTooNew",
    "check_schema_version",
    "parse_actors_file",
    "parse_asset_file",
    "parse_project_file",
    "to_actor_mapping",
    "to_asset",
    "to_constraints",
    "to_preview",
    "to_severities",
    "unknown_fields",
]
