"""Step definitions for `llm-integration` — one wire format, and total degradation.

The arrangement is the real adapter over a recorder standing in for the HTTP
client, so every assertion about a request is an assertion about **what went
out**. The two scenarios that assert an absence are the ones worth reading
twice: the body carries no vendor extension, and an image request carries no
specification content — both checked against the recorded request rather than
against the code that wrote it.

The degradation scenarios run over the in-memory ports instead, because that is
what `llm-integration` asks for in so many words: *"model-backed features SHALL
be testable with no endpoint reachable"*.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.adapters.outbound.openai_compatible.config import ModelSettings
from cybercanon.adapters.outbound.openai_compatible.models import OpenAICompatibleModels
from cybercanon.adapters.outbound.openai_compatible.transport import ChatTransport
from cybercanon.application.ports.llm import (
    DisabledLLM,
    Unavailability,
    answered,
)
from cybercanon.application.ports.vision import DisabledVision
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.vision import describing
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.prompts import DESCRIBE_IMAGE
from derived_world import SCOUT, SCOUT_SPEC, a_derived_world

ANSWER = "a light reconnaissance walker"
PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"

EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

FIRST_ENDPOINT = "https://gateway.one/v1"
SECOND_ENDPOINT = "https://gateway.two/v1"

SPECIFICATION_WORDS = ("mech_scout", "asset.yaml", "tri_budget", "SOCKET_", "owner_art")
"""Words that would mean specification content reached a model. None may appear."""


@dataclass
class Recorder:
    """A stand-in HTTP client: answers what it was told, remembers what it was sent."""

    status: int = 200
    body: Any = None
    raises: Exception | None = None
    sent: list[dict[str, Any]] = field(default_factory=list)

    def request(self, method: str, url: str, **options: Any) -> Any:
        self.sent.append({"url": url, **options})
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

    @property
    def attempts(self) -> int:
        return len(self.sent)

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [request["json"] for request in self.sent]


class Timeout(Exception):
    """Named as a client's timeout is — the transport matches by name, not by class."""


def a_completion(text: str = ANSWER) -> Any:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def built(recorder: Recorder, **overrides: Any) -> OpenAICompatibleModels:
    """The real adapter over that recorder, configured as a deployment would be."""
    declared: dict[str, Any] = {
        "enabled": True,
        "base_url": FIRST_ENDPOINT,
        "api_key": "a-key",
        "model": "chat-v1",
        "vision_model": "vision-v1",
        "timeout": timedelta(seconds=5),
        "max_retries": 2,
    }
    settings = ModelSettings(**{**declared, **overrides})
    return OpenAICompatibleModels(
        settings=settings,
        transport=ChatTransport(
            base_url=settings.api_root,
            api_key=settings.api_key,
            timeout=settings.timeout,
            client=recorder,
        ),
    )


@pytest.fixture
def models() -> dict[str, Any]:
    """Whatever this scenario arranged, and whatever it produced."""
    return {}


# --------------------------------------------------------------------------
# Rule: One wire protocol
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Endpoint substituted without code change",
)
def test_endpoint_substituted_without_code_change() -> None: ...


@given("a deployment configured against one compatible endpoint")
def _one_endpoint(models: dict[str, Any]) -> None:
    models["first"] = Recorder(body=a_completion())
    models["answers"] = [built(models["first"]).complete("anything")]


@when("it is reconfigured to a different compatible endpoint")
def _reconfigured(models: dict[str, Any]) -> None:
    """Configuration only. Nothing about the built artifact changes."""
    models["second"] = Recorder(body=a_completion())
    models["answers"].append(built(models["second"], base_url=SECOND_ENDPOINT).complete("anything"))


@then("all model-backed features SHALL continue to work with no change to the built artifact")
def _both_work(models: dict[str, Any]) -> None:
    first, second = models["answers"]

    assert answered(first) and answered(second)
    assert models["first"].sent[0]["url"].startswith(FIRST_ENDPOINT)
    assert models["second"].sent[0]["url"].startswith(SECOND_ENDPOINT)


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "No vendor-specific feature is required",
)
def test_no_vendor_specific_feature_is_required() -> None: ...


