"""Linked documents over HTTP — five endpoints, and the caller's own authority.

`document-platform` asks for link, unlink, list, create-and-link and a linked
document's revision history to be reachable from the web application, and asks
for exactly one thing this surface has to be careful about: **whose authority
the platform is asked under**. D2 answers it — the caller's own bearer token
travels on, and this deployment's credential never stands in for a person — so
every endpoint passes :func:`~cybercanon.adapters.inbound.http.surface.forwarded`
and none of them can reach the platform without one.

**Why linking is a `PUT` on the document's own address.** The alternative —
one `POST` that creates when the body names no document and links when it does
— makes the difference between *creating a document at the platform* and
*recording a reference to one that exists* a property of which fields a body
happens to carry. Those two have different failure modes (D8: a refused
creation writes nothing; a failed link names the created document), so they get
different addresses and there is no branch to get wrong.

**Which row of G4 authorizes each.** Reading is `READ_PROJECT`, like every
other read. Linking, unlinking and creating write authored content into a
specification file, so they are the durable-authorship row — the same refusal
:mod:`~cybercanon.adapters.inbound.http.writes` applies, reached through the
same function rather than restated here, because an automated caller that may
not author a constraint may not author a link to the document arguing for one
either.

**No read here is pinned to a revision by this module.** The link list reads
the specification at the head the use case resolves for itself, exactly as the
annotation surface does, because the question is *"what does this file say
now"* and a second pinning layer would only answer it twice.

**What is deliberately absent.** There is no endpoint that reads a document's
body, and none that writes one. The only write this surface can reach at the
platform is creating an empty pre-titled document (D10), and the only actions a
listed link offers are the two the domain names
(:func:`~cybercanon.application.use_cases.documents.actions_for`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import outcomes, payloads, routing, writes
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.adapters.inbound.http.versioning import PREFIX, VERSION
from cybercanon.application.ports.document_platform import NO_CREDENTIAL, Credential
from cybercanon.application.results import Invalid, Ok, Result, Unavailable
from cybercanon.application.use_cases.authenticate import Authenticated
from cybercanon.application.use_cases.documents import (
    DocumentWorkspace,
    RecordedLink,
    create_document_for_asset,
    link_document,
    list_document_revisions,
    list_linked_documents,
    unlink_document,
)
from cybercanon.application.use_cases.hosted_repository import author_for
from cybercanon.application.use_cases.resolve_actor import verified_as
from cybercanon.domain.documents import DocumentRef, DocumentScope, MalformedReference
from cybercanon.domain.policy import Operation

DOCUMENTS_TAG = "documents"

WORKSPACE_FIELD = "workspace"
URL_FIELD = "url"
SCOPE_FIELD = "scope"
TITLE_FIELD = "title"
AGENT_FIELD = "agent"
"""The instrument a write was performed through — never the identity (D2)."""

UNREADABLE = "document.unreadable_body"
UNKNOWN_SCOPE = "document.unknown_scope"
MALFORMED = "document.malformed_reference"
NO_WORKING_COPY = "project.no_working_copy"

NOT_HOSTED = (
    "this deployment has no working copy for that project, so nothing can be "
    "linked in its repository"
)

NO_SCOPE = (
    "a document link is scoped to the asset or to the project; send `scope` as "
    f"one of {', '.join(member.value for member in DocumentScope)}"
)


def register(app, surface: wiring.Surface) -> None:
    """Mount the versioned linked-document surface over this wiring."""
    app.include_router(_router(surface))


def _router(surface: wiring.Surface) -> APIRouter:
    router = APIRouter(prefix=PREFIX)
    base = "/projects/{project}/assets/{asset}/documents"
    one = f"{base}/{{document}}"

    @router.get(base, tags=[DOCUMENTS_TAG])
    async def read_links(project: str, asset: str, request: Request) -> JSONResponse:
        """This asset's links and its project's, resolved as this viewer sees them.

        A request carrying no bearer credential still gets the list: the
        references are repository content, and only what each entry *says about
        itself* depends on the platform having answered.
        """
        return _answered(
            surface,
            request,
            project,
            asset,
            list_linked_documents,
            payloads.document_listing,
        )

    @router.get(f"{one}/revisions", tags=[DOCUMENTS_TAG])
    async def read_revisions(
        project: str, asset: str, document: str, request: Request
    ) -> JSONResponse:
        """One linked document's own version history, read and never copied."""
        return _answered(
            surface,
            request,
            project,
            asset,
            lambda workspace: list_document_revisions(workspace, document),
            payloads.document_history,
        )

    @router.put(one, tags=[DOCUMENTS_TAG])
    async def link(project: str, asset: str, document: str, request: Request) -> JSONResponse:
        """Record a reference to a document that already exists. Nothing is fetched."""
        return await _written(surface, request, project, asset, _link(document))

    @router.delete(one, tags=[DOCUMENTS_TAG])
    async def unlink(project: str, asset: str, document: str, request: Request) -> JSONResponse:
        """Remove one reference. The document at the platform is never touched."""
        return await _written(surface, request, project, asset, _unlink(document))

    @router.post(base, tags=[DOCUMENTS_TAG])
    async def create(project: str, asset: str, request: Request) -> JSONResponse:
        """Create an empty pre-titled document for this asset and link it (D8)."""
        return await _written(surface, request, project, asset, _create)

    return router


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

