"""Asset requests: an ask with an owner and an ending.

"Can somebody make me a crate for the loading dock" is a message that scrolls
away. `asset-requests` turns it into a tracked object with a discipline, an
assignee, a lifecycle and an attribution for every move — raised against an
asset that exists or one that does not yet, and **closed by a person rather than
by the asset's status changing underneath it**.

That last clause is the one with teeth, and it is structural here rather than
reviewed: nothing in this module returns an
:class:`~cybercanon.domain.asset.Asset` or a
:class:`~cybercanon.domain.status.Status`, and nothing in `asset.py` or
`status.py` knows this module exists. A request *observes* the asset lifecycle —
:func:`may_transition` reads the asset's current status when the request asked
for one — and it can never move it.

Three more properties the specification fixes:

* **Every state change is attributed and timed.** :class:`RequestEvent` has no
  default actor, for the same reason
  :class:`~cybercanon.domain.identity.Attribution` has none (D5): there is no
  constructor path that records a transition anonymously. `at` is a parameter
  rather than a clock read, because the domain does not read clocks — the
  application supplies one through its `Clock` port.
* **The transition table is data.** :data:`TRANSITIONS` is the whole lifecycle;
  a transition nobody listed is refused, `fulfilled → open` included.
* **Refusals say what kind of refusal they are.** :class:`RefusalKind` exists so
  that "you are not the author" and "that transition does not exist" reach an
  HTTP surface as different status classes without the domain knowing what a
  status class is (D10).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.identity import ActorId
from cybercanon.domain.status import Status

NEEDS_DESCRIPTION = "a request states what is needed"
"""Why an empty request is rejected, in the words the rejection uses."""

NEEDS_REASON = "a declined request states why"
"""`asset-requests`: *"a `declined` request SHALL carry a stated reason"*."""

AUTHOR_WITHDRAWS = "only the author of a request may withdraw it"
"""`asset-requests`: *"only the request's author SHALL be able to withdraw it"*."""

NEEDS_OWNER = "needs an owner"
"""How an unassigned request is reported, rather than being given to somebody."""


class Discipline(Enum):
    """The disciplines a request can concern — the same four the lenses use.

    Deliberately the lens vocabulary
    (:class:`~cybercanon.application.use_cases.spec_lens.Lens`) rather than a
    second one: a studio that says "modelling" when it filters a spec should say
    "modelling" when it asks for an asset, and two discipline vocabularies would
    drift the way four validators drift.
    """

    DESIGN = "design"
    ART = "art"
    MODELING = "modeling"
    CODE = "code"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Every accepted discipline, in declaration order — what a refusal names."""
        return tuple(member.value for member in cls)

    @classmethod
    def from_value(cls, value: str) -> Discipline | None:
        """The discipline this text names, or ``None`` when it names none."""
        return _DISCIPLINES_BY_VALUE.get(value.strip().lower())

    def __str__(self) -> str:
        return self.value


_DISCIPLINES_BY_VALUE = {member.value: member for member in Discipline}


class RequestState(Enum):
    """Where a request sits. Five states, three of them terminal."""

    OPEN = "open"
    ACCEPTED = "accepted"
    FULFILLED = "fulfilled"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"

    @property
    def is_terminal(self) -> bool:
        """Whether nothing may follow this state."""
        return not TRANSITIONS[self]

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def from_value(cls, value: str) -> RequestState | None:
        return _STATES_BY_VALUE.get(value.strip().lower())

    def __str__(self) -> str:
        return self.value


_STATES_BY_VALUE = {member.value: member for member in RequestState}

