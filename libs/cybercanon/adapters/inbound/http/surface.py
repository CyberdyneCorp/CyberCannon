"""What the composition root hands the routers, and the four things they ask it.

A router in this package does exactly four things, and every one of them is a
function here rather than a paragraph in a handler:

* **which project is this** (:func:`project_of`) — the address names it, and an
  address for a project this deployment does not serve is a not-found;
* **who is acting** (:func:`acting`) — the verified credential, through the
  `authenticate` use case. Never a path segment, never a body field: `project.md`
  fixes that and :func:`~cybercanon.application.use_cases.authenticate.authenticate`
  strips anything that tried;
* **may they** (:func:`permitted`) — :func:`~cybercanon.domain.policy.decide`,
  unchanged and unhelped. The adapter translates claims into an
  :class:`~cybercanon.domain.identity.Actor`; the decision is the domain's, which
  is what lets the whole policy suite run with no HTTP and no identity service;
* **read it at one revision** (:func:`at_revision`) — D3. The revision is
  resolved once, the store is pinned to it, and the answer carries the freshness
  `hosted-repository` requires every read to state.

Nothing here decides anything about an asset, and nothing here is a second
implementation of anything: the use cases are the ones the command line and the
agent surface call, reached through the same
:class:`~cybercanon.adapters.wiring.container.Container`.

**The container is per project and it arrives already built.** The surface never
constructs one, because constructing one means naming an outbound adapter, and
an inbound adapter that named one would break the layering contract this package
is checked against by name.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

from fastapi import Request

from cybercanon.adapters.inbound.http import logs
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.dismissals import Dismissals
from cybercanon.application.ports.document_platform import NO_CREDENTIAL
from cybercanon.application.ports.document_platform import Credential as ForwardedCredential
from cybercanon.application.ports.idempotency import IdempotencyStore
from cybercanon.application.ports.identity_provider import Credential, IdentityProvider
from cybercanon.application.ports.image_inspector import ImageInspector
from cybercanon.application.ports.notifier import Notifier
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.thumbnail_renderer import ThumbnailRenderer
from cybercanon.application.ports.view_index import ViewIndex
from cybercanon.application.results import Forbidden, NotFound, Ok, Refusal, Result, Unavailable
from cybercanon.application.use_cases.authenticate import Authenticated, authenticate
from cybercanon.application.use_cases.deployment_status import DeploymentJournal
from cybercanon.application.use_cases.hosted_repository import (
    DEFAULT_INTERVAL,
    Freshness,
    read_at_revision,
)
from cybercanon.application.use_cases.resolve_actor import AlreadyResolved, Resolution, verified_as
from cybercanon.application.use_cases.service_health import ComponentStatus
from cybercanon.domain.identity import Actor
from cybercanon.domain.policy import Operation, Subject, decide

AUTHORIZATION_HEADER = "Authorization"
BEARER = "Bearer"
"""The one place a credential may arrive. Identity is never a parameter."""

IDEMPOTENCY_HEADER = "Idempotency-Key"
"""Where a caller names a write it may repeat (D11)."""

UNKNOWN_PROJECT = "project.unknown"
NO_IDENTITY = "identity.unconfigured"
POLICY_REFUSED = "policy.refused"

NOT_CONFIGURED = (
    "this deployment has no identity service configured, so no request can be "
    "attributed; set the issuer, audience and key set in the environment"
)


Dependency = ComponentStatus
"""One thing the process observes, and what it observed (task 9.9).

