"""Writing a specification back: the revision it was based on, and one commit.

Three requirements meet in this module and none of them is invented here.

* `http-api`: *"A request that modifies specification content SHALL carry the
  revision identifier of the content it was composed against"*, and a request
  that omits it *"SHALL be rejected as invalid"*.
* D5: the precondition that actually **decides** is the per-file content hash,
  not the branch tip. *"The natural precondition is the branch tip, and it is
  wrong: any unrelated commit anywhere in the repository would then conflict
  with every in-flight edit."* So the declared revision is what the edit was
  composed from and what a conflict reports back; `based_on` is what is
  compared.
* G4: *"Author durable content as an agent — nobody — refused for every role."*
  A specification file is durable content by definition, so the authorization
  here is :func:`~cybercanon.domain.authorization.may_author_durable_content`
  over the actor, plus D8's requirement that the person have a git identity. A
  write with no mapped author is refused **naming the missing entry**, because
  committing as a shared identity is how `git blame` stops answering the
  question the tool exists to answer.

**What this module deliberately does not decide.** Which *role* may edit which
part of a specification is gate G3 (`ROADMAP.md`), still open and needed by S16;
nothing here anticipates it. What is enforced is what the specs already fix: the
tenant, the read entitlement, the refusal of automated authorship, the mapped
git identity, the per-file precondition and the idempotency key. A role rule
arrives as an entry in :mod:`cybercanon.domain.policy`, and this module will not
change when it does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import outcomes, payloads, routing
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.adapters.inbound.http.versioning import PREFIX, VERSION
from cybercanon.application.results import Forbidden, Invalid, Ok, Result, Unavailable
from cybercanon.application.use_cases.authenticate import Authenticated
from cybercanon.application.use_cases.hosted_repository import (
    Edit,
    WriteOutcome,
    author_for,
    edit_message,
    write_back,
)
from cybercanon.application.use_cases.resolve_actor import verified_as
from cybercanon.domain.authorization import may_author_durable_content
from cybercanon.domain.identity import Actor
from cybercanon.domain.policy import Operation
from cybercanon.domain.revisions import ContentHash

SPECS_TAG = "specifications"

REVISION_FIELD = "revision"
CONTENT_FIELD = "content"
BASED_ON_FIELD = "based_on"
SUMMARY_FIELD = "summary"
AGENT_FIELD = "agent"

UNREADABLE = "edit.unreadable"
REVISION_MISSING = "edit.revision_missing"
CONTENT_MISSING = "edit.content_missing"
AUTHORSHIP_REFUSED = "edit.automated_authorship"
NO_WORKING_COPY_IDENTIFIER = "project.no_working_copy"

NO_REVISION = (
    "a specification-modifying request must declare the revision it was composed "
    "against; send it as `revision`, taken from the read that produced the content"
)

DEFAULT_SUMMARY = "specification updated"


def register(app, surface: wiring.Surface) -> None:
    """Mount the versioned write surface over this wiring."""
    app.include_router(_router(surface))


def _router(surface: wiring.Surface) -> APIRouter:
    router = APIRouter(prefix=PREFIX)

    @router.put("/projects/{project}/assets/{asset}/spec", tags=[SPECS_TAG])
    async def write_spec(project: str, asset: str, request: Request) -> JSONResponse:
        """One asset's specification file, replaced as one attributed commit."""
        return _written(surface, request, project, asset, await request.body())

    return router


def _written(
    surface: wiring.Surface,
    request: Request,
    project: str,
    asset: str,
    body: bytes,
) -> JSONResponse:
    """The whole write, and the revision its precondition was evaluated against.

    The envelope's `revision` is the head the edit was compared with, taken
    before the attempt and carried whether the attempt succeeded or not. That is
    what makes *"the response SHALL name the current revision"* true for a
    conflict through the same code path as a success, with nothing deciding when
    to include it — and on a success the commit's own revision travels in
    `data`, so the two questions a caller has (*what did I race*, *what did I
    produce*) have distinct answers rather than one ambiguous field.
    """
    prepared = routing.prepared_for(surface, request, project, Operation.READ_PROJECT)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    _, freshness = wiring.at_revision(hosted, _nothing, clock=surface.clock)
    result = _apply(surface, hosted, actor, asset, body, wiring.idempotency_key(request))
    return outcomes.respond(result, version=VERSION, extra=wiring.freshness_fields(freshness))


def _nothing(container: Any) -> Result[None]:
    """A read that reads nothing: the revision is the answer being asked for."""
    return Ok(None)