@given("a compatible endpoint implementing only chat completions")
def _only_chat_completions(models: dict[str, Any]) -> None:
    models["recorder"] = Recorder(body=a_completion())


@when("any model-backed feature runs")
def _any_feature_runs(models: dict[str, Any]) -> None:
    adapter = built(models["recorder"])
    models["answers"] = [adapter.complete("anything"), adapter.describe(PNG, DESCRIBE_IMAGE)]


@then("it SHALL succeed without requiring provider extensions")
def _no_extensions(models: dict[str, Any]) -> None:
    assert all(answered(answer) for answer in models["answers"])
    for body in models["recorder"].bodies:
        assert set(body) == {"model", "messages"}


# --------------------------------------------------------------------------
# Rule: Configuration comes from the environment
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Disabled by default",
)
def test_disabled_by_default() -> None: ...


@given("no model configuration in the environment")
def _empty_environment(models: dict[str, Any]) -> None:
    models["world"] = a_derived_world()
    models["world"].vision = DisabledVision()
    models["llm"] = DisabledLLM()


@when("the system starts")
def _system_starts(models: dict[str, Any]) -> None:
    models["text"] = models["llm"].complete("anything")
    models["described"] = ran(models["world"].describe())


@then("model-backed features SHALL report themselves unavailable")
def _features_unavailable(models: dict[str, Any]) -> None:
    assert models["text"].reason is Unavailability.DISABLED
    assert not models["described"].is_available
    assert str(Unavailability.DISABLED) in models["described"].reason


@then("every other feature SHALL work normally")
def _everything_else_works(models: dict[str, Any]) -> None:
    world = models["world"]

    compiled = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store))

    assert compiled.asset_id == SCOUT
    assert world.aliases() == ()


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Enabled by configuration alone",
)
def test_enabled_by_configuration_alone() -> None: ...


@given("the enable switch, endpoint, credential and model identifiers are set")
def _fully_configured(models: dict[str, Any]) -> None:
    models["recorder"] = Recorder(body=a_completion())
    models["adapter"] = built(models["recorder"])


@when("a model-backed feature is invoked")
def _feature_invoked(models: dict[str, Any]) -> None:
    models["answer"] = models["adapter"].complete("anything")


@then("it SHALL call the configured endpoint")
def _endpoint_called(models: dict[str, Any]) -> None:
    assert answered(models["answer"])
    assert models["recorder"].sent[0]["url"] == f"{FIRST_ENDPOINT}/chat/completions"


# --------------------------------------------------------------------------
# Rule: Model identifiers are opaque
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Unrecognised model accepted",
)
def test_unrecognised_model_accepted() -> None: ...


@given("a model identifier the system has never seen")
def _unknown_identifier(models: dict[str, Any]) -> None:
    models["recorder"] = Recorder(body=a_completion())
    models["identifier"] = "qwen4-omni-2099"
    models["adapter"] = built(models["recorder"], model=models["identifier"])


@then("the identifier SHALL be sent unchanged to the endpoint")
def _sent_unchanged(models: dict[str, Any]) -> None:
    assert models["recorder"].bodies[0]["model"] == models["identifier"]


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "No behavioural branching on model name",
)
def test_no_behavioural_branching_on_model_name() -> None: ...


@given("two different configured model identifiers")
def _two_identifiers(models: dict[str, Any]) -> None:
    models["recorders"] = (Recorder(body=a_completion()), Recorder(body=a_completion()))
    models["identifiers"] = ("chat-v1", "a-model-nobody-has-heard-of")


@when("the same feature is invoked under each")
def _invoked_under_each(models: dict[str, Any]) -> None:
    for recorder, identifier in zip(models["recorders"], models["identifiers"], strict=True):
        built(recorder, model=identifier).complete("describe this")


@then("the request the system constructs SHALL differ only in the model identifier")
def _differ_only_in_the_identifier(models: dict[str, Any]) -> None:
    one, two = (recorder.bodies[0] for recorder in models["recorders"])

    assert (one["model"], two["model"]) == models["identifiers"]
    assert _without_model(one) == _without_model(two)


def _without_model(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != "model"}


