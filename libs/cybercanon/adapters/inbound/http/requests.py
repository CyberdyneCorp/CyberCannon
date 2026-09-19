"""Asset requests over HTTP: five endpoints, and no request logic in any of them.

A request is **repository content** (D7) — one file under `.canon/requests/`,
one commit per transition, authored by the acting person through the actors
mapping (D8). Nothing about that is decided here: this module reads a body,
asks the domain who may act, calls the use case the command line would call, and
renders what it returns.

**The tension this module resolves, and the fact that it is a tension.**
`asset-requests` says *"Any actor permitted to read a project SHALL be permitted
to raise a request within it"*. `hosted-repository` says a write by a person with
no mapped git identity SHALL be refused, naming the missing entry, and D7 accepts
the consequence in so many words: *"because every write needs an actors-mapping
entry (D8), a person who has never been mapped cannot even accept a request"*.
Both cannot hold for an unmapped reader. The **stricter** reading is implemented
— read access **and** a mapped identity — because the alternative is a workflow
record that cannot be attributed, which is the thing D8 exists to prevent, and
because a refusal that names the missing mapping is fixable in one line of a
file while an unattributable history is not fixable at all. The domain already
says so: every mutating operation is in
:data:`~cybercanon.domain.policy.NEEDS_GIT_MAPPING`, and raising is mutating. The
disagreement between the two specifications is reported rather than papered over.

**Which operation each endpoint authorizes**, all of it G4's matrix and none of
it this module's opinion:

* raising is `RAISE_REQUEST` — *"any mapped actor with read access"*;
* deciding and reassigning are `DECIDE_REQUEST` — *"the assigned discipline
  owner, or ART_DIRECTOR"*. Reassignment has no row of its own in G4, and it is
  authorized as a decision because choosing who owns a request is the same class
  of act as accepting one; a looser reading would let anybody who can read a
  project move an ask onto somebody else's list;
* reading and listing are `READ_PROJECT`, like every other read.

Dismissal is the one thing here that writes nothing to the repository, and D9
says why: *"the state that may be lost is whether someone has already looked at
it."*
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import outcomes, payloads, routing
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.adapters.inbound.http.versioning import PREFIX, VERSION
from cybercanon.application.results import Invalid, Ok, Result, Unavailable
from cybercanon.application.use_cases.authenticate import Authenticated
from cybercanon.application.use_cases.hosted_repository import author_for
from cybercanon.application.use_cases.requests import (
    RecordedRequest,
    RequestContext,
    assign_request,
    compose_request,
    dismiss_item,
    list_requests,
    read_request,
    request_context,
    transition_request,
    unread_items,
)
from cybercanon.application.use_cases.requests import (
    raise_request as record_request,
)
from cybercanon.application.use_cases.resolve_actor import verified_as
from cybercanon.domain.asset import AssetId
from cybercanon.domain.identity import ActorId
from cybercanon.domain.policy import Operation, Subject
from cybercanon.domain.requests import Discipline, RequestId, RequestState
from cybercanon.domain.status import Status

REQUESTS_TAG = "requests"

DISCIPLINE_FIELD = "discipline"
DESCRIPTION_FIELD = "description"
ASSET_FIELD = "asset"
ASKED_FOR_FIELD = "asked_for"
IDENTIFIER_FIELD = "id"
ASSIGNEE_FIELD = "assignee"
STATE_FIELD = "state"
REASON_FIELD = "reason"

UNREADABLE = "request.unreadable_body"
UNKNOWN_DISCIPLINE = "request.unknown_discipline"
UNKNOWN_STATE = "request.unknown_state"
UNKNOWN_ASKED_FOR = "request.unknown_asked_for"
NO_WORKING_COPY = "project.no_working_copy"
NO_DISMISSALS = "notifications.unconfigured"

NOT_MIRRORED = (
    "this deployment has no dismissal store configured, so an item cannot be marked as seen"
)


def register(app, surface: wiring.Surface) -> None:
    """Mount the versioned request surface over this wiring."""
    app.include_router(_router(surface))


def _router(surface: wiring.Surface) -> APIRouter:
    router = APIRouter(prefix=PREFIX)

    @router.post("/projects/{project}/requests", tags=[REQUESTS_TAG])
    async def raise_request(project: str, request: Request) -> JSONResponse:
        """Ask somebody for an asset — one file, one commit, one attribution."""
        return _raised(surface, request, project, await request.body())

    @router.get("/projects/{project}/requests", tags=[REQUESTS_TAG])
    async def list_project_requests(
        project: str, request: Request, page: str | None = None, page_size: int | None = None
    ) -> JSONResponse:
        """Every request the repository holds, one page at a time, by identifier."""
        paging = routing.paged(
            lambda listing: listing.requests,
            payloads.asset_request,
            token=page,
            size=page_size,
        )
        return _read(surface, request, project, lambda hosted, actor: _listing(hosted), paging)

    @router.get("/projects/{project}/requests/{request_id}", tags=[REQUESTS_TAG])
    async def read_one_request(project: str, request_id: str, request: Request) -> JSONResponse:
        """One request, by the identifier it was recorded under."""
        return _read(
            surface,
            request,
            project,
            lambda hosted, actor: _one(hosted, request_id),
            render=payloads.asset_request,
        )

    @router.put("/projects/{project}/requests/{request_id}/assignee", tags=[REQUESTS_TAG])
    async def assign(project: str, request_id: str, request: Request) -> JSONResponse:
        """Move a request onto somebody else's list, recording who did it."""
        return _decided(surface, request, project, request_id, await request.body(), _assignment)

    @router.post("/projects/{project}/requests/{request_id}/transitions", tags=[REQUESTS_TAG])
    async def transition(project: str, request_id: str, request: Request) -> JSONResponse:
        """Accept, decline, fulfil or withdraw — one commit per transition (D7)."""
        return _decided(surface, request, project, request_id, await request.body(), _transition)

    @router.get("/projects/{project}/unread", tags=[REQUESTS_TAG])
    async def unread(project: str, request: Request) -> JSONResponse:
        """What this person has not yet looked at — derived, never stored (D9)."""
        return _read(
            surface,
            request,
            project,
            lambda hosted, actor: _items(hosted, actor, surface),
            render=payloads.unread_items,
        )

    @router.post("/projects/{project}/unread/{request_id}/dismissal", tags=[REQUESTS_TAG])
    async def dismiss(project: str, request_id: str, request: Request) -> JSONResponse:
        """Mark one item as seen, for this person and for nobody else (D9)."""
        return _read(
            surface,
            request,
            project,
            lambda hosted, actor: _dismiss(hosted, actor, surface, request_id),
            render=payloads.dismissal,
        )

    return router


