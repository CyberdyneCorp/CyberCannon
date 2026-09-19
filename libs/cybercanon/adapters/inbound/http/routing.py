"""The request pipeline every endpoint runs, written once.

A handler in this package is one line, and this is the line. `http-api` requires
the surface to be *"a thin adapter over shared use cases"*, and the way a thin
adapter stops being thin is never a rule somebody adds on purpose — it is the
fourth endpoint that checks authorization slightly differently from the third.
So the order is fixed here, once:

    which project → who is acting → may they → the use case → the one response

Nothing in that sequence is conditional on what a specification says, and every
step of it either produces the next one or produces a refusal that goes straight
to :func:`~cybercanon.adapters.inbound.http.outcomes.respond`. A handler that
wanted to behave differently would have to stop calling :func:`answered`, which
is visible in review in a way that an extra `if` inside a handler is not.

Paging and idempotency are separate steps rather than parameters of this one,
because only some endpoints have them and a pipeline with five optional stages
is a pipeline nobody can read.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from cybercanon.adapters.inbound.http import logs, outcomes, pagination
from cybercanon.adapters.inbound.http import surface as wiring
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.application.ports.idempotency import RecordedOutcome
from cybercanon.application.results import Ok, Result, refuse
from cybercanon.application.use_cases.deployment_status import IndexRead, served_from_index
from cybercanon.application.use_cases.idempotency import once
from cybercanon.domain.policy import Operation


def answered[T](
    surface: wiring.Surface,
    request: Request,
    project: str,
    operation: Operation,
    read: wiring.Read[T],
    render: outcomes.Rendering = outcomes.identity,
    *,
    paging: Callable[[Result[T]], Result[Any]] | None = None,
    index: IndexRead = IndexRead.NONE,
) -> JSONResponse:
    """One read, from the address to the response, through the shared use case.

    A paged endpoint hands in `paging` and leaves `render` alone: the page has
    already rendered its items by then, and rendering twice would wrap each one
    in the shape of the other.

    `index` says how much of the index this read needs to be complete, and it is
    consulted only while that project is being rebuilt (`deployment-operations`,
    task 5.7): an endpoint served from the working copy declares
    :attr:`~cybercanon.application.use_cases.deployment_status.IndexRead.NONE`
    and keeps answering through a rebuild, which is the specified behaviour
    rather than a nicety.
    """
    prepared = prepared_for(surface, request, project, operation)
    if not isinstance(prepared, Ok):
        return outcomes.respond(prepared, version=VERSION)
    hosted, actor = prepared.value
    result, freshness = wiring.at_revision(
        hosted,
        lambda container: read(wiring.as_actor(container, actor.actor, actor.git_emails)),
        clock=surface.clock,
    )
    answered_from = result if paging is None else paging(result)
    answer = served_from_index(answered_from, project=project, journal=surface.journal, read=index)
    return outcomes.respond(
        answer, render, version=VERSION, extra=wiring.freshness_fields(freshness)
    )


def prepared_for(
    surface: wiring.Surface,
    request: Request,
    project: str,
    operation: Operation,
) -> Result[tuple[wiring.HostedProject, Any]]:
    """The three questions that come before any use case runs, in their order.

    Project first, so an address for a project this deployment does not serve is
    answered without a credential being verified; identity second, because
    `auth-integration` serves no anonymous actor; policy third, because it needs
    the actor. Each refusal is returned as itself, which is what keeps a domain
    refusal from being reported as an internal error.
    """
    logs.remember(request, logs.PROJECT_STATE, project)
    hosted = wiring.project_of(surface, project)
    if not isinstance(hosted, Ok):
        return hosted
    actor = wiring.acting(surface, request)
    if not isinstance(actor, Ok):
        return actor
    logs.remember(request, logs.ACTOR_STATE, actor.value.actor.id.value)
    refusal = wiring.permitted(actor.value.actor, operation, wiring.subject_for(project))
    if refusal is not None:
        return refusal
    return Ok((hosted.value, actor.value))


def paged[T](
    order: Callable[[T], Sequence[Any]],
    render: outcomes.Rendering,
    *,
    token: str | None,
    size: int | None,
) -> Callable[[Result[T]], Result[Any]]:
    """Turn a listing outcome into one page of it, in a deterministic order.

    The order is the caller's function, and it has to be total — paging over an
    order with ties returns some result twice and some never, which is the one
    thing `http-api` asks a traversal to guarantee it will not do.
    """

    def page(result: Result[T]) -> Result[Any]:
        if not isinstance(result, Ok):
            return result
        sliced = pagination.page_of(order(result.value), token=token, size=size)
        if not isinstance(sliced, Ok):
            return sliced
        return Ok(pagination.rendered(sliced.value, render))

    return page


# --------------------------------------------------------------------------
# Writes: run once per key, and replay the first answer afterwards (D11)
# --------------------------------------------------------------------------

type Write[T] = Callable[[], Result[T]]
"""A write, already bound to everything it needs, waiting to be run at most once."""


def applied[T](
    surface: wiring.Surface,
    key: str,
    body: bytes,
    write: Write[T],
    render: outcomes.Rendering,
) -> Result[Any]:
    """The write, performed once per idempotency key and replayed after that.

    A caller that sends no key, or a deployment with no store wired, simply
    performs the write: D11 makes the key the mechanism that keeps a retry
    *quiet*, and D5's per-file precondition is what keeps it *safe*. The second
    holds with or without the first, which is why an absent key is not an error.
    """
    if not key or surface.idempotency is None:
        return _rendered(write(), render)
    record = once(
        key,
        body,
        write,
        store=surface.idempotency,
        clock=surface.clock,
        render=lambda value: json.dumps(render(value)),
    )
    if not isinstance(record, Ok):
        return record
    return _replayed(record.value)


def _rendered[T](result: Result[T], render: outcomes.Rendering) -> Result[Any]:
    if not isinstance(result, Ok):
        return result
    return Ok(render(result.value))


def _replayed(record: RecordedOutcome) -> Result[Any]:
    """A stored outcome as the answer it was the first time, refusal included.

    Refusals are replayed as refusals. A retry of a write that was refused must
    not succeed because the repository moved in between — otherwise a lost
    response turns a conflict into an apply, which is the opposite of what an
    idempotency key is for.
    """
    if record.kind is None:
        return Ok(json.loads(record.payload or "null"))
    return refuse(record.kind, record.identifier, record.message, record.subject)


__all__ = ["Write", "answered", "applied", "paged", "prepared_for"]
