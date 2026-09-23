"""Group 2 — the Chat Completions adapter: no SDK, opaque models, bounded failure.

Everything here runs against a recorder standing in for the HTTP client, so
every assertion is about **what actually went out** rather than about what the
code appears to send. That matters most for the two absences the specification
asks for: no vendor extension in the body, and no specification content in a
vision request.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from cybercanon.adapters.outbound.openai_compatible.config import ModelSettings
from cybercanon.adapters.outbound.openai_compatible.models import OpenAICompatibleModels
from cybercanon.adapters.outbound.openai_compatible.transport import (
    COMPLETIONS_PATH,
    ChatTransport,
    chat_body,
    data_uri,
    first_text,
    image_message,
    media_type,
    text_message,
)
from cybercanon.application.ports.llm import Unavailability, answered
from cybercanon.application.use_cases.prompts import DESCRIBE_IMAGE, SUGGEST_ALIASES

pytestmark = pytest.mark.unit

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"
ANSWER = "a light reconnaissance walker"

VENDOR_SDKS = ("openai", "anthropic", "google-generativeai", "litellm", "cohere", "mistralai")
"""Provider SDKs D1 forbids. Absence is asserted against the manifest, not hoped for."""


def a_settings(**overrides: Any) -> ModelSettings:
    declared = {
        "enabled": True,
        "base_url": "https://gateway.internal/v1",
        "api_key": "a-key",
        "model": "chat-v1",
        "vision_model": "vision-v1",
        "timeout": timedelta(seconds=7),
        "max_retries": 2,
    }
    return ModelSettings(**{**declared, **overrides})


@dataclass
class Recorder:
    """A stand-in HTTP client: answers what it was told, remembers what it was sent."""

    answers: list[Any] = field(default_factory=list)
    raises: Exception | None = None
    requests: list[dict[str, Any]] = field(default_factory=list)

    def request(self, method: str, url: str, **options: Any) -> Any:
        self.requests.append({"method": method, "url": url, **options})
        if self.raises is not None:
            raise self.raises
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    @property
    def attempts(self) -> int:
        return len(self.requests)

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [request["json"] for request in self.requests]


@dataclass
class Reply:
    """One HTTP answer a recorder hands back."""

    status_code: int = 200
    body: Any = None

    def json(self) -> Any:
        if self.body is None:
            raise ValueError("not json")
        return self.body


def a_completion(text: str = ANSWER) -> Reply:
    return Reply(200, {"choices": [{"message": {"role": "assistant", "content": text}}]})


def models(recorder: Recorder, **overrides: Any) -> OpenAICompatibleModels:
    settings = a_settings(**overrides)
    return OpenAICompatibleModels(
        settings=settings,
        transport=ChatTransport(
            base_url=settings.api_root,
            api_key=settings.api_key,
            timeout=settings.timeout,
            client=recorder,
        ),
    )


# --------------------------------------------------------------------------
# 2.1 — no provider SDK anywhere
# --------------------------------------------------------------------------


def test_no_vendor_sdk_is_declared_as_a_dependency(repo_root: Path) -> None:
    """D1: an SDK would quietly make the on-prem gateway a second-class target."""
    manifest = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = manifest["project"]["dependencies"] + manifest["dependency-groups"]["dev"]
    names = {entry.split(">")[0].split("[")[0].split("=")[0].strip() for entry in declared}

    assert not names & set(VENDOR_SDKS)


def test_the_adapter_imports_no_vendor_sdk(repo_root: Path) -> None:
    package = repo_root / "libs" / "cybercanon" / "adapters" / "outbound" / "openai_compatible"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))

    assert not [sdk for sdk in VENDOR_SDKS if f"import {sdk}" in source]


# --------------------------------------------------------------------------
# 2.2 — the identifier is passed through verbatim, and nothing branches on it
# --------------------------------------------------------------------------


def test_two_identifiers_produce_requests_differing_only_in_that_field() -> None:
    first, second = Recorder([a_completion()]), Recorder([a_completion()])

    models(first, model="chat-v1").complete("describe this")
    models(second, model="a-model-nobody-has-heard-of").complete("describe this")

    (one,), (two,) = first.bodies, second.bodies
    assert one["model"] == "chat-v1"
    assert two["model"] == "a-model-nobody-has-heard-of"
    assert {key: value for key, value in one.items() if key != "model"} == {
        key: value for key, value in two.items() if key != "model"
    }


def test_an_unrecognised_identifier_is_sent_unchanged() -> None:
    recorder = Recorder([a_completion()])

    models(recorder, model="qwen4-omni-2027").complete("anything")

    assert recorder.bodies[0]["model"] == "qwen4-omni-2027"


def test_the_body_carries_the_documented_minimum_and_no_vendor_extension() -> None:
    """A field some compatible proxy answers 400 to is a field this never sends."""
    recorder = Recorder([a_completion()])

    models(recorder).complete("anything")

    assert set(recorder.bodies[0]) == {"model", "messages"}


def test_the_request_goes_to_the_one_path_this_system_speaks() -> None:
    recorder = Recorder([a_completion()])

    models(recorder).complete("anything")

    assert recorder.requests[0]["url"] == f"https://gateway.internal/v1{COMPLETIONS_PATH}"
    assert recorder.requests[0]["timeout"] == 7.0


def test_the_credential_travels_as_a_bearer_header() -> None:
    recorder = Recorder([a_completion()])

    models(recorder).complete("anything")

    assert recorder.requests[0]["headers"]["Authorization"] == "Bearer a-key"


def test_no_credential_means_no_header_rather_than_an_empty_one() -> None:
    recorder = Recorder([a_completion()])

    models(recorder, api_key="").complete("anything")

    assert "Authorization" not in recorder.requests[0]["headers"]


# --------------------------------------------------------------------------
# 2.3 — a vision request carries the image and the instruction, and nothing else
# --------------------------------------------------------------------------


def test_an_image_request_transmits_only_the_image_and_a_fixed_instruction() -> None:
    recorder = Recorder([a_completion()])

    models(recorder).describe(PNG, DESCRIBE_IMAGE)

    (body,) = recorder.bodies
    (message,) = body["messages"]
    kinds = [part["type"] for part in message["content"]]
    assert kinds == ["image_url", "text"]
    assert message["content"][0]["image_url"]["url"] == data_uri(PNG)
    assert message["content"][1]["text"] == DESCRIBE_IMAGE


@pytest.mark.parametrize("instruction", [DESCRIBE_IMAGE, SUGGEST_ALIASES])
def test_no_specification_content_can_reach_the_endpoint(instruction: str) -> None:
    """The scope is the image and the instruction; the rest is not a parameter."""
    recorder = Recorder([a_completion()])

    models(recorder).describe(PNG, instruction)

    sent = json.dumps(recorder.bodies[0])
    for leak in ("mech_scout", "asset.yaml", "tri_budget", "SOCKET_", "owner_art"):
        assert leak not in sent


def test_the_vision_request_uses_the_separately_configured_identifier() -> None:
    recorder = Recorder([a_completion()])

    models(recorder).describe(PNG, DESCRIBE_IMAGE)

    assert recorder.bodies[0]["model"] == "vision-v1"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff\xe0", "image/jpeg"),
        (b"GIF89a", "image/gif"),
        (b"RIFF....WEBP", "image/webp"),
        (b"not an image", "application/octet-stream"),
    ],
)
def test_the_media_type_is_read_from_the_bytes_never_from_a_name(
    content: bytes, expected: str
) -> None:
    assert media_type(content) == expected


# --------------------------------------------------------------------------
# 2.4 — the timeout and the retry budget
# --------------------------------------------------------------------------


def test_a_transient_failure_is_retried_up_to_the_budget() -> None:
    """*"a retry budget of two ... at most three attempts SHALL be made in total"*."""
    recorder = Recorder([Reply(503, None)])

    answer = models(recorder, max_retries=2).complete("anything")

    assert recorder.attempts == 3
    assert answer.reason is Unavailability.UNREACHABLE


def test_a_rate_limit_is_transient_and_degrades_like_everything_else() -> None:
    recorder = Recorder([Reply(429, None)])

    answer = models(recorder, max_retries=1).complete("anything")

    assert recorder.attempts == 2
    assert not answered(answer)


def test_an_authentication_failure_is_tried_exactly_once() -> None:
    recorder = Recorder([Reply(401, None)])

    answer = models(recorder, max_retries=2).complete("anything")

    assert recorder.attempts == 1
    assert answer.reason is Unavailability.REJECTED


def test_an_invalid_request_is_tried_exactly_once() -> None:
    recorder = Recorder([Reply(400, None)])

    answer = models(recorder, max_retries=2).complete("anything")

    assert recorder.attempts == 1
    assert answer.reason is Unavailability.REJECTED


def test_a_timeout_is_tried_up_to_the_budget_and_reported_as_a_timeout() -> None:
    recorder = Recorder(raises=ReadTimeout("too slow"))

    answer = models(recorder, max_retries=2).complete("anything")

    assert recorder.attempts == 3
    assert answer.reason is Unavailability.TIMEOUT


def test_a_transient_failure_that_then_succeeds_costs_only_the_attempts_it_took() -> None:
    recorder = Recorder([Reply(503, None), a_completion(), a_completion()])

    answer = models(recorder, max_retries=2).complete("anything")

    assert answered(answer)
    assert recorder.attempts == 2


def test_the_attempt_count_is_about_one_call_and_not_the_whole_session() -> None:
    recorder = Recorder([a_completion()])
    adapter = models(recorder)

    adapter.complete("first")
    adapter.complete("second")

    assert adapter.attempts == 1


class ReadTimeout(Exception):
    """Named as a client's timeout would be — matched by name, not by class."""