# --------------------------------------------------------------------------
# Raising
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProposedRequest:
    """What a caller asked for, as the request body stated it. A value, derived nothing."""

    discipline: Discipline
    description: str
    identifier: RequestId
    asset: AssetId | None = None
    asked_for: Status | None = None


def _raised(surface: wiring.Surface, request: Request, project: str, body: bytes) -> JSONResponse:
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    result = _raise(surface, hosted, actor, body, wiring.idempotency_key(request))
    return outcomes.respond(result, version=VERSION)


def _raise(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    body: bytes,
    key: str,
) -> Result[Any]:
    """Authorize, read the body, compose in the domain, then commit exactly once."""
    identity = _author(hosted, actor)
    refusal = wiring.permitted(
        actor.actor,
        Operation.RAISE_REQUEST,
        _subject(hosted.name, mapped=identity is not None),
    )
    if refusal is not None:
        return refusal
    proposed = read_proposal(body)
    if not isinstance(proposed, Ok):
        return proposed
    composed = _compose(hosted, actor, proposed.value, surface)
    if not isinstance(composed, Ok):
        return composed
    return routing.applied(
        surface,
        key,
        body,
        _record(surface, hosted, composed.value, identity),
        payloads.recorded_request,
    )


def read_proposal(body: bytes) -> Result[ProposedRequest]:
    """The request this body describes, or the refusal that says what is missing.

    The description is not checked here beyond being present — *"a request
    states what is needed"* is the domain's rule and it refuses an empty one on
    its own, which is what keeps this function a reader rather than a validator.
    """
    document = _document(body)
    if not isinstance(document, Ok):
        return document
    fields = document.value
    discipline = Discipline.from_value(str(fields.get(DISCIPLINE_FIELD, "")))
    if discipline is None:
        return _unknown(DISCIPLINE_FIELD, UNKNOWN_DISCIPLINE, Discipline.values())
    asked = _asked_for(fields)
    if not isinstance(asked, Ok):
        return asked
    return Ok(
        ProposedRequest(
            discipline=discipline,
            description=str(fields.get(DESCRIPTION_FIELD, "") or ""),
            identifier=_identifier(fields),
            asset=_optional(fields.get(ASSET_FIELD), AssetId),
            asked_for=asked.value,
        )
    )


