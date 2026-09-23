"""The outcome vocabulary every surface translates and none of them invents (D10).

A use case returns one of seven things: :class:`Ok`, or one of the six refusals.
Each carries a **stable machine-readable identifier** and the **subject at
fault**, which is precisely what `http-api` requires of an error body, and each
maps to exactly one status class through one function the HTTP adapter owns.

Why a union and not exceptions, in the design's own words: *"A per-router
`try/except` satisfies that on the day it is written and stops doing so at the
fourth endpoint. A single mapping is exhaustively testable — one test asserts
every member of the union has a mapping."*

Ports still raise, and that is deliberate rather than a leftover. A port failure
is an *implementation detail of the outside world* — a file that will not parse,
a git binary that is missing, a provider that timed out — and the layer that
knows what it means for the caller is the use case. :func:`attempt` is where the
one becomes the other, exactly once, in the application layer: the use case
below it composes ordinary raising calls, and the adapter above it never catches
anything. The classification is not written there either — every named failure
declares its kind and its identifier where it is defined
(:mod:`cybercanon.application.errors`), so a new failure arrives in the
vocabulary with it.

`Ok` carries an `identifier` and a `subject` too, unused by anything that
succeeds. That uniformity is the point: a renderer, a payload builder and the
status mapping all read the same three attributes off whatever they were handed,
so none of them needs to know which member it has before it can name it.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import ClassVar, TypeGuard

from cybercanon.application.errors import FailureKind, OperationFailed

OK = "ok"
"""The identifier a success carries. It is never rendered; it is never absent."""


@dataclass(frozen=True)
class Ok[T]:
    """The operation ran and produced this.

    `value` is whatever the use case produces — a report, a listing, a compiled
    briefing. A verdict inside it (an export that failed its budget) is still an
    `Ok`: the operation ran, and *"your mesh is wrong"* and *"I could not look at
    your mesh"* are different sentences (D11).
    """

    value: T
    identifier: str = OK
    subject: str = ""

    @property
    def message(self) -> str:
        return ""


@dataclass(frozen=True)
class Refusal:
    """The operation did not run, and this is why. Never raised, always returned.

    `identifier` is stable across releases because a client branches on it;
    `message` is for a person; `subject` is the thing at fault, where one exists.

    `reason` is the discriminating detail *behind* the message, for the record
    and never for the response. An authentication refusal says one undisclosing
    sentence to every caller on purpose — a wrong signature and an untrusted
    client must not be distinguishable from outside — while an operator needs to
    know which of them happened. Carrying it here is what lets those two be
    different without the surface choosing between them, and it is empty for
    every refusal whose message already says everything there is to say.

    Nothing serialises this. The response body is assembled field by field in
    :mod:`cybercanon.adapters.inbound.http.outcomes`, and a test asserts no
    reason reaches a body, because a field that leaked by default would undo the
    non-disclosure the identity capability is explicit about.
    """

    identifier: str
    message: str
    subject: str = ""
    reason: str = ""

    kind: ClassVar[FailureKind]

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class NotFound(Refusal):
    """No such thing — an identifier no specification declares, a missing file."""

    kind: ClassVar[FailureKind] = FailureKind.NOT_FOUND


@dataclass(frozen=True)
class Forbidden(Refusal):
    """The caller is known and may not. The refusal names what would be required."""

    kind: ClassVar[FailureKind] = FailureKind.FORBIDDEN


@dataclass(frozen=True)
class Unauthenticated(Refusal):
    """The caller is not identified, and is never served as an anonymous one."""

    kind: ClassVar[FailureKind] = FailureKind.UNAUTHENTICATED


@dataclass(frozen=True)
class Invalid(Refusal):
    """The request cannot be understood — a lens outside the set, an empty field."""

    kind: ClassVar[FailureKind] = FailureKind.INVALID


@dataclass(frozen=True)
class Conflict(Refusal):
    """What this was composed against has changed, or the move does not exist (D5)."""

    kind: ClassVar[FailureKind] = FailureKind.CONFLICT


@dataclass(frozen=True)
class Unavailable(Refusal):
    """A precondition outside the caller's control is unmet — for now."""

    kind: ClassVar[FailureKind] = FailureKind.UNAVAILABLE


type Result[T] = Ok[T] | Refusal
"""What a use case returns. Seven shapes, and an adapter handles all seven."""