# --------------------------------------------------------------------------
# 2.5 — every reason is produced by its own condition
# --------------------------------------------------------------------------


def test_disabled_configuration_is_disabled_and_never_a_request() -> None:
    recorder = Recorder([a_completion()])

    answer = models(recorder, enabled=False).complete("anything")

    assert answer.reason is Unavailability.DISABLED
    assert recorder.attempts == 0


def test_incomplete_configuration_is_misconfigured_and_never_a_request() -> None:
    """On but unfinished is a deployment somebody has to complete, not an outage."""
    recorder = Recorder([a_completion()])

    answer = models(recorder, base_url="", model="").complete("anything")

    assert answer.reason is Unavailability.MISCONFIGURED
    assert recorder.attempts == 0


def test_a_missing_vision_identifier_disables_only_vision() -> None:
    recorder = Recorder([a_completion()])
    adapter = models(recorder, vision_model="")

    assert answered(adapter.complete("anything"))
    assert adapter.describe(PNG, DESCRIBE_IMAGE).reason is Unavailability.MISCONFIGURED


def test_an_unreachable_endpoint_is_unreachable() -> None:
    answer = models(Recorder(raises=OSError("no route"))).complete("anything")

    assert answer.reason is Unavailability.UNREACHABLE


def test_an_answer_this_adapter_cannot_read_is_malformed() -> None:
    answer = models(Recorder([Reply(200, {"choices": []})])).complete("anything")

    assert answer.reason is Unavailability.MALFORMED


