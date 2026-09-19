"""The explicit version, and the refusal to guess one (task 9.1).

`http-api`: *"The HTTP surface SHALL carry an explicit version"*, and *"a
request ... without an identifiable surface version ... SHALL be rejected as
invalid rather than served by a guessed version"*.

The version is the first path segment, and that choice is the whole design:

* **it is impossible to omit by accident.** A version carried in a header or a
  media type is one a client forgets, a proxy strips and a `curl` in a bug
  report never has — and the specified behaviour for a request with no version
  is a refusal, so every one of those becomes a support conversation;
* **it is visible in a log line and a bookmark**, which is what makes "a client
  written against a version keeps working while that version is served" a claim
  somebody can check rather than believe.

Within a version the surface only *adds* — optional fields, endpoints,
enumerated values — so the shape a client reads never narrows underneath it.
Removing or renaming a field takes a new segment beside this one, which is why
:data:`SERVED` is a set rather than a constant: the day `v2` exists, `v1` keeps
answering from the same application.

A request that names no served version is **invalid rather than not found**, and
that distinction is deliberate: *not found* would tell a client its resource is
gone when what is wrong is the address it asked with.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import outcomes
from cybercanon.application.results import Invalid, NotFound

VERSION = "v1"
"""The version this build serves and stamps on every response."""

SERVED: frozenset[str] = frozenset({VERSION})
"""Every version still answered. It only ever grows, and never in place."""

PREFIX = f"/{VERSION}"
"""Where the versioned surface is mounted."""

UNVERSIONED_IDENTIFIER = "surface.unversioned"
NOT_FOUND_IDENTIFIER = "surface.no_such_resource"

RESERVED: tuple[str, ...] = ("health", "hooks", "openapi.json", "docs", "redoc")
"""Paths that are deliberately outside the versioned surface.

Liveness and readiness are read by a deployment platform that knows nothing
about our versions and must keep working across every one of them; the
repository notification endpoint is an inbound hint from a third party whose
payload shape we do not control (see :mod:`~cybercanon.adapters.inbound.http.webhooks`);
and the generated interface description is how a client discovers the versions.
"""


def first_segment(path: str) -> str:
    """The first segment of a request path, or an empty string for the root."""
    return path.strip("/").split("/", 1)[0]


def names_a_served_version(path: str, served: frozenset[str] = SERVED) -> bool:
    """Whether this path identifies a version this build answers."""
    return first_segment(path) in served


def unversioned(path: str) -> Invalid:
    """The refusal a request with no identifiable version gets, naming the fix."""
    return Invalid(
        identifier=UNVERSIONED_IDENTIFIER,
        message=(
            f"{path!r} names no surface version; address this surface under "
            f"/{'|/'.join(sorted(SERVED))} — no version is assumed, because a "
            "guessed one is a client silently moving to a shape it was not written against"
        ),
        subject=path,
    )


def no_such_resource(path: str) -> NotFound:
    """The refusal for an address inside a served version that names nothing."""
    return NotFound(
        identifier=NOT_FOUND_IDENTIFIER,
        message=f"{path!r} is not a resource this surface serves",
        subject=path,
    )


def is_reserved(path: str) -> bool:
    """Whether this address is one of the deliberately unversioned ones."""
    return first_segment(path) in set(RESERVED)


def refusal_for(path: str) -> Invalid | NotFound:
    """Which of the two an unmatched address deserves.

    Inside a served version, or under one of the reserved roots, the address is
    simply wrong and that is a not-found. Anywhere else the *version* is
    missing, which is invalid. Answering both with 404 would hide a client that
    never sent a version at all; answering both with 400 would tell a
    deployment platform that `/health/typo` was a versioning mistake.
    """
    if names_a_served_version(path) or is_reserved(path):
        return no_such_resource(path)
    return unversioned(path)


def register(app: FastAPI) -> None:
    """Catch every address nothing else matched, and say which kind of wrong it is.

    Registered last, so it only ever sees what no route claimed. FastAPI would
    otherwise answer a bare `/projects/...` with its own 404, which is the
    *guess* the specification refuses: a client that forgot the version would
    read "no such project" and go looking for the project.
    """

    @app.api_route(
        "/{unmatched:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def unmatched_address(unmatched: str, request: Request) -> JSONResponse:
        """One refusal, through the one seam, like every other outcome."""
        return outcomes.respond(refusal_for(request.url.path), version=VERSION)


__all__ = [
    "NOT_FOUND_IDENTIFIER",
    "PREFIX",
    "RESERVED",
    "SERVED",
    "UNVERSIONED_IDENTIFIER",
    "VERSION",
    "first_segment",
    "is_reserved",
    "names_a_served_version",
    "no_such_resource",
    "refusal_for",
    "register",
    "unversioned",
]
