"""Raising, assigning and deciding an asset request — as repository content (D7).

D7 is the decision this module implements and the reason it looks the way it
does: *"One file per request, under the project's `.canon/` directory, with its
state history in the file. Every transition is a commit."* A requests table in
the index would be faster and obvious, and it would make the database
authoritative for a class of content, which is precisely the decision
`project.md` forbids.

So every operation here is the same three steps — decide in the domain, render
the whole request, write it back through
:func:`~cybercanon.application.use_cases.hosted_repository.write_back` — and
each produces exactly one commit, authored by the acting person through the
actors mapping (D8). Nothing is written anywhere else, which is what makes the
index-rebuild guarantee hold for requests without a single line about rebuilding
them.

**The document is JSON, and that is a choice the specifications leave open.** A
request file is machine-written workflow state, not human-authored specification
content: nobody diffs it for design intent, and D7 accepts its churn on exactly
that basis. JSON is in the standard library, renders deterministically with
sorted keys, and keeps the YAML reader — which is an adapter's — out of the
application. `asset.yaml` is unaffected and stays YAML, because it is the thing
a contractor reads.

Notification is best-effort by requirement, never by accident: every use case
records one through :func:`~cybercanon.application.ports.notifier.notify_quietly`
*after* the commit has landed, and a notifier that is down changes no outcome.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.notifier import Notification, Notifier, notify_quietly
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.hosted_repository import Edit, write_back
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import AssetId
from cybercanon.domain.identity import ActorId
from cybercanon.domain.requests import (
    AssetRequest,
    Discipline,
    EventKind,
    RefusalKind,
    RequestEvent,
    RequestId,
    RequestState,
    may_transition,
    reassign,
    transition,
)
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.status import Status

REQUESTS_DIR = ".canon/requests"
"""Where a project's requests live — beside its other machine-written state."""

DOCUMENT_VERSION = 1
"""Bumped only by a change that cannot be read by the previous reader."""


def path_for(request_id: RequestId) -> str:
    """The one file this request lives in, for its whole life (D7)."""
    return f"{REQUESTS_DIR}/{request_id}.json"


class RequestRejected(OperationFailed):
    """A domain refusal on its way out, carrying the kind the domain gave it.

    The domain answers with a
    :class:`~cybercanon.domain.requests.TransitionDecision` that already knows
    whether it is an invalid input, a permission refusal or a lifecycle
    conflict; this carries that distinction to the surface without the surface
    learning anything about requests, and without the domain learning anything
    about status codes (D10).
    """

    identifier = "request.rejected"

    def __init__(self, subject: str, reason: str, kind: FailureKind) -> None:
        super().__init__(reason, subject)
        self.kind = kind  # type: ignore[misc]


class RequestUnreadable(OperationFailed):
    """The stored request cannot be read back — a file somebody hand-edited."""

    kind = FailureKind.INVALID
    identifier = "request.unreadable"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path} could not be read as a request: {reason}", path)
        self.reason = reason


class RequestNotFound(OperationFailed):
    """No request with that identifier is recorded in this project."""

    kind = FailureKind.NOT_FOUND
    identifier = "request.not_found"

    def __init__(self, project: str, request_id: str) -> None:
        super().__init__(f"no request {request_id!r} is recorded in {project!r}", request_id)


_KINDS = {
    RefusalKind.INVALID: FailureKind.INVALID,
    RefusalKind.FORBIDDEN: FailureKind.FORBIDDEN,
    RefusalKind.CONFLICT: FailureKind.CONFLICT,
}
"""The domain's refusal kinds, in the vocabulary every surface translates."""


@dataclass(frozen=True)
class RecordedRequest:
    """A request as it now stands, and the commit that recorded it."""

    request: AssetRequest
    revision: str
    path: str

    @property
    def id(self) -> RequestId:
        return self.request.id