def test_a_successful_answer_that_is_not_json_is_malformed() -> None:
    answer = models(Recorder([Reply(200, None)])).complete("anything")

    assert answer.reason is Unavailability.MALFORMED


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "a string",
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": 4}}]},
    ],
)
def test_reading_an_answer_is_defensive(payload: Any) -> None:
    assert first_text(payload) is None


def test_every_reason_is_produced_by_some_condition() -> None:
    """All six, each by its own cause — none of them unreachable in practice."""
    produced = {
        models(Recorder([a_completion()]), enabled=False).complete("a").reason,
        models(Recorder([a_completion()]), model="").complete("a").reason,
        models(Recorder(raises=OSError("x"))).complete("a").reason,
        models(Recorder([Reply(401, None)])).complete("a").reason,
        models(Recorder(raises=ReadTimeout("x"))).complete("a").reason,
        models(Recorder([Reply(200, {"choices": []})])).complete("a").reason,
    }

    assert produced == set(Unavailability)


# --------------------------------------------------------------------------
# The body builders, on their own
# --------------------------------------------------------------------------


def test_a_text_message_is_one_user_turn() -> None:
    assert text_message("hello") == {"role": "user", "content": "hello"}


def test_the_body_places_the_model_and_one_message() -> None:
    body = chat_body("m", text_message("hello"))

    assert body == {"model": "m", "messages": [{"role": "user", "content": "hello"}]}


def test_an_image_message_carries_a_data_uri_naming_its_own_type() -> None:
    message = image_message(PNG, "look")

    assert message["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
