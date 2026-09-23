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

Plus 8.8: a client-credentials credential from a client this deployment admits
resolves to automation, and a person's identifier supplied beside it has no
effect.

**Every credential here is minted in the shape CyberdyneAuth really emits** —
`roles` prefixed with the client id, `type`, `orgs`, `org`, `entitlements` and
`is_admin` — because the version of this file that minted `groups`, `projects`
and `gty` was writing both halves of the conversation and could only ever agree
with the adapter.

The last two sections are the ones the fixtures made askable: **project
entitlement**, which is `orgs` plus a role on this client and is nothing else;
and **which service may act at all**, which is a configured list of client ids
and is nothing else either.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from joserfc import jwt

from canon_issuer import (
    ANOTHER_CLIENT_ID,
    EPOCH,
    HOME_ORG,
    ORG_ID,
    ORG_SHORT_NAME,
    OTHER_ORG,
    OTHER_ORG_ID,
    OTHER_SERVICE_CLIENT_ID,
    PRO_MONTHLY,
    WORKER_CLIENT_ID,
    FakeIssuer,
    impostor_key,
    signing_key,
)
from cybercanon.adapters.outbound.auth.cyberdyne import (
    BAD_CLAIMS,
    BAD_SIGNATURE,
    NO_ACTOR,
    NO_SERVICE_CLIENTS,
    SERVICE_CLIENTS_SETTING,
    UNTRUSTED_CLIENT,
    CyberdyneAuth,
    Trust,
)
from cybercanon.adapters.outbound.auth.keys import CachedKeySet, KeySetPolicy
from cybercanon.application.ports.identity_provider import (
    CREDENTIAL_REFUSED,
    Credential,
    CredentialRejected,
    IdentityServiceUnavailable,
    IdentityUnavailable,
)
from cybercanon.domain.authorization import may_author_durable_content
from cybercanon.domain.identity import Actor, Role
from cybercanon.domain.policy import (
    HUMAN_ONLY,
    REQUIRES_PERSON,
    Operation,
    Subject,
    decide,
)

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


