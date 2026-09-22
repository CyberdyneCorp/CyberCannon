"""Configuration from the environment, and only from the environment.

`add-web-backend`'s task 1.4 asked for the loader; `add-coolify-deployment`'s
tasks 1.1 to 1.4 asked for the rest of what a deployment needs from it, and both
halves are asserted here because they are one module and one behaviour.

Five properties, and each of them is a sentence `project.md` or
`deployment-operations` states:

* configuration is environment variables **with no file fallback** — not a file
  in the image, not one on a mounted volume, not a `.env` beside the process;
* a project's own settings file inside its working copy is **content**, read
  through the `SpecStore`, and is explicitly outside that rule;
* a misconfigured deployment **fails at boot**, naming every offending variable
  in one message — missing *and* malformed, the malformed ones with the shape
  they were expected to have — because a queue of restarts is how people end up
  baking configuration into an image;
* **no value is ever echoed**, so a mistyped credential cannot reach a log line
  or a traceback;
* **optional configuration absent is not a failure**: the model switch is off by
  default, the service starts, and the features that need one report themselves
  unavailable.
"""

from __future__ import annotations

import hashlib
import os
import traceback
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cybercanon.adapters.inbound.http.health import (
    DEGRADED_FIELD,
    READY,
    READY_PATH,
    STATUS_FIELD,
)
from cybercanon.adapters.wiring import configuration
from cybercanon.adapters.wiring.configuration import (
    PREFIX,
    REQUIRED,
    ConfigurationIncomplete,
    ConfigurationInvalid,
    Secret,
    group_roles,
    load,
    missing_from,
)
from cybercanon.api import main
from cybercanon.api.main import application
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.service_health import LANGUAGE_MODEL

COMPLETE = {
    "CANON_PROJECT": "ironwood",
    "CANON_REPOSITORY_URL": "git@github.com:cyberdynecorp/ironwood.git",
    "CANON_REPOSITORY_BRANCH": "canon",
    "CANON_REPOSITORY_CREDENTIAL": "a-deploy-key",
    "CANON_FETCH_INTERVAL_S": "300",
    "CANON_WEBHOOK_SECRET": "a-webhook-secret",
    "CANON_AUTH_ISSUER": "https://auth.cyberdynecorp.ai/",
    "CANON_AUTH_AUDIENCE": "cybercanon",
    "CANON_AUTH_KEY_SET_URL": "https://auth.cyberdynecorp.ai/.well-known/jwks.json",
    "CANON_AUTH_GROUP_ROLES": "art-leads=ART_DIRECTOR,artists=ARTIST",
    "CANON_DATABASE_URL": "postgresql://canon@db/canon",
    "CANON_OBJECT_STORE_URL": "https://minio.cyberdynecorp.ai",
    "CANON_LINK_EXPIRY_S": "120",
    "CANON_WRITE_BACK_TIMEOUT_S": "30",
    "CANON_DRAIN_WINDOW_S": "90",
}


# --------------------------------------------------------------------------
# A complete environment
# --------------------------------------------------------------------------


def test_a_complete_environment_produces_a_configuration() -> None:
    loaded = load(COMPLETE)

    assert loaded.repository.branch == "canon"
    assert loaded.repository.fetch_interval == timedelta(minutes=5)
    assert loaded.identity.audience == "cybercanon"
    assert loaded.storage.link_expiry == timedelta(minutes=2)


def test_every_required_variable_is_namespaced() -> None:
    """Twelve variables in one process's environment collide with somebody."""
    assert all(name.startswith(PREFIX) for name in REQUIRED)


def test_the_required_set_is_the_one_the_task_enumerates() -> None:
    assert set(REQUIRED) == set(COMPLETE)
    assert len(REQUIRED) == 15


# --------------------------------------------------------------------------
# Refusing to start
# --------------------------------------------------------------------------


