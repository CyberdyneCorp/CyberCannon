"""Step definitions for `auth-integration` — all of it, now that group 8 exists.

Four of these scenarios were bound a sprint early, and the reason is worth
keeping in view because it is the requirement's own argument:

> *"Authorization decisions and recorded actions SHALL be expressed in terms of
> a resolved actor carrying a stable identifier and a set of domain roles ... so
> that authorization behaviour can be exercised with no identity service
> present."*

A decision from a constructed actor, the same decision whether the actor was
resolved or built by hand, a cross-tenant address refused by policy, and a
record carrying a subject and no claim vocabulary — if any of those had needed
an adapter, the requirement they come from would already have been broken.

The other nineteen are group 8's, and they run against `canon_issuer.FakeIssuer`
rather than against a double: it signs with real RSA keys, publishes a real key
set, rotates it, enforces the PKCE comparison at its token endpoint, and can be
told to stop answering. Every one of these scenarios is about a credential the
adapter did not mint, so the thing minting them has to be real in exactly those
places.

**The scoping these scenarios pin down, and which is easy to lose:** on the
networked surface a request with no credential is *refused*, never served as an
anonymous actor (`Degradation never elevates`); the local unauthenticated actor
belongs to the local process surface and is reached through a different use case
entirely (`Validation still requires no sign-in`). Both are here, next to each
other, so a change that merged them fails twice.
"""

from __future__ import annotations

import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from canon_issuer import (
    AUTHORIZE_PATH,
    DEVICE_CODE_PATH,
    EPOCH,
    ORG_ID,
    PRO_MONTHLY,
    TOKEN_PATH,
    FakeIssuer,
    impostor_key,
)
from cybercanon.adapters.outbound.auth.cyberdyne import CyberdyneAuth, Trust
from cybercanon.adapters.outbound.auth.flows import (
    BrowserSignIn,
    DeviceAuthorization,
    Endpoints,
)
from cybercanon.adapters.outbound.auth.keychain import KeychainCredentialStore
from cybercanon.adapters.outbound.auth.keys import CachedKeySet, KeySetPolicy
from cybercanon.adapters.outbound.auth.oauth import OAuthRefusal
from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.authenticate import (
    authenticate,
    authenticate_background,
)
from cybercanon.application.use_cases.hosted_repository import FetchSchedule, scheduled_refresh
from cybercanon.application.use_cases.sign_in import sign_in, sign_in_status, sign_out
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.authorization import WRONG_TENANT
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.identity import (
    Actor,
    ActorId,
    Attribution,
    Role,
    attribute,
    automation_actor,
)
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.policy import Operation, Subject, decide
from cybercanon.domain.requests import Discipline, EventKind, RequestId, raise_request
from cybercanon.domain.tenancy import ProjectRef, Tenant

PROJECT = "cyberdyne-game"
CYBERDYNE = Tenant("cyberdyne")
IRONWOOD = Tenant("ironwood-studios")

SUBJECT = "auth|rafa"
RAFA = ActorId(SUBJECT)
TOKEN = Credential("an-opaque-credential")

GROUP = "art-leads"
CLAIM = "https://auth.cyberdynecorp.ai/groups"

ARTIST_KEY = "artist"
INTERN_KEY = "intern"
MAPPED = {ARTIST_KEY: "ARTIST"}
"""Role keys as CyberdyneAuth spells them, and the one this suite maps.

The feature calls these *groups*, which is the specification's word for
"whatever the identity service names a thing that maps to a domain role". What
CyberdyneAuth actually sends is a `roles` claim whose every entry is prefixed
with the client id it belongs to, so the issuer below writes
`<client id>:artist` and configuration still names the bare key.
"""

WINDOW_S = 900.0
COOLDOWN_S = 10.0

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

ASSET_ID = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"


@pytest.fixture
def identity() -> dict[str, Any]:
    """What this scenario resolved, and what the policy said about it."""
    return {}


def a_person(*roles: Role, tenant: Tenant | None = None) -> Actor:
    return Actor(id=RAFA, display_name="Rafa", roles=roles, projects=(PROJECT,), tenant=tenant)


# --------------------------------------------------------------------------
# The issuer, the clock, and the adapter over both
# --------------------------------------------------------------------------


