"""Task 1.4 — configuration from the environment, and only from the environment.

Three properties, and each of them is a sentence `project.md` states:

* configuration is environment variables **with no file fallback**;
* **no secret is ever committed**, which is only true if a secret cannot reach a
  log line either;
* a misconfigured deployment **fails at boot**, naming every variable it needs
  and does not have — all of them, in one message, because a queue of restarts
  is how people end up baking configuration into an image.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

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

COMPLETE = {
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
    assert len(REQUIRED) == 12


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
