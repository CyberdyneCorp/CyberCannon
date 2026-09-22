"""Annotations, threads and triage over HTTP — ten endpoints, no rules in any.

The model sheet, the 3D viewer and the art director's triage pass all reach the
product through this module, and none of them may find anything here that the
command line would not find. So every handler does the same four things, in the
order :mod:`~cybercanon.adapters.inbound.http.routing` fixes for the whole
surface — which project, who is acting, may they, then the use case — and the
only thing this module adds is reading a JSON body into the value objects the
use case takes.

**Which row of G4 each endpoint authorizes**, none of it decided here:

* creating and replying are `CREATE_ANNOTATION` and `REPLY_IN_THREAD` — *"any
  actor with project write access, independent of their role"*;
* editing, withdrawing and moving are the contribution-ownership rows: a person
  edits, withdraws and moves **their own**;
* resolving and reopening are `RESOLVE_ISSUE` and `REOPEN_ISSUE` — its author,
  the discipline owner, or an art director;
* promoting is `PROMOTE_TO_RULE` — an art director, and **never** an automated
  caller, which :mod:`cybercanon.domain.policy` refuses before a role is even
  consulted;
* reading and the queue are `READ_PROJECT`, like every other read.

**Hiding an action is not enforcement.** The thread panel offers promotion only
to somebody who may promote, and `model-sheet-2d` says in the same breath that a
submitted action the person may not take *"SHALL be refused by the system"*.
That refusal is here — or rather, it is in the domain and this endpoint simply
cannot avoid asking for it, because the use case authorizes before it reads
anything.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import outcomes, payloads, routing
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.adapters.inbound.http.versioning import PREFIX, VERSION
from cybercanon.application.results import Invalid, Ok, Result, Unavailable
from cybercanon.application.use_cases.annotations import (
    Draft,
    RecordedAnnotation,
    Workspace,
    create_annotation,
    delete_annotation,
    edit_annotation,
    kind_of,
    list_annotations,
    list_triage_queue,
    move_annotation,
    promote_annotation,
    reanchor_annotation,
    reopen_annotation,
    reply_to_annotation,
    resolve_annotation,
    state_of,
)
from cybercanon.application.use_cases.authenticate import Authenticated
from cybercanon.application.use_cases.hosted_repository import author_for
from cybercanon.application.use_cases.resolve_actor import verified_as
from cybercanon.domain.annotations import (
    Anchor,
    Anchor2D,
    Anchor3D,
    AnnotationFilter,
    AnnotationKind,
    AnnotationState,
    Camera,
    Stroke,
)
from cybercanon.domain.identity import AgentId
from cybercanon.domain.policy import Operation
from cybercanon.domain.triage import PromotionTarget

ANNOTATIONS_TAG = "annotations"
TRIAGE_TAG = "triage"

KIND_FIELD = "kind"
TEXT_FIELD = "text"
ANCHOR_FIELD = "anchor"
STROKES_FIELD = "strokes"
IDENTIFIER_FIELD = "id"
RULE_FIELD = "rule"
DESTINATION_FIELD = "destination"
CONCLUSION_FIELD = "conclusion"
AUTHORED_AGAINST_FIELD = "authored_against"
AGENT_FIELD = "agent"
"""Where a caller names the instrument it performed a write through.

