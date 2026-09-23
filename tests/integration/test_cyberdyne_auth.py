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
* **mapping** (8.3) — unmapped role keys grant nothing, an all-unmapped
  credential resolves role-less rather than being refused, and a mapping added
  to the configuration alone changes the resolved roles;
* **degradation** (8.5) — cached keys keep verifying while the issuer is
  unreachable, and beyond the configured window the refusal names the identity
  service.

Plus 8.8: a client-credentials credential resolves to automation, and a person's
identifier supplied beside it has no effect.

**Every credential here is minted in the shape CyberdyneAuth really emits** —
`roles` prefixed with the client id, `type`, `orgs`, `org`, `entitlements` and
`is_admin` — because the version of this file that minted `groups`, `projects`
and `gty` was writing both halves of the conversation and could only ever agree
with the adapter.

The last section is new and is the one the fixtures made askable: **project
entitlement**, which is `orgs` plus a role on this client and is nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from canon_issuer import (
    ANOTHER_CLIENT_ID,
    EPOCH,
    HOME_ORG,
    ORG_ID,
    OTHER_ORG,
    OTHER_ORG_ID,
    PRO_MONTHLY,
    FakeIssuer,
    impostor_key,
)
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

ART_LEAD_KEY = "art_director"
ARTIST_KEY = "artist"
UNMAPPED_KEY = "intern"
"""Role keys as CyberdyneAuth spells them, unprefixed — the mapping's side.

The issuer writes each of these into the `roles` claim as
`<client id>:<role key>`. What configuration names is the key, which is why the
mapping below is keyed on the bare value and the prefix never appears here.
"""

PROJECT = "Ronin"
"""The one project this deployment serves — `CANON_PROJECT`, in the hosted case.

Entitlement is no longer a list of project names on the credential, because
CyberdyneAuth sends no such list. A deployment serves a project, and a person
either may read it or may not; :data:`PROJECT` is the name the adapter has to be
told, the way it is told its issuer and its audience.
"""

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
    """The adapter, trusting this issuer and mapping exactly these role keys.

    It is told four things, and the last three are what the real token shape
    made necessary: the issuer and audience it accepts, the **client id** its
    own roles are prefixed with, the **organisation** whose members it serves,
    and the **project** they read. None of them is a constant — an adapter that
    guessed any of them would be the mistake this branch is undoing — and the
    two identifiers are this fixture's own invented values, so nothing here
    depends on a record in somebody else's database.
    """
    return CyberdyneAuth(
        trust=Trust(
            issuer=issuer.issuer,
            audience=issuer.audience,
            client_id=issuer.client_id,
            organisation=ORG_ID,
        ),
        keys=keys,
        project=PROJECT,
        group_roles=dict(group_roles) or {ART_LEAD_KEY: "ART_DIRECTOR", ARTIST_KEY: "ARTIST"},
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
        issuer.mint("auth|rafa", roles=[ARTIST_KEY], entitlements=[PRO_MONTHLY])
    )

    assert resolved.actor.subject == "auth|rafa"
    assert resolved.actor.roles == (Role.ARTIST,)
    assert resolved.actor.may_see(PROJECT)
    assert str(resolved.actor.tenant) == ORG_ID, (
        "the tenant is the organisation's id — `short_name` and `github_login` "
        "are display and integration fields, and one of them is null today"
    )
    assert resolved.git_emails == (), "a real access token carries no commit addresses (D13)"


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
    resolved = auth.resolve(issuer.mint("auth|rafa", roles=[ARTIST_KEY, UNMAPPED_KEY]))

    assert resolved.actor.roles == (Role.ARTIST,)