class Ticking:
    """A clock a step moves by hand — the offline window is minutes long."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


def a_verifier(identity: dict[str, Any], **group_roles: str) -> CyberdyneAuth:
    """A CyberdyneAuth adapter over a fresh issuer, remembered by the scenario."""
    issuer = identity.setdefault("issuer", FakeIssuer())
    clock = identity.setdefault("clock", Ticking())
    keys = identity.setdefault(
        "keys",
        CachedKeySet(
            issuer,
            policy=KeySetPolicy(offline_window_s=WINDOW_S, refresh_cooldown_s=COOLDOWN_S),
            clock=clock,
        ),
    )
    verifier = CyberdyneAuth(
        trust=Trust(
            issuer=issuer.issuer,
            audience=issuer.audience,
            client_id=issuer.client_id,
            organisation=ORG_ID,
        ),
        keys=keys,
        project=PROJECT,
        group_roles=dict(group_roles) or MAPPED,
        now=lambda: datetime.fromtimestamp(EPOCH, tz=UTC),
    )
    identity["verifier"] = verifier
    return verifier


def endpoints_of(issuer: FakeIssuer) -> Endpoints:
    return Endpoints(
        token=f"{issuer.issuer}{TOKEN_PATH}",
        device_authorization=f"{issuer.issuer}{DEVICE_CODE_PATH}",
        authorization=f"{issuer.issuer}{AUTHORIZE_PATH}",
    )


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


# Every scenario this capability declares, bound one literal at a time.
#
# The bindings are read statically from this source rather than by importing it
# (`canon_bdd.implemented`), so a helper that computed the scenario name would
# read as *not executing* and the gate would report twenty-three absent
# scenarios. Verbose on purpose, and load-bearing.


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Body-supplied identity is ignored",
)
def test_body_supplied_identity_is_ignored() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Path-supplied tenant cannot widen access",
)
def test_path_supplied_tenant_cannot_widen_access() -> None: ...


@scenario("../features/add-web-backend/auth-integration.feature", "Expired credential is refused")
def test_expired_credential_is_refused() -> None: ...


@scenario("../features/add-web-backend/auth-integration.feature", "Wrong audience is refused")
def test_wrong_audience_is_refused() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Unverifiable signature is refused",
)
def test_unverifiable_signature_is_refused() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Key rotation is tolerated without a restart",
)
def test_key_rotation_is_tolerated_without_a_restart() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Authorization tested without an identity service",
)
def test_authorization_tested_without_an_identity_service() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "No claim vocabulary in recorded actions",
)
def test_no_claim_vocabulary_in_recorded_actions() -> None: ...


@scenario("../features/add-web-backend/auth-integration.feature", "Unmapped group grants nothing")
def test_unmapped_group_grants_nothing() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "A role-less actor is resolved, not rejected",
)
def test_a_role_less_actor_is_resolved_not_rejected() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Adding a mapping requires no code change",
)
def test_adding_a_mapping_requires_no_code_change() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Identical decision for identical actors",
)
def test_identical_decision_for_identical_actors() -> None: ...


@scenario("../features/add-web-backend/auth-integration.feature", "The adapter cannot grant")
def test_the_adapter_cannot_grant() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Authorization code without proof is refused",
)
def test_authorization_code_without_proof_is_refused() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "The surface never sees a password",
)
def test_the_surface_never_sees_a_password() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Credential is not written into the repository",
)
def test_credential_is_not_written_into_the_repository() -> None: ...


@scenario("../features/add-web-backend/auth-integration.feature", "Sign-out removes the credential")
def test_sign_out_removes_the_credential() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Validation still requires no sign-in",
)
def test_validation_still_requires_no_sign_in() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Scheduled refresh names no person",
)
def test_scheduled_refresh_names_no_person() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Service credential cannot impersonate",
)
def test_service_credential_cannot_impersonate() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Reads survive a short identity outage",
)
def test_reads_survive_a_short_identity_outage() -> None: ...


@scenario("../features/add-web-backend/auth-integration.feature", "Degradation never elevates")
def test_degradation_never_elevates() -> None: ...


@scenario(
    "../features/add-web-backend/auth-integration.feature",
    "Beyond the window, refusal names the cause",
)
def test_beyond_the_window_refusal_names_the_cause() -> None: ...


# --------------------------------------------------------------------------
# Identity and tenant come only from verified claims
# --------------------------------------------------------------------------


@given("a request whose credential verifies to one person")
def _a_credential_that_verifies(identity: dict[str, Any]) -> None:
    verifier = a_verifier(identity)
    identity["credential"] = identity["issuer"].mint(
        SUBJECT, roles=[ARTIST_KEY], entitlements=[PRO_MONTHLY]
    )
    identity["verifier"] = verifier


@when("the request body names a different person as the actor")
def _the_body_names_somebody_else(identity: dict[str, Any]) -> None:
    identity["result"] = authenticate(
        identity["credential"],
        identity_provider=identity["verifier"],
        claimed={"actor": "auth|somebody-else", "roles": ["ART_DIRECTOR"]},
    )


@then("the request SHALL be evaluated as the credential's person")
def _evaluated_as_the_credentials_person(identity: dict[str, Any]) -> None:
    authenticated = ran(identity["result"])

    assert authenticated.subject == SUBJECT
    assert authenticated.actor.roles == (Role.ARTIST,)


@then("the supplied value SHALL have no effect")
def _the_supplied_value_had_no_effect(identity: dict[str, Any]) -> None:
    authenticated = ran(identity["result"])

    assert set(authenticated.ignored) == {"actor", "roles"}
    assert "somebody-else" not in authenticated.subject


@given("a credential whose claims grant access to one tenant")
def _a_credential_for_one_tenant(identity: dict[str, Any]) -> None:
    provider = InMemoryIdentityProvider()
    provider.add(TOKEN, a_person(Role.ARTIST, tenant=CYBERDYNE))
    identity["actor"] = provider.resolve(TOKEN).actor


@when("a request addresses a project belonging to another tenant")
def _a_project_in_another_tenant(identity: dict[str, Any]) -> None:
    elsewhere = Subject(project=ProjectRef(PROJECT, tenant=IRONWOOD))
    identity["decision"] = decide(identity["actor"], Operation.READ_PROJECT, elsewhere)


@then("the request SHALL be refused")
def _the_request_was_refused(identity: dict[str, Any]) -> None:
    """Refused by **domain policy**, over an actor the credential already produced.

    Its neighbour two rules down — *"it SHALL be refused"*, for a request with no
    credential — is refused by the networked authentication before a policy is
    ever consulted. Two refusals, two mechanisms, and the phrasings stay apart so
    that neither can quietly become the other.
    """
    decision = identity["decision"]

    assert decision.refused
    assert WRONG_TENANT in decision.reason


# --------------------------------------------------------------------------
# Credentials are verified against the issuer's published keys
# --------------------------------------------------------------------------


@when("a request presents a credential past its validity period")
def _an_expired_credential(identity: dict[str, Any]) -> None:
    verifier = a_verifier(identity)
    expired = identity["issuer"].mint(SUBJECT, issued_at=EPOCH - 100_000, lifetime_s=60)
    identity["result"] = authenticate(expired, identity_provider=verifier)


@when("a request presents a credential issued for a different audience")
def _a_credential_for_another_audience(identity: dict[str, Any]) -> None:
    verifier = a_verifier(identity)
    elsewhere = identity["issuer"].mint(SUBJECT, audience="https://another.service")
    identity["result"] = authenticate(elsewhere, identity_provider=verifier)


@when(
    "a request presents a credential whose signature does not verify against any "
    "published key of the configured issuer"
)
def _a_credential_signed_by_nobody(identity: dict[str, Any]) -> None:
    verifier = a_verifier(identity)
    issuer = identity["issuer"]
    forged = issuer.mint(SUBJECT, key=impostor_key(issuer.current))
    identity["result"] = authenticate(forged, identity_provider=verifier)


@then("it SHALL be refused as unauthenticated")
def _refused_as_unauthenticated(identity: dict[str, Any]) -> None:
    refusal = refused(identity["result"])

    assert refusal.kind.value == "unauthenticated"
    assert refusal.identifier == "identity.credential_rejected"


@given("the issuer publishes a new signing key")
def _the_issuer_publishes_a_new_key(identity: dict[str, Any]) -> None:
    verifier = a_verifier(identity)
    issuer, clock = identity["issuer"], identity["clock"]
    ran(authenticate(issuer.mint(SUBJECT), identity_provider=verifier))
    identity["retrievals"] = identity["keys"].retrievals
    identity["rotated_to"] = issuer.rotate()
    clock.advance(COOLDOWN_S)


@when("a credential signed by that key is presented")
def _a_credential_signed_by_the_new_key(identity: dict[str, Any]) -> None:
    signed = identity["issuer"].mint(SUBJECT, kid=identity["rotated_to"])
    identity["result"] = authenticate(signed, identity_provider=identity["verifier"])


@then("it SHALL be accepted without the service being restarted or reconfigured")
def _accepted_without_a_restart(identity: dict[str, Any]) -> None:
    """The same adapter object, the same configuration — only the key set moved."""
    assert ran(identity["result"]).subject == SUBJECT
    assert identity["keys"].retrievals == identity["retrievals"] + 1
    assert identity["verifier"].group_roles == MAPPED


# --------------------------------------------------------------------------
# The credential's representation never reaches the core
# --------------------------------------------------------------------------


@given("no identity service is configured or reachable")
def _no_identity_service(identity: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Proving "needs nothing external" requires a connection to fail the test."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("an authorization decision opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    identity["actor"] = a_person(Role.ART_DIRECTOR)


@when("an authorization decision is evaluated for a constructed actor")
def _a_decision_for_a_constructed_actor(identity: dict[str, Any]) -> None:
    identity["decisions"] = {
        operation: decide(identity["actor"], operation, Subject(project=PROJECT))
        for operation in Operation
    }


@then("the decision SHALL be produced from that actor's identifier and roles alone")
def _from_the_actor_alone(identity: dict[str, Any]) -> None:
    decisions = identity["decisions"]

    assert set(decisions) == set(Operation)
    assert decisions[Operation.READ_PROJECT].allowed
    assert decisions[Operation.PROMOTE_TO_RULE].allowed


@given(
    "two actors with the same roles, one resolved from a verified credential and one "
    "constructed directly"
)
def _two_actors_one_shape(identity: dict[str, Any]) -> None:
    provider = InMemoryIdentityProvider()
    provider.add(TOKEN, a_person(Role.ARTIST))
    identity["resolved"] = provider.resolve(TOKEN).actor
    identity["constructed"] = a_person(Role.ARTIST)


@when("the same operation is evaluated for each")
def _the_same_operation_for_each(identity: dict[str, Any]) -> None:
    subject = Subject(project=PROJECT)
    identity["pairs"] = {
        operation: (
            decide(identity["resolved"], operation, subject),
            decide(identity["constructed"], operation, subject),
        )
        for operation in Operation
    }


@then("both SHALL receive the same decision")
def _the_decisions_agree(identity: dict[str, Any]) -> None:
    for operation, (resolved, constructed) in identity["pairs"].items():
        assert resolved == constructed, operation


# --------------------------------------------------------------------------
# A record names a subject, and no group
# --------------------------------------------------------------------------


@when("an action is recorded")
def _an_action_is_recorded(identity: dict[str, Any]) -> None:
    """Two records the product actually writes: an attribution and a request event."""
    identity["attribution"] = Attribution(actor=RAFA)
    identity["request"] = raise_request(
        RequestId("req-0001"),
        author=RAFA,
        discipline=Discipline.MODELING,
        description="a supply crate for the loading dock",
        at=NOON,
    )


@then("the record SHALL identify the actor by its stable identifier")
def _identified_by_subject(identity: dict[str, Any]) -> None:
    (raised,) = identity["request"].history

    assert identity["attribution"].responsible == RAFA
    assert raised.kind is EventKind.RAISED
    assert raised.actor == RAFA
    assert str(raised.actor) == SUBJECT


@then("SHALL NOT contain claim or group names from the identity service")
def _no_claim_vocabulary(identity: dict[str, Any]) -> None:
    written = f"{identity['attribution']!r} {identity['request']!r}"

    assert GROUP not in written
    assert CLAIM not in written
    assert "Credential" not in written
    assert str(TOKEN.value) not in written


# --------------------------------------------------------------------------
# Group-to-role mapping is configuration, and unmapped grants nothing
# --------------------------------------------------------------------------


@given("a credential carrying a group with no configured mapping")
def _a_credential_with_an_unmapped_group(identity: dict[str, Any]) -> None:
    a_verifier(identity)
    identity["credential"] = identity["issuer"].mint(SUBJECT, roles=[ARTIST_KEY, INTERN_KEY])


@when("the actor is resolved")
def _the_actor_is_resolved(identity: dict[str, Any]) -> None:
    identity["result"] = authenticate(
        identity["credential"], identity_provider=identity["verifier"]
    )


@then("the actor SHALL hold no role from that group")
def _no_role_from_the_unmapped_group(identity: dict[str, Any]) -> None:
    """The mapped group still grants; the unmapped one adds nothing."""
    assert ran(identity["result"]).actor.roles == (Role.ARTIST,)


@given("a credential whose groups all lack mappings")
def _a_credential_with_only_unmapped_groups(identity: dict[str, Any]) -> None:
    a_verifier(identity)
    identity["credential"] = identity["issuer"].mint(
        SUBJECT, roles=[INTERN_KEY, "guest"], entitlements=[PRO_MONTHLY]
    )


@when("a request is made")
def _a_request_is_made(identity: dict[str, Any]) -> None:
    identity["result"] = authenticate(
        identity["credential"], identity_provider=identity["verifier"]
    )


@then("the actor SHALL be resolved with no roles")
def _resolved_with_no_roles(identity: dict[str, Any]) -> None:
    """Resolved, not refused: a mapping mistake must not look like an outage."""
    authenticated = ran(identity["result"])

    assert authenticated.subject == SUBJECT
    assert authenticated.actor.roles == ()


@then("role-requiring operations SHALL be refused naming the required role")
def _role_requiring_operations_are_refused(identity: dict[str, Any]) -> None:
    actor = ran(identity["result"]).actor
    decision = decide(actor, Operation.PROMOTE_TO_RULE, Subject(project=PROJECT))

    assert decision.refused
    assert str(Role.ART_DIRECTOR) in decision.reason


@given("a new group in the identity service")
def _a_new_group(identity: dict[str, Any]) -> None:
    a_verifier(identity)
    identity["credential"] = identity["issuer"].mint(SUBJECT, roles=[INTERN_KEY])
    identity["before"] = ran(
        authenticate(identity["credential"], identity_provider=identity["verifier"])
    ).actor


@when("it is mapped to a domain role in configuration")
def _the_group_is_mapped(identity: dict[str, Any]) -> None:
    """Configuration alone: the same issuer, the same keys, a different mapping."""
    identity["result"] = authenticate(
        identity["credential"],
        identity_provider=a_verifier(identity, **{INTERN_KEY: "DESIGNER"}),
    )


@then("credentials carrying that group SHALL resolve with that role")
def _the_group_now_grants_its_role(identity: dict[str, Any]) -> None:
    assert identity["before"].roles == ()
    assert ran(identity["result"]).actor.roles == (Role.DESIGNER,)


# --------------------------------------------------------------------------
# Authorization is decided by domain policy, never by the adapter
# --------------------------------------------------------------------------


@when("the verification adapter resolves an actor")
def _the_adapter_resolves(identity: dict[str, Any]) -> None:
    verifier = a_verifier(identity)
    credential = identity["issuer"].mint(SUBJECT, roles=[ARTIST_KEY], entitlements=[PRO_MONTHLY])
    identity["resolution"] = verifier.resolve(credential)


@then("the resolution SHALL produce an identifier and roles only")
def _an_identifier_and_roles_only(identity: dict[str, Any]) -> None:
    resolution = identity["resolution"]

    assert resolution.actor.subject == SUBJECT
    assert resolution.actor.roles == (Role.ARTIST,)
    assert not hasattr(resolution, "decision")
    assert not hasattr(resolution, "permissions")


@then("SHALL NOT produce an allow or deny outcome for any operation")
def _no_allow_or_deny(identity: dict[str, Any]) -> None:
    """The adapter has no method that could be asked about an operation."""
    surface = {name for name in dir(identity["verifier"]) if not name.startswith("_")}

    assert "resolve" in surface
    assert not surface & {"allow", "deny", "may", "decide", "authorize", "permits"}


# --------------------------------------------------------------------------
# Interactive sign-in uses authorization code with proof of possession
# --------------------------------------------------------------------------


@when("an authorization code is exchanged without the matching proof")
def _a_code_without_its_proof(identity: dict[str, Any]) -> None:
    issuer = identity.setdefault("issuer", FakeIssuer())
    browser = BrowserSignIn(
        endpoints=endpoints_of(issuer),
        client_id=issuer.client_id,
        redirect_uri="https://canon.cyberdynecorp.ai/signed-in",
        transport=issuer,
    )
    request = browser.begin()
    code, _state = issuer.authorize(request.url)
    try:
        issuer.post(
            f"{issuer.issuer}{TOKEN_PATH}", {"grant_type": "authorization_code", "code": code}
        )
    except OAuthRefusal as refusal:
        identity["exchange"] = refusal
    identity["browser"] = browser


@then("the exchange SHALL fail and no credential SHALL be issued")
def _the_exchange_failed(identity: dict[str, Any]) -> None:
    assert isinstance(identity.get("exchange"), OAuthRefusal)
    assert "credential" not in identity


@when("a person signs in")
def _a_person_signs_in(identity: dict[str, Any]) -> None:
    issuer = identity.setdefault("issuer", FakeIssuer())
    browser = BrowserSignIn(
        endpoints=endpoints_of(issuer),
        client_id=issuer.client_id,
        redirect_uri="https://canon.cyberdynecorp.ai/signed-in",
        transport=issuer,
    )
    request = browser.begin()
    code, state = issuer.authorize(request.url)
    identity["credential"] = browser.redeem(request, code, state)
    identity["authorization_url"] = request.url
    identity["browser"] = browser


@then("the credential presented to the surface SHALL be an issuer-signed token")
def _an_issuer_signed_token(identity: dict[str, Any]) -> None:
    """Presented to the surface and verified there, by the surface's own trust."""
    resolved = a_verifier(identity).resolve(identity["credential"])

    assert resolved.actor.subject == SUBJECT