The *identity* is never a body field and never could be — it is the verified
credential, and `strip_identity_claims` empties anything that tried. The
**instrument** is different in kind: naming it can only ever *narrow* what the
caller may do (an agent may not promote, whoever it acts for), so a caller that
lied about it would only refuse itself more. The concept-view and specification
endpoints read it from the same field, for the same reason.
"""

UNREADABLE = "annotation.unreadable_body"
UNKNOWN_KIND = "annotation.unknown_kind"
UNKNOWN_STATE = "annotation.unknown_state"
UNKNOWN_DESTINATION = "annotation.unknown_destination"
MALFORMED_ANCHOR = "annotation.malformed_anchor"
MALFORMED_STROKE = "annotation.malformed_stroke"
NO_WORKING_COPY = "project.no_working_copy"

NOT_HOSTED = (
    "this deployment has no working copy for that project, so nothing can be "
    "written to its repository"
)

NO_ANCHOR = (
    "an annotation is created against exactly one anchor: a 2D anchor names a "
    "view with `u` and `v`, a 3D anchor names a part"
)


def register(app, surface: wiring.Surface) -> None:
    """Mount the versioned annotation and triage surface over this wiring."""
    app.include_router(_router(surface))


def _router(surface: wiring.Surface) -> APIRouter:
    router = APIRouter(prefix=PREFIX)
    base = "/projects/{project}/assets/{asset}/annotations"
    one = f"{base}/{{annotation}}"

    @router.get(base, tags=[ANNOTATIONS_TAG])
    async def read_annotations(
        project: str,
        asset: str,
        request: Request,
        kind: str | None = None,
        state: str | None = None,
    ) -> JSONResponse:
        """One asset's threads, filtered exactly as every other surface filters."""
        return _listed(surface, request, project, asset, kind, state)

    @router.post(base, tags=[ANNOTATIONS_TAG])
    async def create(project: str, asset: str, request: Request) -> JSONResponse:
        """One annotation against one durable anchor, as one attributed commit."""
        return await _written(surface, request, project, asset, _create)

    @router.patch(one, tags=[ANNOTATIONS_TAG])
    async def edit(project: str, asset: str, annotation: str, request: Request) -> JSONResponse:
        """Re-word one's own contribution. Author and anchor are not parameters."""
        return await _written(surface, request, project, asset, _edit(annotation))

    @router.delete(one, tags=[ANNOTATIONS_TAG])
    async def withdraw(project: str, asset: str, annotation: str, request: Request) -> JSONResponse:
        """Withdraw one's own untouched annotation; a thread with replies exits."""
        return await _written(surface, request, project, asset, _withdraw(annotation))

    @router.post(f"{one}/replies", tags=[ANNOTATIONS_TAG])
    async def reply(project: str, asset: str, annotation: str, request: Request) -> JSONResponse:
        """One contribution to a thread — no anchor and no exit of its own."""
        return await _written(surface, request, project, asset, _reply(annotation))

    @router.post(f"{one}/anchor", tags=[ANNOTATIONS_TAG])
    async def move(project: str, asset: str, annotation: str, request: Request) -> JSONResponse:
        """Move one's own annotation to another anchor of the same form."""
        return await _written(surface, request, project, asset, _move(annotation))

    @router.post(f"{one}/reanchor", tags=[ANNOTATIONS_TAG])
    async def reanchor(project: str, asset: str, annotation: str, request: Request) -> JSONResponse:
        """Rescue an orphan by naming the subject it belongs on now (`anchor-resolution`)."""
        return await _written(surface, request, project, asset, _reanchor(annotation))

    @router.post(f"{one}/resolution", tags=[ANNOTATIONS_TAG])
    async def resolve(project: str, asset: str, annotation: str, request: Request) -> JSONResponse:
        """Exit two: a transient issue, addressed and out of the briefing."""
        return await _written(surface, request, project, asset, _resolve(annotation))

    @router.delete(f"{one}/resolution", tags=[ANNOTATIONS_TAG])
    async def reopen(project: str, asset: str, annotation: str, request: Request) -> JSONResponse:
        """Back into the open set — refused for one whose content is now a rule."""
        return await _written(surface, request, project, asset, _reopen(annotation))

    @router.post(f"{one}/promotion", tags=[ANNOTATIONS_TAG])
    async def promote(project: str, asset: str, annotation: str, request: Request) -> JSONResponse:
        """Exit one: a durable rule and a retired thread, in one commit (D6)."""
        return await _written(surface, request, project, asset, _promote(annotation))

    @router.get("/projects/{project}/triage", tags=[TRIAGE_TAG])
    async def triage(
        project: str,
        request: Request,
        kind: str | None = None,
        asset: str | None = None,
        owner: str | None = None,
    ) -> JSONResponse:
        """The art director's pass: every open annotation, ordered by the domain."""
        return _queued(surface, request, project, kind, asset, owner)

    return router


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _listed(
    surface: wiring.Surface,
    request: Request,
    project: str,
    asset: str,
    kind: str | None,
    state: str | None,
) -> JSONResponse:
    """The listing, with the filter the query string named, parsed once."""
    wanted = _filter(kind, state)
    if not isinstance(wanted, Ok):
        return outcomes.respond(wanted, version=VERSION)
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    result = _read(surface, hosted, actor, asset, wanted.value)
    return outcomes.respond(result, payloads.annotation_listing, version=VERSION)