def test_an_all_unmapped_credential_resolves_role_less_rather_than_refused(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    resolved = auth.resolve(issuer.mint("auth|rafa", roles=[UNMAPPED_KEY, "guest"]))

    assert resolved.actor.subject == "auth|rafa"
    assert resolved.actor.roles == ()


def test_adding_a_mapping_in_configuration_alone_changes_the_resolved_roles(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """The same credential, two configurations, no code between them."""
    credential = issuer.mint("auth|rafa", roles=[UNMAPPED_KEY])

    before = provider(issuer, keys, **{ARTIST_KEY: "ARTIST"}).resolve(credential)
    after = provider(issuer, keys, **{UNMAPPED_KEY: "DESIGNER"}).resolve(credential)

    assert before.actor.roles == ()
    assert after.actor.roles == (Role.DESIGNER,)


def test_a_mapping_naming_something_that_is_not_a_role_grants_nothing(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """A typo in configuration grants less, never more."""
    resolved = provider(issuer, keys, **{ARTIST_KEY: "SUPERUSER"}).resolve(
        issuer.mint("auth|rafa", roles=[ARTIST_KEY])
    )

    assert resolved.actor.roles == ()


# --------------------------------------------------------------------------
# 8.4 — nothing of the credential's vocabulary escapes
# --------------------------------------------------------------------------


def test_the_resolution_carries_no_claim_or_group_name(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    credential = issuer.mint("auth|rafa", roles=[ARTIST_KEY], entitlements=[PRO_MONTHLY])

    written = repr(auth.resolve(credential))

    assert ARTIST_KEY not in written
    assert issuer.qualified(ARTIST_KEY) not in written
    assert "entitlements" not in written
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
        issuer.mint("cybercanon-worker", service=True, entitlements=[PRO_MONTHLY])
    )

    assert resolved.actor.is_automation
    assert "automation" in resolved.actor.display


def test_a_service_credential_naming_a_person_is_still_automation(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """`type` decides it, not the subject — and a service token carries no roles.

    The subject a real client-credentials token carries is `client:<id>`, so the
    person's identifier can only ever reach the adapter wrapped in that prefix.
    Automation is read from `type`, and there is no `roles` claim to read.
    """
    resolved = auth.resolve(issuer.mint("auth|rafa", service=True))

    assert resolved.actor.is_automation
    assert resolved.actor.roles == ()


def test_a_credential_of_an_unrecognised_kind_is_refused(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """`type` is how a person is told from a service, so an unknown one is neither.

    CyberdyneAuth mints more than these two kinds — an id token is the obvious
    one — and every one of them verifies against the same keys and carries the
    same audience. Reading an unrecognised `type` as a person would make the
    adapter's answer to *"is this a session?"* a guess, and the shape it would
    guess wrong about is the one that is not a session at all.
    """
    with pytest.raises(CredentialRejected):
        auth.resolve(issuer.mint("auth|rafa", roles=[ARTIST_KEY], kind="id"))


def test_a_credential_carrying_no_kind_at_all_is_refused(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """Absence is not `access`: a default that is a guess is worse than a refusal."""
    with pytest.raises(CredentialRejected):
        auth.resolve(issuer.mint("auth|rafa", roles=[ARTIST_KEY], kind=""))


# --------------------------------------------------------------------------
# The two properties only the real token shape can be asked about
# --------------------------------------------------------------------------


def test_a_role_held_on_another_client_grants_nothing_here(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """`roles` covers every client the person has a role on, so it must be filtered.

    CyberdyneAuth answers with one claim for the whole organisation. A reader
    that took it as given would hand somebody CyberCanon's art director because
    they are an art director in a different application, which is the sharpest
    privilege escalation this shape makes available.
    """
    resolved = auth.resolve(
        issuer.mint("auth|rafa", roles=[ARTIST_KEY, f"{ANOTHER_CLIENT_ID}:{ART_LEAD_KEY}"])
    )

    assert resolved.actor.roles == (Role.ARTIST,)


def test_an_absent_roles_claim_is_not_read_as_no_roles(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """An absent claim means IAM was unreachable, and that is not an answer.

    `roles: []` says *this person holds nothing*; no `roles` claim at all says
    *nobody asked IAM successfully*. Resolving the second one role-less would
    turn an identity-service outage into a silently powerless session, which is
    the failure this whole branch exists over. It fails closed: the resolution
    does not produce an actor.
    """
    with pytest.raises(IdentityUnavailable):
        auth.resolve(issuer.mint("auth|rafa", roles=None))


# --------------------------------------------------------------------------
# Project entitlement: `orgs` AND a role on this client, and nothing else
# --------------------------------------------------------------------------
#
# The rule, settled by team-cyberauth against production:
#
#   A person may read the project **iff** `orgs[].id` contains the org id this
#   deployment belongs to **AND** `roles` holds at least one entry prefixed with
#   this deployment's client id.
#
# Every scenario below is one clause of that sentence, in both directions. They
# are here rather than in a unit test because entitlement is behaviour — the
# question "can this person open this project" is the one an operator asks — and
# because the claims they are made of only exist once a real issuer mints them.
#
# Four things the rule is *not*, each of which was somebody's first instinct:
#
#   * not `org` — that is the primary organisation only, so keying on it locks
#     out a member whose primary is elsewhere;
#   * not `entitlements` — those are billing products;
#   * not `github_login` — nullable, and null for the only organisation today;
#   * not `is_admin` — an admin flag that quietly widens access is what gets
#     added later "to unblock someone".


def entitling(
    issuer: FakeIssuer, keys: CachedKeySet, *, organisation: str = ORG_ID
) -> CyberdyneAuth:
    """The adapter as it must be configured for entitlement to be decidable.

    Three things today's `CyberdyneAuth` is not told and has to be: the
    organisation this deployment belongs to, the client id its roles are
    prefixed with, and the project it serves. The first is a new setting
    (`CANON_AUTH_ORG_ID`) — **configuration**, never a constant, because a
    hard-coded org id would tie this repository to one organisation's database
    and would have to be edited by the second studio to install it.

    It differs from :func:`provider` in one parameter and that parameter is the
    point: `organisation` is what the deployment was told, so a scenario can
    hand the same credential to two deployments and watch one admit it and the
    other refuse.
    """
    return CyberdyneAuth(
        trust=Trust(
            issuer=issuer.issuer,
            audience=issuer.audience,
            client_id=issuer.client_id,
            organisation=organisation,
        ),
        keys=keys,
        project=PROJECT,
        group_roles={ART_LEAD_KEY: "ART_DIRECTOR", ARTIST_KEY: "ARTIST"},
        now=lambda: datetime.fromtimestamp(EPOCH, tz=UTC),
    )


def test_a_member_of_this_organisation_holding_a_role_here_reads_the_project(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """Both clauses satisfied — and note the org is matched on a null `github_login`."""
    resolved = entitling(issuer, keys).resolve(
        issuer.mint("auth|rafa", roles=[ARTIST_KEY], orgs=[HOME_ORG])
    )

    assert resolved.actor.may_see(PROJECT)


def test_a_member_of_another_organisation_is_refused(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """A role on this client is not membership. Someone else's employee reads nothing.

    They resolve — they are a real person with a real credential — and they are
    entitled to nothing, which is the shape D4 already gives a person holding no
    role: a refusal that names what is missing, rather than an outage.
    """
    resolved = entitling(issuer, keys).resolve(
        issuer.mint("auth|ana", roles=[ARTIST_KEY], orgs=[OTHER_ORG])
    )

    assert not resolved.actor.may_see(PROJECT)


def test_an_empty_organisation_list_is_refused(issuer: FakeIssuer, keys: CachedKeySet) -> None:
    """`orgs: []` is an answer, and the answer is no."""
    resolved = entitling(issuer, keys).resolve(issuer.mint("auth|ana", roles=[ARTIST_KEY], orgs=[]))

    assert not resolved.actor.may_see(PROJECT)


def test_a_credential_carrying_no_organisation_claim_at_all_is_refused(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """The legacy token: the claim does not exist, so membership is unproven.

    This is the second shape of absence and it fails closed for the same reason
    as the first. "The claim is missing" has never been a reason to let somebody
    in, and a reader that treated an absent `orgs` as permissive would admit
    every token minted before the claim existed.
    """
    resolved = entitling(issuer, keys).resolve(
        issuer.mint("auth|ana", roles=[ARTIST_KEY], orgs=None)
    )

    assert not resolved.actor.may_see(PROJECT)


def test_a_member_holding_no_role_on_this_client_is_refused(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """Membership is not access either. Both clauses, or neither."""
    resolved = entitling(issuer, keys).resolve(issuer.mint("auth|ana", roles=[], orgs=[HOME_ORG]))

    assert not resolved.actor.may_see(PROJECT)


def test_a_role_on_another_client_alone_does_not_entitle(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """`roles` spans every client, so an unfiltered reader admits other applications.

    A member of this organisation who is an art director *somewhere else* holds
    no role here, maps to no domain role, and reads nothing.
    """
    resolved = entitling(issuer, keys).resolve(
        issuer.mint("auth|ana", roles=[f"{ANOTHER_CLIENT_ID}:{ART_LEAD_KEY}"], orgs=[HOME_ORG])
    )

    assert resolved.actor.roles == ()
    assert not resolved.actor.may_see(PROJECT)


def test_an_administrator_who_is_not_a_member_is_still_refused(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """`is_admin` does not bypass. Written down before anybody needs it to.

    An admin flag that quietly widens access is exactly what gets added later to
    unblock somebody, and the moment to refuse it is while nobody is blocked.
    """
    resolved = entitling(issuer, keys).resolve(
        issuer.mint("auth|root", roles=[ARTIST_KEY], orgs=[OTHER_ORG], is_admin=True)
    )

    assert not resolved.actor.may_see(PROJECT)


def test_a_member_whose_primary_organisation_is_elsewhere_still_reads(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """The reason the rule reads `orgs` and not `org`.

    `org` is the person's primary organisation. Keying on it would have worked
    for the one test account and for nobody else, and would have read like an
    intermittent permissions problem rather than a design error — which is why
    team-cyberauth refused it.
    """
    resolved = entitling(issuer, keys).resolve(
        issuer.mint("auth|ana", roles=[ARTIST_KEY], orgs=[OTHER_ORG, HOME_ORG], org=OTHER_ORG)
    )

    assert resolved.actor.may_see(PROJECT)


def test_the_organisation_is_configuration_rather_than_a_constant(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """One credential, two deployments: the same person reads one and not the other.

    The org id is `CANON_AUTH_ORG_ID`, set by the operator. A second studio
    installing CyberCanon changes a variable, and no org id is written into this
    repository — including into this test, whose two values are invented.
    """
    credential = issuer.mint("auth|ana", roles=[ARTIST_KEY], orgs=[HOME_ORG])

    ours = entitling(issuer, keys, organisation=ORG_ID).resolve(credential)
    theirs = entitling(issuer, keys, organisation=OTHER_ORG_ID).resolve(credential)

    assert ours.actor.may_see(PROJECT)
    assert not theirs.actor.may_see(PROJECT)