type Read = Callable[[DocumentWorkspace], Result[Any]]
"""One document read, expressed over the workspace it should run against."""


def _answered(
    surface: wiring.Surface,
    request: Request,
    project: str,
    asset: str,
    read: Read,
    render: outcomes.Rendering,
) -> JSONResponse:
    """Which project, who is acting, may they, then the use case — in that order."""
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    workspace = _workspace(hosted, actor, asset, credential=wiring.forwarded(request))
    if not isinstance(workspace, Ok):
        return outcomes.respond(workspace, version=VERSION)
    return outcomes.respond(read(workspace.value), render, version=VERSION)


# --------------------------------------------------------------------------
# Writing — one shape for all three, because they refuse for the same reasons
# --------------------------------------------------------------------------

type Operate = Callable[[DocumentWorkspace], Result[RecordedLink]]
"""One link operation, bound to the address and the body it was read from."""

type Bind = Callable[[dict[str, Any]], Result[Operate]]
"""Reading a request body into the operation it asks for, or the refusal."""


async def _written(
    surface: wiring.Surface,
    request: Request,
    project: str,
    asset: str,
    bind: Bind,
) -> JSONResponse:
    """Who, then may they author, then the body, then the use case, then one response."""
    body = await request.body()
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    result = _apply(
        surface,
        hosted,
        actor,
        asset,
        body,
        bind,
        credential=wiring.forwarded(request),
        key=wiring.idempotency_key(request),
    )
    return outcomes.respond(result, version=VERSION)


def _apply(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    body: bytes,
    bind: Bind,
    *,
    credential: Credential,
    key: str,
) -> Result[Any]:
    """The write, performed once per idempotency key and replayed after that.

    The authorship refusal comes first, before the body is read, for the reason
    :func:`~cybercanon.adapters.inbound.http.writes.authorship` gives: a caller
    that may not write should not learn whether its content would have been
    accepted.
    """
    refusal = writes.authorship(actor.actor)
    if refusal is not None:
        return refusal
    document = _document(body)
    if not isinstance(document, Ok):
        return document
    bound = bind(document.value)
    if not isinstance(bound, Ok):
        return bound
    workspace = _workspace(
        hosted,
        actor,
        asset,
        credential=credential,
        agent=str(document.value.get(AGENT_FIELD, "") or ""),
    )
    if not isinstance(workspace, Ok):
        return workspace
    return routing.applied(
        surface,
        key,
        body,
        lambda: bound.value(workspace.value),
        payloads.recorded_link,
    )