@then("no password SHALL be transmitted to or stored by the surface")
def _no_password_anywhere(identity: dict[str, Any]) -> None:
    import inspect

    browser = identity["browser"]
    named = {
        name
        for member in (type(browser).__init__, browser.begin, browser.redeem)
        for name in inspect.signature(member).parameters
    }

    assert not {name for name in named if "password" in name or "secret" in name}
    assert "password" not in identity["authorization_url"]


# --------------------------------------------------------------------------
# The command line signs in by device authorization, into the OS keychain
# --------------------------------------------------------------------------


class StandInKeyring:
    """`keyring`, as far as the adapter is concerned — and nowhere near a path."""

    def __init__(self) -> None:
        self.secrets: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self.secrets.get((service, account))

    def set_password(self, service: str, account: str, password: str) -> None:
        self.secrets[(service, account)] = password

    def delete_password(self, service: str, account: str) -> None:
        self.secrets.pop((service, account), None)


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=root, check=True, capture_output=True, text=True
    ).stdout


@given("a person completes a terminal sign-in inside a repository working copy")
def _a_terminal_sign_in_inside_a_working_copy(identity: dict[str, Any], tmp_path: Path) -> None:
    root = tmp_path / "game"
    (root / "characters" / "mech_scout").mkdir(parents=True)
    (root / "characters" / "mech_scout" / "asset.yaml").write_text(
        "id: mech_scout\nname: Scout Mech\n", encoding="utf-8"
    )
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "rafa@cyberdyne.com")
    _git(root, "config", "user.name", "Rafa")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the scout mech")

    issuer = identity.setdefault("issuer", FakeIssuer())
    flow = DeviceAuthorization(
        endpoints=endpoints_of(issuer),
        client_id=issuer.client_id,
        transport=issuer,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
    )
    store = KeychainCredentialStore(service="cybercanon-scenario", backend=StandInKeyring())

    def approve(grant) -> None:
        issuer.approve(grant.user_code)

    identity["repository"] = root
    identity["store"] = store
    ran(sign_in(interactive_sign_in=flow, credential_store=store, announce=approve))
    identity["credential"] = store.load()