REFUSALS: Mapping[FailureKind, type[Refusal]] = {
    FailureKind.NOT_FOUND: NotFound,
    FailureKind.FORBIDDEN: Forbidden,
    FailureKind.UNAUTHENTICATED: Unauthenticated,
    FailureKind.INVALID: Invalid,
    FailureKind.CONFLICT: Conflict,
    FailureKind.UNAVAILABLE: Unavailable,
}
"""Kind to member, one entry each. A test asserts it covers `FailureKind` exactly."""


def refuse(
    kind: FailureKind,
    identifier: str,
    message: str,
    subject: str = "",
    reason: str = "",
) -> Refusal:
    """The refusal of that kind — the one constructor that takes a kind as data.

    Used where the kind was decided by something that is not an exception: a
    domain :class:`~cybercanon.domain.requests.TransitionDecision`, a policy
    decision, a precondition a use case checked for itself.
    """
    return REFUSALS[kind](identifier=identifier, message=message, subject=subject, reason=reason)


def classify(error: OperationFailed) -> Refusal:
    """The refusal a port failure means to the caller, from its own declaration.

    `reason` is read with :func:`getattr` because only the identity failures
    carry one, and this function converts every port failure there is. Dropping
    it here is the bug this argument fixes: the detail survived the whole way up
    the call stack and was discarded one line before anything could record it,
    which is why the identity port's own documentation said the reason lived
    "where a log line reaches it" while no log line ever did.
    """
    return refuse(
        error.kind,
        error.identifier,
        error.message,
        error.subject or "",
        getattr(error, "reason", ""),
    )


def attempt[T](operation: Callable[[], T]) -> Result[T]:
    """Run a use case body, turning the failures it composes into one answer.

    Only :class:`~cybercanon.application.errors.OperationFailed` is converted.
    Anything else propagates untouched, and it should: an unexpected exception is
    not an outcome the domain expressed, and `http-api` requires it to be
    reported as a generic failure with a correlation identifier rather than
    dressed up as a refusal somebody can act on.
    """
    try:
        return Ok(operation())
    except OperationFailed as failure:
        return classify(failure)


class UseCase[**P, T]:
    """A use case, seen from outside: call it and get one of the seven answers.

    The body it wraps is written the way every body in this package is written —
    ordinary calls to ports that raise when the outside world will not cooperate
    — and this object is the single place where that becomes a returned value
    (D10). Wrapping rather than rewriting each body is deliberate: the
    alternative is a `try/except` at the top of seventeen functions, which is
    seventeen chances to classify the same failure differently, and exactly the
    drift the outcome vocabulary exists to prevent.

    `raising` is the body itself, and it is public for one reason: a use case
    that *composes* another — `read_asset_spec` compiles a specification on its
    way to projecting a lens — needs the value, not the wrapper, and wrapping
    twice would bury a refusal inside an `Ok`. Nothing outside
    `application/use_cases/` and the composition root calls it.
    """

    def __init__(self, raising: Callable[P, T]) -> None:
        self.raising = raising
        functools.update_wrapper(self, raising)

    def __call__(self, *arguments: P.args, **keywords: P.kwargs) -> Result[T]:
        return attempt(lambda: self.raising(*arguments, **keywords))


def as_result[**P, T](operation: Callable[P, T]) -> UseCase[P, T]:
    """Make a use case body into the use case. Applied as a decorator."""
    return UseCase(operation)


def succeeded[T](result: Result[T]) -> TypeGuard[Ok[T]]:
    """Whether the operation ran. The one question every adapter asks first."""
    return isinstance(result, Ok)


def first_refusal[T](results: tuple[Result[T], ...]) -> Refusal | None:
    """The first refusal among several results, or ``None`` when all succeeded.

    `canon validate a.glb b.glb` runs one use case per export and the command
    ends once, so the surface needs *the* refusal rather than a list of them —
    and needs it in argument order, because the person reads the first thing
    that went wrong.
    """
    return next((result for result in results if not succeeded(result)), None)


def values[T](results: tuple[Result[T], ...]) -> tuple[T, ...]:
    """The values of results already known to have succeeded."""
    return tuple(result.value for result in results if succeeded(result))


__all__ = [
    "OK",
    "REFUSALS",
    "Conflict",
    "Forbidden",
    "Invalid",
    "NotFound",
    "Ok",
    "Refusal",
    "Result",
    "Unauthenticated",
    "Unavailable",
    "UseCase",
    "as_result",
    "attempt",
    "classify",
    "first_refusal",
    "refuse",
    "succeeded",
    "values",
]