@as_result
def raise_request(
    project: str,
    request: AssetRequest,
    *,
    repository_host: RepositoryHost,
    author: GitAuthor | None,
    notifier: Notifier | None = None,
    clock: Clock = system_clock,
) -> RecordedRequest:
    """Record a new request as one commit, and tell its assignee.

    The request arrives already built — the domain decides what a valid one is,
    who it is assigned to and what its first history entry says — so this does
    the part the domain cannot: write it where it survives an index rebuild.

    A request whose commit does not land *did not happen*: nothing is written
    anywhere else, so there is no listing it could appear in and the refusal is
    what its author is told.
    """
    return _record(
        project,
        request,
        repository_host=repository_host,
        author=author,
        notifier=notifier,
        clock=clock,
        based_on=None,
        message=_message(request, "raised"),
        summary=f"{request.author} asked for {request.description}",
    )


@as_result
def assign_request(
    project: str,
    request_id: RequestId,
    assignee: ActorId | None,
    *,
    actor: ActorId,
    repository_host: RepositoryHost,
    author: GitAuthor | None,
    notifier: Notifier | None = None,
    clock: Clock = system_clock,
) -> RecordedRequest:
    """Reassign a request, recording who did it and when (`asset-requests`)."""
    at = clock()
    current, based_on = _load(project, request_id, repository_host)
    moved = reassign(current, assignee, actor=actor, at=at)
    return _record(
        project,
        moved,
        repository_host=repository_host,
        author=author,
        notifier=notifier,
        clock=lambda: at,
        based_on=based_on,
        message=_message(moved, f"assigned to {assignee or 'nobody'}"),
        summary=f"{actor} assigned {moved.id} to {assignee or 'nobody'}",
    )


@as_result
def transition_request(
    project: str,
    request_id: RequestId,
    to: RequestState,
    *,
    actor: ActorId,
    repository_host: RepositoryHost,
    author: GitAuthor | None,
    reason: str = "",
    asset_status: Status | None = None,
    notifier: Notifier | None = None,
    clock: Clock = system_clock,
) -> RecordedRequest:
    """Move a request through its lifecycle, one commit per transition (D7).

    The domain decides whether the move is permitted — the table, the stated
    reason, the author-only withdrawal, the asked-for status — and this
    translates its refusal into the outcome vocabulary without re-deciding any
    of it. Nothing about the referenced asset is written, because a request
    observes the asset lifecycle and never drives it.
    """
    at = clock()
    current, based_on = _load(project, request_id, repository_host)
    decision = may_transition(current, to, actor=actor, reason=reason, asset_status=asset_status)
    if decision.refused:
        raise RequestRejected(
            str(request_id), decision.reason, _KINDS[decision.kind or RefusalKind.CONFLICT]
        )
    moved = transition(current, to, actor=actor, at=at, reason=reason, asset_status=asset_status)
    return _record(
        project,
        moved,
        repository_host=repository_host,
        author=author,
        notifier=notifier,
        clock=lambda: at,
        based_on=based_on,
        message=_message(moved, str(to)),
        summary=f"{actor} marked {moved.id} {to}",
    )


@as_result
def read_request(
    project: str,
    request_id: RequestId,
    *,
    repository_host: RepositoryHost,
) -> AssetRequest:
    """One request as the repository holds it — the only place it is held."""
    return _load(project, request_id, repository_host)[0]


def _record(
    project: str,
    request: AssetRequest,
    *,
    repository_host: RepositoryHost,
    author: GitAuthor | None,
    notifier: Notifier | None,
    clock: Clock,
    based_on: ContentHash | None,
    message: str,
    summary: str,
) -> RecordedRequest:
    """The shared half of all three: one file, one commit, then a notification."""
    path = path_for(request.id)
    written = write_back.raising(
        project,
        [Edit(path=path, content=to_document(request), based_on=based_on)],
        repository_host=repository_host,
        author=author,
        message=message,
        subject=str(request.author),
    )
    _tell(notifier, request, summary, clock())
    return RecordedRequest(request=request, revision=written.revision.value, path=path)


def _tell(notifier: Notifier | None, request: AssetRequest, summary: str, at: datetime) -> None:
    """Tell the assignee and the author, and never let it change the outcome (D9)."""
    for recipient in {request.assignee, request.author} - {None}:
        assert recipient is not None
        notify_quietly(
            notifier,
            Notification(recipient=recipient, subject=str(request.id), summary=summary, at=at),
        )


