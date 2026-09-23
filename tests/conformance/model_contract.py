"""What every model port SHALL do, whoever implements it (tasks 1.3, 2.5).

The asymmetry is the usual one and it matters more here than anywhere: every
model-backed test in this repository runs against the in-memory fake, so a fake
that answered differently from the real adapter would be a green build over a
feature nobody had exercised. And the *real* adapter is exercised without a
network, because a stub HTTP client is where its behaviour ends — the contract
is about the port, not about a gateway.

Four properties, each a sentence of `llm-integration`:

* **text comes back with the model that produced it**, because provenance
  records the identifier on every derived row;
* **an image request carries the image**, and the implementation can say what it
  was shown;
* **no model failure raises** — every one of the six reasons is a returned
  value, for both ports;
* **the reasons are the same six everywhere**, so a surface rendering the
  distinction cannot meet a seventh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol

import pytest

from cybercanon.adapters.outbound.openai_compatible.config import ModelSettings
from cybercanon.adapters.outbound.openai_compatible.models import OpenAICompatibleModels
from cybercanon.adapters.outbound.openai_compatible.transport import ChatTransport
from cybercanon.application.ports.llm import ModelUnavailable, Unavailability, answered
from cybercanon.application.testing.llm import InMemoryLLM
from cybercanon.application.testing.vision import InMemoryVision

ANSWER = "a light reconnaissance walker"
INSTRUCTION = "describe this concept art"
PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"

MODEL = "chat-v1"
VISION_MODEL = "vision-v1"


class Models(Protocol):
    """One implementation of both ports, plus the seams a contract needs.

    `working` answers; `refusing` is unavailable for a named reason; `shown` is
    what actually reached the implementation. All three exist on the fake and on
    the real adapter, so the same body runs over both.
    """

    def working(self) -> Any: ...

    def refusing(self, reason: Unavailability) -> Any: ...

    def shown(self, models: Any) -> list[bytes]: ...


# --------------------------------------------------------------------------
# The fake
# --------------------------------------------------------------------------


@dataclass
class Pair:
    """The two fakes, presented as one implementation of both ports."""

    text: InMemoryLLM
    vision: InMemoryVision

    def complete(self, instruction: str) -> Any:
        return self.text.complete(instruction)

    def describe(self, image: bytes, instruction: str) -> Any:
        return self.vision.describe(image, instruction)


class FakeModels:
    """The in-memory ports, behind the contract's three seams."""

    def working(self) -> Pair:
        text, vision = InMemoryLLM(model=MODEL), InMemoryVision(model=VISION_MODEL)
        text.always_answers(ANSWER)
        vision.always_answers(ANSWER)
        return Pair(text=text, vision=vision)

    def refusing(self, reason: Unavailability) -> Pair:
        text, vision = InMemoryLLM(model=MODEL), InMemoryVision(model=VISION_MODEL)
        text.always_refuses(reason)
        vision.always_refuses(reason)
        return Pair(text=text, vision=vision)

    def shown(self, models: Pair) -> list[bytes]:
        return models.vision.images


# --------------------------------------------------------------------------
# The real adapter, over a stub client
# --------------------------------------------------------------------------


@dataclass
class Stub:
    """A stand-in HTTP client: one canned answer, and what it was sent."""

    status: int = 200
    body: Any = None
    raises: Exception | None = None
    sent: list[dict[str, Any]] = field(default_factory=list)

    def request(self, method: str, url: str, **options: Any) -> Any:
        self.sent.append(options)
        if self.raises is not None:
            raise self.raises
        return self

    @property
    def status_code(self) -> int:
        return self.status

    def json(self) -> Any:
        if self.body is None:
            raise ValueError("not json")
        return self.body


class Timeout(Exception):
    """Named as a client's timeout is — the transport matches by name."""


def _completion(text: str = ANSWER) -> Any:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