@when("the working tree is inspected")
def _the_working_tree_is_inspected(identity: dict[str, Any]) -> None:
    root = identity["repository"]
    identity["status"] = _git(root, "status", "--porcelain")
    identity["files"] = tuple(
        path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


@then("it SHALL be unchanged")
def _the_working_tree_is_unchanged(identity: dict[str, Any]) -> None:
    assert identity["status"] == ""


@then("no credential SHALL exist in any file under the repository")
def _no_credential_under_the_repository(identity: dict[str, Any]) -> None:
    credential = identity["credential"]

    assert credential is not None
    for path in identity["files"]:
        assert credential.value not in path.read_text(encoding="utf-8", errors="ignore"), path


@given("a stored credential")
def _a_stored_credential(identity: dict[str, Any]) -> None:
    store = KeychainCredentialStore(service="cybercanon-scenario", backend=StandInKeyring())
    store.store(Credential("the-credential-this-machine-holds"))
    identity["store"] = store


@when("the person signs out")
def _the_person_signs_out(identity: dict[str, Any]) -> None:
    identity["result"] = sign_out(credential_store=identity["store"])


@then("the credential SHALL be removed from the credential store")
def _the_credential_is_gone(identity: dict[str, Any]) -> None:
    assert ran(identity["result"]).removed
    assert identity["store"].load() is None
    assert not ran(sign_in_status(credential_store=identity["store"])).signed_in


@given("no credential has ever been stored on a machine")
def _a_machine_that_never_signed_in(identity: dict[str, Any]) -> None:
    store = KeychainCredentialStore(service="cybercanon-scenario", backend=StandInKeyring())

    assert store.load() is None
    identity["store"] = store


@when("an export is validated locally")
def _an_export_is_validated(identity: dict[str, Any]) -> None:
    """The local surface, with no credential, no provider and no network.

    Validation reaches no identity at all — not the store, not a provider, not
    the networked authentication. That is the scoping this scenario protects:
    the day `canon validate` needs a token is the day the tool becomes the
    enemy.
    """
    specs = InMemorySpecStore()
    specs.add(
        SPEC_PATH,
        Asset(id=AssetId(ASSET_ID), name="Scout Mech", constraints=Constraints(tri_budget=12000)),
    )
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, facts_for(MeshFormat.GLB, objects=(OBJECT,), triangles=1000))
    identity["result"] = validate_export(EXPORT, spec_store=specs, mesh_inspector=inspector)


