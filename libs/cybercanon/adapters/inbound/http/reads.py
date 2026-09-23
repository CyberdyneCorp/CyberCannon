"""The read endpoints — five kinds of answer, and not one of them decided here.

Task 9.5 lists them: assets, specifications, compiled briefings, validation and
lookup. Each is one call to the use case the command line and the agent surface
already call, through :func:`~cybercanon.adapters.inbound.http.routing.answered`,
so *"a verdict here is the verdict `canon validate` gives, because it is the
same function"* is structural rather than a promise.

**Addressing** is `http-api`'s second requirement and it decides the shape of
every path below: *"Every addressable resource SHALL be identified by a project
identifier and the identifier the specification already uses for that resource"*,
and *"SHALL NOT address a resource by a database-generated key"*. So an asset is
at `/v1/projects/{project}/assets/{asset}` — the identifier written in
`asset.yaml` — and dropping the index and rebuilding it cannot move anything,
because no address was ever derived from a row.

**Validation is a GET**, which reads oddly beside the other two surfaces and is
deliberate: over HTTP it validates an export *already in the repository* at the
served revision, and it changes nothing. The upload-and-validate path is not
here at all — G1 puts server-side validation in a worker outside the request
path, because mesh loading is unbounded work and an HTTP handler that waits on
it is a timeout with extra steps.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import payloads, routing
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.adapters.inbound.http.versioning import PREFIX
from cybercanon.application.results import Ok, Result
from cybercanon.application.use_cases.compile_spec import CompiledSpec
from cybercanon.application.use_cases.deployment_status import IndexRead
from cybercanon.application.use_cases.lookup_assets import AssetListing
from cybercanon.application.use_cases.search_delegation import DelegatedSearch
from cybercanon.domain.policy import Operation

ASSETS_TAG = "assets"
PROJECT_TAG = "project"


def register(app, surface: wiring.Surface) -> None:
    """Mount the versioned read surface over this wiring."""
    app.include_router(_router(surface))


def _router(surface: wiring.Surface) -> APIRouter:
    router = APIRouter(prefix=PREFIX)

    @router.get("/projects/{project}/assets", tags=[ASSETS_TAG])
    async def list_assets(
        project: str,
        request: Request,
        page: str | None = None,
        page_size: int | None = None,
        status: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
    ) -> JSONResponse:
        """The project's assets under every filter that was given, one page at a time."""
        return routing.answered(
            surface,
            request,
            project,
            Operation.READ_PROJECT,
            lambda container: container.list_assets(status=status, owner=owner, tag=tag),
            paging=routing.paged(_rows, payloads.asset_row, token=page, size=page_size),
            index=IndexRead.EXHAUSTIVE,
        )

    @router.get("/projects/{project}/assets/{asset}", tags=[ASSETS_TAG])
    async def read_asset(
        project: str, asset: str, request: Request, lens: str | None = None
    ) -> JSONResponse:
        """One asset's specification, projected for a discipline when one is named."""
        return routing.answered(
            surface,
            request,
            project,
            Operation.READ_PROJECT,
            lambda container: container.asset_spec(asset, lens),
            payloads.lensed,
        )

    @router.get("/projects/{project}/assets/{asset}/briefing", tags=[ASSETS_TAG])
    async def read_briefing(project: str, asset: str, request: Request) -> JSONResponse:
        """The compiled briefing for one asset — the same text `canon compile` writes."""
        return routing.answered(
            surface,
            request,
            project,
            Operation.COMPILE_SPEC,
            lambda container: _briefing(container, asset),
            payloads.compiled,
        )

    @router.get("/projects/{project}/assets/{asset}/locations", tags=[ASSETS_TAG])
    async def read_locations(project: str, asset: str, request: Request) -> JSONResponse:
        """Where every artifact of one asset lives, with the unrecorded ones named."""
        return routing.answered(
            surface,
            request,
            project,
            Operation.LOOKUP_ASSET,
            lambda container: container.where_is(asset),
            payloads.lookup,
            index=IndexRead.ENTRY,
        )

    @router.get("/projects/{project}/search", tags=[PROJECT_TAG])
    async def search(
        project: str,
        request: Request,
        q: str = "",
        page: str | None = None,
        page_size: int | None = None,
    ) -> JSONResponse:
        """The ranked cascade, plus the delegated half when the gate opens.

        The page carries the exact group, in the order the local cascade
        produced it and in no other: this surface applies no ranking of its
        own, and a semantic passage is never one of its items. The approximate
        group travels beside the page, labelled, with the reason when it is not
        there — and a request carrying no bearer credential gets the local
        answer with the semantic half reported unavailable for lack of
        authority, because the alternative is asking the document platform a
        question under somebody else's name.
        """
        return routing.answered(
            surface,
            request,
            project,
            Operation.SEARCH_ASSETS,
            lambda container: container.search_assets_and_docs(
                q, credential=wiring.forwarded(request)
            ),
            paging=routing.paged(_hits, _hit, token=page, size=page_size),
            beside=payloads.semantic_group,
            index=IndexRead.EXHAUSTIVE,
        )

    @router.get("/projects/{project}/briefing", tags=[PROJECT_TAG])
    async def read_project_briefing(project: str, request: Request) -> JSONResponse:
        """The project's standing rules, with no asset in them."""
        return routing.answered(
            surface,
            request,
            project,
            Operation.COMPILE_SPEC,
            lambda container: container.compile_project_briefing(),
            payloads.project_briefing,
        )

    @router.get("/projects/{project}/validations", tags=[PROJECT_TAG])
    async def validate(project: str, request: Request, export: str = "") -> JSONResponse:
        """One export in the repository, against its governing specification."""
        return routing.answered(
            surface,
            request,
            project,
            Operation.VALIDATE_EXPORT,
            lambda container: container.validate_export(export),
            payloads.validation,
        )

    return router


def _briefing(container, asset: str) -> Result[CompiledSpec]:
    """The asset's specification file, then its briefing. Two use cases, in order.

    The identifier is what the address carries and the compiler takes a path, so
    something has to turn one into the other. That something is
    `spec_path_for`, which is the same lookup `canon compile mech_scout`
    performs — not a path this surface derives, which would be a second opinion
    about where a specification lives.
    """
    path = container.spec_path_for(asset)
    if not isinstance(path, Ok):
        return path
    return container.compile_spec(path.value)


def _rows(listing: AssetListing) -> tuple:
    """A listing in its total order: by the identifier the specification uses.

    Sorted here rather than trusted from the index, because paging's
    exactly-once guarantee needs an order that cannot change between two
    requests, and an index is entitled to return rows in whatever order is
    cheapest for it.
    """
    return tuple(sorted(listing.rows, key=lambda row: row.asset_id))


def _hits(answer: DelegatedSearch) -> tuple:
    """The exact group, in the cascade's order: that ordering *is* the ranking."""
    return answer.exact


def _hit(hit) -> dict:
    """One exact result — the pass that found it, and where it came from (D6)."""
    return {
        "asset": hit.asset_id,
        "name": hit.name,
        "matched": hit.matched.value,
        "provenance": str(hit.provenance),
    }


__all__ = ["ASSETS_TAG", "PROJECT_TAG", "register"]