def _load(
    project: str, request_id: RequestId, repository_host: RepositoryHost
) -> tuple[AssetRequest, ContentHash]:
    """The stored request and the digest an edit to it must be composed against."""
    path = path_for(request_id)
    content = repository_host.read(project, path, repository_host.head(project))
    if content is None:
        raise RequestNotFound(project, str(request_id))
    return from_document(content, path), ContentHash.of(content)


def _message(request: AssetRequest, what: str) -> str:
    """What the commit says: the request, the asset it concerns, what changed."""
    about = f" for {request.asset}" if request.asset is not None else ""
    return f"request {request.id}{about}: {what}"


# --------------------------------------------------------------------------
# The document (D7)
# --------------------------------------------------------------------------


def to_document(request: AssetRequest) -> bytes:
    """One request as the bytes committed to its file.

    Deterministic by construction — sorted keys, a fixed indent, a trailing
    newline — because a renderer that reordered fields would produce a diff on
    every transition and make the history unreadable for the one thing it is
    good for, which is seeing what changed.
    """
    document = {
        "schema_version": DOCUMENT_VERSION,
        "id": str(request.id),
        "author": str(request.author),
        "discipline": str(request.discipline),
        "description": request.description,
        "asset": str(request.asset) if request.asset is not None else None,
        "asked_for_status": (
            str(request.asked_for_status) if request.asked_for_status is not None else None
        ),
        "assignee": str(request.assignee) if request.assignee is not None else None,
        "state": str(request.state),
        "history": [_event_document(event) for event in request.history],
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def from_document(content: bytes, path: str = "") -> AssetRequest:
    """The request those bytes hold, or a named failure.

    The round trip is asserted rather than assumed: `to_document` then
    `from_document` is the whole of the index-rebuild guarantee for requests, so
    a field that does not survive it is a state, an assignee or an attribution
    that a rebuild would lose.
    """
    try:
        return _parsed(json.loads(content.decode("utf-8")))
    except (ValueError, KeyError, TypeError) as failure:
        raise RequestUnreadable(path, str(failure) or type(failure).__name__) from failure


def _parsed(document: dict[str, object]) -> AssetRequest:
    return AssetRequest(
        id=RequestId(str(document["id"])),
        author=ActorId(str(document["author"])),
        discipline=_required(Discipline.from_value(str(document["discipline"])), "discipline"),
        description=str(document["description"]),
        asset=_optional(document.get("asset"), AssetId),
        asked_for_status=_status(document.get("asked_for_status")),
        assignee=_optional(document.get("assignee"), ActorId),
        state=_required(RequestState.from_value(str(document["state"])), "state"),
        history=tuple(_event(entry) for entry in document.get("history", [])),  # type: ignore[union-attr]
    )


def _event_document(event: RequestEvent) -> dict[str, object]:
    return {
        "kind": str(event.kind),
        "actor": str(event.actor),
        "at": event.at.isoformat(),
        "state": str(event.state) if event.state is not None else None,
        "assignee": str(event.assignee) if event.assignee is not None else None,
        "reason": event.reason,
    }


def _event(entry: dict[str, object]) -> RequestEvent:
    return RequestEvent(
        kind=EventKind(str(entry["kind"])),
        actor=ActorId(str(entry["actor"])),
        at=datetime.fromisoformat(str(entry["at"])),
        state=_required_state(entry.get("state")),
        assignee=_optional(entry.get("assignee"), ActorId),
        reason=str(entry.get("reason") or ""),
    )


def _required[T](value: T | None, field: str) -> T:
    if value is None:
        raise ValueError(f"{field} is not one of the values this version knows")
    return value


def _required_state(value: object) -> RequestState | None:
    return RequestState.from_value(str(value)) if value is not None else None


def _status(value: object) -> Status | None:
    return Status.from_value(str(value)) if value is not None else None


def _optional[T](value: object, build: type[T]) -> T | None:
    return build(str(value)) if value is not None else None  # type: ignore[call-arg]


__all__ = [
    "DOCUMENT_VERSION",
    "REQUESTS_DIR",
    "RecordedRequest",
    "RequestNotFound",
    "RequestRejected",
    "RequestUnreadable",
    "assign_request",
    "from_document",
    "path_for",
    "raise_request",
    "read_request",
    "to_document",
    "transition_request",
]