# --------------------------------------------------------------------------
# Rule: Provider details never leave the adapter
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Features tested without an endpoint",
)
def test_features_tested_without_an_endpoint() -> None: ...


@given("no configured endpoint and no network")
def _no_endpoint(models: dict[str, Any]) -> None:
    models["world"] = a_derived_world()


@when("a model-backed use case is exercised against a substitute")
def _against_a_substitute(models: dict[str, Any]) -> None:
    world = models["world"]
    world.vision = describing(ANSWER)
    world.vision.will_answer(ANSWER, "mech, walker")
    models["described"] = ran(world.describe())


@then("it SHALL run to completion and produce its result")
def _produced_its_result(models: dict[str, Any]) -> None:
    described = models["described"]

    assert described.is_available
    assert described.records
    assert described.pending


# --------------------------------------------------------------------------
# Rule: Every failure degrades identically
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Timeout does not fail the surrounding operation",
)
def test_timeout_does_not_fail_the_surrounding_operation() -> None: ...


@given("an endpoint that does not respond within the configured timeout")
def _a_slow_endpoint(models: dict[str, Any]) -> None:
    models["world"] = a_derived_world()
    models["world"].refusing(Unavailability.TIMEOUT, "the request budget ran out")


@when("a feature requests generation as part of a larger operation")
def _generation_within_a_larger_operation(models: dict[str, Any]) -> None:
    """The larger operation is the whole command: describe, then read the project."""
    world = models["world"]
    models["described"] = ran(world.describe())
    models["compiled"] = ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store))


@then("the larger operation SHALL complete")
def _the_larger_operation_completed(models: dict[str, Any]) -> None:
    assert models["compiled"].asset_id == SCOUT
    assert models["world"].spec_text()


@then("the generated content SHALL be reported as unavailable")
def _reported_unavailable(models: dict[str, Any]) -> None:
    described = models["described"]

    assert not described.is_available
    assert str(Unavailability.TIMEOUT) in described.reason


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Cause is reported",
)
def test_cause_is_reported() -> None: ...


@when("generation is unavailable")
def _generation_unavailable(models: dict[str, Any]) -> None:
    reported: dict[Unavailability, str] = {}
    for reason in Unavailability:
        world = a_derived_world()
        world.refusing(reason)
        reported[reason] = ran(world.describe()).reason
    models["reported"] = reported


@then(
    "the system SHALL state the reason distinguishing at least disabled, misconfigured, "
    "unreachable and rejected"
)
def _reason_distinguished(models: dict[str, Any]) -> None:
    reported = models["reported"]
    named = (
        Unavailability.DISABLED,
        Unavailability.MISCONFIGURED,
        Unavailability.UNREACHABLE,
        Unavailability.REJECTED,
    )

    for reason in named:
        assert str(reason) in reported[reason]
    assert len({reported[reason] for reason in named}) == len(named)


# --------------------------------------------------------------------------
# Rule: Core paths never depend on a model
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Validation unaffected by model availability",
)
def test_validation_unaffected_by_model_availability() -> None: ...


@given("an export and its specification")
def _an_export_and_its_specification(models: dict[str, Any]) -> None:
    """The in-memory store, because validation discovers its specification by
    walking *upward* from the export — the walk that makes
    `canon validate exports/...glb` work."""
    from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
    from cybercanon.application.testing.spec_store import InMemorySpecStore
    from cybercanon.domain.asset import Asset, AssetId
    from cybercanon.domain.constraints import Constraints
    from cybercanon.domain.format_matrix import facts_for
    from cybercanon.domain.mesh_facts import MeshFormat
    from cybercanon.domain.status import Status

    store = InMemorySpecStore()
    store.add(
        SCOUT_SPEC,
        Asset(
            id=AssetId(SCOUT),
            name="Scout Mech",
            status=Status.MODELING,
            constraints=Constraints(tri_budget=12000),
        ),
    )
    inspector = InMemoryMeshInspector()
    inspector.add(
        EXPORT,
        facts_for(
            MeshFormat.GLB,
            triangles=9000,
            objects=("SM_mech_scout",),
            transforms_applied=True,
            unit_scale=1.0,
            up_axis="Y",
            uv_sets=1,
            materials=("M_mech_scout",),
            empties=(),
            clips=(),
            frame_rate=None,
            is_skinned=False,
        ),
    )
    models["store"] = store
    models["inspector"] = inspector
    models["world"] = a_derived_world()