@then("validation SHALL complete normally")
def _validation_completed(identity: dict[str, Any]) -> None:
    outcome = ran(identity["result"])

    assert outcome.asset_id == ASSET_ID
    assert outcome.passed
    assert identity["store"].load() is None


# --------------------------------------------------------------------------
# Background work authenticates as the system and is recorded as automation
# --------------------------------------------------------------------------


@when("a scheduled refresh performs a recorded action")
def _a_scheduled_refresh_records(identity: dict[str, Any]) -> None:
    """The real timer path: authenticate as the system, then refresh, then record.

    `scheduled_refresh` is the thing the deployment actually runs on an interval,
    so the recorded action is its outcome rather than a stand-in for one — the
    question the scenario asks is *who does the record name*, and a record built
    beside the operation could name anybody.
    """
    verifier = a_verifier(identity)
    service = identity["issuer"].mint("cybercanon-worker", service=True, entitlements=[PRO_MONTHLY])
    authenticated = ran(authenticate_background(service, identity_provider=verifier))

    host = InMemoryRepositoryHost()
    host.add_project(PROJECT, {SPEC_PATH: b"id: mech_scout\n"})
    host.clone(PROJECT)
    outcomes = scheduled_refresh(
        [PROJECT],
        repository_host=host,
        schedule=FetchSchedule(interval=timedelta(0)),
        clock=fixed_clock(NOON),
    )

    assert outcomes and ran(outcomes[0]).refreshed
    identity["actor"] = authenticated.actor
    identity["attribution"] = attribute(authenticated.actor)