def _apply(
    surface: wiring.Surface,
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    body: bytes,
    key: str,
) -> Result[Any]:
    """Authorize the authorship, read the edit, and write it back at most once."""
    refusal = authorship(actor.actor)
    if refusal is not None:
        return refusal
    proposed = read_edit(body)
    if not isinstance(proposed, Ok):
        return proposed
    prepared = _target(hosted, asset)
    if not isinstance(prepared, Ok):
        return prepared
    return routing.applied(
        surface,
        key,
        body,
        _write(hosted, actor, asset, prepared.value, proposed.value),
        payloads.written,
    )


def authorship(actor: Actor) -> Forbidden | None:
    """G4's last row: no automated caller authors durable specification content.

    Checked before the body is even read, because the refusal does not depend on
    what the body says and a caller that may not write should not learn whether
    its content would have been accepted.
    """
    decision = may_author_durable_content(actor)
    if decision.refused:
        return Forbidden(
            identifier=AUTHORSHIP_REFUSED, message=decision.reason, subject=actor.subject
        )
    return None


@dataclass(frozen=True)
class ProposedEdit:
    """One edit as the request stated it. A value, with nothing derived.

    `revision` is carried and reported; `based_on` is what decides (D5). Keeping
    both, rather than collapsing them, is the honest reading of two documents
    that ask for different things for different reasons.
    """

    revision: str
    content: str
    based_on: ContentHash | None = None
    summary: str = DEFAULT_SUMMARY
    agent: str = ""


def read_edit(body: bytes) -> Result[ProposedEdit]:
    """The edit this request carries, or the refusal that says what is missing.

    `based_on` absent means *the file did not exist when this was composed*,
    which is how a new specification is written without racing a second author
    who had the same idea (D5). It is therefore a meaningful absence rather than
    a missing field, and is the one thing here that is optional.
    """
    document = _document(body)
    if not isinstance(document, Ok):
        return document
    fields = document.value
    revision = str(fields.get(REVISION_FIELD, "")).strip()
    if not revision:
        return Invalid(identifier=REVISION_MISSING, message=NO_REVISION, subject=REVISION_FIELD)
    content = fields.get(CONTENT_FIELD)
    if not isinstance(content, str):
        return Invalid(
            identifier=CONTENT_MISSING,
            message="an edit must carry the specification content it proposes, as `content`",
            subject=CONTENT_FIELD,
        )
    return Ok(
        ProposedEdit(
            revision=revision,
            content=content,
            based_on=_hash(fields.get(BASED_ON_FIELD)),
            summary=str(fields.get(SUMMARY_FIELD, "") or DEFAULT_SUMMARY),
            agent=str(fields.get(AGENT_FIELD, "") or ""),
        )
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
        message="the request body is not a JSON object describing an edit",
        subject="body",
    )


def _hash(declared: Any) -> ContentHash | None:
    """The precondition this edit states, or ``None`` for *it did not exist*."""
    if not isinstance(declared, str) or not declared.strip():
        return None
    return ContentHash(declared.strip())


def _target(hosted: wiring.HostedProject, asset: str) -> Result[str]:
    """The specification file this asset is written in — the shared lookup, again."""
    if hosted.repository_host is None:
        return Unavailable(
            identifier=NO_WORKING_COPY_IDENTIFIER,
            message=(
                f"project {hosted.name!r} has no working copy wired, so nothing can "
                "be committed to it"
            ),
            subject=hosted.name,
        )
    return hosted.container.spec_path_for(asset)


def _write(
    hosted: wiring.HostedProject,
    actor: Authenticated,
    asset: str,
    path: str,
    proposed: ProposedEdit,
) -> routing.Write[WriteOutcome]:
    """The write itself, bound and ready to be run at most once (D11)."""
    identity = author_for(verified_as(actor.actor, actor.git_emails), hosted.container.spec_store)

    def run() -> Result[WriteOutcome]:
        return write_back(
            hosted.name,
            [Edit(path=path, content=proposed.content.encode("utf-8"), based_on=proposed.based_on)],
            repository_host=hosted.repository_host,
            author=identity.author,
            message=edit_message(asset, proposed.summary),
            subject=actor.subject,
            agent=proposed.agent,
        )

    return run


__all__ = [
    "AUTHORSHIP_REFUSED",
    "BASED_ON_FIELD",
    "CONTENT_FIELD",
    "CONTENT_MISSING",
    "NO_REVISION",
    "NO_WORKING_COPY_IDENTIFIER",
    "REVISION_FIELD",
    "REVISION_MISSING",
    "SPECS_TAG",
    "UNREADABLE",
    "ProposedEdit",
    "authorship",
    "read_edit",
    "register",
]