@when("it is validated with model access enabled and again with it disabled")
def _validated_twice(models: dict[str, Any]) -> None:
    from cybercanon.application.use_cases.validate_export import validate_export

    world = models["world"]
    world.always_answering()
    reports = []
    for _ in range(2):
        reports.append(
            ran(
                validate_export(
                    EXPORT,
                    spec_store=models["store"],
                    mesh_inspector=models["inspector"],
                )
            ).report
        )
        world.vision = DisabledVision()
    models["reports"] = reports


@then("the reports SHALL be identical")
def _reports_identical(models: dict[str, Any]) -> None:
    first, second = models["reports"]

    assert first == second


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Compiled specification unaffected",
)
def test_compiled_specification_unaffected() -> None: ...


@when("a specification is compiled with model access enabled and again disabled")
def _compiled_twice(models: dict[str, Any]) -> None:
    enabled = a_derived_world()
    enabled.answering()
    ran(enabled.describe())
    disabled = a_derived_world()
    disabled.vision = DisabledVision()
    models["compiled"] = tuple(
        ran(compile_spec(SCOUT_SPEC, spec_store=world.views.spec_store)).text
        for world in (enabled, disabled)
    )
    models["records"] = enabled.records()


@then("the two outputs SHALL be byte-identical")
def _byte_identical(models: dict[str, Any]) -> None:
    first, second = models["compiled"]

    assert models["records"]  # generation really did happen on one side
    assert first == second


# --------------------------------------------------------------------------
# Rule: Bounded and non-retrying-forever requests
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Retry budget respected",
)
def test_retry_budget_respected() -> None: ...


@given("a retry budget of two and an endpoint failing transiently")
def _a_transient_endpoint(models: dict[str, Any]) -> None:
    models["recorder"] = Recorder(status=503)
    models["adapter"] = built(models["recorder"], max_retries=2)


@when("generation is requested")
def _generation_requested(models: dict[str, Any]) -> None:
    models["answer"] = models["adapter"].complete("anything")


@then("at most three attempts SHALL be made in total")
def _at_most_three_attempts(models: dict[str, Any]) -> None:
    assert models["recorder"].attempts == 3
    assert not answered(models["answer"])


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Authentication failure is not retried",
)
def test_authentication_failure_is_not_retried() -> None: ...


@when("the endpoint rejects the credential")
def _credential_rejected(models: dict[str, Any]) -> None:
    models["recorder"] = Recorder(status=401)
    models["answer"] = built(models["recorder"], max_retries=2).complete("anything")


@then("exactly one attempt SHALL be made")
def _exactly_one_attempt(models: dict[str, Any]) -> None:
    assert models["recorder"].attempts == 1


@then("the cause SHALL be reported as rejected")
def _cause_is_rejected(models: dict[str, Any]) -> None:
    assert models["answer"].reason is Unavailability.REJECTED


# --------------------------------------------------------------------------
# Rule: Content sent to a model is recorded in scope
# --------------------------------------------------------------------------


@scenario(
    "../features/add-derived-metadata/llm-integration.feature",
    "Image description sends only the image",
)
def test_image_description_sends_only_the_image() -> None: ...


@when("a concept view is described")
def _a_concept_view_described(models: dict[str, Any]) -> None:
    models["recorder"] = Recorder(body=a_completion())
    models["image"] = PNG
    built(models["recorder"]).describe(PNG, DESCRIBE_IMAGE)


@then("only that image and a fixed instruction SHALL be transmitted")
def _only_the_image_and_the_instruction(models: dict[str, Any]) -> None:
    (body,) = models["recorder"].bodies
    (message,) = body["messages"]

    assert [part["type"] for part in message["content"]] == ["image_url", "text"]
    assert message["content"][1]["text"] == DESCRIBE_IMAGE


@then("no specification content SHALL be included")
def _no_specification_content(models: dict[str, Any]) -> None:
    sent = json.dumps(models["recorder"].bodies)

    assert not [word for word in SPECIFICATION_WORDS if word in sent]