@then("the record SHALL identify it as automation")
def _the_record_says_automation(identity: dict[str, Any]) -> None:
    assert identity["actor"].is_automation
    assert "automation" in identity["actor"].display


@then("SHALL NOT name any person as responsible")
def _no_person_is_named(identity: dict[str, Any]) -> None:
    written = f"{identity['attribution']!r} {identity['actor'].display}"

    assert SUBJECT not in written
    assert "Rafa" not in written


@given("a service credential")
def _a_service_credential(identity: dict[str, Any]) -> None:
    a_verifier(identity)
    identity["credential"] = identity["issuer"].mint(
        "cybercanon-worker", service=True, entitlements=[PRO_MONTHLY]
    )


@when("a request using it supplies a person's identifier")
def _a_service_request_naming_a_person(identity: dict[str, Any]) -> None:
    identity["result"] = authenticate_background(
        identity["credential"],
        identity_provider=identity["verifier"],
        claimed={"actor": SUBJECT, "on_behalf_of": SUBJECT},
    )


@then("the request SHALL be evaluated as automation")
def _evaluated_as_automation(identity: dict[str, Any]) -> None:
    assert ran(identity["result"]).is_automation


@then("the supplied identifier SHALL have no effect")
def _the_supplied_identifier_had_no_effect(identity: dict[str, Any]) -> None:
    authenticated = ran(identity["result"])

    assert SUBJECT not in authenticated.subject
    assert set(authenticated.ignored) == {"actor", "on_behalf_of"}
    assert automation_actor().kind is authenticated.actor.kind


