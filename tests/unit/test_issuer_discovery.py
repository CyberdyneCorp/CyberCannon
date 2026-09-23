"""The endpoints come from the issuer, and a wrong document is refused.

`canon auth login` used to post its redemption to `<issuer>/oauth/token` — a
path this repository invented — and CyberdyneAuth serves
`/api/v1/auth/oauth2/token`, so every terminal sign-in against the real identity
service ended in a 404 that looked like an outage. **The constant was the
defect, not its value**, so this suite is about where an address comes from
rather than about which address it is: not one test here names a path the
product knows.

Five properties, and each of them is a way the previous shape could have been
wrong again:

* the address is whatever the document says, whatever that is;
* the document is read **once**, and only after somebody actually signs in —
  `canon` builds its container on every invocation, and a validator that opened
  a socket to an identity service to tell an artist her mesh is fine would be
  unusable on a train;
* a **failed** read is not remembered, so an identity service that was down at
  09:00 is not down for this process for ever;
* a document published by a *different* issuer is refused rather than followed,
  because the endpoints in it belong to whoever answered that address;
* a configured address still wins, per endpoint, for the deployment whose issuer
  publishes nothing — the escape hatch, kept, and no longer the default.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from cybercanon.adapters.outbound.auth.discovery import (
    DISCOVERY_PATH,
    Discovered,
    IssuerEndpoints,
)
from cybercanon.adapters.outbound.auth.flows import DeviceAuthorization, Endpoints
from cybercanon.application.ports.interactive_sign_in import SignInUnavailable

pytestmark = pytest.mark.unit

ISSUER = "https://auth.example"
TOKEN = f"{ISSUER}/api/v1/auth/oauth2/token"
DEVICE = f"{ISSUER}/api/v1/auth/oauth2/device"
AUTHORIZE = f"{ISSUER}/api/v1/auth/oauth2/authorize"

DOCUMENT: dict[str, Any] = {
    "issuer": ISSUER,
    "authorization_endpoint": AUTHORIZE,
    "token_endpoint": TOKEN,
    "device_authorization_endpoint": DEVICE,
}


class Publishing:
    """An issuer that publishes a document, and counts who asked for it."""

    def __init__(self, document: Mapping[str, Any] | None = None, fails: int = 0) -> None:
        self.document = dict(DOCUMENT if document is None else document)
        self.fails = fails
        self.reads = 0
        self.addresses: list[str] = []

    def __call__(self, url: str) -> Mapping[str, Any]:
        self.reads += 1
        self.addresses.append(url)
        if self.fails > 0:
            self.fails -= 1
            raise OSError("the identity service is not answering")
        return self.document


def endpoints(source: Publishing, **keywords: Any) -> IssuerEndpoints:
    return IssuerEndpoints(ISSUER, source=source, **keywords)


# --------------------------------------------------------------------------
# Where an address comes from
# --------------------------------------------------------------------------


def test_the_endpoints_are_the_ones_the_issuer_publishes() -> None:
    """Whatever the document says, including paths nothing here has heard of."""
    published = endpoints(Publishing())

    assert published.token == TOKEN
    assert published.device_authorization == DEVICE
    assert published.authorization == AUTHORIZE


def test_the_document_is_looked_for_where_the_specification_puts_it() -> None:
    source = Publishing()

    assert endpoints(source).url == f"{ISSUER}{DISCOVERY_PATH}"


def test_an_issuer_with_a_trailing_slash_is_the_same_issuer() -> None:
    """A deployment panel's value is pasted by a person, and people paste slashes."""
    source = Publishing()

    assert IssuerEndpoints(f"{ISSUER}/", source=source).token == TOKEN


def test_nothing_is_retrieved_until_an_address_is_asked_for() -> None:
    """Construction opens no socket: `canon` builds this on every invocation."""
    source = Publishing()

    endpoints(source)

    assert source.reads == 0


def test_the_document_is_read_once_however_many_addresses_are_asked_for() -> None:
    source = Publishing()
    published = endpoints(source)

    assert (published.token, published.device_authorization, published.token) == (
        TOKEN,
        DEVICE,
        TOKEN,
    )
    assert source.reads == 1


def test_a_failed_read_is_not_remembered() -> None:
    """An outage at the first sign-in must not outlive itself for this process."""
    source = Publishing(fails=1)
    published = endpoints(source)
    with pytest.raises(SignInUnavailable):
        _ = published.token

    assert published.token == TOKEN
    assert source.reads == 2


# --------------------------------------------------------------------------
# The two documents that must not be followed
# --------------------------------------------------------------------------


def test_a_document_published_by_another_issuer_is_refused() -> None:
    """Its endpoints are somebody else's, and a device code would go to them."""
    source = Publishing({**DOCUMENT, "issuer": "https://auth.somewhere-else"})

    with pytest.raises(SignInUnavailable) as refused:
        _ = endpoints(source).token

    assert "different issuer" in str(refused.value)


def test_an_unreachable_issuer_is_a_sign_in_that_is_unavailable() -> None:
    """Never a wrong address, and never a guess at one."""
    with pytest.raises(SignInUnavailable):
        _ = endpoints(Publishing(fails=1)).token


def test_an_endpoint_the_issuer_does_not_publish_is_named_rather_than_invented() -> None:
    """The whole finding, as one assertion: no path is appended to an issuer."""
    source = Publishing({"issuer": ISSUER, "token_endpoint": TOKEN})

    with pytest.raises(SignInUnavailable) as refused:
        _ = endpoints(source).device_authorization

    assert "device authorization" in str(refused.value)
    assert "/oauth/device/code" not in str(refused.value)


# --------------------------------------------------------------------------
# The escape hatch, kept and demoted
# --------------------------------------------------------------------------


def test_a_configured_address_wins_and_is_not_looked_up() -> None:
    source = Publishing()
    published = endpoints(source, overrides=Endpoints(token="https://pinned.example/token"))

    assert published.token == "https://pinned.example/token"
    assert source.reads == 0, "a pinned endpoint needs no document"


def test_one_endpoint_can_be_pinned_while_the_rest_are_discovered() -> None:
    source = Publishing()
    published = endpoints(source, overrides=Endpoints(token="https://pinned.example/token"))

    assert published.device_authorization == DEVICE


# --------------------------------------------------------------------------
# What a flow does with one
# --------------------------------------------------------------------------


def test_a_device_sign_in_posts_to_the_discovered_address() -> None:
    """The flow cannot tell the two directories apart, which is the point."""
    posted: list[str] = []

    class Transport:
        def post(self, url: str, form: Mapping[str, str]) -> Mapping[str, Any]:
            posted.append(url)
            return {"device_code": "d", "user_code": "WDJB-MJHT", "verification_uri": ISSUER}

    DeviceAuthorization(
        endpoints=endpoints(Publishing()),
        client_id="cyb_Fixture0Client01",
        transport=Transport(),
    ).begin()

    assert posted == [DEVICE]


def test_a_document_that_is_not_a_document_describes_no_endpoints() -> None:
    """Read defensively: a field that is not a string is not an address."""
    found = Discovered.of({"issuer": ISSUER, "token_endpoint": ["nonsense"]})

    assert found.token_endpoint == ""