def test_an_empty_environment_names_every_missing_variable_at_once() -> None:
    with pytest.raises(ConfigurationIncomplete) as refused:
        load({})

    assert refused.value.missing == REQUIRED
    for name in REQUIRED:
        assert name in refused.value.message


def test_one_missing_variable_is_named_and_the_others_are_not() -> None:
    incomplete = {name: value for name, value in COMPLETE.items() if name != "CANON_AUTH_ISSUER"}

    with pytest.raises(ConfigurationIncomplete) as refused:
        load(incomplete)

    assert refused.value.missing == ("CANON_AUTH_ISSUER",)


def test_a_variable_set_to_whitespace_counts_as_missing() -> None:
    """An empty value in a deployment panel is somebody meaning to fill it in."""
    blank = {**COMPLETE, "CANON_WEBHOOK_SECRET": "   "}

    assert missing_from(blank) == ("CANON_WEBHOOK_SECRET",)


def test_the_missing_variables_are_listed_in_the_order_they_are_declared() -> None:
    assert missing_from({}) == REQUIRED


@pytest.mark.parametrize("value", ["not-a-number", "", "5s", "-1", "0"])
def test_an_interval_that_is_not_a_positive_number_of_seconds_is_refused(
    value: str,
) -> None:
    broken = {**COMPLETE, "CANON_FETCH_INTERVAL_S": value}

    with pytest.raises((ConfigurationInvalid, ConfigurationIncomplete)):
        load(broken)


def test_a_link_expiry_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(ConfigurationInvalid, match="CANON_LINK_EXPIRY_S"):
        load({**COMPLETE, "CANON_LINK_EXPIRY_S": "two minutes"})


# --------------------------------------------------------------------------
# No file fallback
# --------------------------------------------------------------------------


def test_nothing_in_the_module_opens_a_path() -> None:
    """The mechanical half of "no file fallback": there is no reader to call."""
    source = Path(configuration.__file__).read_text(encoding="utf-8")

    for reader in ("open(", "read_text", "Path(", "load_dotenv", "configparser"):
        assert reader not in source, f"configuration reaches for a file via {reader!r}"


def test_a_dotenv_file_beside_the_service_is_not_configuration(tmp_path: Path) -> None:
    """Present, readable, and ignored — because the loader takes a mapping."""
    (tmp_path / ".env").write_text(
        "\n".join(f"{name}={value}" for name, value in COMPLETE.items()), encoding="utf-8"
    )

    with pytest.raises(ConfigurationIncomplete):
        load({})


# --------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------


def test_a_secret_never_renders_its_value() -> None:
    loaded = load(COMPLETE)

    assert "a-deploy-key" not in repr(loaded.repository)
    assert "a-deploy-key" not in str(loaded.repository.credential)
    assert "a-webhook-secret" not in repr(loaded)
    assert str(loaded.storage.database_url) == "<secret>"


def test_a_secret_still_compares_and_still_knows_it_is_present() -> None:
    assert Secret("x") == Secret("x")
    assert Secret("x")
    assert not Secret("")


# --------------------------------------------------------------------------
# The group mapping (D12)
# --------------------------------------------------------------------------


def test_groups_become_roles_through_configuration_alone() -> None:
    assert group_roles("art-leads=ART_DIRECTOR,artists=ARTIST") == {
        "art-leads": "ART_DIRECTOR",
        "artists": "ARTIST",
    }


def test_an_empty_mapping_is_a_mapping_that_grants_nothing() -> None:
    """An unmapped group grants no role; a project with none is still a project."""
    assert group_roles("") == {}


def test_surrounding_space_in_the_mapping_is_forgiven() -> None:
    assert group_roles(" art-leads = ART_DIRECTOR , artists=ARTIST ") == {
        "art-leads": "ART_DIRECTOR",
        "artists": "ARTIST",
    }