# --------------------------------------------------------------------------
# Identity outage degrades within a bounded window
# --------------------------------------------------------------------------


@given("published keys retrieved before the identity service became unreachable")
def _keys_retrieved_before_the_outage(identity: dict[str, Any]) -> None:
    """The person holds a role here, because that is what admits them.

    Entitlement is the organisation their `orgs` claim carries *plus* a role on
    this client, so a credential carrying neither is served nothing however
    reachable the identity service is — and this scenario is about the outage,
    not about somebody who was never entitled.
    """
    verifier = a_verifier(identity)
    ran(
        authenticate(
            identity["issuer"].mint(SUBJECT, roles=[ARTIST_KEY]), identity_provider=verifier
        )
    )
    identity["credential"] = identity["issuer"].mint(
        SUBJECT, roles=[ARTIST_KEY], entitlements=[PRO_MONTHLY]
    )
    identity["issuer"].go_dark()
    identity["clock"].advance(WINDOW_S / 2)


@when("a caller presents a valid, unexpired credential signed by one of them")
def _a_valid_credential_during_the_outage(identity: dict[str, Any]) -> None:
    identity["result"] = authenticate(
        identity["credential"], identity_provider=identity["verifier"]
    )


@then("the request SHALL be served")
def _the_request_was_served(identity: dict[str, Any]) -> None:
    authenticated = ran(identity["result"])

    assert authenticated.subject == SUBJECT
    assert decide(authenticated.actor, Operation.READ_PROJECT, Subject(project=PROJECT)).allowed


