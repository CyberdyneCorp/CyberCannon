"""Concept views over HTTP — an upload, a history, and not one decision here.

Every handler below maps a request onto
:mod:`cybercanon.application.use_cases.ingest_views` or
:mod:`cybercanon.application.use_cases.view_revisions` and renders what came
back. There is no branch on image content anywhere in this module and there
cannot be one: `tests/tooling/test_http_adapter_is_a_translator.py` walks this
package's syntax tree looking for exactly that, and task 7.4 adds the image
vocabulary to what it looks for. A surface that decided which formats it
accepted would be a second acceptance rule, which is the same class of bug as a
second validator.

**Why the image travels base64 in a JSON envelope.** `concept-ingestion` says
*"A multi-image upload is all or nothing"* and specifies no transport; the rest
of this surface speaks JSON envelopes, and a multipart body would add a parser
dependency and a second body shape for one endpoint. Base64 costs a third in
size on the wire against a limit measured in tens of megabytes, and it keeps the
all-or-nothing request a single document that the idempotency store can hash
exactly as it hashes every other write.

**Authorship is the same rule the specification write surface applies** (G4, D8):
a view is content in the repository committed in a person's name, so an
automated caller is refused, and a person with no entry in `.canon/actors.yaml`
is refused *naming the missing entry*.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import outcomes, payloads, routing
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.adapters.inbound.http.versioning import PREFIX, VERSION
from cybercanon.adapters.inbound.http.writes import authorship
from cybercanon.application.results import Invalid, Ok, Result, Unavailable
from cybercanon.application.use_cases.authenticate import Authenticated
from cybercanon.application.use_cases.hosted_repository import author_for
from cybercanon.application.use_cases.ingest_views import (
    IngestionOutcome,
    UploadedImage,
    ingest_views,
    limits_of,
    remove_view,
)
from cybercanon.application.use_cases.resolve_actor import verified_as
from cybercanon.application.use_cases.view_revisions import (
    compare_view_revisions,
    current_view_token,
    get_view_revision,
    list_view_revisions,
)
from cybercanon.domain.policy import Operation

VIEWS_TAG = "concept views"

IMAGES_FIELD = "images"
SLOT_FIELD = "slot"
CONTENT_FIELD = "content"
FILENAME_FIELD = "filename"
NAME_FIELD = "name"
AGENT_FIELD = "agent"

UNREADABLE = "upload.unreadable"
NO_IMAGES = "upload.no_images"
NO_WORKING_COPY = "project.no_working_copy"

NOTHING_TO_INGEST = (
    "an upload carries at least one image, as `images`: a list of objects with a "
    "`slot` and base64 `content`"
)


def register(app, surface: wiring.Surface) -> None:
    """Mount the versioned concept-view surface over this wiring."""
    app.include_router(_router(surface))


def _router(surface: wiring.Surface) -> APIRouter:
    router = APIRouter(prefix=PREFIX)
    base = "/projects/{project}/assets/{asset}/views"

    @router.post(base, tags=[VIEWS_TAG])
    async def ingest(project: str, asset: str, request: Request) -> JSONResponse:
        """One or more concept views, as one attributed commit or none at all."""
        return _ingested(surface, request, project, asset, await request.body())

    @router.delete(base + "/{slot}", tags=[VIEWS_TAG])
    async def remove(project: str, asset: str, slot: str, request: Request) -> JSONResponse:
        """Remove a view. A removal is a revision, and earlier ones stay readable."""
        return _removed(surface, request, project, asset, slot)

    @router.get(base + "/{slot}/revisions", tags=[VIEWS_TAG])
    async def revisions(project: str, asset: str, slot: str, request: Request) -> JSONResponse:
        """Every revision of one view, newest first, from the repository alone."""
        return _read(
            surface,
            request,
            project,
            lambda hosted: list_view_revisions(
                project,
                asset,
                slot,
                repository_host=hosted.repository_host,
                spec_store=hosted.container.spec_store,
                image_inspector=_inspector(surface),
            ),
            payloads.view_history,
        )

    @router.get(base + "/{slot}/revisions/{revision}", tags=[VIEWS_TAG])
    async def revision(
        project: str, asset: str, slot: str, revision: str, request: Request
    ) -> JSONResponse:
        """One revision's image, labelled historical unless it is the current one."""
        return _read(
            surface,
            request,
            project,
            lambda hosted: get_view_revision(
                project,
                asset,
                slot,
                revision,
                repository_host=hosted.repository_host,
                spec_store=hosted.container.spec_store,
            ),
            payloads.view_revision_image,
        )

    @router.get(base + "/{slot}/comparison", tags=[VIEWS_TAG])
    async def comparison(
        project: str, asset: str, slot: str, request: Request, first: str = "", second: str = ""
    ) -> JSONResponse:
        """Two revisions side by side, older first whichever order they were asked in."""
        return _read(
            surface,
            request,
            project,
            lambda hosted: compare_view_revisions(
                project,
                asset,
                slot,
                first,
                second,
                repository_host=hosted.repository_host,
                spec_store=hosted.container.spec_store,
                image_inspector=_inspector(surface),
            ),
            payloads.view_comparison,
        )

    @router.get(base + "/{slot}/token", tags=[VIEWS_TAG])
    async def token(project: str, asset: str, slot: str, request: Request) -> JSONResponse:
        """The current revision's content hash — what a surface polls (D8)."""
        return _read(
            surface,
            request,
            project,
            lambda hosted: current_view_token(
                project,
                asset,
                slot,
                repository_host=hosted.repository_host,
                spec_store=hosted.container.spec_store,
            ),
            payloads.view_token,
        )

    return router