The value object is
:class:`~cybercanon.application.use_cases.service_health.ComponentStatus`, and
the name here is the one `http-api` used for it before
`deployment-operations` existed. It is an alias rather than a second class on
purpose: which dependencies may withhold traffic is that capability's decision,
taken over these values, and two shapes would let the surface describe one thing
and the readiness rule classify another.
"""


type Observe = Callable[[], Sequence[ComponentStatus]]
"""How the composition root reports what it can currently see."""


def observes_nothing() -> tuple[Dependency, ...]:
    """The default: a process that has been given nothing to watch."""
    return ()


@dataclass(frozen=True)
class HostedProject:
    """One project this deployment serves: its wiring, and its working copy.

    `repository_host` is optional, and its absence is a *local* wiring rather
    than a broken one: a container built over a working copy on disk answers
    every read without one, and simply states no revision. A hosted deployment
    always has one, which is how its reads become revision-pinned (D3).

    **`name` is the address, and the address is the project's identity here.**
    `http-api` requires a resource to stay reachable at one address for as long
    as it exists, so what this deployment serves the project as is what every
    project-keyed decision underneath is made with: the container is pinned to
    it at construction. Without the pin there are two answers to *which project
    is this* — the address, and the `name:` in the working copy's
    `.canon/project.yaml` — and they are used by different endpoints: the
    pipeline authorizes against the address, while a lensed read re-authorizes
    inside the use case against the declared name. One actor, entitled to one
    project, then gets a different verdict from `/assets` and from
    `/assets/{asset}`, which is not a policy anybody wrote.
    """

    name: str
    container: Container
    repository_host: RepositoryHost | None = None
    interval: timedelta = DEFAULT_INTERVAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "container", replace(self.container, project_id=self.name))


@dataclass(frozen=True)
class Surface:
    """Everything the versioned routers are allowed to reach.

    One object rather than several application attributes, so that "what does
    this surface depend on" has a single answer a reader can see at once — and
    so that a test builds the whole of it in one expression.
    """

    projects: Mapping[str, HostedProject] = field(default_factory=dict)
    identity_provider: IdentityProvider | None = None
    idempotency: IdempotencyStore | None = None
    dismissals: Dismissals | None = None
    notifier: Notifier | None = None
    image_inspector: ImageInspector | None = None
    """How an uploaded concept view is read (add-concept-ingestion D1).

    Optional, like every other port here: a deployment wired without one serves
    reads and refuses an upload through the use case's own vocabulary rather
    than through a missing attribute.
    """

    thumbnail_renderer: ThumbnailRenderer | None = None
    view_index: ViewIndex | None = None
    """The two derived halves of ingestion (D3, D9). Absent means *not derived*.

    Both are droppable by specification — the mirror rebuilds from the
    repository and the index row is reconstructible by walking it — so a
    deployment missing either still commits views, and says they are awaiting
    their derived step.
    """

    observe: Observe = observes_nothing
    journal: DeploymentJournal = field(default_factory=DeploymentJournal)
    clock: Clock = system_clock
    web_origins: tuple[str, ...] = ()
    """The browser origins this deployment permits (:mod:`cybercanon.adapters.inbound.http.cors`).

    Empty by default, and empty means *no cross-origin permission at all* rather
    than *any*. A deployment that has not been told which web application talks
    to it is one reached by `canon` and the agent surface, and those are not
    browsers.
    """

    def project_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.projects))


# --------------------------------------------------------------------------
# Which project, and who is asking
# --------------------------------------------------------------------------


def project_of(surface: Surface, name: str) -> Result[HostedProject]:
    """The project at this address, or a not-found that names it.

    A project this deployment does not serve is *not found* rather than
    forbidden, and deliberately so: the two would otherwise let anybody probe
    which projects exist by reading the difference between them.
    """
    hosted = surface.projects.get(name)
    if hosted is None:
        return NotFound(
            identifier=UNKNOWN_PROJECT,
            message=f"no project named {name!r} is served by this deployment",
            subject=name,
        )
    return Ok(hosted)


def presented(request: Request) -> Credential | None:
    """The credential this request carries, or nothing. It reads one header."""
    offered = request.headers.get(AUTHORIZATION_HEADER, "").strip()
    scheme, _, value = offered.partition(" ")
    if scheme.lower() != BEARER.lower() or not value.strip():
        return None
    return Credential(value.strip())


def forwarded(request: Request) -> ForwardedCredential:
    """The caller's own bearer token, as the document platform's credential (D2).

    The same header, read again for a different purpose, and deliberately not
    the same value object: `auth-integration`'s credential is what *this*
    service verifies, and the document platform's is what gets sent *on*. Two
    types make "whose authority is this, and where is it going" a thing a
    signature says rather than a thing a reader has to trace.

    A request with no bearer header forwards
    :data:`~cybercanon.application.ports.document_platform.NO_CREDENTIAL` —
    which carries nothing and says so — rather than anything of this
    deployment's. A service credential standing in for a person is the one
    thing `semantic-search-delegation` rules out by name.
    """
    offered = presented(request)
    return ForwardedCredential(offered.value) if offered is not None else NO_CREDENTIAL


def idempotency_key(request: Request) -> str:
    """The key this write may be repeated under, or an empty string."""
    return request.headers.get(IDEMPOTENCY_HEADER, "").strip()


def acting(surface: Surface, request: Request) -> Result[Authenticated]:
    """Who this request is evaluated as — from the credential and nothing else.

    A deployment with no identity service configured answers *unavailable*
    rather than serving an anonymous actor: `auth-integration` forbids the
    second in so many words, and the first is the honest description of a
    service that was started without an issuer.
    """
    if surface.identity_provider is None:
        return Unavailable(identifier=NO_IDENTITY, message=NOT_CONFIGURED, subject="this surface")
    resolved = authenticate(
        presented(request),
        identity_provider=surface.identity_provider,
        claimed=dict(request.query_params),
    )
    if isinstance(resolved, Refusal) and resolved.reason:
        logs.remember(request, logs.REASON_STATE, resolved.reason)
    return resolved


# --------------------------------------------------------------------------
# May they
# --------------------------------------------------------------------------


def permitted(actor: Actor, operation: Operation, subject: Subject) -> Refusal | None:
    """The domain's answer, translated — or ``None`` when there is nothing to say.

    The translation is the adapter's whole contribution to authorization. The
    decision, the ordering of its checks and the sentence it refuses with are
    all :mod:`cybercanon.domain.policy`'s, which is why a service credential
    holding every role is refused a promotion here without this module knowing
    that promotions are special (task 9.8).
    """
    decision = decide(actor, operation, subject)
    if decision.refused:
        return Forbidden(identifier=POLICY_REFUSED, message=decision.reason, subject=subject.named)
    return None


def as_actor(container: Container, actor: Actor, git_emails: tuple[str, ...] = ()) -> Container:
    """The container, wired to resolve this request's actor and no other.

    The use cases that authorize for themselves — a lensed read, an open-thread
    read — ask their resolver who is acting. On a laptop that is the local
    actor; over HTTP it is the verified subject this request presented, and
    substituting it here is what keeps *"identity from verified claims only"*
    true for the shared use case rather than only for the adapter.
    """
    return replace(container, actor_resolver=AlreadyResolved(verified_as(actor, git_emails)))


# --------------------------------------------------------------------------
# One read, one revision (D3)
# --------------------------------------------------------------------------

type Read[T] = Callable[[Container], Result[T]]
"""A read expressed as a use case call over the container it should run against."""


def at_revision[T](
    hosted: HostedProject,
    read: Read[T],
    *,
    clock: Clock = system_clock,
) -> tuple[Result[T], Freshness | None]:
    """Serve one read from one revision, and say which one it was.

    The pinning is
    :func:`~cybercanon.application.use_cases.hosted_repository.read_at_revision`'s,
    not this module's: the revision is resolved before the read starts and the
    store is pinned to it, so a briefing assembled from six files is assembled
    from one revision by construction and a fetch landing mid-read changes
    nothing the reader can see.

    A container with no repository host answers unpinned and states no
    revision — the local wiring, where there is no fetch to race.
    """
    if hosted.repository_host is None:
        return read(hosted.container), None
    outcome = read_at_revision(
        hosted.name,
        lambda pinned: read(replace(hosted.container, spec_store=pinned)),
        repository_host=hosted.repository_host,
        spec_store=hosted.container.spec_store,
        clock=clock,
        interval=hosted.interval,
    )
    if not isinstance(outcome, Ok):
        return outcome, None
    return outcome.value.value, outcome.value.freshness


def freshness_fields(freshness: Freshness | None) -> dict[str, Any]:
    """What a read adds to its envelope: the revision, and how stale it may be.

    Both halves or neither. `hosted-repository` requires a response carrying
    specification content to state the revision *and* when it was last
    confirmed, and a surface that rendered one without the other would be
    reporting freshness it has not established.
    """
    if freshness is None:
        return {}
    return {
        "revision": freshness.revision.value,
        "confirmed_at": freshness.confirmed_at.isoformat(),
        "may_be_stale": freshness.may_be_stale,
    }


def subject_for(project: str, description: str = "") -> Subject:
    """The policy subject for a project-scoped operation."""
    return Subject(project=project, description=description)


__all__ = [
    "AUTHORIZATION_HEADER",
    "BEARER",
    "IDEMPOTENCY_HEADER",
    "NOT_CONFIGURED",
    "NO_IDENTITY",
    "POLICY_REFUSED",
    "UNKNOWN_PROJECT",
    "Dependency",
    "DeploymentJournal",
    "HostedProject",
    "Observe",
    "Read",
    "Resolution",
    "Surface",
    "acting",
    "as_actor",
    "at_revision",
    "forwarded",
    "freshness_fields",
    "idempotency_key",
    "observes_nothing",
    "permitted",
    "presented",
    "project_of",
    "subject_for",
]