def _link(document: str) -> Bind:
    """Link the reference the body describes, at the identifier the address names."""

    def read(fields: dict[str, Any]) -> Result[Operate]:
        scope = _scope(fields)
        if not isinstance(scope, Ok):
            return scope
        ref = _reference(fields, document)
        if not isinstance(ref, Ok):
            return ref
        return Ok(lambda workspace: link_document(workspace, ref.value, scope.value))

    return read


def _unlink(document: str) -> Bind:
    """Remove the reference the address names, from the scope the body names."""

    def read(fields: dict[str, Any]) -> Result[Operate]:
        scope = _scope(fields)
        if not isinstance(scope, Ok):
            return scope
        return Ok(lambda workspace: unlink_document(workspace, document, scope.value))

    return read


def _create(fields: dict[str, Any]) -> Result[Operate]:
    """Create a document under the caller's own authority, then link it (D8)."""
    title = str(fields.get(TITLE_FIELD, "") or "")
    return Ok(lambda workspace: create_document_for_asset(workspace, title))


# --------------------------------------------------------------------------
# The workspace, and reading the request
# --------------------------------------------------------------------------


def _workspace(
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    *,
    credential: Credential = NO_CREDENTIAL,
    agent: str = "",
) -> Result[DocumentWorkspace]:
    """Everything one operation needs, assembled from the wiring and the credential.

    The acting identity comes from the verified credential and the git identity
    from the project's mapping — never from the body. The platform credential
    is the caller's own bearer token and travels as an argument, so there is no
    path here that could reach the platform under this deployment's name.

    The repository host is the hosted project's, attached here rather than at
    composition: a hosted deployment keeps the host beside the container
    because a read is pinned per request (`hosted-repository` D3), so the
    container it holds has none of its own and the surface is where the two
    meet.
    """
    if hosted.repository_host is None:
        return Unavailable(identifier=NO_WORKING_COPY, message=NOT_HOSTED, subject=hosted.name)
    container = replace(hosted.container, repository_host=hosted.repository_host)
    return Ok(
        container.document_workspace_for(
            asset,
            credential=credential,
            actor=actor.actor,
            author=author_for(
                verified_as(actor.actor, actor.git_emails), container.spec_store
            ).author,
            agent=agent,
        )
    )


def _scope(fields: dict[str, Any]) -> Result[DocumentScope]:
    """Asset or project, defaulting to the asset the address already named."""
    declared = str(fields.get(SCOPE_FIELD, "") or "").strip().lower()
    if not declared:
        return Ok(DocumentScope.ASSET)
    for member in DocumentScope:
        if member.value == declared:
            return Ok(member)
    return Invalid(identifier=UNKNOWN_SCOPE, message=NO_SCOPE, subject=SCOPE_FIELD)


def _reference(fields: dict[str, Any], document: str) -> Result[DocumentRef]:
    """The reference this body describes, or the refusal naming what is wrong.

    Well-formedness is the domain's rule
    (:func:`~cybercanon.domain.documents.reference_problem`), raised on
    construction and translated here — so this surface and `canon lint` refuse
    the same references for the same stated reason.
    """
    try:
        return Ok(
            DocumentRef(
                workspace=str(fields.get(WORKSPACE_FIELD, "") or ""),
                document_id=document,
                url=str(fields.get(URL_FIELD, "") or ""),
            )
        )
    except MalformedReference as problem:
        return Invalid(identifier=MALFORMED, message=str(problem), subject=document)


def _document(body: bytes) -> Result[dict[str, Any]]:
    """The body as a mapping. An empty body is an empty mapping, not a refusal."""
    if not body.strip():
        return Ok({})
    try:
        parsed = json.loads(body)
    except ValueError:
        return _unreadable()
    if not isinstance(parsed, dict):
        return _unreadable()
    return Ok(parsed)


def _unreadable() -> Invalid:
    return Invalid(
        identifier=UNREADABLE,
        message="the request body is a JSON object describing a document link",
        subject="body",
    )
