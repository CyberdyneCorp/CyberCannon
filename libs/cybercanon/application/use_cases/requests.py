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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.dismissals import Dismissal, Dismissals
from cybercanon.application.ports.notifier import Notification, Notifier, notify_quietly
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.results import Ok, Result, as_result
from cybercanon.application.use_cases.hosted_repository import Edit, write_back
from cybercanon.domain.actors import ActorMapping, GitAuthor, resolve_git_author
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.identity import ActorId
from cybercanon.domain.requests import (
    NO_OWNERS,
    AssetRequest,
    Discipline,
    DisciplineOwners,
    EventKind,
    RefusalKind,
    RequestEvent,
    RequestId,
    RequestState,
    assignee_for,
    may_transition,
    owners_declared_by,
    reassign,
    transition,
)
from cybercanon.domain.requests import raise_request as build_request
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


class RequestInvalid(OperationFailed):
    """The described request is not one — an empty description, above all.

    The domain refuses it by refusing to construct: *"a request with nothing in
    it is not a request in a refused state, it is not a request"*. That refusal
    arrives as a :class:`ValueError`, which is the domain's vocabulary, and this
    is where it becomes the outcome vocabulary every surface translates (D10) —
    so *"it SHALL be rejected as invalid"* holds over HTTP without the domain
    learning what a status code is.
    """

    kind = FailureKind.INVALID
    identifier = "request.invalid"

    def __init__(self, subject: str, reason: str) -> None:
        super().__init__(reason, subject)


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


type Locate = Callable[[str], Result[str]]
"""How an asset identifier becomes the path of the file that declares it.

The lookup the command line performs, handed in rather than repeated: a module
that derived a specification path from an identifier would be a second opinion
about where a specification lives.
"""


@dataclass(frozen=True)
class RequestContext:
    """One request and the two facts a decision about it needs beside it.

    Both extras come from the asset the request references, and both are read
    and never written: `discipline_owner` is who policy compares the acting
    actor against, and `asset_status` is what the fulfilment precondition is
    evaluated against. A request that references no asset has neither, which is
    the ordinary case for *something that does not exist yet*.
    """

    request: AssetRequest
    discipline_owner: ActorId | None = None
    asset_status: Status | None = None


def discipline_owners(asset: Asset, mapping: ActorMapping) -> DisciplineOwners:
    """The owners an asset declares, as actors, through `.canon/actors.yaml` (D8).

    An owner the mapping does not bind resolves to nobody rather than to a
    guess, which is the same answer as declaring none — and the answer D8
    requires, since assigning a request to an address nobody can be reached at
    would be worse than reporting that it needs an owner.
    """
    return owners_declared_by(asset, _resolvable(asset, mapping))


def _resolvable(asset: Asset, mapping: ActorMapping) -> dict[str, ActorId]:
    """The declared addresses that name somebody, as the subjects they name."""
    declared = (asset.owner_art, asset.owner_design, asset.owner_code)
    resolved = ((address, resolve_git_author(mapping, address)) for address in declared if address)
    return {address: actor.id for address, actor in resolved if not actor.is_unmapped}


@as_result
def compose_request(
    project: str,
    request_id: RequestId,
    *,
    author: ActorId,
    discipline: Discipline,
    description: str,
    at: datetime,
    asset: AssetId | None = None,
    asked_for_status: Status | None = None,
    spec_store: SpecStore | None = None,
    locate: Locate | None = None,
) -> AssetRequest:
    """The request a surface's arguments describe, assigned by the domain cascade.

    Composition is here rather than in an inbound adapter because it is two
    domain decisions — who owns this discipline, and therefore who this is
    assigned to — and an adapter that made them would be the second
    implementation this change exists not to grow. What the adapter supplies is
    only what it read off the request: the discipline, the words, the asset.

    A project-level owner would be the second step of the cascade; the file that
    declares one is an open question in `design.md`, so today an asset with no
    owner for the discipline yields an unassigned request *reported as needing
    an owner*, which is exactly what `asset-requests` specifies for the case
    where no owner can be determined.
    """
    owners = _owners_of(asset, spec_store=spec_store, locate=locate)
    try:
        return build_request(
            request_id,
            author=author,
            discipline=discipline,
            description=description,
            at=at,
            asset=asset,
            asked_for_status=asked_for_status,
            assignee=assignee_for(discipline, on_asset=owners, author=author),
        )
    except ValueError as rejected:
        raise RequestInvalid(str(request_id), str(rejected)) from rejected


@as_result
def request_context(
    project: str,
    request_id: RequestId,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore | None = None,
    locate: Locate | None = None,
) -> RequestContext:
    """One request, with the owner and the asset status a decision needs.

    The asset is read only when the request asked for a status, because that is
    the only thing the status is needed for and a request whose asset was
    deleted should still be declinable.
    """
    request = _load(project, request_id, repository_host)[0]
    owners = _owners_of(request.asset, spec_store=spec_store, locate=locate)
    return RequestContext(
        request=request,
        discipline_owner=owners.owner_of(request.discipline),
        asset_status=_asked_status(request, spec_store=spec_store, locate=locate),
    )


def _owners_of(
    asset: AssetId | None,
    *,
    spec_store: SpecStore | None,
    locate: Locate | None,
) -> DisciplineOwners:
    """Who owns each discipline on that asset, or nobody when there is no asset."""
    loaded = _loaded(asset, spec_store=spec_store, locate=locate)
    if loaded is None:
        return NO_OWNERS
    return discipline_owners(loaded, spec_store.load_actor_mapping().mapping)  # type: ignore[union-attr]