@pytest.mark.parametrize("declared", ["art-leads", "=ART_DIRECTOR", "art-leads="])
def test_a_pair_that_cannot_be_read_is_refused_rather_than_dropped(declared: str) -> None:
    """Dropping it would grant nothing while looking like it granted something."""
    with pytest.raises(ConfigurationInvalid, match="CANON_AUTH_GROUP_ROLES"):
        group_roles(declared)


def test_no_group_name_appears_in_the_code() -> None:
    """D12: configuration, not code that names specific groups."""
    source = Path(configuration.__file__).read_text(encoding="utf-8")

    assert "art-leads" not in source
    assert "ART_DIRECTOR" not in source.split('"""')[-1]


# --------------------------------------------------------------------------
# Tasks 1.1-1.4 (add-coolify-deployment) — the file that is not consulted, the
# one aggregated refusal, the secret that never renders, and the optional half
# --------------------------------------------------------------------------

IMAGE_FILES = (".env", "settings.toml", "canon.yaml", "config/service.env")
"""The shapes of file a service like this one is repeatedly asked to read."""


def test_a_value_present_only_in_a_file_in_the_image_is_not_picked_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1.1 — the file is there, on the image and on a mounted volume. It is ignored.

    `deployment-operations`: *"it SHALL treat the setting as absent"*. The
    loader is handed the process environment, and there is nothing in this
    module that could reach a path even if somebody wanted it to.
    """
    for name in IMAGE_FILES:
        written = tmp_path / name
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(
            "\n".join(f"{key}={value}" for key, value in COMPLETE.items()), encoding="utf-8"
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, "environ", {})

    with pytest.raises(ConfigurationIncomplete) as refused:
        load()

    assert refused.value.missing == REQUIRED


def test_the_carve_out_is_repository_content_and_not_this_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project's own settings file is content, read through the `SpecStore`.

    The two are asserted together on purpose: the same directory holds a project
    configuration that *is* read — by the store, at a revision — and a service
    configuration that is not.
    """
    store = InMemorySpecStore()
    store.set_project(ProjectConfig(name="cyberdyne-game"))
    monkeypatch.setattr(os, "environ", {})

    assert store.load_project("").name == "cyberdyne-game"
    with pytest.raises(ConfigurationIncomplete):
        load()


def test_changing_a_value_takes_effect_with_no_new_artifact() -> None:
    """The other half of environment-only: a restart is the whole deployment step."""
    before = _artifact_digest()
    first = load({**COMPLETE, "CANON_REPOSITORY_BRANCH": "canon"})
    second = load({**COMPLETE, "CANON_REPOSITORY_BRANCH": "main"})

    assert first.repository.branch == "canon"
    assert second.repository.branch == "main"
    assert _artifact_digest() == before


def _artifact_digest() -> str:
    """A digest over the deployable's own source — the stand-in for the image.

    Task 3.3 records the built image's digest; what matters here is the weaker
    claim the specification makes, which is that nothing about the artifact
    changed when the value did.
    """
    source = Path(configuration.__file__).read_bytes()
    return hashlib.sha256(source).hexdigest()


def test_a_missing_and_a_malformed_setting_are_reported_in_one_message() -> None:
    """1.2 — both kinds of problem, one refusal, every offending name in it."""
    broken = {
        **{name: value for name, value in COMPLETE.items() if name != "CANON_AUTH_ISSUER"},
        "CANON_FETCH_INTERVAL_S": "five minutes",
    }

    with pytest.raises(ConfigurationInvalid) as refused:
        load(broken)

    assert set(refused.value.names) == {"CANON_AUTH_ISSUER", "CANON_FETCH_INTERVAL_S"}
    for name in refused.value.names:
        assert name in refused.value.message


def test_a_malformed_setting_names_the_shape_it_expected() -> None:
    with pytest.raises(ConfigurationInvalid) as refused:
        load({**COMPLETE, "CANON_FETCH_INTERVAL_S": "five minutes"})

    assert "a whole number of seconds" in refused.value.message