# --------------------------------------------------------------------------
# The two writes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProposedUpload:
    """One ingestion request as it arrived. A value, with nothing derived."""

    images: tuple[UploadedImage, ...]
    name: str = ""
    agent: str = ""


def _ingested(
    surface: wiring.Surface, request: Request, project: str, asset: str, body: bytes
) -> JSONResponse:
    """The whole upload, from the address to the response."""
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    result = _apply(surface, hosted, actor, asset, body, wiring.idempotency_key(request))
    return outcomes.respond(result, version=VERSION)


def _apply(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    body: bytes,
    key: str,
) -> Result[Any]:
    """Authorize the authorship, read the envelope, and ingest at most once (D11)."""
    refusal = authorship(actor.actor)
    if refusal is not None:
        return refusal
    proposed = read_upload(body)
    if not isinstance(proposed, Ok):
        return proposed
    available = _wired(hosted)
    if not isinstance(available, Ok):
        return available
    return routing.applied(
        surface,
        key,
        body,
        _upload(surface, hosted, actor, asset, proposed.value),
        payloads.ingested,
    )


def _upload(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    proposed: ProposedUpload,
) -> routing.Write[IngestionOutcome]:
    """The ingestion itself, bound and ready to be run at most once."""
    identity = author_for(verified_as(actor.actor, actor.git_emails), hosted.container.spec_store)

    def run() -> Result[IngestionOutcome]:
        return ingest_views(
            hosted.name,
            asset,
            proposed.images,
            repository_host=hosted.repository_host,
            spec_store=hosted.container.spec_store,
            image_inspector=_inspector(surface),
            author=identity.author,
            limits=limits_of(hosted.container.project()),
            blob_store=hosted.container.blob_store,
            thumbnail_renderer=_renderer(surface),
            view_index=_index(surface),
            subject=actor.subject,
            agent=proposed.agent,
            name=proposed.name,
        )

    return run


def _removed(
    surface: wiring.Surface, request: Request, project: str, asset: str, slot: str
) -> JSONResponse:
    """A removal, attributed exactly as an upload is."""
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    refusal = authorship(actor.actor)
    if refusal is not None:
        return outcomes.respond(refusal, version=VERSION)
    identity = author_for(verified_as(actor.actor, actor.git_emails), hosted.container.spec_store)
    result = remove_view(
        hosted.name,
        asset,
        slot,
        repository_host=hosted.repository_host,
        spec_store=hosted.container.spec_store,
        author=identity.author,
        subject=actor.subject,
    )
    return outcomes.respond(result, payloads.ingested, version=VERSION)