def _compose(
    hosted: wiring.HostedProject,
    actor: Authenticated,
    proposed: ProposedRequest,
    surface: wiring.Surface,
) -> Result[Any]:
    """The domain's request, assigned by the domain's cascade (`asset-requests`)."""
    return compose_request(
        hosted.name,
        proposed.identifier,
        author=ActorId(actor.subject),
        discipline=proposed.discipline,
        description=proposed.description,
        at=surface.clock(),
        asset=proposed.asset,
        asked_for_status=proposed.asked_for,
        spec_store=hosted.container.spec_store,
        locate=hosted.container.spec_path_for,
    )


def _record(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    composed: Any,
    identity: Any,
) -> routing.Write[RecordedRequest]:
    """The commit itself, bound and ready to be run at most once (D11)."""

    def run() -> Result[RecordedRequest]:
        return record_request(
            hosted.name,
            composed,
            repository_host=hosted.repository_host,
            author=identity,
            notifier=surface.notifier,
            clock=surface.clock,
        )

    return run


# --------------------------------------------------------------------------
# Deciding: assignment and transitions
# --------------------------------------------------------------------------

type Decision = Callable[
    [wiring.Surface, wiring.HostedProject, Authenticated, RequestContext, dict[str, Any], Any],
    routing.Write[RecordedRequest],
]
"""One decision, bound to everything it needs and waiting to be run at most once."""


def _decided(
    surface: wiring.Surface,
    request: Request,
    project: str,
    request_id: str,
    body: bytes,
    decide: Decision,
) -> JSONResponse:
    """The shared half of assignment and transition: who, what, then one commit."""
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    result = _decide(
        surface, hosted, actor, request_id, body, decide, wiring.idempotency_key(request)
    )
    return outcomes.respond(result, version=VERSION)


def _decide(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    request_id: str,
    body: bytes,
    decide: Decision,
    key: str,
) -> Result[Any]:
    """Read the body, load the request, ask policy about *it*, then act once."""
    document = _document(body)
    if not isinstance(document, Ok):
        return document
    context = _context(surface, hosted, request_id)
    if not isinstance(context, Ok):
        return context
    identity = _author(hosted, actor)
    refusal = wiring.permitted(
        actor.actor,
        _operation_for(document.value),
        _subject_for(hosted.name, context.value, identity),
    )
    if refusal is not None:
        return refusal
    written = decide(surface, hosted, actor, context.value, document.value, identity)
    return routing.applied(surface, key, body, written, payloads.recorded_request)


def _operation_for(fields: dict[str, Any]) -> Operation:
    """Which row of G4 this move is, and why withdrawal is not the deciding one.

    G4 has two rows for requests: *"raise"* — any mapped actor with read access —
    and *"accept or decline"* — the assigned discipline owner or `ART_DIRECTOR`.
    Withdrawal is neither: it is the author retracting their own ask, which is
    the raising side of the matrix, and `asset-requests` already fixes who may
    do it in terms no adapter should restate — *"only the request's author SHALL
    be able to withdraw it"*, enforced by
    :func:`~cybercanon.domain.requests.may_transition`. Authorizing a withdrawal
    as a decision would refuse the one person the specification names.
    """
    if str(fields.get(STATE_FIELD, "")) == str(RequestState.WITHDRAWN):
        return Operation.RAISE_REQUEST
    return Operation.DECIDE_REQUEST