def test_every_declared_setting_carries_the_shape_it_expects() -> None:
    """A refusal that cannot say what it wanted is a refusal nobody can act on."""
    assert all(setting.expected for setting in configuration.SETTINGS)


@pytest.mark.parametrize("name", ["CANON_DATABASE_URL", "CANON_REPOSITORY_CREDENTIAL"])
def test_a_secret_is_declared_as_one(name: str) -> None:
    assert name in configuration.SECRETS


def test_a_malformed_secret_names_the_setting_and_never_its_value() -> None:
    """1.3 — including when the failure is rendered as a traceback."""
    secret = "postgres-password-hunter2"

    with pytest.raises(ConfigurationInvalid) as refused:
        load({**COMPLETE, "CANON_DATABASE_URL": secret})

    rendered = "".join(
        traceback.format_exception(type(refused.value), refused.value, refused.value.__traceback__)
    )
    assert "CANON_DATABASE_URL" in refused.value.message
    assert secret not in refused.value.message
    assert secret not in rendered
    assert secret not in repr(refused.value)


def test_no_value_at_all_is_echoed_by_a_refusal() -> None:
    """The rule is not "redact secrets"; it is "never quote a value"."""
    with pytest.raises(ConfigurationInvalid) as refused:
        load({**COMPLETE, "CANON_OBJECT_STORE_URL": "minio-without-a-scheme"})

    assert "minio-without-a-scheme" not in refused.value.message


# --------------------------------------------------------------------------
# 1.4 — the optional half
# --------------------------------------------------------------------------


def test_the_model_settings_are_optional_and_absent_means_off() -> None:
    loaded = load(COMPLETE)

    assert not loaded.model.enabled
    assert not loaded.model.available
    assert configuration.MODEL_ENABLED in loaded.model.absence


def test_the_model_settings_are_read_when_they_are_there() -> None:
    loaded = load(
        {
            **COMPLETE,
            "CANON_LLM_ENABLED": "true",
            "CANON_LLM_BASE_URL": "https://llm.cyberdynecorp.ai/v1",
            "CANON_LLM_API_KEY": "a-gateway-key",
            "CANON_LLM_MODEL": "qwen3-32b",
            "CANON_LLM_VISION_MODEL": "qwen3-vl",
            "CANON_LLM_TIMEOUT_S": "45",
            "CANON_LLM_MAX_RETRIES": "3",
        }
    )

    assert loaded.model.available
    assert loaded.model.model == "qwen3-32b"
    assert loaded.model.timeout == timedelta(seconds=45)
    assert loaded.model.max_retries == 3
    assert "a-gateway-key" not in repr(loaded.model)


def test_a_malformed_optional_setting_is_still_a_refusal() -> None:
    """Optional means absent is allowed, not that anything goes."""
    with pytest.raises(ConfigurationInvalid, match="CANON_LLM_ENABLED"):
        load({**COMPLETE, "CANON_LLM_ENABLED": "perhaps"})


def test_the_service_starts_with_the_model_off_and_reports_it_unavailable() -> None:
    client = TestClient(application(COMPLETE))

    response = client.get(READY_PATH)
    body = response.json()

    assert response.status_code == 200
    assert body[STATUS_FIELD] == READY
    assert LANGUAGE_MODEL in body[DEGRADED_FIELD]
    assert {"search_index", "object_store"} <= set(body[DEGRADED_FIELD]), (
        "the deployable now wires the index and the blob mirror, so a process "
        "that cannot reach them has to say which one it cannot reach"
    )


def test_a_malformed_setting_stops_the_boot_before_an_application_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """*"no request SHALL have been served"* — there is nothing to serve one."""
    built: list[object] = []
    monkeypatch.setattr(main, "build_app", lambda *a, **k: built.append(a) or object())

    with pytest.raises(ConfigurationInvalid, match="CANON_LINK_EXPIRY_S"):
        application({**COMPLETE, "CANON_LINK_EXPIRY_S": "two minutes"})

    assert built == []