# --------------------------------------------------------------------------
# Reading the envelope
# --------------------------------------------------------------------------


def read_upload(body: bytes) -> Result[ProposedUpload]:
    """The images this request carries, or the refusal that says what is missing.

    Base64 that does not decode is an invalid request rather than an unreadable
    image: nothing has reached an inspector yet, and telling the caller the
    difference is what lets them fix the right thing.
    """
    document = _document(body)
    if not isinstance(document, Ok):
        return document
    fields = document.value
    declared = fields.get(IMAGES_FIELD)
    if not isinstance(declared, list) or not declared:
        return Invalid(identifier=NO_IMAGES, message=NOTHING_TO_INGEST, subject=IMAGES_FIELD)
    images = [_image(entry) for entry in declared]
    refused = next((entry for entry in images if not isinstance(entry, Ok)), None)
    if refused is not None:
        return refused
    return Ok(
        ProposedUpload(
            images=tuple(entry.value for entry in images if isinstance(entry, Ok)),
            name=str(fields.get(NAME_FIELD, "") or ""),
            agent=str(fields.get(AGENT_FIELD, "") or ""),
        )
    )


def _image(entry: Any) -> Result[UploadedImage]:
    """One element of `images`, decoded. The slot is carried through verbatim."""
    if not isinstance(entry, dict):
        return _unreadable("each element of `images` is an object")
    try:
        content = base64.b64decode(str(entry.get(CONTENT_FIELD, "")), validate=True)
    except (ValueError, TypeError):
        return _unreadable("an image's `content` is base64-encoded bytes")
    return Ok(
        UploadedImage(
            slot=str(entry.get(SLOT_FIELD, "")),
            content=content,
            filename=str(entry.get(FILENAME_FIELD, "") or ""),
        )
    )


def _document(body: bytes) -> Result[dict[str, Any]]:
    try:
        parsed = json.loads(body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return _unreadable("the request body is not a JSON object describing an upload")
    if not isinstance(parsed, dict):
        return _unreadable("the request body is not a JSON object describing an upload")
    return Ok(parsed)


def _unreadable(message: str) -> Invalid:
    return Invalid(identifier=UNREADABLE, message=message, subject="body")


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------


def _read(
    surface: wiring.Surface,
    request: Request,
    project: str,
    read: Any,
    render: outcomes.Rendering,
) -> JSONResponse:
    """The read pipeline for a history question: project, actor, policy, use case.

    It does not go through :func:`~cybercanon.adapters.inbound.http.routing.answered`
    because these reads are over the repository host rather than over the
    container — a view's history is git's history of a path, and the container
    has no opinion about it.
    """
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, _ = prepared.value
    available = _wired(hosted)
    if not isinstance(available, Ok):
        return outcomes.respond(available, version=VERSION)
    return outcomes.respond(read(hosted), render, version=VERSION)


def _wired(hosted: wiring.HostedProject) -> Result[None]:
    """Whether this project has a working copy at all — a wiring answer, not a rule."""
    if hosted.repository_host is None:
        return Unavailable(
            identifier=NO_WORKING_COPY,
            message=(
                f"project {hosted.name!r} has no working copy wired, so its concept "
                "views cannot be read or written"
            ),
            subject=hosted.name,
        )
    return Ok(None)


def _inspector(surface: wiring.Surface):
    return surface.image_inspector


def _renderer(surface: wiring.Surface):
    return surface.thumbnail_renderer


def _index(surface: wiring.Surface):
    return surface.view_index


__all__ = [
    "AGENT_FIELD",
    "CONTENT_FIELD",
    "FILENAME_FIELD",
    "IMAGES_FIELD",
    "NAME_FIELD",
    "NOTHING_TO_INGEST",
    "NO_IMAGES",
    "NO_WORKING_COPY",
    "SLOT_FIELD",
    "UNREADABLE",
    "VIEWS_TAG",
    "ProposedUpload",
    "read_upload",
    "register",
]
