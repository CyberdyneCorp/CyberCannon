"""Tasks 1.1-1.3 — the two model ports, their six reasons, and their fakes.

`llm-integration` requires that *"model-backed features SHALL be testable with
no endpoint reachable"* and that every failure *"degrades identically"*. Both
are properties of the port's return type rather than of a caller's discipline,
so this suite is about the type.
"""

from __future__ import annotations

import inspect

import pytest

from cybercanon.application.ports.llm import (
    Completion,
    DisabledLLM,
    LLMPort,
    ModelUnavailable,
    Unavailability,
    answered,
    unavailable,
)
from cybercanon.application.ports.vision import DisabledVision, VisionPort
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.llm import EVERY_REASON, InMemoryLLM, answering, refusing
from cybercanon.application.testing.vision import InMemoryVision, describing, refusing_vision

pytestmark = pytest.mark.unit

FORBIDDEN_PARAMETERS = ("endpoint", "base_url", "url", "api_key", "credential", "token", "model")
"""Names a provider detail would arrive under. The port has none of them."""


# --------------------------------------------------------------------------
# 1.2 — the six reasons, closed and each meaning something different
# --------------------------------------------------------------------------


def test_the_six_reasons_are_exactly_what_the_specification_names() -> None:
    assert Unavailability.values() == (
        "disabled",
        "misconfigured",
        "unreachable",
        "rejected",
        "timeout",
        "malformed",
    )


@pytest.mark.parametrize("reason", EVERY_REASON, ids=str)
def test_every_reason_is_a_value_a_caller_receives(reason: Unavailability) -> None:
    """Not an exception. Forgetting to handle one is visible, not the default."""
    answer = refusing(reason).complete("anything")

    assert isinstance(answer, ModelUnavailable)
    assert not answered(answer)
    assert answer.reason is reason


@pytest.mark.parametrize("reason", EVERY_REASON, ids=str)
def test_every_reason_states_itself_in_the_sentence_a_person_reads(
    reason: Unavailability,
) -> None:
    """*"the system SHALL state the reason"* — so the reason is in the message."""
    assert str(reason) in unavailable(reason).message


def test_only_a_missing_endpoint_and_a_spent_budget_are_worth_trying_again() -> None:
    transient = {reason for reason in EVERY_REASON if reason.is_transient}

    assert transient == {Unavailability.UNREACHABLE, Unavailability.TIMEOUT}


def test_an_answer_and_a_refusal_read_as_a_boolean_the_same_way() -> None:
    assert bool(Completion(text="something"))
    assert not bool(unavailable(Unavailability.DISABLED))


# --------------------------------------------------------------------------
# 1.2 — no model failure propagates as an exception
# --------------------------------------------------------------------------


@pytest.mark.parametrize("reason", EVERY_REASON, ids=str)
def test_no_failure_raises_out_of_either_port(reason: Unavailability) -> None:
    text = refusing(reason).complete("describe this")
    image = refusing_vision(reason).describe(b"\x89PNG", "describe this")

    assert not answered(text)
    assert not answered(image)


# --------------------------------------------------------------------------
# 1.2 — provider details are not reachable through the port
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("port", "method"), [(LLMPort, "complete"), (VisionPort, "describe")], ids=["llm", "vision"]
)
def test_no_provider_detail_is_a_parameter_of_either_port(port: type, method: str) -> None:
    """A use case cannot observe the endpoint, the credential or the model."""
    parameters = set(inspect.signature(getattr(port, method)).parameters) - {"self"}

    assert not parameters & set(FORBIDDEN_PARAMETERS)


def test_an_answer_carries_the_model_that_produced_it_for_provenance() -> None:
    """Carried, never interpreted: `derived-metadata` records it on every row."""
    answer = answering("something", model="qwen3-vl").complete("anything")

    assert answered(answer)
    assert answer.model == "qwen3-vl"


# --------------------------------------------------------------------------
# 1.3 — the fakes, and the null adapters
# --------------------------------------------------------------------------


def test_the_disabled_ports_answer_disabled_rather_than_failing() -> None:
    """*"The system SHALL be fully usable with it off"*, as one wiring decision."""
    text = DisabledLLM().complete("anything")
    image = DisabledVision().describe(b"\x89PNG", "anything")

    assert text.reason is Unavailability.DISABLED
    assert image.reason is Unavailability.DISABLED


def test_both_fakes_are_built_through_the_one_registry() -> None:
    built = build_fakes()

    assert isinstance(built["llm"], InMemoryLLM)
    assert isinstance(built["vision"], InMemoryVision)


def test_the_text_fake_records_what_it_was_actually_asked() -> None:
    fake = answering("done")

    fake.complete("first")
    fake.complete("second")

    assert fake.sent == ("first", "second")
    assert fake.calls == 2


def test_the_vision_fake_records_the_bytes_it_was_shown() -> None:
    fake = describing("a walker")

    fake.describe(b"\x89PNG-bytes", "describe this")

    assert fake.images == [b"\x89PNG-bytes"]
    assert fake.instructions == ["describe this"]


def test_a_queued_answer_is_used_once_and_then_the_standing_one() -> None:
    fake = InMemoryLLM()
    fake.always_answers("standing")
    fake.will_answer("queued")

    assert fake.complete("a").text == "queued"
    assert fake.complete("b").text == "standing"


def test_a_fake_given_nothing_to_say_says_so_rather_than_inventing() -> None:
    assert InMemoryLLM().complete("a").reason is Unavailability.MALFORMED
