"""The `LLMPort` — text from a model, or the reason there is none (D2, D3).

One capability, stated the smallest way it can be: *given this instruction,
return this text*. `llm-integration` requires that use cases and domain logic
*"SHALL NOT observe the endpoint, the credential, the model identifier, request
or response structures, or any provider-specific error"*, and the signature
below is what makes that true by construction rather than by review — there is
no argument a caller could pass an endpoint through and no value it could read
one out of.

**Availability is a value the caller receives, not an exception it catches**
(D3). :class:`ModelUnavailable` is a member of the return type, so forgetting to
handle it is a visible omission the type checker and the reader both see; an
exception would make forgetting it the default, and *"the larger operation SHALL
complete"* would depend on every call site remembering a `try`.

**The six reasons are closed and each means something different.** A surface
renders the distinction — `llm-integration` requires the system to *"state the
reason distinguishing at least disabled, misconfigured, unreachable and
rejected"* — so an adapter maps every way of not answering onto exactly one
member, and there is no seventh for a new client library to invent.

Absence is a **null adapter chosen at composition**, exactly as it is for the
document platform: :class:`DisabledLLM` answers every call with `DISABLED`, so
no use case branches on configuration and *"degrades to absent"* is one wiring
decision tested once.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, TypeGuard


class Unavailability(Enum):
    """Why there is no generated content. Six, and the set is closed.

    The four the specification names by name — disabled, misconfigured,
    unreachable, rejected — plus the two a bounded request adds: a budget that
    ran out, and an answer that was not the shape this system can read. Every
    one of them produces the *same* observable outcome (the feature is
    unavailable and nothing else changes); they differ only in the sentence a
    person is shown, which is the sentence that tells them whether to set a
    variable, call an administrator or simply try later.
    """

    DISABLED = "disabled"
    MISCONFIGURED = "misconfigured"
    UNREACHABLE = "unreachable"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    MALFORMED = "malformed"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @property
    def is_transient(self) -> bool:
        """Whether trying again could plausibly answer differently (D4).

        The retry rule in one place: a budget that ran out and an endpoint that
        was not there may be retried; a switch that is off, a credential that
        was refused, a request that was rejected and an answer that could not be
        read will say exactly the same thing the second time.
        """
        return self in (Unavailability.UNREACHABLE, Unavailability.TIMEOUT)

    def __str__(self) -> str:
        return self.value


DISABLED_DETAIL = "no model is configured for this deployment"
"""What an unconfigured deployment says. Not an outage, and never logged as one."""


@dataclass(frozen=True)
class Completion:
    """What a model said, and which model said it.

    `model` is the configured identifier echoed back so that provenance can
    record it (`derived-metadata` requires the model identifier to travel with
    every derived record). It is carried, never interpreted: nothing in this
    system branches on its value.
    """

    text: str
    model: str = ""

    @property
    def is_available(self) -> bool:
        return True

    def __bool__(self) -> bool:
        return True


@dataclass(frozen=True)
class ModelUnavailable:
    """There is no generated content, and this is which way there is none.

    Named `ModelUnavailable` rather than `Unavailable` deliberately:
    :class:`cybercanon.application.results.Unavailable` is a *refusal a use case
    returns to a surface*, and the two must not be confusable at an import. A
    model that did not answer is an input a use case handles, not an outcome it
    hands back — the surrounding operation still completes.
    """

    reason: Unavailability
    detail: str = ""

    @property
    def is_available(self) -> bool:
        return False

    @property
    def message(self) -> str:
        """The sentence a person reads: the reason, and any detail there was."""
        return f"generation is unavailable: {self.reason}" + (
            f" — {self.detail}" if self.detail else ""
        )

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return self.message


type ModelAnswer = Completion | ModelUnavailable
"""What either model port returns. Two shapes, and a caller handles both."""


def answered(answer: ModelAnswer) -> TypeGuard[Completion]:
    """Whether a model produced text. The one question every caller asks first."""
    return isinstance(answer, Completion)


def unavailable(reason: Unavailability, detail: str = "") -> ModelUnavailable:
    """The refusal of that kind, built once so every adapter spells it the same."""
    return ModelUnavailable(reason=reason, detail=detail)


class LLMPort(Protocol):
    """Text generation, with no vendor, endpoint or wire format in the signature."""

    def complete(self, instruction: str) -> ModelAnswer:
        """Answer this instruction, or say why there is no answer.

        Never raises for a model failure: every way of not answering is a
        :class:`ModelUnavailable`, which is what makes *"a timeout does not fail
        the surrounding operation"* a property of the port rather than of each
        caller's discipline.
        """
        ...


class DisabledLLM:
    """The null adapter: no model is configured, and that is an ordinary state.

    Chosen at composition when the master switch is off or the configuration is
    incomplete, so that *"the system SHALL be fully usable with it off"* is one
    wiring decision rather than a flag every call site reads.
    """

    def complete(self, instruction: str) -> ModelAnswer:
        return unavailable(Unavailability.DISABLED, DISABLED_DETAIL)


__all__ = [
    "DISABLED_DETAIL",
    "Completion",
    "DisabledLLM",
    "LLMPort",
    "ModelAnswer",
    "ModelUnavailable",
    "Unavailability",
    "answered",
    "unavailable",
]