def _read(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    wanted: AnnotationFilter,
) -> Result[Any]:
    workspace = _workspace(surface, hosted, actor, asset)
    if not isinstance(workspace, Ok):
        return workspace
    return list_annotations(workspace.value, wanted)


def _queued(
    surface: wiring.Surface,
    request: Request,
    project: str,
    kind: str | None,
    asset: str | None,
    owner: str | None,
) -> JSONResponse:
    """The project's queue, computed from the repository alone (D11)."""
    kinds = _kinds(kind)
    if not isinstance(kinds, Ok):
        return outcomes.respond(kinds, version=VERSION)
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, _ = prepared.value
    result = list_triage_queue(
        hosted.name,
        spec_store=hosted.container.spec_store,
        repository_host=hosted.repository_host,
        kinds=kinds.value,
        asset_id=asset or "",
        owner=owner or "",
        clock=surface.clock,
    )
    return outcomes.respond(result, payloads.triage_queue, version=VERSION)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

type Operate = Callable[[Workspace, dict[str, Any]], Result[RecordedAnnotation]]
"""One annotation operation, bound to the identifier its address named."""


async def _written(
    surface: wiring.Surface,
    request: Request,
    project: str,
    asset: str,
    operate: Operate,
) -> JSONResponse:
    """Who, then the body, then the use case, then one response — in that order."""
    body = await request.body()
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    result = _apply(surface, hosted, actor, asset, body, operate, wiring.idempotency_key(request))
    return outcomes.respond(result, version=VERSION)


def _apply(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    body: bytes,
    operate: Operate,
    key: str,
) -> Result[Any]:
    """The write, performed once per idempotency key and replayed after that."""
    document = _document(body)
    if not isinstance(document, Ok):
        return document
    workspace = _workspace(surface, hosted, actor, asset, _named_agent(document.value))
    if not isinstance(workspace, Ok):
        return workspace
    return routing.applied(
        surface,
        key,
        body,
        lambda: operate(workspace.value, document.value),
        payloads.recorded_annotation,
    )


def _named_agent(fields: dict[str, Any]) -> str:
    """The instrument this write declares, or nothing at all."""
    return str(fields.get(AGENT_FIELD, "") or "")


