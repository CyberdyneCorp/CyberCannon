"""The `VisionPort` — a description of one image, or the reason there is none (D2).

Two ports rather than one, and the reason is a state rather than a taste: *"the
vision model identifier is separately configured, and a deployment may have text
without vision"*. Two ports make **vision unavailable, text available** a
representable state instead of a special case buried inside one method — and the
composition root can hand out :class:`DisabledVision` beside a working
:class:`~cybercanon.application.ports.llm.LLMPort` with nothing above it
noticing.

The signature carries the scope requirement (`llm-integration`, *"Content sent
to a model is recorded in scope"*) in the only way that survives review: the
method takes **the image bytes and an instruction**, and there is no parameter a
specification, an annotation or an export could travel through. A caller that
wanted to send one would have to change this file, which is a change somebody
reads.

The answer vocabulary is
:mod:`cybercanon.application.ports.llm`'s — one :class:`ModelAnswer`, one set of
six reasons — because a second vocabulary would mean two ways of saying *the
model is unavailable* and two renderings of the same sentence.
"""

from __future__ import annotations

from typing import Protocol

from cybercanon.application.ports.llm import (
    DISABLED_DETAIL,
    ModelAnswer,
    Unavailability,
    unavailable,
)


class VisionPort(Protocol):
    """Describing one image, with nothing else transmittable through it."""

    def describe(self, image: bytes, instruction: str) -> ModelAnswer:
        """Answer this instruction about these bytes, or say why there is no answer.

        `image` is the concept view verbatim and `instruction` is a fixed prompt
        the adapter holds; nothing else reaches the endpoint. Never raises for a
        model failure — see :class:`~cybercanon.application.ports.llm.LLMPort`.
        """
        ...


class DisabledVision:
    """The null adapter for image description. No vision model is configured."""

    def describe(self, image: bytes, instruction: str) -> ModelAnswer:
        return unavailable(Unavailability.DISABLED, DISABLED_DETAIL)


__all__ = ["DisabledVision", "VisionPort"]