@given("the identity service is unreachable")
def _the_identity_service_is_unreachable(identity: dict[str, Any]) -> None:
    a_verifier(identity)
    identity["issuer"].go_dark()


@when("a request presents no credential")
def _no_credential_is_presented(identity: dict[str, Any]) -> None:
    identity["result"] = authenticate(None, identity_provider=identity["verifier"])


@then("it SHALL be refused")
def _refused_for_want_of_a_credential(identity: dict[str, Any]) -> None:
    """The networked surface, refusing before any policy is consulted."""
    refusal = refused(identity["result"])

    assert refusal.kind.value == "unauthenticated"


@then("SHALL NOT be served as an anonymous or default actor")
def _never_anonymous(identity: dict[str, Any]) -> None:
    """The refusal carries no actor at all — not a local one, not a default one."""
    refusal = refused(identity["result"])

    assert refusal.identifier == "auth.credential_missing"
    assert "anonymous" in refusal.message
    assert "local" not in refusal.message


@given("the identity service has been unreachable longer than the configured period")
def _unreachable_beyond_the_window(identity: dict[str, Any]) -> None:
    verifier = a_verifier(identity)
    ran(authenticate(identity["issuer"].mint(SUBJECT), identity_provider=verifier))
    identity["credential"] = identity["issuer"].mint(SUBJECT)
    identity["issuer"].go_dark()
    identity["clock"].advance(WINDOW_S + 1)


@when("any authenticated request is made")
def _any_authenticated_request(identity: dict[str, Any]) -> None:
    identity["result"] = authenticate(
        identity["credential"], identity_provider=identity["verifier"]
    )


@then("it SHALL be refused with a message naming the identity service as unavailable")
def _refused_naming_the_identity_service(identity: dict[str, Any]) -> None:
    refusal = refused(identity["result"])

    assert refusal.kind.value == "unavailable"
    assert "identity service" in refusal.message
    assert "unavailable" in refusal.message