TRANSITIONS: Mapping[RequestState, frozenset[RequestState]] = {
    RequestState.OPEN: frozenset(
        {RequestState.ACCEPTED, RequestState.DECLINED, RequestState.WITHDRAWN}
    ),
    RequestState.ACCEPTED: frozenset(
        {RequestState.FULFILLED, RequestState.DECLINED, RequestState.WITHDRAWN}
    ),
    RequestState.FULFILLED: frozenset(),
    RequestState.DECLINED: frozenset(),
    RequestState.WITHDRAWN: frozenset(),
}
"""The lifecycle, exactly as `asset-requests` writes it.

The empty sets are load-bearing rather than decorative: they are what makes
`fulfilled → open` a refusal by the table instead of by a special case somebody
has to remember, and what :attr:`RequestState.is_terminal` reads.
"""


class RefusalKind(Enum):
    """Why a move was refused, in terms an outer layer can map (D10).

    The domain does not know about status codes, but it does know the
    *difference* between "you may not" and "that is not a legal move", and
    losing that difference at the boundary is how a permission failure reaches a
    caller as a validation error.
    """

    INVALID = "invalid"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TransitionDecision:
    """Allowed, or refused with a reason and the kind of refusal it is.

    Shaped after :class:`~cybercanon.domain.authorization.Decision` — same
    `allowed`/`reason`/`refused` surface — with `kind` added, because a
    lifecycle refusal and a permission refusal are not the same answer.
    """

    allowed: bool
    reason: str = ""
    kind: RefusalKind | None = None

    @property
    def refused(self) -> bool:
        return not self.allowed

    def __bool__(self) -> bool:
        return self.allowed


PERMITTED = TransitionDecision(allowed=True)
"""The unremarkable answer, shared because it carries no case-specific words."""


class EventKind(Enum):
    """What a history entry records."""

    RAISED = "raised"
    ASSIGNED = "assigned"
    TRANSITIONED = "transitioned"
    LINKED = "linked"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RequestEvent:
    """One entry of a request's history: what happened, who caused it, when.

    `actor` and `at` have no defaults. `asset-requests` requires every change to
    *"identify the person who caused the change and when"*, and a default would
    be the one path by which an unattributed entry gets written.
    """

    kind: EventKind
    actor: ActorId
    at: datetime
    state: RequestState | None = None
    assignee: ActorId | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise ValueError("a request event names the actor that caused it")
        if not isinstance(self.at, datetime):
            raise ValueError("a request event records when it happened")