def _create(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
    kind = kind_of(str(fields.get(KIND_FIELD, "") or ""))
    if kind is None:
        return _unknown(KIND_FIELD, UNKNOWN_KIND, _kind_values())
    target = _anchor(fields.get(ANCHOR_FIELD))
    if not isinstance(target, Ok):
        return target
    marks = _strokes(fields.get(STROKES_FIELD))
    if not isinstance(marks, Ok):
        return marks
    return create_annotation(
        workspace,
        Draft(
            id=str(fields.get(IDENTIFIER_FIELD, "") or ""),
            kind=kind,
            text=str(fields.get(TEXT_FIELD, "") or ""),
            anchor=target.value,
            strokes=marks.value,
            authored_against=str(fields.get(AUTHORED_AGAINST_FIELD, "") or ""),
        ),
    )


def _reply(annotation_id: str) -> Operate:
    def operate(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
        return reply_to_annotation(
            workspace,
            annotation_id,
            str(fields.get(IDENTIFIER_FIELD, "") or ""),
            str(fields.get(TEXT_FIELD, "") or ""),
        )

    return operate


def _edit(annotation_id: str) -> Operate:
    def operate(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
        return edit_annotation(workspace, annotation_id, str(fields.get(TEXT_FIELD, "") or ""))

    return operate


def _withdraw(annotation_id: str) -> Operate:
    def operate(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
        return delete_annotation(workspace, annotation_id)

    return operate


def _move(annotation_id: str) -> Operate:
    def operate(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
        target = _anchor(fields.get(ANCHOR_FIELD))
        if not isinstance(target, Ok):
            return target
        return move_annotation(workspace, annotation_id, target.value)

    return operate


def _reanchor(annotation_id: str) -> Operate:
    def operate(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
        target = _anchor(fields.get(ANCHOR_FIELD))
        if not isinstance(target, Ok):
            return target
        return reanchor_annotation(workspace, annotation_id, target.value)

    return operate


def _resolve(annotation_id: str) -> Operate:
    def operate(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
        return resolve_annotation(
            workspace, annotation_id, str(fields.get(CONCLUSION_FIELD, "") or "")
        )

    return operate


def _reopen(annotation_id: str) -> Operate:
    def operate(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
        return reopen_annotation(workspace, annotation_id)

    return operate


def _promote(annotation_id: str) -> Operate:
    def operate(workspace: Workspace, fields: dict[str, Any]) -> Result[RecordedAnnotation]:
        declared = str(fields.get(DESTINATION_FIELD, "") or "")
        return promote_annotation(
            workspace,
            annotation_id,
            str(fields.get(RULE_FIELD, "") or ""),
            PromotionTarget.from_value(declared),
        )

    return operate


# --------------------------------------------------------------------------
# Reading a body, and nothing more
# --------------------------------------------------------------------------


def _workspace(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    agent: str = "",
) -> Result[Workspace]:
    """Everything one operation needs, assembled from the wiring and the credential.

    The acting identity comes from the verified credential and the git identity
    from the project's mapping — never from the body, which
    :func:`~cybercanon.application.use_cases.resolve_actor.strip_identity_claims`
    has already emptied of anything that tried.
    """
    if hosted.repository_host is None:
        return Unavailable(identifier=NO_WORKING_COPY, message=NOT_HOSTED, subject=hosted.name)
    return Ok(
        Workspace(
            project=hosted.name,
            asset_id=asset,
            repository_host=hosted.repository_host,
            spec_store=hosted.container.spec_store,
            actor=actor.actor,
            author=author_for(
                verified_as(actor.actor, actor.git_emails), hosted.container.spec_store
            ).author,
            via=AgentId(agent) if agent else None,
            agent=agent,
            clock=surface.clock,
        )
    )


def _document(body: bytes) -> Result[dict[str, Any]]:
    """The body as a mapping, or the refusal that it is not one.

    An empty body is an empty mapping: three of these endpoints carry nothing,
    and refusing a request for lacking a document it does not need would be the
    surface inventing a rule.
    """
    if not body.strip():
        return Ok({})
    try:
        parsed = json.loads(body)
    except ValueError:
        return Invalid(
            identifier=UNREADABLE,
            message="the request body is not valid JSON",
            subject="body",
        )
    return _mapping(parsed)


def _mapping(parsed: Any) -> Result[dict[str, Any]]:
    if isinstance(parsed, dict):
        return Ok(parsed)
    return Invalid(
        identifier=UNREADABLE,
        message="the request body is a JSON object",
        subject="body",
    )


def _anchor(declared: Any) -> Result[Anchor]:
    """The anchor this body names — exactly one form, or a refusal naming both.

    *"A creation request carrying no anchor, both anchor forms, or an anchor
    naming a view or part that the asset does not have SHALL be refused."* The
    first two are shape and are answered here; the third is about the asset and
    is answered by the use case, which is the only thing that has read it.
    """
    if not isinstance(declared, dict):
        return Invalid(identifier=MALFORMED_ANCHOR, message=NO_ANCHOR, subject=ANCHOR_FIELD)
    named = declared.get("part")
    flat = declared.get("view")
    if named and flat:
        return Invalid(
            identifier=MALFORMED_ANCHOR,
            message="an annotation carries one anchor; this one names a view and a part",
            subject=ANCHOR_FIELD,
        )
    return _one_anchor(declared, named, flat)


def _one_anchor(declared: dict[str, Any], named: Any, flat: Any) -> Result[Anchor]:
    """Whichever form was named, constructed by the domain so it validates itself."""
    try:
        return Ok(_built(declared, named, flat))
    except (TypeError, ValueError) as refusal:
        return Invalid(identifier=MALFORMED_ANCHOR, message=str(refusal), subject=ANCHOR_FIELD)


def _built(declared: dict[str, Any], named: Any, flat: Any) -> Anchor:
    if named:
        return Anchor3D(
            part=str(named),
            bone=_optional_text(declared.get("bone")),
            point=_point(declared.get("point")),
            normal=_point(declared.get("normal")),
            camera=_camera(declared.get("camera")),
            clip=_optional_text(declared.get("clip")),
            t=_optional_number(declared.get("t")),
        )
    if not flat:
        raise ValueError(NO_ANCHOR)
    return Anchor2D(view=str(flat), u=float(declared["u"]), v=float(declared["v"]))


def _optional_text(value: Any) -> str | None:
    return str(value) if value else None


def _point(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    first, second, third = (float(part) for part in value)
    return (first, second, third)


def _optional_number(value: Any) -> float | None:
    """A playback position the body declared, unchecked here (D9).

    The range is the domain's to refuse — :class:`~cybercanon.domain.annotations.Anchor3D`
    raises over a value that is not a proportion — and the refusal reaches the
    caller through :func:`_one_anchor` as the message the domain wrote.
    """
    return None if value is None else float(value)


def _camera(value: Any) -> Camera | None:
    """The viewing angle a 3D anchor records, so opening it restores what its
    author saw. Absent members make it absent rather than partial: a camera with
    no target is not a camera."""
    if not isinstance(value, dict):
        return None
    position = _point(value.get("position"))
    target = _point(value.get("target"))
    if position is None or target is None:
        return None
    return Camera(position=position, target=target, fov_deg=float(value.get("fov_deg", 0.0)))


def _strokes(declared: Any) -> Result[tuple[Stroke, ...]]:
    """The freehand marks, as ordered normalized pairs. Never pixels, never a raster."""
    if declared is None:
        return Ok(())
    try:
        return Ok(tuple(Stroke(tuple(_pair(point) for point in mark)) for mark in declared))
    except (TypeError, ValueError) as refusal:
        return Invalid(identifier=MALFORMED_STROKE, message=str(refusal), subject=STROKES_FIELD)


def _pair(point: Any) -> tuple[float, float]:
    first, second = (float(part) for part in point)
    return (first, second)


def _filter(kind: str | None, state: str | None) -> Result[AnnotationFilter]:
    """The filter a query string named, parsed into the domain's own value."""
    kinds = _kinds(kind)
    if not isinstance(kinds, Ok):
        return kinds
    exit_states = _states(state)
    if not isinstance(exit_states, Ok):
        return exit_states
    return Ok(AnnotationFilter.of(kinds=kinds.value, states=exit_states.value))


def _kinds(declared: str | None) -> Result[tuple[Any, ...]]:
    """The kinds a comma-separated parameter named, or a refusal naming the set."""
    return _members(declared, kind_of, UNKNOWN_KIND, KIND_FIELD, _kind_values())


def _states(declared: str | None) -> Result[tuple[Any, ...]]:
    """The exit states asked for; none named means every one, which is not a filter."""
    return _members(declared, state_of, UNKNOWN_STATE, "state", _state_values())


def _members(
    declared: str | None,
    read: Callable[[str], Any],
    identifier: str,
    field: str,
    allowed: tuple[str, ...],
) -> Result[tuple[Any, ...]]:
    names = tuple(part.strip() for part in (declared or "").split(",") if part.strip())
    found = tuple(read(name) for name in names)
    if None in found:
        return _unknown(field, identifier, allowed)
    return Ok(found)


def _unknown(field: str, identifier: str, allowed: tuple[str, ...]) -> Result[Any]:
    return Invalid(
        identifier=identifier,
        message=f"{field} is one of: {', '.join(allowed)}",
        subject=field,
    )


def _kind_values() -> tuple[str, ...]:
    return tuple(member.value for member in AnnotationKind)


def _state_values() -> tuple[str, ...]:
    return tuple(member.value for member in AnnotationState)


__all__ = ["register"]