def provider(
    issuer: FakeIssuer,
    keys: CachedKeySet,
    *,
    service_clients: tuple[str, ...] = (WORKER_CLIENT_ID,),
    **group_roles: str,
) -> CyberdyneAuth:
    """The adapter, trusting this issuer and mapping exactly these role keys.

    It is told five things, and the last four are what the real token shape made
    necessary: the issuer and audience it accepts, the **client id** its own
    roles are prefixed with, the **organisation** whose members it serves, the
    **project** they read, and the **service clients** whose background work it
    admits. None of them is a constant — an adapter that guessed any of them
    would be the mistake this branch is undoing — and every identifier is this
    fixture's own invented value, so nothing here depends on a record in
    somebody else's database.

    `service_clients` defaults to this deployment's own worker and to nothing
    else, which is what a configured deployment looks like. A scenario that
    wants the *unconfigured* deployment — the one that admits no automation at
    all — passes an empty tuple and gets the fail-closed default the setting
    ships with.
    """
    return CyberdyneAuth(
        trust=Trust(
            issuer=issuer.issuer,
            audience=issuer.audience,
            client_id=issuer.client_id,
            organisation=ORG_ID,
            service_clients=service_clients,
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
    """The deployment's own worker, in the shape the issuer really mints it.

    `WORKER_CLIENT_ID` is the client this adapter was told to admit, which is
    now half of what makes this pass: `type` says *a machine*, and the allowlist
    says *our machine*. The credential carries no `roles`, no `orgs` and no
    `org`, because a client-credentials token carries none of the three.
    """
    resolved = auth.resolve(issuer.mint_service(WORKER_CLIENT_ID))

    assert resolved.actor.is_automation
    assert "automation" in resolved.actor.display


def test_a_service_credential_never_resolves_to_the_person_it_might_name(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """`type` decides it, not the subject — and a service token carries no roles.

    The subject a real client-credentials token carries is `client:<id>`, so an
    admitted service credential resolves to *the client* and there is no shape
    in which a person's identifier comes back out of one. Automation is read
    from `type`, and there is no `roles` claim to read.
    """
    resolved = auth.resolve(issuer.mint_service(WORKER_CLIENT_ID))

    assert resolved.actor.is_automation
    assert resolved.actor.subject == f"client:{WORKER_CLIENT_ID}"
    assert "auth|" not in resolved.actor.subject
    assert resolved.actor.roles == ()


def test_a_service_credential_whose_subject_is_a_person_is_refused_as_malformed(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """`sub` is `client:<id>` on a service token, and a bare person is not guessed at.

    This is the parse being exact rather than helpful. A `type: service` token
    whose subject does not carry the `client:` prefix names no client, so there
    is no id to check against the allowlist — and inventing one from the subject
    would be the adapter deciding who it trusts by reading a string somebody
    else chose. It is refused as a credential that describes no resolvable
    actor, which is a **different** refusal from the trusted-client one below.
    """
    with pytest.raises(CredentialRejected) as raised:
        auth.resolve(issuer.mint("auth|rafa", kind="service"))

    assert raised.value.reason == NO_ACTOR


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


# --------------------------------------------------------------------------
# Which service may act at all: the allowlist, and the hole where it is not
# --------------------------------------------------------------------------
#
# What team-cyberauth found against the live issuer: `_automation()` admits
# **any** token whose `type` is `service`, once the issuer and audience checks
# have passed. In CyberdyneAuth a client-credentials client registered with no
# `allowed_audiences` may request *any* audience, and most of the service
# clients on that issuer are registered exactly that way — so most of them can
# mint a token that names this deployment, and every one of those tokens
# verifies. Until this branch, the adapter resolved every one of them to
# automation and handed it the project.
#
# That is a total failure of the product's sharpest rule. An agent reads
# constraints and never writes them, and a service credential is precisely what
# an agent presents; admitting every service that asks means any unrelated
# background job on the shared issuer authenticates here as trusted automation.
# It is not a missing validation. It is the entitlement decision for automation
# never having been made.
#
# **It is closed.** `Deployment.service_clients` is the list, the setting is
# `CANON_AUTH_SERVICE_CLIENTS`, and the strict xfail that recorded the open
# defect went in the same commit that made it pass — which is what the marker
# said would happen.
#
# The rule that closes it: a configured list of service client ids
# (`CANON_AUTH_SERVICE_CLIENTS`), and a service token admitted **only** when the
# client it names is on that list — the `client_id` claim, or the id inside
# `sub`'s `client:<id>` form. Membership claims cannot stand in for it, because
# a service token carries none.
#
# Nobody caught it because the fixtures could not express it. Every service
# token these suites minted was our own worker, so "a token from a different
# client" was not a case anybody declined to check — it was a case nobody could
# write down. :meth:`FakeIssuer.mint_service` is what makes it writable, and
# these two scenarios are the two halves of the rule: an unlisted client is
# refused, and a listed one is admitted **as automation and as nothing more**.


def presented(auth: CyberdyneAuth, credential: Credential) -> Actor | CredentialRejected:
    """What the adapter did with this credential: the actor it admitted, or the refusal.

    A `pytest.raises` that does not raise reports only that nothing was raised,
    and the interesting half of this failure is *what the adapter handed back
    instead* — which actor, entitled to what. Returning either outcome lets the
    assertion say that out loud, because a report that says "DID NOT RAISE" and
    a report that says "admitted as automation entitled to the project" send a
    reader to different places.
    """
    try:
        return auth.resolve(credential).actor
    except CredentialRejected as refusal:
        return refusal


def test_a_service_credential_from_an_unlisted_client_is_refused(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """The shape eight production clients can mint today, and it must not be a session.

    A different client id, a `sub` of `client:<that id>`, no roles, no orgs —
    and a **valid** audience, because that is the point: nothing about this
    token is malformed. The signature verifies against the issuer's published
    keys, the issuer matches, the audience matches, and it was minted by a
    service that has nothing to do with this deployment. Signature, issuer and
    audience have already agreed; only a list of accepted clients can disagree.
    """
    outcome = presented(auth, issuer.mint_service(OTHER_SERVICE_CLIENT_ID))

    assert isinstance(outcome, CredentialRejected), (
        f"a service credential minted by {OTHER_SERVICE_CLIENT_ID}, a client this "
        f"deployment never listed, was admitted: automation="
        f"{outcome.is_automation}, subject={outcome.subject!r}, "
        f"entitled to {outcome.projects}"
    )
    assert outcome.kind.value == "unauthenticated", (
        "an unlisted client is a credential this deployment does not accept, "
        "not an identity service that could not be reached"
    )
    assert str(outcome) == CREDENTIAL_REFUSED, (
        "and the caller is told the same sentence as for every other refusal"
    )
    assert outcome.reason == UNTRUSTED_CLIENT, (
        "the reason is the log's, and it has to separate *this client is not "
        "trusted here* from *this token is invalid*: an operator sent looking "
        "for a malformed credential would find a perfectly good one"
    )
    assert outcome.reason != NO_ACTOR


def test_both_spellings_of_the_client_resolve_and_neither_is_preferred(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """The recorded shape and the claim-light one name the same client, the same way.

    `sub` carries the id in `client:<id>` form and is the authority, because it
    is also what the admitted actor is recorded as. The `client_id` claim is a
    cross-check that has to agree — it is not consulted *first* and it is not a
    fallback — so a token carrying only `sub`, which is what
    :meth:`FakeIssuer.mint` produces for `service=True`, resolves identically to
    one carrying both.

    This test used to be named for a precedence and asserted only the two cases
    where the claims agree, which is the shape of question that let the
    disagreement through: two spellings of a fact that a fixture could only ever
    write the same way. The case where they differ is asserted below.
    """
    auth = provider(issuer, keys)

    from_claim = auth.resolve(issuer.mint_service(WORKER_CLIENT_ID)).actor
    from_subject = auth.resolve(issuer.mint(WORKER_CLIENT_ID, service=True)).actor

    assert from_claim.is_automation and from_subject.is_automation
    assert from_claim.subject == from_subject.subject == f"client:{WORKER_CLIENT_ID}"
    assert from_claim == from_subject, (
        "the same client, so the same actor — the extra claim adds nothing and "
        "its absence takes nothing away"
    )


def test_a_deployment_that_lists_no_service_client_admits_none(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """The decision this setting makes, stated: **empty admits nothing**.

    Two readings were available for an unset allowlist and only one of them is
    this product's. An empty list admitting *anything* is the hole with a
    configuration file in front of it — every deployment that has not thought
    about automation reproduces it exactly. An empty list admitting *nothing*
    costs a deployment its background work until somebody writes the list down,
    and that is the cost this takes: automation that stops is visible, and
    automation that was never authorised is not.

    So the refusal has to name what is missing. A worker refused because nobody
    configured the allowlist must not read like a worker holding a broken
    token — those send a person to two different places, and only one of them
    has the answer.
    """
    unconfigured = provider(issuer, keys, service_clients=())

    outcome = presented(unconfigured, issuer.mint_service(WORKER_CLIENT_ID))

    assert isinstance(outcome, CredentialRejected), (
        "the very credential a configured deployment admits, refused by one that "
        "has listed nothing — because listing nothing is an answer, and it is no"
    )
    assert outcome.reason == NO_SERVICE_CLIENTS
    assert SERVICE_CLIENTS_SETTING in outcome.reason, (
        "and it names the variable, so the operator reads *nobody set this* "
        "rather than *this token is broken*"
    )
    assert str(outcome) == CREDENTIAL_REFUSED, (
        "the caller still learns nothing beyond the one sentence every refusal "
        "gives: which of our variables is unset is not a stranger's business"
    )


def test_a_service_credential_from_a_listed_client_is_admitted_as_automation_and_no_more(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """The other half of the rule, and the guard on how it is closed.

    An allowlist is an admission decision, never a grant: the client this
    deployment lists reads the project it serves and holds nothing else. It is
    automation, it holds no role, it belongs to no organisation — a service
    token carries no `orgs` for one to be read from — and every operation the
    project reserves to a person is still refused it.

    Written now, before the allowlist exists, because the cheap way to close a
    hole like this is a list whose members are trusted a little more than they
    were, and that would trade one hole for another.
    """
    resolved = auth.resolve(issuer.mint_service(WORKER_CLIENT_ID))
    actor = resolved.actor

    assert actor.is_automation
    assert actor.subject == f"client:{WORKER_CLIENT_ID}"
    assert actor.roles == (), "an allowlist admits; it does not grant"
    assert actor.tenant is None, "a client stands for no person, so it is a member of nothing"
    assert actor.may_see(PROJECT)
    assert decide(actor, Operation.READ_PROJECT, Subject(project=PROJECT)).allowed, (
        "background work that could not read would stop the scheduled refresh"
    )
    assert may_author_durable_content(actor).refused, (
        "and background work that could write would be the rule this product states"
    )


# --------------------------------------------------------------------------
# Trying to get past the allowlist
# --------------------------------------------------------------------------
#
# The list is only as good as the answer to *which client is this*, and that
# answer is read out of a token somebody else wrote. So every way of making the
# adapter read it wrong is a scenario here, and one of them was a second hole.
#
# **`client_id` said ours and `sub` said a stranger, and it was admitted.** The
# allowlist was consulted about the `client_id` claim while
# :func:`~cybercanon.domain.identity.automation_actor` was handed `sub`, so the
# credential was admitted as this deployment's worker and recorded as the other
# client — the decision and the record came out of two different claims. It is
# the same defect as the one above wearing different clothes: a rule written
# against a mental model of an issuer that always writes the two the same way,
# and fixtures that could only write them the same way, so nobody could ask.
# `sub` is now the authority and `client_id` is a cross-check that refuses on
# disagreement, and `FakeIssuer.mint_service` can write the two apart.


def test_a_credential_whose_two_claims_name_two_clients_is_refused(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """Both directions, because only one of them used to be refused.

    `client_id=ours, sub=theirs` was **admitted** before this branch: the check
    read one claim and the record kept the other, so a stranger's client was
    resolved as trusted automation under this deployment's own worker's
    admission. `client_id=theirs, sub=ours` was refused, and the asymmetry is
    the tell — a rule that answers differently depending on which of two claims
    a caller lies in is not reading one fact, it is preferring one claim.

    Neither is a token any issuer mints, and that is not a reason to allow one:
    both verify, both carry this issuer and this audience, and what the adapter
    does with a credential nobody predicted is the whole subject of this branch.
    """
    ours_theirs = issuer.mint_service(WORKER_CLIENT_ID, subject=f"client:{OTHER_SERVICE_CLIENT_ID}")
    theirs_ours = issuer.mint_service(OTHER_SERVICE_CLIENT_ID, subject=f"client:{WORKER_CLIENT_ID}")

    admitted = presented(auth, ours_theirs)
    assert isinstance(admitted, CredentialRejected), (
        "a credential claiming our client in `client_id` and a stranger's in "
        f"`sub` was admitted: subject={getattr(admitted, 'subject', None)!r} — "
        "checked as one client, recorded as another"
    )
    assert admitted.reason == NO_ACTOR, (
        "two claims naming two clients describe no actor to resolve, which is "
        "not the same refusal as a client that is simply not on the list"
    )
    assert admitted.reason != UNTRUSTED_CLIENT

    assert isinstance(presented(auth, theirs_ours), CredentialRejected), (
        "and the mirror image, so the rule cannot be satisfied from either side"
    )


@pytest.mark.parametrize(
    ("what", "subject"),
    [
        ("nothing after the prefix", "client:"),
        ("whitespace after the prefix", "client:   "),
        ("a padded id", f"client: {WORKER_CLIENT_ID}"),
    ],
)
def test_a_subject_that_only_looks_like_it_names_a_client_names_none(
    issuer: FakeIssuer, keys: CachedKeySet, what: str, subject: str
) -> None:
    """`client:<id>` is parsed exactly, and a near miss is not read as a hit.

    The padded shapes are the interesting two. Trimming `client: <id>` into
    `<id>` would check the allowlist against an identifier the credential does
    not carry, and then record the actor as the padded subject it does — the
    same decision-and-record split as the disagreement above, reached by a
    different route. Nothing arriving inside a token is normalised on its way to
    the list; trimming belongs to the **configured** side, where an operator's
    stray space is a typo rather than an assertion.

    Every one of these is minted with no `client_id` claim, which is the
    claim-light service shape, so `sub` is the only thing naming a client and
    there is no second claim to be rescued by.
    """
    auth = provider(issuer, keys)

    outcome = presented(auth, issuer.mint_service(WORKER_CLIENT_ID, subject=subject, named=False))

    assert isinstance(outcome, CredentialRejected), (
        f"a subject with {what} was admitted as {getattr(outcome, 'subject', None)!r}"
    )
    assert outcome.reason == NO_ACTOR, what


def test_the_prefix_is_stripped_once_and_never_unwrapped_again(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """`client:client:<id>` names a client called `client:<id>`, and that is nobody.

    The parse takes the prefix off once and treats the remainder as an opaque
    identifier — it does not go looking for a client id inside it. A reader that
    unwrapped repeatedly would let a subject be written so that the id the
    allowlist sees is not the last thing in the string, which is the shape this
    kind of check is usually defeated by.
    """
    outcome = presented(
        auth,
        issuer.mint_service(
            WORKER_CLIENT_ID, subject=f"client:client:{WORKER_CLIENT_ID}", named=False
        ),
    )

    assert isinstance(outcome, CredentialRejected)
    assert outcome.reason == UNTRUSTED_CLIENT, (
        "the id it names is the literal `client:<id>`, which is not on the list "
        "— refused as an unlisted client rather than unwrapped into a listed one"
    )


def test_the_client_the_allowlist_is_asked_about_is_the_one_that_gets_recorded(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """The invariant the whole of this fix is about, asserted directly.

    A subject padded on the *outside* is trimmed once, before anything reads it,
    and the trimmed value is both what the allowlist is asked about and what the
    actor is recorded as. That is the difference between this and the shapes
    refused above: nothing is normalised *between* the check and the record, so
    there is no gap for the two to disagree in. The credential that was admitted
    and the identity that was written down name the same client, which is the
    property that failed before this branch.
    """
    padded = issuer.mint_service(WORKER_CLIENT_ID, subject=f" client:{WORKER_CLIENT_ID} ")

    resolved = auth.resolve(padded)

    assert resolved.actor.subject == f"client:{WORKER_CLIENT_ID}"
    assert resolved.actor.subject.removeprefix("client:") == WORKER_CLIENT_ID, (
        "and the id inside it is the one the deployment listed, verbatim"
    )


@pytest.mark.parametrize(
    ("what", "value"),
    [("empty", ""), ("whitespace", "   "), ("a number", 7), ("a list", [WORKER_CLIENT_ID])],
)
def test_a_client_id_claim_that_names_no_client_is_not_an_absent_one(
    auth: CyberdyneAuth, issuer: FakeIssuer, what: str, value: object
) -> None:
    """Present and unreadable is a broken claim, not a claim-light token.

    A service token legitimately carries no `client_id` claim, and `sub` names
    its client on its own. A token that carries the claim and puts *nothing
    readable* in it is a different thing entirely, and falling back to `sub` for
    it would mean the one claim whose job is to name the client can be filled
    with anything at all and still be ignored into a pass. The claim is the
    cross-check; a cross-check that cannot be read has failed.
    """
    minted = issuer.mint_service(WORKER_CLIENT_ID, named=False)
    tampered = _reissued(issuer, minted, client_id=value)

    outcome = presented(auth, tampered)

    assert isinstance(outcome, CredentialRejected), (
        f"a `client_id` claim carrying {what} was ignored in favour of `sub`"
    )
    assert outcome.reason == NO_ACTOR, what


@pytest.mark.parametrize("kind", ["Service", "SERVICE", "sErViCe", "services", "svc"])
def test_the_kind_claim_is_matched_exactly_and_never_case_insensitively(
    auth: CyberdyneAuth, issuer: FakeIssuer, kind: str
) -> None:
    """`type` is compared to `service` as written, and a near miss is neither kind.

    It matters in both directions and the unusual one is why it is here. A
    reader that lower-cased `type` would turn `Service` into automation, which
    is the *safer* of the two kinds — but the same leniency applied to `access`
    would turn `Access` into a person, and a comparison is lenient or it is not.
    So neither is: an unrecognised `type` is refused as a credential describing
    no actor, exactly as `id` is.
    """
    outcome = presented(auth, issuer.mint(WORKER_CLIENT_ID, service=True, kind=kind))

    assert isinstance(outcome, CredentialRejected), (
        f"type={kind!r} was read as one of the two kinds this adapter knows"
    )
    assert outcome.reason == NO_ACTOR


@pytest.mark.parametrize(
    ("what", "listed"),
    [
        ("upper-cased", (WORKER_CLIENT_ID.upper(),)),
        ("lower-cased", (WORKER_CLIENT_ID.lower(),)),
        ("padded", (f"  {WORKER_CLIENT_ID}  ",)),
        ("a prefix of ours", (WORKER_CLIENT_ID[:-2],)),
        ("ours with something appended", (f"{WORKER_CLIENT_ID}x",)),
        ("internally spaced", (f"{WORKER_CLIENT_ID[:4]} {WORKER_CLIENT_ID[4:]}",)),
    ],
)
def test_an_allowlist_entry_matches_a_client_id_exactly_or_not_at_all(
    issuer: FakeIssuer, keys: CachedKeySet, what: str, listed: tuple[str, ...]
) -> None:
    """A client id is opaque, so the comparison is exact and fails closed.

    Case-folding it would be inventing an equivalence the issuer never promised
    — two client ids differing only in case are two clients — and trimming it
    here would be normalising the **token's** side of the comparison, which is
    the mistake above. An entry that does not match admits nobody, which is the
    direction a configuration mistake has to fail in: an operator whose worker
    stopped goes and looks at the variable, and the refusal names it.

    An operator's stray whitespace is handled where it belongs, one layer up:
    `client_ids` trims each entry as it reads `CANON_AUTH_SERVICE_CLIENTS`, so
    the padded case never reaches here from a real deployment. It is asserted
    anyway, because the adapter must not depend on having been configured by
    that reader to be safe.
    """
    auth = provider(issuer, keys, service_clients=listed)

    outcome = presented(auth, issuer.mint_service(WORKER_CLIENT_ID))

    assert isinstance(outcome, CredentialRejected), f"an entry that is {what} matched"
    assert outcome.reason == UNTRUSTED_CLIENT, (
        "the list was configured, so this is the client-not-listed refusal "
        "rather than the nobody-configured-the-list one"
    )


def test_a_persons_credential_carrying_a_client_id_claim_is_still_a_person(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """The allowlist is consulted for `type: service` and for nothing else.

    A `client_id` claim on an `access` token names the client the token was
    issued *through*, and it has never been an entitlement. Reading it on this
    path would let a person's session inherit whatever the allowlist grants —
    which is nothing today, and the point of asserting it is that it stays
    nothing the day somebody widens the list.
    """
    minted = issuer.mint("auth|rafa", roles=[ARTIST_KEY])
    resolved = auth.resolve(_reissued(issuer, minted, client_id=WORKER_CLIENT_ID))

    assert not resolved.actor.is_automation
    assert resolved.actor.subject == "auth|rafa"
    assert resolved.actor.roles == (Role.ARTIST,), "their roles, and not one more"


def test_an_unlisted_person_is_unaffected_by_the_allowlist_being_empty(
    issuer: FakeIssuer, keys: CachedKeySet
) -> None:
    """Listing no service client stops automation and nothing else.

    The fail-closed default has a cost and it has to be *this* cost. A
    deployment that has not configured the allowlist loses its background work;
    if it also lost its people, the pressure to set the variable to something
    permissive would arrive on day one and from the wrong direction.
    """
    unconfigured = provider(issuer, keys, service_clients=())

    resolved = unconfigured.resolve(issuer.mint("auth|rafa", roles=[ARTIST_KEY]))

    assert resolved.actor.roles == (Role.ARTIST,)
    assert resolved.actor.may_see(PROJECT)


# --------------------------------------------------------------------------
# What being on the list is not: the guarantee that predates it
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", list(Role))
def test_an_allowlisted_service_is_refused_every_human_only_operation_holding_any_role(
    auth: CyberdyneAuth, issuer: FakeIssuer, role: Role
) -> None:
    """Admitted, holding one role, and still refused all six. For every role.

    The parametrisation is the argument. `HUMAN_ONLY` is checked before any rule
    that reads a role, so an automated caller holding *the very role the
    operation requires* is refused by kind rather than by permission — and the
    only way to say that out loud is to hand it each role in turn and watch all
    six refuse anyway.

    The actor is the real admitted one, taken from the adapter and then given a
    role it could not have obtained, rather than a constructed stand-in: the
    claim being made is about what this deployment admits, so the thing under
    test has to be what this deployment admitted. An allowlist is an admission
    decision; it has never been a grant, and it must not become one by the back
    door of somebody later deciding a trusted client deserves a role.
    """
    admitted = auth.resolve(issuer.mint_service(WORKER_CLIENT_ID)).actor
    holding = replace(admitted, roles=(role,))

    assert holding.holds(role), "the role really is held, so the refusal is not about absence"
    for operation in HUMAN_ONLY:
        decision = decide(holding, operation, Subject(project=PROJECT))
        assert not decision.allowed, f"{operation} allowed to automation holding {role}"
        assert REQUIRES_PERSON in decision.reason, (
            f"{operation} refused for some reason other than needing a person"
        )
    assert may_author_durable_content(holding).refused, (
        "and authoring durable content — the rule the whole product turns on"
    )


def test_every_operation_this_product_reserves_to_a_person_is_in_that_set(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """The six by name, so a deletion from the registry fails here too.

    The test above iterates `HUMAN_ONLY`, which would keep passing if somebody
    emptied it. This names what the assignment names — promote, accept, decide,
    resolve, reopen, transition — so the set cannot shrink quietly.
    """
    assert {
        Operation.PROMOTE_TO_RULE,
        Operation.ACCEPT_SUGGESTED_ALIAS,
        Operation.DECIDE_REQUEST,
        Operation.RESOLVE_ISSUE,
        Operation.REOPEN_ISSUE,
        Operation.TRANSITION_ASSET_STATUS,
    } == HUMAN_ONLY

    admitted = auth.resolve(issuer.mint_service(WORKER_CLIENT_ID)).actor

    assert decide(admitted, Operation.READ_PROJECT, Subject(project=PROJECT)).allowed, (
        "background work still reads, which is what it is admitted for"
    )


def _reissued(issuer: FakeIssuer, credential: Credential, **overrides: object) -> Credential:
    """The same claims, re-signed with these ones added. A shape, not a forgery.

    Some of what the adapter has to survive is a claim `FakeIssuer` has no
    parameter for — a `client_id` carrying a list, an `access` token carrying a
    `client_id` at all — and inventing a parameter per shape would turn the
    fixture into a copy of the argument. This re-signs with the issuer's own
    current key, so what reaches the adapter is a credential that **verifies**,
    which is the only kind whose handling is in question here.
    """
    signer = signing_key(issuer.current)
    claims = dict(jwt.decode(credential.value, signer).claims) | dict(overrides)
    return Credential(jwt.encode({"alg": "RS256", "kid": signer.kid}, claims, signer))


# --------------------------------------------------------------------------
# What the fixture mints, against what the issuer really sends
# --------------------------------------------------------------------------
#
# The suites above are only as true as the credentials they are handed, and this
# branch exists because they once were not: the fixtures minted `groups`,
# `projects` and `gty`, the adapter read them back, and both halves of the
# conversation agreed for months about a token nobody had ever seen. So the
# shape itself is asserted here rather than trusted — and each of these three
# deletes a claim rather than adding one, which is the direction a correction
# takes when the original mistake was inventing a field.


def claims_of(credential: Credential, issuer: FakeIssuer) -> dict:
    """The claims inside a minted credential, read the way a verifier reads them."""
    return dict(jwt.decode(credential.value, signing_key(issuer.current)).claims)


def test_the_primary_organisation_claim_carries_no_github_login(issuer: FakeIssuer) -> None:
    """`org` is `{id, short_name}`; only `orgs` entries carry `github_login`.

    Both claims were read off the live issuer and they are not the same object.
    A fixture minting a key the issuer never sends is exactly how this branch's
    first bug survived, so the two shapes are asserted apart from each other:
    the entry in the list has three fields and the primary has two.
    """
    minted = claims_of(issuer.mint("auth|rafa", roles=[ARTIST_KEY]), issuer)

    assert minted["org"] == {"id": ORG_ID, "short_name": ORG_SHORT_NAME}
    assert "github_login" not in minted["org"]
    assert minted["orgs"] == [HOME_ORG], "the list entry keeps all three, as it really does"
    assert "github_login" in minted["orgs"][0]


def test_a_service_token_carries_no_membership_and_no_roles(issuer: FakeIssuer) -> None:
    """The recorded service shape, exactly: nine claims, and none of them membership.

    `iss`, `sub`, `aud`, `client_id`, `type`, `scope`, `iat`, `exp`, `jti` — and
    **no `orgs`, no `org`, no `roles`**. This suite already assumed as much; it
    is asserted now because the assumption became the argument. Entitlement for
    automation cannot be read from membership when there is no membership claim
    to read, which is why it is a list of client ids and nothing else.
    """
    minted = claims_of(issuer.mint_service(WORKER_CLIENT_ID), issuer)

    assert set(minted) == {"iss", "sub", "aud", "client_id", "type", "scope", "iat", "exp", "jti"}
    assert minted["sub"] == f"client:{WORKER_CLIENT_ID}"
    assert minted["client_id"] == WORKER_CLIENT_ID
    assert minted["aud"] == issuer.audience, (
        "and it names *us* — the ordinary case, because a client with no "
        "audience restriction may ask for any audience it likes"
    )


def test_an_admitted_service_actor_is_built_exactly_as_it_always_was(
    auth: CyberdyneAuth, issuer: FakeIssuer
) -> None:
    """`Actor.tenant` stays as built: automation belongs to no organisation.

    The allowlist changes *who is admitted* and nothing about what an admitted
    actor is. A client stands for no person, so it is a member of nothing and
    its tenant is `None` — not this deployment's organisation, which would be
    the tempting mistake now that a list says the client is ours. Being trusted
    is not being a member.
    """
    actor = auth.resolve(issuer.mint_service(WORKER_CLIENT_ID)).actor

    assert actor.tenant is None
    assert actor.projects == (PROJECT,)
    assert actor.roles == ()