@dataclass(frozen=True)
class RequestId:
    """A stable identifier for one request, unique within its project."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValueError(f"request id {self.value!r} must be non-empty and unpadded")
        if any(character.isspace() for character in self.value):
            raise ValueError(f"request id {self.value!r} must not contain whitespace")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AssetRequest:
    """One ask: what is needed, from which discipline, by whom, and where it got to.

    `asset` is optional because a request for *something that does not exist
    yet* is the case the capability exists for, and `asked_for_status` is
    optional because a request may simply ask for work rather than for a
    lifecycle position.
    """

    id: RequestId
    author: ActorId
    discipline: Discipline
    description: str
    asset: AssetId | None = None
    asked_for_status: Status | None = None
    assignee: ActorId | None = None
    state: RequestState = RequestState.OPEN
    history: tuple[RequestEvent, ...] = ()

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError(f"{NEEDS_DESCRIPTION}: {self.id} carries no description")

    @property
    def is_terminal(self) -> bool:
        """Whether this request has ended."""
        return self.state.is_terminal

    @property
    def needs_owner(self) -> bool:
        """Whether this request is waiting for somebody to own it.

        `asset-requests` requires an unownable request to be *"recorded as
        unassigned and reported as needing an owner"*, which is two facts: the
        empty assignee, and this. A terminal request needs nobody.
        """
        return self.assignee is None and not self.is_terminal

    @property
    def last_event(self) -> RequestEvent | None:
        """The most recent thing that happened to this request."""
        return self.history[-1] if self.history else None


@dataclass(frozen=True)
class DisciplineOwners:
    """Who owns each discipline, already resolved to actors.

    Resolution from the addresses `asset.yaml` declares is the application's
    job, through `.canon/actors.yaml`: a domain that did it would need the
    mapping, and assignment would stop being answerable from its arguments.

    `MODELING` has no field of its own because the specification format declares
    three owners — art, design and code — and modelling is the art owner's work.
    A fourth field would ask every project to fill in an owner it has never had.
    """

    art: ActorId | None = None
    design: ActorId | None = None
    code: ActorId | None = None

    def owner_of(self, discipline: Discipline) -> ActorId | None:
        """The owner of that discipline here, or ``None`` when none is declared."""
        return _OWNER_FIELDS[discipline](self)


_OWNER_FIELDS = {
    Discipline.ART: lambda owners: owners.art,
    Discipline.MODELING: lambda owners: owners.art,
    Discipline.DESIGN: lambda owners: owners.design,
    Discipline.CODE: lambda owners: owners.code,
}

NO_OWNERS = DisciplineOwners()
"""What an asset or a project that declares no owners has."""


def owners_declared_by(asset: Asset, resolve: Mapping[str, ActorId]) -> DisciplineOwners:
    """The owners an asset declares, as actors, through an already-built mapping.

    `resolve` maps the address a specification wrote — an email, a handle — onto
    the stable subject the domain compares. It is a plain mapping rather than a
    function so that this stays a total, inspectable transformation: an owner
    the mapping does not bind resolves to nobody, which is the same answer as
    declaring none, and is the answer D8 requires (never a guess).
    """
    return DisciplineOwners(
        art=_resolved(asset.owner_art, resolve),
        design=_resolved(asset.owner_design, resolve),
        code=_resolved(asset.owner_code, resolve),
    )


def _resolved(declared: str | None, resolve: Mapping[str, ActorId]) -> ActorId | None:
    return resolve.get(declared) if declared else None


def assignee_for(
    discipline: Discipline,
    *,
    on_asset: DisciplineOwners | None = None,
    on_project: DisciplineOwners | None = None,
    author: ActorId | None = None,
) -> ActorId | None:
    """Who a request for this discipline goes to: asset owner, project owner, nobody.

    The cascade `asset-requests` specifies, and the refusal it specifies too:
    *"SHALL NOT be assigned to its author or to an arbitrary person"*. `author`
    is accepted so that the rule is written down here rather than being a
    property nobody checks — it can never *become* the answer, and a caller that
    passes it gets the same ``None`` as one that does not.

    An owner who happens to be the author is still the owner: the prohibition is
    on falling back to the author, not on a person owning what they asked for.
    """
    owner = (on_asset or NO_OWNERS).owner_of(discipline)
    if owner is None:
        owner = (on_project or NO_OWNERS).owner_of(discipline)
    return owner


def raise_request(
    request_id: RequestId,
    *,
    author: ActorId,
    discipline: Discipline,
    description: str,
    at: datetime,
    asset: AssetId | None = None,
    asked_for_status: Status | None = None,
    assignee: ActorId | None = None,
) -> AssetRequest:
    """A new request, already carrying the history entry that records its raising.

    Raises :class:`ValueError` when the description is empty — the one rejection
    that happens at construction, because a request with nothing in it is not a
    request in a refused state, it is not a request.
    """
    raised = RequestEvent(
        kind=EventKind.RAISED,
        actor=author,
        at=at,
        state=RequestState.OPEN,
        assignee=assignee,
    )
    return AssetRequest(
        id=request_id,
        author=author,
        discipline=discipline,
        description=description,
        asset=asset,
        asked_for_status=asked_for_status,
        assignee=assignee,
        state=RequestState.OPEN,
        history=(raised,),
    )


def may_transition(
    request: AssetRequest,
    to: RequestState,
    *,
    actor: ActorId,
    reason: str = "",
    asset_status: Status | None = None,
) -> TransitionDecision:
    """Whether this actor may move this request there, and why not when they may not.

    Four rules, in the order that keeps each one answerable:

    1. the table permits the move at all (`fulfilled → open` never does);
    2. a decline states a reason;
    3. only the author withdraws;
    4. a request that asked for a status is fulfilled only once the asset has
       reached it — and the refusal *names the asset's current status*, because
       "not yet" without saying what "yet" means is not an answer.

    `asset_status` is read and never written. That asymmetry is the whole of
    "a request observes the asset status lifecycle and never drives it".
    """
    if to not in TRANSITIONS[request.state]:
        return TransitionDecision(
            allowed=False,
            reason=f"a {request.state} request may not become {to}",
            kind=RefusalKind.CONFLICT,
        )
    if to is RequestState.DECLINED and not reason.strip():
        return TransitionDecision(allowed=False, reason=NEEDS_REASON, kind=RefusalKind.INVALID)
    if to is RequestState.WITHDRAWN and actor != request.author:
        return TransitionDecision(
            allowed=False, reason=AUTHOR_WITHDRAWS, kind=RefusalKind.FORBIDDEN
        )
    if to is RequestState.FULFILLED:
        return _fulfilment(request, asset_status)
    return PERMITTED


def _fulfilment(request: AssetRequest, asset_status: Status | None) -> TransitionDecision:
    """The asked-for status precondition, named in the refusal (`asset-requests`)."""
    wanted = request.asked_for_status
    if wanted is None or asset_status is wanted:
        return PERMITTED
    reached = asset_status.value if asset_status is not None else "unknown"
    return TransitionDecision(
        allowed=False,
        reason=(f"the request asks for {wanted}; {_names(request)} is {reached}"),
        kind=RefusalKind.CONFLICT,
    )


def _names(request: AssetRequest) -> str:
    return str(request.asset) if request.asset is not None else "the asset"


def transition(
    request: AssetRequest,
    to: RequestState,
    *,
    actor: ActorId,
    at: datetime,
    reason: str = "",
    asset_status: Status | None = None,
) -> AssetRequest:
    """The request after the move, with the move recorded in its history.

    Re-checks :func:`may_transition` and raises :class:`ValueError` when it
    refuses. Callers are expected to ask first and turn the decision into their
    own vocabulary; the re-check is here so that no second path can apply a move
    the policy would have refused.
    """
    decision = may_transition(request, to, actor=actor, reason=reason, asset_status=asset_status)
    if decision.refused:
        raise ValueError(decision.reason)
    moved = RequestEvent(kind=EventKind.TRANSITIONED, actor=actor, at=at, state=to, reason=reason)
    return replace(request, state=to, history=(*request.history, moved))


def reassign(
    request: AssetRequest,
    assignee: ActorId | None,
    *,
    actor: ActorId,
    at: datetime,
) -> AssetRequest:
    """The request assigned to somebody else, with who did it and when recorded."""
    assigned = RequestEvent(
        kind=EventKind.ASSIGNED, actor=actor, at=at, state=request.state, assignee=assignee
    )
    return replace(request, assignee=assignee, history=(*request.history, assigned))


def link_to_asset(
    request: AssetRequest,
    asset: AssetId,
    *,
    actor: ActorId,
    at: datetime,
) -> AssetRequest:
    """The request, now referencing an asset somebody has created for it.

    The other half of *"a request for a not-yet-existing asset SHALL NOT create
    a specification"*: the link is made when a person creates the asset and
    associates it, and it is a change to the request only.
    """
    linked = RequestEvent(kind=EventKind.LINKED, actor=actor, at=at, state=request.state)
    return replace(request, asset=asset, history=(*request.history, linked))


__all__ = [
    "AUTHOR_WITHDRAWS",
    "NEEDS_DESCRIPTION",
    "NEEDS_OWNER",
    "NEEDS_REASON",
    "NO_OWNERS",
    "PERMITTED",
    "TRANSITIONS",
    "AssetRequest",
    "Discipline",
    "DisciplineOwners",
    "EventKind",
    "RefusalKind",
    "RequestEvent",
    "RequestId",
    "RequestState",
    "TransitionDecision",
    "assignee_for",
    "link_to_asset",
    "may_transition",
    "owners_declared_by",
    "raise_request",
    "reassign",
    "transition",
]