REAL_FAILURES = {
    Unavailability.DISABLED: ("settings", {"enabled": False}),
    Unavailability.MISCONFIGURED: ("settings", {"model": "", "vision_model": ""}),
    Unavailability.UNREACHABLE: ("client", Stub(raises=OSError("no route"))),
    Unavailability.REJECTED: ("client", Stub(status=401)),
    Unavailability.TIMEOUT: ("client", Stub(raises=Timeout("too slow"))),
    Unavailability.MALFORMED: ("client", Stub(status=200, body={"choices": []})),
}
"""How each reason is produced against the real adapter, one condition each."""


class RealModels:
    """`OpenAICompatibleModels` over a stub client — no socket, real behaviour."""

    def working(self) -> OpenAICompatibleModels:
        return self._built(Stub(status=200, body=_completion()))

    def refusing(self, reason: Unavailability) -> OpenAICompatibleModels:
        kind, value = REAL_FAILURES[reason]
        if kind == "settings":
            return self._built(Stub(status=200, body=_completion()), **value)
        return self._built(value)

    def shown(self, models: OpenAICompatibleModels) -> list[bytes]:
        """What reached the endpoint, recovered from the request that went out."""
        import base64

        found: list[bytes] = []
        for body in models.transport.sent:
            for message in body["messages"]:
                for part in message["content"] if isinstance(message["content"], list) else []:
                    if part["type"] == "image_url":
                        found.append(base64.b64decode(part["image_url"]["url"].split(",", 1)[1]))
        return found

    def _built(self, client: Stub, **overrides: Any) -> OpenAICompatibleModels:
        declared = {
            "enabled": True,
            "base_url": "https://gateway.internal/v1",
            "api_key": "a-key",
            "model": MODEL,
            "vision_model": VISION_MODEL,
            "timeout": timedelta(seconds=5),
            "max_retries": 0,
        }
        settings = ModelSettings(**{**declared, **overrides})
        return OpenAICompatibleModels(
            settings=settings,
            transport=ChatTransport(
                base_url=settings.api_root,
                api_key=settings.api_key,
                timeout=settings.timeout,
                client=client,
            ),
        )


class ModelContract:
    """The body every model implementation runs through."""

    def test_a_completion_returns_the_text(self, implementation: Models) -> None:
        answer = implementation.working().complete(INSTRUCTION)

        assert answered(answer)
        assert answer.text == ANSWER

    def test_an_answer_names_the_model_that_produced_it(self, implementation: Models) -> None:
        """Provenance records it on every derived row, so it has to come back."""
        assert implementation.working().complete(INSTRUCTION).model == MODEL

    def test_describing_an_image_returns_the_text(self, implementation: Models) -> None:
        answer = implementation.working().describe(PNG, INSTRUCTION)

        assert answered(answer)
        assert answer.text == ANSWER

    def test_the_image_is_what_reached_the_implementation(self, implementation: Models) -> None:
        models = implementation.working()

        models.describe(PNG, INSTRUCTION)

        assert implementation.shown(models) == [PNG]

    def test_a_vision_answer_names_the_vision_model(self, implementation: Models) -> None:
        assert implementation.working().describe(PNG, INSTRUCTION).model == VISION_MODEL

    @pytest.mark.parametrize("reason", list(Unavailability), ids=str)
    def test_every_reason_comes_back_as_a_value(
        self, implementation: Models, reason: Unavailability
    ) -> None:
        answer = implementation.refusing(reason).complete(INSTRUCTION)

        assert isinstance(answer, ModelUnavailable)
        assert answer.reason is reason

    @pytest.mark.parametrize("reason", list(Unavailability), ids=str)
    def test_no_reason_raises_out_of_either_port(
        self, implementation: Models, reason: Unavailability
    ) -> None:
        models = implementation.refusing(reason)

        assert not answered(models.complete(INSTRUCTION))
        assert not answered(models.describe(PNG, INSTRUCTION))

    def test_an_unavailable_answer_states_its_reason(self, implementation: Models) -> None:
        answer = implementation.refusing(Unavailability.REJECTED).complete(INSTRUCTION)

        assert str(Unavailability.REJECTED) in answer.message
