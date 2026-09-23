"""The adapter against a **real** OpenAI-compatible endpoint — opt-in, never required.

Task 7.3 asks for *"an opt-in integration suite runnable against any configured
compatible endpoint"*, and the design says why it is worth having: *"a compatible
endpoint is compatible only in name (subtle differences in multimodal message
formatting are the usual offender)"*. A conformance suite over a stub proves the
adapter is self-consistent; it cannot prove the stub is right, and the multimodal
message is exactly the shape nobody can check by reading a client.

**It is opt-in and skips cleanly.** With `CANON_LLM_ENABLED` unset — the default
everywhere — `just check` behaves identically on a machine that has never seen a
gateway, which is the same rule the whole integration follows: absent
configuration is a feature being off, never a broken build. No credential is
read from, written to, or defaulted inside this repository.

Set the environment the product already reads (or `source` a file that does):

    CANON_LLM_ENABLED=true
    CANON_LLM_BASE_URL     any OpenAI-compatible endpoint, `/v1` included
    CANON_LLM_API_KEY      its bearer credential, if it wants one
    CANON_LLM_MODEL        a text model identifier
    CANON_LLM_VISION_MODEL a multimodal model identifier

What it checks is the half a stub cannot, and it is deliberately about *this
system's* requirements rather than about the model's taste:

* a completion really comes back, and really names the model that produced it;
* the **multimodal message** this adapter builds is really accepted — the one
  shape a "compatible" endpoint is most likely to differ on;
* the alias answer really parses into normalised terms, which is the whole
  feature working end to end against a real model;
* a **wrong credential** is really refused rather than retried, so the retry
  rule is checked against a real gateway's status codes;
* an **unknown model identifier** is really passed through and really rejected
  by the endpoint rather than by us — the proof that identifiers are opaque.
"""

from __future__ import annotations

import os

import pytest

from cybercanon.adapters.outbound.openai_compatible.config import (
    ModelSettings,
    settings_from,
)
from cybercanon.adapters.outbound.openai_compatible.models import OpenAICompatibleModels
from cybercanon.application.ports.llm import Unavailability, answered
from cybercanon.application.use_cases.prompts import DESCRIBE_IMAGE, SUGGEST_ALIASES
from cybercanon.domain.derived import is_normalised, normalised_aliases, parse_aliases

pytestmark = pytest.mark.integration

INSTRUCTION = "Answer with the single word: ready"
"""The smallest question that proves a text completion round-tripped."""

UNKNOWN_MODEL = "a-model-that-does-not-exist-2099"
"""Passed through verbatim. The endpoint refuses it; this system never does."""


def _settings() -> ModelSettings:
    settings = settings_from(os.environ)
    if not settings.is_complete:
        pytest.skip(
            "no model endpoint in the environment "
            f"({', '.join(settings.missing)} unset); this suite is opt-in"
        )
    return settings


@pytest.fixture(scope="module")
def settings() -> ModelSettings:
    return _settings()


@pytest.fixture(scope="module")
def models(settings: ModelSettings) -> OpenAICompatibleModels:
    return OpenAICompatibleModels(settings=settings)


@pytest.fixture(scope="module")
def vision(settings: ModelSettings) -> OpenAICompatibleModels:
    if not settings.vision_is_complete:
        pytest.skip("CANON_LLM_VISION_MODEL is not set; the image half is opt-in too")
    return OpenAICompatibleModels(settings=settings)


@pytest.fixture(scope="module")
def an_image() -> bytes:
    """A real PNG, written from code, so nothing binary lives in git."""
    from canon_fixtures import image as fixtures

    return fixtures.image_bytes(fixtures.PNG, 320, 240, seed=3)


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------


def test_a_completion_really_comes_back(models: OpenAICompatibleModels) -> None:
    answer = models.complete(INSTRUCTION)

    assert answered(answer), getattr(answer, "message", answer)
    assert answer.text.strip()


def test_the_answer_names_the_configured_model(
    models: OpenAICompatibleModels, settings: ModelSettings
) -> None:
    """Provenance records it on every derived row, so it has to come back."""
    answer = models.complete(INSTRUCTION)

    assert answered(answer)
    assert answer.model == settings.model


# --------------------------------------------------------------------------
# The multimodal message — the shape a "compatible" endpoint most often differs on
# --------------------------------------------------------------------------


def test_the_multimodal_message_this_adapter_builds_is_accepted(
    vision: OpenAICompatibleModels, an_image: bytes
) -> None:
    answer = vision.describe(an_image, DESCRIBE_IMAGE)

    assert answered(answer), getattr(answer, "message", answer)
    assert answer.text.strip()


def test_the_alias_answer_parses_into_normalised_terms(
    vision: OpenAICompatibleModels, an_image: bytes
) -> None:
    """The whole feature, end to end, against a real model."""
    answer = vision.describe(an_image, SUGGEST_ALIASES)
    assert answered(answer), getattr(answer, "message", answer)

    terms = parse_aliases(answer.text)

    assert terms is not None, f"the model answered something unparseable: {answer.text!r}"
    assert all(is_normalised(term) for term in normalised_aliases(terms))


# --------------------------------------------------------------------------
# Failure, against a real gateway's real status codes
# --------------------------------------------------------------------------


def test_a_refused_credential_is_rejected_and_tried_exactly_once(
    settings: ModelSettings,
) -> None:
    """The retry rule, checked against what a gateway actually answers."""
    if not settings.api_key:
        pytest.skip("this endpoint takes no credential, so none can be wrong")
    wrong = OpenAICompatibleModels(
        settings=ModelSettings(
            enabled=True,
            base_url=settings.base_url,
            api_key="not-a-valid-credential",
            model=settings.model,
            timeout=settings.timeout,
            max_retries=2,
        )
    )

    answer = wrong.complete(INSTRUCTION)

    assert answer.reason is Unavailability.REJECTED
    assert wrong.attempts == 1


def test_an_unknown_identifier_is_refused_by_the_endpoint_and_never_by_us(
    settings: ModelSettings,
) -> None:
    """*"SHALL NOT refuse an unrecognised identifier"* — the endpoint decides."""
    unknown = OpenAICompatibleModels(
        settings=ModelSettings(
            enabled=True,
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=UNKNOWN_MODEL,
            timeout=settings.timeout,
            max_retries=0,
        )
    )

    answer = unknown.complete(INSTRUCTION)

    assert not answered(answer)
    assert unknown.attempts == 1
    assert unknown.transport.sent[0]["model"] == UNKNOWN_MODEL
