"""Task 6.1 — the drain window is longer than the write-back budget, and it is asserted.

D7 makes *"an interrupted write-back leaves a commit or leaves nothing"* a
property of **two configured numbers in a known order** rather than a hope about
process shutdown. A comment saying so would be a hope with formatting, so the
order is a thing this suite reads out of the configuration the service actually
starts with:

* the pair is read from the environment like everything else, with no file
  fallback and no default hiding an unset variable;
* an **inverted** pair is a refused boot naming *both* variables, because either
  one could be the one that is wrong and the person reading the message is the
  one who knows which;
* an **equal** pair is refused too. Equal is the case that looks fine and is
  not: a write-back that used its whole budget would abandon itself at exactly
  the instant the platform stops waiting, and "at exactly the instant" is not a
  guarantee anybody can hold.

The write-back side of the same decision — that a budget which runs out resets
the working copy and reports that nothing was recorded — is asserted against
real git in `tests/integration/test_rollover.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from cybercanon.adapters.wiring.configuration import (
    DRAIN_WINDOW,
    REQUIRED,
    WRITE_BACK_TIMEOUT,
    ConfigurationIncomplete,
    ConfigurationInvalid,
    RolloverConfig,
    load,
)

pytestmark = pytest.mark.unit

COMPLETE = {
    "CANON_PROJECT": "ronin",
    "CANON_REPOSITORY_URL": "git@github.com:cyberdynecorp/ronin.git",
    "CANON_REPOSITORY_BRANCH": "canon",
    "CANON_REPOSITORY_CREDENTIAL": "a-deploy-key",
    "CANON_FETCH_INTERVAL_S": "300",
    "CANON_WEBHOOK_SECRET": "a-webhook-secret",
    "CANON_AUTH_ISSUER": "https://auth.cyberdynecorp.ai/",
    "CANON_AUTH_AUDIENCE": "cybercanon",
    "CANON_AUTH_CLIENT_ID": "cyb_Rollover0Client1",
    "CANON_AUTH_ORG_ID": "org_Rollover0Studio",
    "CANON_AUTH_KEY_SET_URL": "https://auth.cyberdynecorp.ai/.well-known/jwks.json",
    "CANON_AUTH_GROUP_ROLES": "art-leads=ART_DIRECTOR",
    "CANON_DATABASE_URL": "postgresql://canon@db/canon",
    "CANON_OBJECT_STORE_URL": "https://minio.cyberdynecorp.ai",
    "CANON_LINK_EXPIRY_S": "120",
    "CANON_WRITE_BACK_TIMEOUT_S": "30",
    "CANON_DRAIN_WINDOW_S": "90",
}


def _configured(**overrides: str):
    return load({**COMPLETE, **overrides})


# --------------------------------------------------------------------------
# The pair is configuration, and the service will not start without it
# --------------------------------------------------------------------------


def test_both_numbers_are_required_settings() -> None:
    """Not defaults. A rollover nobody configured is a rollover nobody sized."""
    assert WRITE_BACK_TIMEOUT in REQUIRED
    assert DRAIN_WINDOW in REQUIRED


def test_a_deployment_that_sets_neither_is_refused_naming_both() -> None:
    environment = {
        name: value
        for name, value in COMPLETE.items()
        if name not in {WRITE_BACK_TIMEOUT, DRAIN_WINDOW}
    }

    with pytest.raises(ConfigurationIncomplete) as refused:
        load(environment)

    assert {WRITE_BACK_TIMEOUT, DRAIN_WINDOW} <= set(refused.value.names)


def test_the_configured_values_are_what_the_service_carries() -> None:
    rollover = _configured().rollover

    assert rollover.write_back_timeout == timedelta(seconds=30)
    assert rollover.drain_window == timedelta(seconds=90)


# --------------------------------------------------------------------------
# The order between them, asserted rather than documented
# --------------------------------------------------------------------------


def test_the_drain_window_is_longer_than_the_write_back_budget() -> None:
    """D7, as one comparison over the values a real deployment starts with."""
    rollover = _configured().rollover

    assert rollover.drain_window > rollover.write_back_timeout
    assert rollover.drains_longer_than_write_back
    assert rollover.headroom > timedelta()


def test_an_inverted_pair_refuses_the_boot_naming_both_variables() -> None:
    with pytest.raises(ConfigurationInvalid) as refused:
        _configured(CANON_WRITE_BACK_TIMEOUT_S="120", CANON_DRAIN_WINDOW_S="60")

    assert set(refused.value.names) == {WRITE_BACK_TIMEOUT, DRAIN_WINDOW}


def test_an_equal_pair_is_refused_too() -> None:
    """Abandoned at exactly the instant the platform stops waiting is not a window."""
    with pytest.raises(ConfigurationInvalid):
        _configured(CANON_WRITE_BACK_TIMEOUT_S="60", CANON_DRAIN_WINDOW_S="60")


def test_the_refusal_says_which_way_round_they_go() -> None:
    """The message has to be actionable at three in the morning, not merely correct."""
    with pytest.raises(ConfigurationInvalid) as refused:
        _configured(CANON_WRITE_BACK_TIMEOUT_S="120", CANON_DRAIN_WINDOW_S="60")

    assert "drain window must be longer" in str(refused.value)
    assert "120" not in str(refused.value), "the message names settings, not values"


@pytest.mark.parametrize(
    ("write_back", "drain", "ordered"),
    [
        (timedelta(seconds=30), timedelta(seconds=90), True),
        (timedelta(seconds=30), timedelta(seconds=31), True),
        (timedelta(seconds=30), timedelta(seconds=30), False),
        (timedelta(seconds=90), timedelta(seconds=30), False),
    ],
)
def test_the_ordering_predicate_is_strict(
    write_back: timedelta, drain: timedelta, ordered: bool
) -> None:
    pair = RolloverConfig(write_back_timeout=write_back, drain_window=drain)

    assert pair.drains_longer_than_write_back is ordered