def _assignment(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    context: RequestContext,
    fields: dict[str, Any],
    identity: Any,
) -> routing.Write[RecordedRequest]:
    """Reassign, recording who did it and when (`asset-requests`)."""

    def run() -> Result[RecordedRequest]:
        return assign_request(
            hosted.name,
            context.request.id,
            _optional(fields.get(ASSIGNEE_FIELD), ActorId),
            actor=ActorId(actor.subject),
            repository_host=hosted.repository_host,
            author=identity,
            notifier=surface.notifier,
            clock=surface.clock,
        )

    return run


def _transition(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    context: RequestContext,
    fields: dict[str, Any],
    identity: Any,
) -> routing.Write[RecordedRequest]:
    """Move the request, with the asset's own position read and never written."""
    wanted = RequestState.from_value(str(fields.get(STATE_FIELD, "")))

    def run() -> Result[RecordedRequest]:
        if wanted is None:
            return _unknown(STATE_FIELD, UNKNOWN_STATE, RequestState.values())
        return transition_request(
            hosted.name,
            context.request.id,
            wanted,
            actor=ActorId(actor.subject),
            repository_host=hosted.repository_host,
            author=identity,
            reason=str(fields.get(REASON_FIELD, "") or ""),
            asset_status=context.asset_status,
            notifier=surface.notifier,
            clock=surface.clock,
        )

    return run


# --------------------------------------------------------------------------
# Reading, listing, and what one person has not looked at (D9)
# --------------------------------------------------------------------------


type Produce = Callable[[wiring.HostedProject, Authenticated], Result[Any]]
"""One answer about a project's requests, once the caller is known to be entitled."""


def _read(
    surface: wiring.Surface,
    request: Request,
    project: str,
    produce: Produce,
    paging: Callable[[Result[Any]], Result[Any]] | None = None,
    render: outcomes.Rendering = outcomes.identity,
) -> JSONResponse:
    """Which project, who is asking, may they, then one answer — and no revision.

    Deliberately not
    :func:`~cybercanon.adapters.inbound.http.routing.answered`: that pipeline
    pins the *specification* store to a revision, which is what a specification
    read needs (D3) and what a request read does not have. A request is read
    from the repository at its own resolved revision, and the freshness a
    specification read reports would be a claim about content this answer does
    not contain.
    """
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    answer = produce(hosted, actor)
    return outcomes.respond(answer if paging is None else paging(answer), render, version=VERSION)


def _listing(hosted: wiring.HostedProject) -> Result[Any]:
    if hosted.repository_host is None:
        return _no_working_copy(hosted.name)
    return list_requests(hosted.name, repository_host=hosted.repository_host)


def _one(hosted: wiring.HostedProject, request_id: str) -> Result[Any]:
    if hosted.repository_host is None:
        return _no_working_copy(hosted.name)
    return read_request(hosted.name, RequestId(request_id), repository_host=hosted.repository_host)


def _items(
    hosted: wiring.HostedProject, actor: Authenticated, surface: wiring.Surface
) -> Result[Any]:
    if hosted.repository_host is None:
        return _no_working_copy(hosted.name)
    if surface.dismissals is None:
        return Unavailable(identifier=NO_DISMISSALS, message=NOT_MIRRORED, subject=hosted.name)
    return unread_items(
        hosted.name,
        ActorId(actor.subject),
        repository_host=hosted.repository_host,
        dismissals=surface.dismissals,
    )


def _dismiss(
    hosted: wiring.HostedProject,
    actor: Authenticated,
    surface: wiring.Surface,
    request_id: str,
) -> Result[Any]:
    if hosted.repository_host is None:
        return _no_working_copy(hosted.name)
    if surface.dismissals is None:
        return Unavailable(identifier=NO_DISMISSALS, message=NOT_MIRRORED, subject=hosted.name)
    return dismiss_item(
        hosted.name,
        ActorId(actor.subject),
        RequestId(request_id),
        repository_host=hosted.repository_host,
        dismissals=surface.dismissals,
        clock=surface.clock,
    )