def _asked_status(
    request: AssetRequest,
    *,
    spec_store: SpecStore | None,
    locate: Locate | None,
) -> Status | None:
    """The referenced asset's current lifecycle position, when one is asked for."""
    if request.asked_for_status is None:
        return None
    loaded = _loaded(request.asset, spec_store=spec_store, locate=locate)
    return loaded.status if loaded is not None else None


def _loaded(
    asset: AssetId | None,
    *,
    spec_store: SpecStore | None,
    locate: Locate | None,
) -> Asset | None:
    """The specification that declares that asset, or ``None`` when there is none."""
    if asset is None or spec_store is None or locate is None:
        return None
    path = locate(str(asset))
    if not isinstance(path, Ok):
        return None
    return spec_store.load(path.value).asset


@dataclass(frozen=True)
class UnreadableRequest:
    """A request file that would not parse, named rather than skipped in silence."""

    path: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


@dataclass(frozen=True)
class RequestListing:
    """Every request a project holds at one revision, and what would not read.

    The unreadable files travel beside the requests for the same reason a
    listing of assets carries them: a request somebody hand-edited into invalid
    JSON is a thing to fix, and dropping it silently would make a listing that
    is quietly short indistinguishable from a project that is quietly small.
    """

    project: str
    requests: tuple[AssetRequest, ...] = ()
    unreadable: tuple[UnreadableRequest, ...] = ()

    @property
    def ids(self) -> tuple[RequestId, ...]:
        return tuple(request.id for request in self.requests)


@dataclass(frozen=True)
class UnreadItems:
    """What one person has not yet looked at, derived and never stored (D9).

    There is no notification entity: this is a query over the project's
    requests, narrowed to the ones where this person is the assignee or the
    author, minus the ones they have dismissed. `count` is beside `items`
    because `asset-requests` requires notification to be *countable*, and a
    caller that counted a page would count the page.
    """

    project: str
    actor: ActorId
    items: tuple[AssetRequest, ...] = ()

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class Dismissed:
    """One person saying they have seen one item. Index state, and losable (D9)."""

    project: str
    actor: ActorId
    request_id: RequestId
    at: datetime


@as_result
def list_requests(
    project: str,
    *,
    repository_host: RepositoryHost,
) -> RequestListing:
    """Every request in the project, read from the repository at one revision.

    There is no index row to read instead, and that is D7 working rather than a
    gap: requests are repository content, so the listing is a tree listing at
    the served revision followed by one read per file. Every answer therefore
    survives the index being dropped, because the index was never asked.
    """
    revision = repository_host.head(project)
    paths = [
        path
        for path in repository_host.paths_at(project, revision)
        if path.startswith(f"{REQUESTS_DIR}/") and path.endswith(".json")
    ]
    read = [(path, repository_host.read(project, path, revision)) for path in paths]
    return _listed(project, [(path, content) for path, content in read if content is not None])


def _listed(project: str, files: Sequence[tuple[str, bytes]]) -> RequestListing:
    """The requests those files hold, and the ones that would not parse."""
    requests: list[AssetRequest] = []
    unreadable: list[UnreadableRequest] = []
    for path, content in files:
        try:
            requests.append(from_document(content, path))
        except RequestUnreadable as failure:
            unreadable.append(UnreadableRequest(path=path, reason=failure.reason))
    return RequestListing(
        project=project,
        requests=tuple(sorted(requests, key=lambda request: str(request.id))),
        unreadable=tuple(unreadable),
    )


def concerns(request: AssetRequest, actor: ActorId) -> bool:
    """Whether this person is one of the two `asset-requests` names.

    *"that person and the request's author SHALL be able to see it as an unread
    item"* — the assignee and the author, and nobody else. A watcher list would
    be a notification entity, which D9 says there is not.
    """
    return actor in (request.assignee, request.author)


@as_result
def unread_items(
    project: str,
    actor: ActorId,
    *,
    repository_host: RepositoryHost,
    dismissals: Dismissals,
) -> UnreadItems:
    """This person's unread items: a derived query minus their dismissals (D9).

    Nothing is stored to answer this, which is the whole of D9. The requests
    come from the repository and the dismissals from the index, and the two are
    combined here rather than in a table, so an index rebuild costs a person
    their dismissals and never an item.
    """
    listing = list_requests.raising(project, repository_host=repository_host)
    dismissed = dismissals.dismissed_by(actor, project)
    return UnreadItems(
        project=project,
        actor=actor,
        items=tuple(
            request
            for request in listing.requests
            if concerns(request, actor) and str(request.id) not in dismissed
        ),
    )


@as_result
def dismiss_item(
    project: str,
    actor: ActorId,
    request_id: RequestId,
    *,
    repository_host: RepositoryHost,
    dismissals: Dismissals,
    clock: Clock = system_clock,
) -> Dismissed:
    """Mark one item as seen by one person, and by nobody else (D9).

    The request is read first so that dismissing something that does not exist
    is a not-found rather than a flag nobody will ever look at again. Nothing is
    committed: a read receipt in git would be a commit per glance, in a history
    that is supposed to be worth reading.
    """
    _load(project, request_id, repository_host)
    at = clock()
    dismissals.dismiss(Dismissal(project=project, actor=actor, subject=str(request_id), at=at))
    return Dismissed(project=project, actor=actor, request_id=request_id, at=at)


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
    "Dismissed",
    "Locate",
    "RecordedRequest",
    "RequestContext",
    "RequestInvalid",
    "RequestListing",
    "RequestNotFound",
    "RequestRejected",
    "RequestUnreadable",
    "UnreadItems",
    "UnreadableRequest",
    "assign_request",
    "compose_request",
    "concerns",
    "discipline_owners",
    "dismiss_item",
    "from_document",
    "list_requests",
    "path_for",
    "raise_request",
    "read_request",
    "request_context",
    "to_document",
    "transition_request",
    "unread_items",
]
