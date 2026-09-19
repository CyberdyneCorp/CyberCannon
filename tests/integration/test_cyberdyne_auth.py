"""Tasks 8.1-8.5 and 8.8 — the CyberdyneAuth adapter against a real issuer.

Everything here runs over `canon_issuer.FakeIssuer`, which signs with real RSA
keys, publishes a real JWKS, rotates it, and can be told to stop answering. That
matters more than it might look: the behaviours this group is responsible for
are almost all about credentials the adapter did **not** mint — a token signed
by somebody else, a token for another audience, a token whose key the issuer
published five minutes ago — and a double that answered `True` would agree with
whatever the adapter happened to do.

Four groups of assertion, one per requirement:

* **verification** (8.1) — expired, wrong-audience, wrong-issuer and
  unverifiable credentials are each refused as unauthenticated, and the refusal
  tells the caller the same sentence for all of them;
* **rotation** (8.2) — a credential signed by a newly published key is accepted,
  with no restart and no reconfiguration, and the adapter goes back to the
  issuer exactly once to learn that;
* **mapping** (8.3) — unmapped groups grant nothing, an all-unmapped credential
  resolves role-less rather than being refused, and a mapping added to the
  configuration alone changes the resolved roles;
* **degradation** (8.5) — cached keys keep verifying while the issuer is
  unreachable, and beyond the configured window the refusal names the identity
  service.

Plus 8.8: a client-credentials credential resolves to automation, and a person's
identifier supplied beside it has no effect.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from canon_issuer import EPOCH, FakeIssuer, impostor_key
from cybercanon.adapters.outbound.auth.cyberdyne import (
    BAD_CLAIMS,
    BAD_SIGNATURE,
    CyberdyneAuth,
    Trust,
)
from cybercanon.adapters.outbound.auth.keys import CachedKeySet, KeySetPolicy
from cybercanon.application.ports.identity_provider import (
    CREDENTIAL_REFUSED,
    CredentialRejected,
    IdentityServiceUnavailable,
    IdentityUnavailable,
)
from cybercanon.domain.identity import Role

ART_LEADS = "cyberdyne-art-leads"
ARTISTS = "cyberdyne-artists"
UNKNOWN_GROUP = "cyberdyne-interns"

WINDOW_S = 900.0
COOLDOWN_S = 10.0


class Ticking:
    """A clock a test moves by hand — the offline window is minutes long."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


@pytest.fixture
def issuer() -> FakeIssuer:
    return FakeIssuer()


@pytest.fixture
def clock() -> Ticking:
    return Ticking()


@pytest.fixture
def keys(issuer: FakeIssuer, clock: Ticking) -> CachedKeySet:
    return CachedKeySet(
        issuer,
        policy=KeySetPolicy(offline_window_s=WINDOW_S, refresh_cooldown_s=COOLDOWN_S),
        clock=clock,
    )


def provider(issuer: FakeIssuer, keys: CachedKeySet, **group_roles: str) -> CyberdyneAuth:
    """The adapter, trusting this issuer and mapping exactly these groups."""
    return CyberdyneAuth(
        trust=Trust(issuer=issuer.issuer, audience=issuer.audience),
        keys=keys,
        group_roles=dict(group_roles) or {ART_LEADS: "ART_DIRECTOR", ARTISTS: "ARTIST"},
        now=lambda: datetime.fromtimestamp(EPOCH, tz=UTC),
    )


@pytest.fixture
def auth(issuer: FakeIssuer, keys: CachedKeySet) -> CyberdyneAuth:
    return provider(issuer, keys)


# --------------------------------------------------------------------------
# 8.1 — verification against the issuer's published keys
# --------------------------------------------------------------------------


