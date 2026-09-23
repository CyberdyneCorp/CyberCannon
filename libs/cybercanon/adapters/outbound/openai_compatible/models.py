"""The adapter itself: both ports, one transport, and a bounded retry loop.

One class implements `LLMPort` and `VisionPort` because one endpoint serves
both (D2) — the *ports* are two so that "text available, vision unavailable" is
representable, not because two adapters would be different objects.

The loop is `llm-integration`'s two sentences and nothing more: *"Every model
request SHALL be bounded by the configured timeout and SHALL retry at most the
configured number of times before reporting unavailability. The system SHALL NOT
retry a request rejected for authentication or for an invalid request."* Which
failures are worth trying again is
:attr:`~cybercanon.application.ports.llm.Unavailability.is_transient`, decided
beside the reasons themselves, so this loop has no table of its own to fall out
of step with.

**No failure leaves this module as an exception** (D3). Every path returns a
:class:`~cybercanon.application.ports.llm.ModelAnswer`, which is what makes
*"the larger operation SHALL complete"* a property of the adapter rather than of
every caller's discipline.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from cybercanon.adapters.outbound.openai_compatible.config import ModelSettings
from cybercanon.adapters.outbound.openai_compatible.transport import (
    ChatTransport,
    TransportFailure,
    chat_body,
    image_message,
    text_message,
)
from cybercanon.application.ports.llm import (
    Completion,
    ModelAnswer,
    Unavailability,
    unavailable,
)


@dataclass
class OpenAICompatibleModels:
    """Text and vision over one OpenAI-compatible endpoint, configured by environment.

    `transport` is built from the settings when it is not supplied, which is
    what a composition root does; a suite supplies one holding a recorder so
    that every assertion about a request is an assertion about the bytes that
    left rather than about the code that wrote them.
    """

    settings: ModelSettings
    transport: ChatTransport | None = None
    attempts_made: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.transport is None:
            self.transport = ChatTransport(
                base_url=self.settings.api_root,
                api_key=self.settings.api_key,
                timeout=self.settings.timeout,
            )

    # -- LLMPort ---------------------------------------------------------

    def complete(self, instruction: str) -> ModelAnswer:
        """Answer this instruction with the configured text model."""
        if not self.settings.is_complete:
            return unavailable(_absence(self.settings), self.settings.absence)
        return self._ask(chat_body(self.settings.model, text_message(instruction)))

    # -- VisionPort ------------------------------------------------------

    def describe(self, image: bytes, instruction: str) -> ModelAnswer:
        """Describe these bytes with the configured vision model, and nothing else."""
        if not self.settings.vision_is_complete:
            return unavailable(_absence(self.settings), self.settings.vision_absence)
        return self._ask(chat_body(self.settings.vision_model, image_message(image, instruction)))

    # -- the bounded loop ------------------------------------------------

    def _ask(self, body: Mapping[str, Any]) -> ModelAnswer:
        """At most `1 + max_retries` attempts, and exactly one for a refusal."""
        model = str(body.get("model", ""))
        self.attempts_made = []
        failure = TransportFailure(Unavailability.MALFORMED, "no attempt was made")
        for attempt in range(1, self.settings.max_retries + 2):
            self.attempts_made.append(attempt)
            try:
                return Completion(text=self._transport().send(body), model=model)
            except TransportFailure as raised:
                failure = raised
                if not raised.is_transient:
                    break
        return unavailable(failure.reason, failure.detail)

    def _transport(self) -> ChatTransport:
        assert self.transport is not None  # __post_init__ builds one
        return self.transport

    @property
    def attempts(self) -> int:
        """How many requests the **last** call made. What the retry suite asserts.

        Reset at the start of every call rather than accumulated, because the
        requirement is about one generation — *"at most three attempts SHALL be
        made in total"* — and a counter that grew across calls would make the
        second assertion in a suite pass for the wrong reason.
        """
        return len(self.attempts_made)


def _absence(settings: ModelSettings) -> Unavailability:
    """Off is `disabled`; on but incomplete is `misconfigured`.

    The distinction `llm-integration` requires in so many words — *"the reason
    distinguishing at least disabled, misconfigured, unreachable and rejected"* —
    and it is the actionable one: a deployment that never enabled this is
    working as intended, and one that enabled it and set nothing else is a
    deployment somebody has to finish.
    """
    return Unavailability.DISABLED if not settings.enabled else Unavailability.MISCONFIGURED


__all__ = ["OpenAICompatibleModels"]
