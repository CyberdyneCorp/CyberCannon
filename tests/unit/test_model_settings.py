"""Tasks 1.1, 1.4 — the seven variables, and that an empty environment is off.

`llm-integration` requires model access to be configured *"by environment
variables covering: a master enable switch, the endpoint base URL, the
credential, a text model identifier, a vision model identifier, a request
timeout and a retry budget"*, with the switch *"defaulting to disabled"*.

Two readers exist for one environment — the hosted service's
`ServiceConfiguration` and the command line's own settings — and the last test
here is what stops them drifting apart: the names are asserted to be the same
set, in the same spelling, read from the code both of them actually use.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from cybercanon.adapters.outbound.openai_compatible.config import (
    API_KEY,
    BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    ENABLED,
    MAX_RETRIES,
    MODEL,
    TIMEOUT,
    VARIABLES,
    VISION_MODEL,
    ModelSettings,
    settings_from,
)
from cybercanon.adapters.wiring.configuration import SETTINGS

pytestmark = pytest.mark.unit

COMPLETE = {
    ENABLED: "true",
    BASE_URL: "https://llm.cyberdynecorp.ai/v1",
    API_KEY: "a-gateway-key",
    MODEL: "chat-v1",
    VISION_MODEL: "vision-v1",
    TIMEOUT: "45",
    MAX_RETRIES: "3",
}

ENV_EXAMPLE = Path(".env.example")


# --------------------------------------------------------------------------
# 1.1 — an empty environment yields a disabled configuration
# --------------------------------------------------------------------------


def test_an_empty_environment_is_a_disabled_configuration() -> None:
    settings = settings_from({})

    assert not settings.enabled
    assert not settings.is_complete
    assert not settings.vision_is_complete
    assert settings.absence == f"{ENABLED} is off"


def test_the_default_settings_object_is_the_same_as_an_empty_environment() -> None:
    assert settings_from({}) == ModelSettings()


def test_a_complete_environment_is_read_verbatim() -> None:
    settings = settings_from(COMPLETE)

    assert settings.is_complete and settings.vision_is_complete
    assert settings.base_url == "https://llm.cyberdynecorp.ai/v1"
    assert settings.model == "chat-v1"
    assert settings.vision_model == "vision-v1"
    assert settings.timeout == timedelta(seconds=45)
    assert settings.max_retries == 3


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_the_switch_reads_the_usual_spellings_of_yes(value: str) -> None:
    assert settings_from({**COMPLETE, ENABLED: value}).enabled


@pytest.mark.parametrize("value", ["0", "false", "no", "", "perhaps"])
def test_anything_else_is_off(value: str) -> None:
    assert not settings_from({**COMPLETE, ENABLED: value}).enabled


def test_half_a_configuration_is_off_rather_than_broken() -> None:
    """A switch with no endpoint fails once at composition, not once per click."""
    settings = settings_from({ENABLED: "true"})

    assert not settings.is_complete
    assert settings.missing == (BASE_URL, MODEL)
    assert BASE_URL in settings.absence and MODEL in settings.absence


def test_text_can_be_available_while_vision_is_not() -> None:
    """The state two ports exist to make representable."""
    settings = settings_from({**COMPLETE, VISION_MODEL: ""})

    assert settings.is_complete
    assert not settings.vision_is_complete
    assert VISION_MODEL in settings.vision_absence


def test_a_credential_is_not_required() -> None:
    """A private gateway that accepts unauthenticated calls is a real deployment."""
    assert settings_from({**COMPLETE, API_KEY: ""}).is_complete


def test_a_mistyped_budget_falls_back_rather_than_stopping_the_deployment() -> None:
    settings = settings_from({**COMPLETE, TIMEOUT: "soon", MAX_RETRIES: "lots"})

    assert settings.timeout == DEFAULT_TIMEOUT
    assert settings.max_retries == DEFAULT_MAX_RETRIES


def test_a_negative_retry_budget_means_one_attempt() -> None:
    assert settings_from({**COMPLETE, MAX_RETRIES: "-4"}).max_retries == 0


def test_the_credential_is_never_printed() -> None:
    """A credential in a repr is a credential in a traceback and then in a log."""
    assert "a-gateway-key" not in repr(settings_from(COMPLETE))


# --------------------------------------------------------------------------
# 1.4 — the documented names are the names the code reads
# --------------------------------------------------------------------------


def test_the_seven_variables_are_the_ones_the_service_declares() -> None:
    """One environment, two readers, and no room for them to drift apart."""
    declared = {setting.name for setting in SETTINGS if setting.name.startswith("CANON_LLM_")}

    assert set(VARIABLES) == declared
    assert len(VARIABLES) == 7


@pytest.mark.parametrize("name", VARIABLES)
def test_env_example_documents_every_variable(name: str, repo_root: Path) -> None:
    documented = (repo_root / ENV_EXAMPLE).read_text(encoding="utf-8")

    assert f"{name}=" in documented


def test_env_example_ships_the_feature_switched_off(repo_root: Path) -> None:
    """The documented default is the supported one: off."""
    documented = (repo_root / ENV_EXAMPLE).read_text(encoding="utf-8")

    assert f"{ENABLED}=false" in documented