def test_a_good_credential_resolves_to_the_person_it_names(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    resolved = auth.resolve(
        issuer.mint(
            "auth|rafa",
            name="Rafa",
            groups=[ARTISTS],
            projects=["Ronin"],
            tenant="cyberdyne",
            git_emails=["rafa@cyberdyne.com"],
        )
    )

    assert resolved.actor.subject == "auth|rafa"
    assert resolved.actor.roles == (Role.ARTIST,)
    assert resolved.actor.may_see("Ronin")
    assert str(resolved.actor.tenant) == "cyberdyne"
    assert resolved.git_emails == ("rafa@cyberdyne.com",)


@pytest.mark.parametrize(
    ("what", "minted"),
    [
        ("expired", {"issued_at": EPOCH - 100_000, "lifetime_s": 60}),
        ("wrong audience", {"audience": "https://another.service"}),
        ("wrong issuer", {"issuer": "https://auth.somebody-else.example"}),
    ],
)
def test_a_credential_outside_the_configured_trust_is_unauthenticated(
    auth: CyberdyneAuth, issuer: FakeIssuer, what: str, minted: dict
) -> None:
    with pytest.raises(CredentialRejected) as raised:
        auth.resolve(issuer.mint("auth|rafa", **minted))

    assert raised.value.kind.value == "unauthenticated", what
    assert raised.value.reason == BAD_CLAIMS


def test_an_unverifiable_signature_is_unauthenticated(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """The right key identifier in the header, the wrong private key underneath."""
    with pytest.raises(CredentialRejected) as raised:
        auth.resolve(issuer.mint("auth|rafa", key=impostor_key(issuer.current)))

    assert raised.value.reason == BAD_SIGNATURE


def test_the_caller_cannot_tell_a_wrong_signature_from_a_wrong_audience(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """The requirement's exact words: recorded, and not disclosed to the caller."""
    refusals = []
    for minted in ({"key": impostor_key(issuer.current)}, {"audience": "https://elsewhere"}):
        with pytest.raises(CredentialRejected) as raised:
            auth.resolve(issuer.mint("auth|rafa", **minted))
        refusals.append(raised.value)

    signature, audience = refusals
    assert signature.message == audience.message == CREDENTIAL_REFUSED
    assert signature.identifier == audience.identifier
    assert signature.reason != audience.reason


def test_a_credential_that_is_not_a_token_at_all_is_refused(auth: CyberdyneAuth) -> None:
    from cybercanon.application.ports.identity_provider import Credential

    with pytest.raises(IdentityUnavailable):
        auth.resolve(Credential("not-a-token-at-all"))


# --------------------------------------------------------------------------
# 8.2 — key rotation, with no restart and no reconfiguration
# --------------------------------------------------------------------------


def test_a_newly_published_key_is_accepted_without_a_restart(
    auth: CyberdyneAuth, issuer: FakeIssuer, keys: CachedKeySet, clock: Ticking
) -> None:
    auth.resolve(issuer.mint("auth|rafa"))
    retrievals = keys.retrievals

    issuer.rotate()
    clock.advance(COOLDOWN_S)
    resolved = auth.resolve(issuer.mint("auth|ana"))

    assert resolved.actor.subject == "auth|ana"
    assert keys.retrievals == retrievals + 1


def test_the_cached_key_set_is_not_re_retrieved_for_every_request(
    auth: CyberdyneAuth, issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """Rotation must not become a request to the issuer per credential."""
    for _ in range(5):
        auth.resolve(issuer.mint("auth|rafa"))

    assert keys.retrievals == 1


def test_an_unknown_key_within_the_cooldown_is_refused_rather_than_re_retrieved(
    auth: CyberdyneAuth, issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """A stream of garbage identifiers cannot be turned into traffic at the issuer."""
    auth.resolve(issuer.mint("auth|rafa"))
    issuer.rotate("key-nobody-waited-for")

    with pytest.raises(CredentialRejected):
        auth.resolve(issuer.mint("auth|rafa"))
    assert keys.retrievals == 1


# --------------------------------------------------------------------------
# 8.3 — the group mapping is configuration, and unmapped grants nothing
# --------------------------------------------------------------------------


def test_an_unmapped_group_grants_no_role(auth: CyberdyneAuth, issuer: FakeIssuer) -> None:
    resolved = auth.resolve(issuer.mint("auth|rafa", groups=[ARTISTS, UNKNOWN_GROUP]))

    assert resolved.actor.roles == (Role.ARTIST,)


def test_an_all_unmapped_credential_resolves_role_less_rather_than_refused(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    resolved = auth.resolve(issuer.mint("auth|rafa", groups=[UNKNOWN_GROUP, "cyberdyne-guests"]))

    assert resolved.actor.subject == "auth|rafa"
    assert resolved.actor.roles == ()


def test_adding_a_mapping_in_configuration_alone_changes_the_resolved_roles(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """The same credential, two configurations, no code between them."""
    credential = issuer.mint("auth|rafa", groups=[UNKNOWN_GROUP])

    before = provider(issuer, keys, **{ARTISTS: "ARTIST"}).resolve(credential)
    after = provider(issuer, keys, **{UNKNOWN_GROUP: "DESIGNER"}).resolve(credential)

    assert before.actor.roles == ()
    assert after.actor.roles == (Role.DESIGNER,)


def test_a_mapping_naming_something_that_is_not_a_role_grants_nothing(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """A typo in configuration grants less, never more."""
    resolved = provider(issuer, keys, **{ARTISTS: "SUPERUSER"}).resolve(
        issuer.mint("auth|rafa", groups=[ARTISTS])
    )

    assert resolved.actor.roles == ()


# --------------------------------------------------------------------------
# 8.4 — nothing of the credential's vocabulary escapes
# --------------------------------------------------------------------------


def test_the_resolution_carries_no_claim_or_group_name(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    credential = issuer.mint("auth|rafa", name="Rafa", groups=[ARTISTS], projects=["Ronin"])

    written = repr(auth.resolve(credential))

    assert ARTISTS not in written
    assert "groups" not in written
    assert credential.value not in written


def test_the_adapter_produces_no_decision(auth: CyberdyneAuth) -> None:
    """It resolves. It cannot allow, deny, or be asked about an operation."""
    surface = {name for name in dir(auth) if not name.startswith("_")}

    assert "resolve" in surface
    assert not surface & {"allow", "deny", "may", "decide", "authorize", "permits"}


# --------------------------------------------------------------------------
# 8.5 — bounded offline degradation
# --------------------------------------------------------------------------


def test_a_valid_credential_is_served_from_cached_keys_during_an_outage(
    auth: CyberdyneAuth, issuer: FakeIssuer, clock: Ticking
) -> None:
    credential = issuer.mint("auth|rafa")
    auth.resolve(credential)

    issuer.go_dark()
    clock.advance(WINDOW_S / 2)

    assert auth.resolve(credential).actor.subject == "auth|rafa"


def test_beyond_the_window_the_refusal_names_the_identity_service(
    auth: CyberdyneAuth, issuer: FakeIssuer, clock: Ticking
) -> None:
    credential = issuer.mint("auth|rafa")
    auth.resolve(credential)

    issuer.go_dark()
    clock.advance(WINDOW_S + 1)

    with pytest.raises(IdentityServiceUnavailable) as raised:
        auth.resolve(credential)
    assert "identity service" in raised.value.message
    assert raised.value.kind.value == "unavailable"


def test_a_credential_needing_a_fresh_key_during_an_outage_is_an_unavailability(
    auth: CyberdyneAuth, issuer: FakeIssuer, clock: Ticking
) -> None:
    """*"or for a credential requiring a fresh exchange"* — it is the issuer that is down."""
    auth.resolve(issuer.mint("auth|rafa"))
    rotated = issuer.mint("auth|rafa", kid=issuer.rotate())

    issuer.go_dark()
    clock.advance(COOLDOWN_S)

    with pytest.raises(IdentityServiceUnavailable):
        auth.resolve(rotated)


def test_the_service_comes_back_and_so_does_verification(
    auth: CyberdyneAuth, issuer: FakeIssuer, clock: Ticking
) -> None:
    credential = issuer.mint("auth|rafa")
    auth.resolve(credential)
    issuer.go_dark()
    clock.advance(WINDOW_S + 1)
    with pytest.raises(IdentityServiceUnavailable):
        auth.resolve(credential)

    issuer.come_back()

    assert auth.resolve(credential).actor.subject == "auth|rafa"


# --------------------------------------------------------------------------
# 8.8 — background work is automation, and cannot be a person
# --------------------------------------------------------------------------


def test_a_service_credential_resolves_to_automation(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    resolved = auth.resolve(
        issuer.mint("cybercanon-worker", grant="client-credentials", projects=["Ronin"])
    )

    assert resolved.actor.is_automation
    assert "automation" in resolved.actor.display


def test_a_service_credential_naming_a_person_is_still_automation(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """A subject that looks like a person does not make automation into one."""
    resolved = auth.resolve(
        issuer.mint("auth|rafa", name="Rafa", grant="client-credentials", groups=[ART_LEADS])
    )

    assert resolved.actor.is_automation
    assert resolved.actor.holds(Role.ART_DIRECTOR)
