"""The in-memory `LLMPort` — scripted answers, and a record of what was asked.

`llm-integration` requires that *"model-backed features SHALL be testable with
no endpoint reachable"*, so this is not a convenience: it is the substitute the
requirement names, and every use case above the port is exercised against it
with no network anywhere.

Two properties it has that a mock would not:

* **It records what was actually sent.** `instructions` is what reached the
  port, which is how the scope requirement is asserted against the traffic
  rather than against what the code appears to send.
* **It can be every failure.** :func:`refusing` builds one for each of the six
  reasons, so *"every failure degrades identically"* is exercised six times by
  parametrisation instead of once by the reason somebody happened to pick.
"""

from __future__ import annotations

from collections.abc import Sequence

from cybercanon.application.ports.llm import (
    Completion,
    ModelAnswer,
    ModelUnavailable,
    Unavailability,
    unavailable,
)

FAKE_MODEL = "fake-text-v1"
"""The identifier this fake echoes back. Opaque, like every other identifier."""


class InMemoryLLM:
    """Answers whatever it was told to answer, and remembers what it was asked."""

    def __init__(self, model: str = FAKE_MODEL) -> None:
        self.model = model
        self.instructions: list[str] = []
        self._queued: list[ModelAnswer] = []
        self._standing: ModelAnswer | None = None

    # -- arranging -------------------------------------------------------

    def will_answer(self, *texts: str) -> None:
        """Queue one answer per call, in order. A test's ordinary arrangement."""
        self._queued.extend(Completion(text=text, model=self.model) for text in texts)

    def always_answers(self, text: str) -> None:
        """Answer the same thing however many times it is called."""
        self._standing = Completion(text=text, model=self.model)

    def will_refuse(self, reason: Unavailability, detail: str = "") -> None:
        """Queue one refusal — the next call is unavailable for that reason."""
        self._queued.append(unavailable(reason, detail))

    def always_refuses(self, reason: Unavailability, detail: str = "") -> None:
        """Be unavailable for that reason, permanently. What a disabled model is."""
        self._standing = unavailable(reason, detail)

    # -- the port --------------------------------------------------------

    def complete(self, instruction: str) -> ModelAnswer:
        self.instructions.append(instruction)
        if self._queued:
            return self._queued.pop(0)
        if self._standing is not None:
            return self._standing
        return unavailable(Unavailability.MALFORMED, "this fake was given no answer to give")

    # -- what happened ---------------------------------------------------

    @property
    def calls(self) -> int:
        """How many times a model was asked. Zero is what most tests assert."""
        return len(self.instructions)

    @property
    def sent(self) -> Sequence[str]:
        return tuple(self.instructions)


def refusing(reason: Unavailability, detail: str = "") -> InMemoryLLM:
    """An `LLMPort` that is unavailable for exactly that reason, every time."""
    fake = InMemoryLLM()
    fake.always_refuses(reason, detail)
    return fake


def answering(text: str, model: str = FAKE_MODEL) -> InMemoryLLM:
    """An `LLMPort` that always answers the same text."""
    fake = InMemoryLLM(model=model)
    fake.always_answers(text)
    return fake


EVERY_REASON: tuple[Unavailability, ...] = tuple(Unavailability)
"""Every way a model can fail to answer, for a parametrised suite to walk."""


def every_refusal() -> tuple[ModelUnavailable, ...]:
    """One refusal per reason, in declaration order."""
    return tuple(unavailable(reason) for reason in EVERY_REASON)


__all__ = [
    "EVERY_REASON",
    "FAKE_MODEL",
    "InMemoryLLM",
    "answering",
    "every_refusal",
    "refusing",
]
