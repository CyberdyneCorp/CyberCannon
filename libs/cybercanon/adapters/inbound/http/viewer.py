"""The 3D viewer over HTTP — three reads, and not one decision in any of them.

Everything here maps a request onto
:mod:`cybercanon.application.use_cases.viewer` and renders what came back. The
re-anchor *write* is deliberately not here: it is an annotation operation, it
goes through the same body reader, the same idempotency key and the same
attribution as every other annotation write, and a second write pipeline for one
verb is how two surfaces start attributing the same change differently.

**Why the preview travels base64 in a JSON envelope.** It is the shape this
surface already uses for a concept view's bytes
(:func:`~cybercanon.adapters.inbound.http.payloads.view_revision_image`), and
uniformity is worth more here than a third of the bytes: one envelope, one
failure shape, one place the correlation identifier is attached, and a router
that never writes a status code — which is what
`tests/tooling/test_http_adapter_is_a_translator.py` checks this package for. The
preview is decimated by construction (`asset-preview`), so what is encoded is
small by the same decision that put it in the browser at all.

**D7 is enforced here rather than in the browser.** No address this module
registers resolves to a working export, and `tests/unit/test_http_viewer.py`
enumerates the application's routes to say so — *"a rule only held in the
frontend is one `fetch` away from being broken"*.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import outcomes, payloads, routing
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.adapters.inbound.http.versioning import PREFIX, VERSION
from cybercanon.application.results import Ok, Result, Unavailable
from cybercanon.application.use_cases.annotations import Workspace
from cybercanon.application.use_cases.authenticate import Authenticated
from cybercanon.application.use_cases.hosted_repository import author_for
from cybercanon.application.use_cases.resolve_actor import verified_as
from cybercanon.application.use_cases.viewer import (
    PreviewDescriptor,
    annotation_resolutions,
    get_preview_descriptor,
    read_preview,
)
from cybercanon.domain.policy import Operation

VIEWER_TAG = "3D viewer"

NO_WORKING_COPY = "project.no_working_copy"
NOT_HOSTED = (
    "this deployment has no working copy for that project, so its preview and "
    "its anchor resolutions cannot be read"
)


def register(app, surface: wiring.Surface) -> None:
    """Mount the versioned viewer surface over this wiring."""
    app.include_router(_router(surface))


def _router(surface: wiring.Surface) -> APIRouter:
    router = APIRouter(prefix=PREFIX)
    base = "/projects/{project}/assets/{asset}/preview"

    @router.get(base, tags=[VIEWER_TAG])
    async def descriptor(project: str, asset: str, request: Request) -> JSONResponse:
        """What to load, where it came from, and what the validation run measured.

        An asset with no preview is answered *with a descriptor carrying its
        reason*, not with a failure: the specification, the annotations and the
        rest of the asset stay usable, which `viewer-3d` requires in so many
        words.
        """
        return _read(surface, request, project, lambda hosted: _descriptor(hosted, asset))

    @router.get(f"{base}/content", tags=[VIEWER_TAG])
    async def content(project: str, asset: str, request: Request) -> JSONResponse:
        """The stored preview's bytes, verbatim, or the failure that names it."""
        return _read(
            surface,
            request,
            project,
            lambda hosted: _content(hosted, asset),
            payloads.preview_content,
        )

    @router.get(f"{base}/resolutions", tags=[VIEWER_TAG])
    async def resolutions(project: str, asset: str, request: Request) -> JSONResponse:
        """Each annotation's standing against the current export's part names (D6)."""
        return _read(
            surface,
            request,
            project,
            lambda hosted: _resolutions(surface, hosted, request, asset),
            payloads.anchor_resolutions,
        )

    return router


# --------------------------------------------------------------------------
# The pipeline, once
# --------------------------------------------------------------------------


def _read(
    surface: wiring.Surface,
    request: Request,
    project: str,
    read,
    render: outcomes.Rendering = payloads.preview_descriptor,
) -> JSONResponse:
    """Which project, who is acting, may they, then the use case — in that order."""
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, _ = prepared.value
    available = _wired(hosted)
    if not isinstance(available, Ok):
        return outcomes.respond(available, version=VERSION)
    return outcomes.respond(read(hosted), render, version=VERSION)


def _descriptor(hosted: wiring.HostedProject, asset: str) -> Result[PreviewDescriptor]:
    return get_preview_descriptor(
        hosted.name,
        asset,
        repository_host=hosted.repository_host,
        spec_store=hosted.container.spec_store,
        mesh_inspector=hosted.container.mesh_inspector,
        blob_store=hosted.container.blob_store,
    )


def _content(hosted: wiring.HostedProject, asset: str) -> Result:
    return read_preview(
        hosted.name,
        asset,
        repository_host=hosted.repository_host,
        spec_store=hosted.container.spec_store,
        blob_store=hosted.container.blob_store,
    )


def _resolutions(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    request: Request,
    asset: str,
) -> Result:
    """Resolutions against the parts the source export records, and nothing else.

    The part set is the server's answer rather than a query parameter: a client
    that supplied one would be proposing which parts exist, and the orphan count
    the asset page shows would then depend on what a browser had managed to
    load.
    """
    described = _descriptor(hosted, asset)
    if not isinstance(described, Ok):
        return described
    actor = wiring.acting(surface, request)
    if not isinstance(actor, Ok):
        return actor
    return annotation_resolutions(
        _workspace(hosted, actor.value, asset),
        export=described.value.latest_validated_export,
        parts=described.value.parts,
    )


def _workspace(hosted: wiring.HostedProject, actor: Authenticated, asset: str) -> Workspace:
    """The same workspace the annotation surface builds, from the same credential."""
    assert hosted.repository_host is not None
    return Workspace(
        project=hosted.name,
        asset_id=asset,
        repository_host=hosted.repository_host,
        spec_store=hosted.container.spec_store,
        actor=actor.actor,
        author=author_for(
            verified_as(actor.actor, actor.git_emails), hosted.container.spec_store
        ).author,
    )


def _wired(hosted: wiring.HostedProject) -> Result[None]:
    """Whether this project has a working copy at all — a wiring answer, not a rule."""
    if hosted.repository_host is None:
        return Unavailable(identifier=NO_WORKING_COPY, message=NOT_HOSTED, subject=hosted.name)
    return Ok(None)


__all__ = ["NOT_HOSTED", "NO_WORKING_COPY", "VIEWER_TAG", "register"]