# --------------------------------------------------------------------------
# The small shared pieces
# --------------------------------------------------------------------------


def _context(
    surface: wiring.Surface, hosted: wiring.HostedProject, request_id: str
) -> Result[RequestContext]:
    """The request, its discipline owner and the asset position policy needs."""
    if hosted.repository_host is None:
        return _no_working_copy(hosted.name)
    return request_context(
        hosted.name,
        RequestId(request_id),
        repository_host=hosted.repository_host,
        spec_store=hosted.container.spec_store,
        locate=hosted.container.spec_path_for,
    )


def _author(hosted: wiring.HostedProject, actor: Authenticated):
    """This person's git identity in this project, or ``None`` when unmapped (D8)."""
    return author_for(
        verified_as(actor.actor, actor.git_emails), hosted.container.spec_store
    ).author


def _subject(project: str, *, mapped: bool) -> Subject:
    return Subject(project=project, has_git_identity=mapped)


def _subject_for(project: str, context: RequestContext, identity: Any) -> Subject:
    """What policy is asked about: this request, its owner, and this person's mapping."""
    return Subject(
        project=project,
        author=context.request.author,
        assignee=context.request.assignee,
        discipline_owner=context.discipline_owner,
        has_git_identity=identity is not None,
        description=f"request {context.request.id}",
    )


def _document(body: bytes) -> Result[dict[str, Any]]:
    try:
        parsed = json.loads(body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return _unreadable()
    if not isinstance(parsed, dict):
        return _unreadable()
    return Ok(parsed)


def _unreadable() -> Invalid:
    return Invalid(
        identifier=UNREADABLE,
        message="the request body is not a JSON object",
        subject="body",
    )


def _asked_for(fields: dict[str, Any]) -> Result[Status | None]:
    """The lifecycle position this request is asking the asset to reach, if any."""
    declared = str(fields.get(ASKED_FOR_FIELD, "") or "")
    if not declared:
        return Ok(None)
    wanted = Status.from_value(declared)
    if wanted is None:
        return _unknown(ASKED_FOR_FIELD, UNKNOWN_ASKED_FOR, Status.values())
    return Ok(wanted)


def _unknown(field: str, identifier: str, accepted: tuple[str, ...]) -> Invalid:
    """One refusal shape for every value the vocabulary does not contain."""
    return Invalid(
        identifier=identifier,
        message=f"`{field}` must be one of: {', '.join(accepted)}",
        subject=field,
    )


def _identifier(fields: dict[str, Any]) -> RequestId:
    """The identifier the caller chose, or one nobody has used before.

    A caller-supplied identifier makes a retry over a flaky network land on the
    same file; a generated one keeps the common case from needing a scheme.
    Either way it is the address of the request for the rest of its life (D7),
    so it is never derived from anything that could change.
    """
    declared = str(fields.get(IDENTIFIER_FIELD, "") or "").strip()
    return RequestId(declared or f"req-{uuid.uuid4().hex[:12]}")


def _optional[T](value: Any, build: type[T]) -> T | None:
    text = str(value or "").strip()
    return build(text) if text else None  # type: ignore[call-arg]


def _no_working_copy(project: str) -> Unavailable:
    return Unavailable(
        identifier=NO_WORKING_COPY,
        message=(
            f"project {project!r} has no working copy wired, so its requests "
            "cannot be read or written"
        ),
        subject=project,
    )


__all__ = [
    "NO_DISMISSALS",
    "NO_WORKING_COPY",
    "REQUESTS_TAG",
    "UNKNOWN_ASKED_FOR",
    "UNKNOWN_DISCIPLINE",
    "UNKNOWN_STATE",
    "UNREADABLE",
    "ProposedRequest",
    "read_proposal",
    "register",
]
