"""The in-memory `VisionPort` — scripted descriptions, and the bytes it was given.

The half of the substitute that matters here is `images`: the scope requirement
is about what is *transmitted*, so a test asserts against the bytes that reached
the port and the instruction beside them, and nothing else can have reached it
because nothing else is a parameter.
"""

from __future__ import annotations

from cybercanon.application.ports.llm import (
    Completion,
    ModelAnswer,
    Unavailability,
    unavailable,
)

FAKE_VISION_MODEL = "fake-vision-v1"
"""The identifier this fake echoes back into provenance."""


class InMemoryVision:
    """Describes an image with whatever it was told, and keeps what it was shown."""

    def __init__(self, model: str = FAKE_VISION_MODEL) -> None:
        self.model = model
        self.images: list[bytes] = []
        self.instructions: list[str] = []
        self._queued: list[ModelAnswer] = []
        self._standing: ModelAnswer | None = None

    # -- arranging -------------------------------------------------------

    def will_answer(self, *texts: str) -> None:
        self._queued.extend(Completion(text=text, model=self.model) for text in texts)

    def always_answers(self, text: str) -> None:
        self._standing = Completion(text=text, model=self.model)

    def will_refuse(self, reason: Unavailability, detail: str = "") -> None:
        self._queued.append(unavailable(reason, detail))

    def always_refuses(self, reason: Unavailability, detail: str = "") -> None:
        self._standing = unavailable(reason, detail)

    # -- the port --------------------------------------------------------

    def describe(self, image: bytes, instruction: str) -> ModelAnswer:
        self.images.append(image)
        self.instructions.append(instruction)
        if self._queued:
            return self._queued.pop(0)
        if self._standing is not None:
            return self._standing
        return unavailable(Unavailability.MALFORMED, "this fake was given no answer to give")

    # -- what happened ---------------------------------------------------

    @property
    def calls(self) -> int:
        return len(self.images)


def refusing_vision(reason: Unavailability, detail: str = "") -> InMemoryVision:
    """A `VisionPort` unavailable for exactly that reason, every time."""
    fake = InMemoryVision()
    fake.always_refuses(reason, detail)
    return fake


def describing(text: str, model: str = FAKE_VISION_MODEL) -> InMemoryVision:
    """A `VisionPort` that always answers the same description."""
    fake = InMemoryVision(model=model)
    fake.always_answers(text)
    return fake


__all__ = ["FAKE_VISION_MODEL", "InMemoryVision", "describing", "refusing_vision"]
