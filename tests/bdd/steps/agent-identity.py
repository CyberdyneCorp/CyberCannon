"""Step definitions for `agent-identity` — the scenarios the domain answers alone.

Group 1 of `add-mcp-read-server` builds the identity domain: `Actor`, `Role`,
`AgentId`, the read-entitlement policy, `Attribution` with a non-optional actor
(D5), the rule that automated callers may not author durable content, and the
actor mapping with its resolution in both directions and its structural checks
(D12, D14).

The scenarios bound here are exactly the ones that code answers with no
credential, no provider, no store and no file — which is the property
`agent-identity` demands of authorization in the first place: a decision must be
producible with no identity service running.

Group 2 adds the application half: the resolution chain of D4 — configured
credential, then a cached actor within its TTL, then the local unauthenticated
actor — the claims-before-file precedence of D13, and the mapping read through
`SpecStore`. Those scenarios are bound here too, against the in-memory provider
and spec store, so the whole capability still runs with no credential, no
network and no file.

Group 3 adds the presentation half: every owner, author and caller is resolved
through the mapping before anything renders it, so a mapped person shows as their
display name, an unmapped one as the raw email marked unmapped, and one person
appearing as an owner, as a commit author and as the caller renders identically
in all three places.

The rest of this capability's scenarios stay in `tests/bdd/pending.txt` until the
groups that earn them: the automation actor for autonomous runs, and the recorded
observation an agent's report becomes (`add-mcp-writes`).
"""

from __future__ import annotations

import socket
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.ports.identity_provider import Credential, IdentityUnavailable
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.index_assets import rebuild_index
from cybercanon.application.use_cases.lookup_assets import ART, where_is
from cybercanon.application.use_cases.resolve_actor import (
    UNVERIFIABLE,
    ActorResolver,
    GitIdentitySource,
    IdentityCache,
    list_unmapped_authors,
    may_act_in_role,
    may_read,
    resolve_git_identity,
    strip_identity_claims,
)
from cybercanon.domain.actor_checks import (
    RULE_DUPLICATE_EMAIL,
    RULE_DUPLICATE_SUBJECT,
    RULE_PROVIDER_DISAGREEMENT,
    RULE_UNKNOWN_ROLE,
    check_mapping,
)
from cybercanon.domain.actors import (
    ActorBinding,
    ActorMapping,
    actor_for,
    git_author_for,
    resolve_git_author,
    resolve_subject,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.authorization import may_author_durable_content, may_read_project
from cybercanon.domain.identity import (
    UNMAPPED_MARK,
    Actor,
    ActorId,
    AgentId,
    Attribution,
    Role,
)

SUBJECT = "auth|rafa"
DISPLAY_NAME = "Rafa"
WORK_EMAIL = "rafa@cyberdyne.com"
PERSONAL_EMAIL = "rafa@personal.dev"
COMMITTED_AS = "RAFA@Cyberdyne.com"
NEAR_MISS = "r.santos@cyberdyne.com"
STRANGER = "contractor@elsewhere.io"

PROJECT = "cyberdyne-game"
OTHER_SUBJECT = "auth|ana"
BLENDER = AgentId("blender-agent")

RAFA = ActorBinding(
    subject=SUBJECT,
    display_name=DISPLAY_NAME,
    emails=(WORK_EMAIL, PERSONAL_EMAIL),
    chat_handle="@rafa",
    default_role="ARTIST",
)

TOKEN = Credential("opaque-launch-token")
CLAIMED_EMAIL = "rafa@cyberdyne.ai"
SECOND_STRANGER = "designer@studio.example"
SPEC_PATH = "characters/mech_scout/asset.yaml"
MECH_SCOUT = Asset(id=AssetId("mech_scout"), name="Scout Mech")
TTL_SECONDS = 60.0


class Ticks:
    """A clock a scenario advances by hand, so a TTL costs no wall time."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def a_provider(actor: Actor, git_emails: tuple[str, ...] = ()) -> InMemoryIdentityProvider:
    provider = InMemoryIdentityProvider()
    provider.add(TOKEN, actor, git_emails=git_emails)
    return provider


def a_resolver(provider: InMemoryIdentityProvider, clock: Ticks) -> ActorResolver:
    return ActorResolver(
        project=PROJECT,
        provider=provider,
        credential=TOKEN,
        cache=IdentityCache(clock=clock, ttl=TTL_SECONDS),
    )


def a_store(mapping: ActorMapping | None = None) -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, MECH_SCOUT)
    if mapping is not None:
        store.set_actor_mapping(mapping)
    return store


def read_the_spec(session: dict[str, Any]) -> None:
    """Authorize, then read — D3's order, with the lens nowhere near it."""
    resolution = session["resolution"]
    store: InMemorySpecStore = session["store"]
    decision = may_read(resolution, PROJECT)
    session["decision"] = decision
    session["read"] = store.load(SPEC_PATH) if decision.allowed else None


@pytest.fixture
def session() -> dict[str, Any]:
    """What this scenario set up, and what the domain answered."""
    return {}


def a_person(*roles: Role, projects: tuple[str, ...] = ()) -> Actor:
    return Actor(id=ActorId(SUBJECT), display_name=DISPLAY_NAME, roles=roles, projects=projects)


def take_the_network_away(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proving 'needs nothing external' requires a connection to fail the test."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("an identity decision opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Agent denied what its person is denied",
)
def test_agent_denied_what_its_person_is_denied() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Authorization verified without an identity service",
)
def test_authorization_verified_without_an_identity_service() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Attribution names both",
)
def test_attribution_names_both() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Unattributable action is refused",
)
def test_unattributable_action_is_refused() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Constraint edit refused for every role",
)
def test_constraint_edit_refused_for_every_role() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "One entry binds both identities",
)
def test_one_entry_binds_both_identities() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Commit author is recognised as the person",
)
def test_commit_author_is_recognised_as_the_person() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Git identity for acting on a person's behalf",
)
def test_git_identity_for_acting_on_a_persons_behalf() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Round trip is stable",
)
def test_round_trip_is_stable() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Unmapped author is preserved and flagged",
)
def test_unmapped_author_is_preserved_and_flagged() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "A near miss is never guessed",
)
def test_a_near_miss_is_never_guessed() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Duplicate email is a violation",
)
def test_duplicate_email_is_a_violation() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Duplicate subject is a violation",
)
def test_duplicate_subject_is_a_violation() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Unknown role is a violation",
)
def test_unknown_role_is_a_violation() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Mapping validation needs nothing external",
)
def test_mapping_validation_needs_nothing_external() -> None: ...


# --------------------------------------------------------------------------
# Authorization, attribution and the durable-content rule
# --------------------------------------------------------------------------


@given("an actor who may not read a given project")
def _an_unentitled_actor(session: dict[str, Any]) -> None:
    session["actor"] = a_person(Role.ARTIST, projects=("another-game",))
    session["project"] = PROJECT


@when("an agent acting as that actor requests an asset from that project")
def _an_agent_requests_an_asset(session: dict[str, Any]) -> None:
    """The agent is recorded as the instrument and changes nothing about the answer."""
    actor: Actor = session["actor"]
    session["attribution"] = Attribution(actor=actor.id, via=BLENDER)
    session["decision"] = may_read_project(actor, session["project"])
    session["decision_for_the_person"] = may_read_project(actor, session["project"])


@then("the request SHALL be refused")
def _the_request_is_refused(session: dict[str, Any]) -> None:
    assert session["decision"].refused
    assert session["decision"] == session["decision_for_the_person"], (
        "an agent is permitted exactly what the actor it acts as is permitted"
    )
    assert session["project"] in session["decision"].reason


@given("no identity service is reachable")
def _no_identity_service(session: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    take_the_network_away(monkeypatch)
    session["offline"] = True


@when("an authorization decision is evaluated for a resolved actor")
def _a_decision_is_evaluated(session: dict[str, Any]) -> None:
    entitled = a_person(Role.ARTIST, projects=(PROJECT,))
    unentitled = a_person(Role.ART_DIRECTOR)
    session["decisions"] = {
        "entitled": may_read_project(entitled, PROJECT),
        "unentitled": may_read_project(unentitled, PROJECT),
    }


@then("the decision SHALL be produced from the actor's roles alone")
def _the_decision_came_from_the_actor(session: dict[str, Any]) -> None:
    assert session["offline"], "the guard was never installed, so this proves nothing"
    assert session["decisions"]["entitled"].allowed
    assert session["decisions"]["unentitled"].refused


@when("an action is recorded for an agent acting as a given actor")
def _an_action_is_recorded(session: dict[str, Any]) -> None:
    session["attribution"] = Attribution(actor=ActorId(SUBJECT), via=BLENDER)


@then("the record SHALL identify that actor as responsible")
def _the_record_names_the_person(session: dict[str, Any]) -> None:
    attribution: Attribution = session["attribution"]

    assert attribution.responsible == ActorId(SUBJECT)
    assert SUBJECT in str(attribution)


@then("SHALL identify the agent as the instrument")
def _the_record_names_the_agent(session: dict[str, Any]) -> None:
    attribution: Attribution = session["attribution"]

    assert attribution.instrument == BLENDER
    assert attribution.is_automated
    assert str(BLENDER) in str(attribution)


@when("an action would be recorded with no resolvable actor")
def _an_action_with_no_actor(session: dict[str, Any]) -> None:
    """D5 — the refusal is the type's, so it happens at construction."""
    try:
        Attribution(actor=None, via=BLENDER)  # type: ignore[arg-type]
    except (TypeError, ValueError) as refusal:
        session["refusal"] = refusal


@then("it SHALL be refused rather than recorded anonymously")
def _it_was_refused(session: dict[str, Any]) -> None:
    refusal = session.get("refusal")

    assert refusal is not None, "an attribution with no actor was constructed"
    assert "actor" in str(refusal)


@when(
    "an automated caller attempts to modify a constraint while acting as an actor holding any role"
)
def _an_agent_edits_a_constraint(session: dict[str, Any]) -> None:
    session["decisions"] = {
        role: may_author_durable_content(a_person(role), via=BLENDER) for role in Role
    }


@then("the attempt SHALL be refused")
def _every_role_was_refused(session: dict[str, Any]) -> None:
    decisions = session["decisions"]

    assert set(decisions) == set(Role), "every role is tried in turn"
    for role, decision in decisions.items():
        assert decision.refused, f"an agent acting for a {role} was allowed to author"


# --------------------------------------------------------------------------
# The actor mapping
# --------------------------------------------------------------------------


@given(
    "an entry binding the subject `auth|rafa` to the display name `Rafa`, the git emails "
    "`rafa@cyberdyne.com` and `rafa@personal.dev`, and the default role `ARTIST`"
)
def _an_entry_binding_both_identities(session: dict[str, Any]) -> None:
    session["mapping"] = ActorMapping((RAFA,))


@when("either that subject or either email is resolved to an actor")
def _the_subject_and_both_emails_are_resolved(session: dict[str, Any]) -> None:
    mapping: ActorMapping = session["mapping"]
    session["resolved"] = (
        resolve_subject(mapping, SUBJECT),
        resolve_git_author(mapping, WORK_EMAIL),
        resolve_git_author(mapping, PERSONAL_EMAIL),
    )


@then("the same actor SHALL be returned, carrying that display name and that default role")
def _the_same_actor_every_time(session: dict[str, Any]) -> None:
    resolved = session["resolved"]

    assert len(set(resolved)) == 1, "the two identities resolved to two different people"
    actor = resolved[0]
    assert actor.display_name == DISPLAY_NAME
    assert actor.roles == (Role.ARTIST,)
    assert not actor.is_unmapped


@given("a mapping entry listing the email `rafa@cyberdyne.com`")
def _a_mapping_entry_listing_the_work_email(session: dict[str, Any]) -> None:
    session["mapping"] = ActorMapping((RAFA,))


@when("a commit authored by `RAFA@Cyberdyne.com` is resolved")
def _a_commit_in_another_case_is_resolved(session: dict[str, Any]) -> None:
    session["resolved"] = resolve_git_author(session["mapping"], COMMITTED_AS)


@then("it SHALL resolve to that entry's actor")
def _it_resolved_to_that_entry(session: dict[str, Any]) -> None:
    assert session["resolved"] == actor_for(RAFA)
    assert session["resolved"].display_name == DISPLAY_NAME


@given("an actor whose entry lists `rafa@cyberdyne.com` then `rafa@personal.dev`")
def _an_actor_with_two_emails(session: dict[str, Any]) -> None:
    session["mapping"] = ActorMapping((RAFA,))
    session["actor"] = actor_for(RAFA)


@when("the git author identity for that actor is requested")
def _the_git_identity_is_requested(session: dict[str, Any]) -> None:
    session["author"] = git_author_for(session["mapping"], session["actor"])


@then("it SHALL be that actor's display name with `rafa@cyberdyne.com`")
def _it_is_the_display_name_and_the_first_email(session: dict[str, Any]) -> None:
    author = session["author"]

    assert author is not None
    assert author.name == DISPLAY_NAME
    assert author.email == WORK_EMAIL, "the first listed email is the one commits use"


@when(
    "an actor is resolved to a git author identity and that identity's email is resolved "
    "back to an actor"
)
def _a_round_trip(session: dict[str, Any]) -> None:
    mapping = ActorMapping((RAFA,))
    original = actor_for(RAFA)
    author = git_author_for(mapping, original)
    assert author is not None
    session["original"] = original
    session["returned"] = resolve_git_author(mapping, author.email)


@then("the original actor SHALL be returned")
def _the_original_actor_came_back(session: dict[str, Any]) -> None:
    assert session["returned"] == session["original"]


@given("a commit authored by an email present in no mapping entry")
def _a_commit_by_a_stranger(session: dict[str, Any]) -> None:
    session["mapping"] = ActorMapping((RAFA,))
    session["email"] = STRANGER


@when("its author is resolved")
def _the_stranger_is_resolved(session: dict[str, Any]) -> None:
    session["resolved"] = resolve_git_author(session["mapping"], session["email"])


@then("an explicitly unknown actor SHALL be returned carrying that email")
def _an_unknown_actor_carrying_the_email(session: dict[str, Any]) -> None:
    resolved: Actor = session["resolved"]

    assert resolved.is_unmapped
    assert resolved.unmapped_as == session["email"], "the address is kept verbatim"
    assert resolved.roles == ()


@then("any response naming it SHALL mark it as unmapped")
def _every_presentation_marks_it(session: dict[str, Any]) -> None:
    presented = session["resolved"].display

    assert session["email"] in presented
    assert UNMAPPED_MARK in presented


@given("a mapping entry listing `rafa@cyberdyne.com`")
def _a_mapping_entry_for_the_near_miss(session: dict[str, Any]) -> None:
    session["mapping"] = ActorMapping((RAFA,))


@when("a commit authored by `r.santos@cyberdyne.com` is resolved")
def _a_near_miss_is_resolved(session: dict[str, Any]) -> None:
    session["resolved"] = resolve_git_author(session["mapping"], NEAR_MISS)


@then("the result SHALL be an unknown actor")
def _the_result_is_unknown(session: dict[str, Any]) -> None:
    assert session["resolved"].is_unmapped
    assert session["resolved"].unmapped_as == NEAR_MISS


@then("SHALL NOT be the actor holding `rafa@cyberdyne.com`")
def _it_is_not_the_similar_person(session: dict[str, Any]) -> None:
    assert session["resolved"] != actor_for(RAFA)
    assert session["resolved"].display_name != DISPLAY_NAME


# --------------------------------------------------------------------------
# Structural validation of the mapping
# --------------------------------------------------------------------------


@given("two entries that both list `rafa@cyberdyne.com`")
def _two_entries_sharing_an_email(session: dict[str, Any]) -> None:
    borrowed = ActorBinding(
        subject=OTHER_SUBJECT, display_name="Ana", emails=("RAFA@Cyberdyne.com",)
    )
    session["mapping"] = ActorMapping((RAFA, borrowed))
    session["expected_rule"] = RULE_DUPLICATE_EMAIL


@given("two entries that declare the same identity subject")
def _two_entries_sharing_a_subject(session: dict[str, Any]) -> None:
    twin = ActorBinding(subject=SUBJECT, display_name="Rafael", emails=("other@x.dev",))
    session["mapping"] = ActorMapping((RAFA, twin))
    session["expected_rule"] = RULE_DUPLICATE_SUBJECT


@given("an entry whose default role is outside the defined role set")
def _an_entry_with_an_unknown_role(session: dict[str, Any]) -> None:
    entry = ActorBinding(
        subject="auth|zoe", display_name="Zoe", emails=("zoe@x.dev",), default_role="BOSS"
    )
    session["mapping"] = ActorMapping((entry,))
    session["entry"] = entry
    session["expected_rule"] = RULE_UNKNOWN_ROLE


@given("no identity service is reachable and the machine has no network")
def _no_identity_service_and_no_network(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    take_the_network_away(monkeypatch)
    borrowed = ActorBinding(subject=OTHER_SUBJECT, display_name="Ana", emails=(WORK_EMAIL,))
    session["offline"] = True
    session["mapping"] = ActorMapping((RAFA, borrowed))
    session["expected_rule"] = RULE_DUPLICATE_EMAIL


@when("the mapping is validated")
def _the_mapping_is_validated(session: dict[str, Any]) -> None:
    session["violations"] = check_mapping(session["mapping"])


@then("a violation SHALL be reported naming that email and both entries")
def _the_duplicate_email_is_named(session: dict[str, Any]) -> None:
    (violation,) = session["violations"]

    assert violation.rule_id == RULE_DUPLICATE_EMAIL
    assert WORK_EMAIL in violation.message
    assert SUBJECT in violation.message
    assert OTHER_SUBJECT in violation.message


@then("a violation SHALL be reported naming that subject")
def _the_duplicate_subject_is_named(session: dict[str, Any]) -> None:
    (violation,) = session["violations"]

    assert violation.rule_id == RULE_DUPLICATE_SUBJECT
    assert SUBJECT in violation.message
    assert SUBJECT in violation.subject


@then("a violation SHALL be reported naming the entry and the available roles")
def _the_unknown_role_is_named(session: dict[str, Any]) -> None:
    (violation,) = session["violations"]
    entry: ActorBinding = session["entry"]

    assert violation.rule_id == RULE_UNKNOWN_ROLE
    assert entry.subject in violation.message
    assert entry.default_role is not None and entry.default_role in violation.message
    for role in Role.values():
        assert role in violation.message


@then("validation SHALL complete and report its violations normally")
def _validation_completed_offline(session: dict[str, Any]) -> None:
    assert session["offline"], "the guard was never installed, so this proves nothing"
    (violation,) = session["violations"]

    assert violation.rule_id == session["expected_rule"]
    assert violation.severity.value == "error"
    assert violation.subject and violation.message


# --------------------------------------------------------------------------
# Group 2 — the resolution chain (D4), its degradation, and D13's precedence
# --------------------------------------------------------------------------


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Claimed role is ignored",
)
def test_claimed_role_is_ignored() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Claimed identity is ignored",
)
def test_claimed_identity_is_ignored() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Read works with no credential",
)
def test_read_works_with_no_credential() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Role-requiring action refused with a reason",
)
def test_role_requiring_action_refused_with_a_reason() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Reads survive an identity outage",
)
def test_reads_survive_an_identity_outage() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Cached actor expires",
)
def test_cached_actor_expires() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "A project without a mapping still works",
)
def test_a_project_without_a_mapping_still_works() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Unmapped authors are enumerable",
)
def test_unmapped_authors_are_enumerable() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Provider-supplied emails win",
)
def test_provider_supplied_emails_win() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "The file answers what the provider does not",
)
def test_the_file_answers_what_the_provider_does_not() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "Disagreement is surfaced",
)
def test_disagreement_is_surfaced() -> None: ...


# -- identity never comes from a parameter ---------------------------------


@given("a caller whose credential resolves to an actor holding the artist role")
def _a_caller_holding_the_artist_role(session: dict[str, Any]) -> None:
    provider = a_provider(a_person(Role.ARTIST, projects=(PROJECT,)))
    session["resolver"] = a_resolver(provider, Ticks())
    session["resolution"] = session["resolver"].resolve()


@when("it supplies a parameter claiming the art director role")
def _it_claims_the_art_director_role(session: dict[str, Any]) -> None:
    """The claim is dropped and named; the resolver is never asked about it."""
    session["kept"], session["claimed"] = strip_identity_claims(
        {"asset_id": "mech_scout", "role": str(Role.ART_DIRECTOR)}
    )
    session["resolution"] = session["resolver"].resolve()


@then("the system SHALL evaluate the request as the artist")
def _it_is_evaluated_as_the_artist(session: dict[str, Any]) -> None:
    resolution = session["resolution"]

    assert resolution.actor.holds(Role.ARTIST)
    assert resolution.actor.roles == (Role.ARTIST,)


@then("the supplied claim SHALL have no effect")
def _the_claim_had_no_effect(session: dict[str, Any]) -> None:
    assert "role" in session["claimed"], "a claimed role must be reported, not tolerated"
    assert "role" not in session["kept"]
    assert may_act_in_role(session["resolution"], Role.ART_DIRECTOR).refused


@when("a caller supplies an actor identifier differing from its credential")
def _a_caller_claims_another_identity(session: dict[str, Any]) -> None:
    provider = a_provider(a_person(Role.ARTIST, projects=(PROJECT,)))
    resolver = a_resolver(provider, Ticks())
    session["kept"], session["claimed"] = strip_identity_claims({"actor": OTHER_SUBJECT})
    session["resolution"] = resolver.resolve()


@then("the system SHALL use the credential's actor")
def _the_credentials_actor_is_used(session: dict[str, Any]) -> None:
    assert session["resolution"].actor.id == ActorId(SUBJECT)
    assert session["kept"] == {}
    assert "actor" in session["claimed"]


# -- reads degrade to a local actor ----------------------------------------


@given("no credential is configured")
def _no_credential_is_configured(session: dict[str, Any]) -> None:
    session["store"] = a_store()
    session["resolution"] = ActorResolver(project=PROJECT).resolve()


@when("an agent reads an asset's specification")
def _an_agent_reads_a_specification(session: dict[str, Any]) -> None:
    session["attribution"] = Attribution(actor=session["resolution"].actor.id, via=BLENDER)
    read_the_spec(session)


@then("the read SHALL succeed")
def _the_read_succeeded(session: dict[str, Any]) -> None:
    assert session["decision"].allowed, session["decision"].reason
    assert session["read"] is not None
    assert session["read"].asset.id == MECH_SCOUT.id


@when("an action requiring a role is attempted")
def _a_role_requiring_action_is_attempted(session: dict[str, Any]) -> None:
    session["role_decision"] = may_act_in_role(
        session["resolution"], Role.ART_DIRECTOR, action="promoting an annotation to a rule"
    )


@then("it SHALL be refused with a message naming the required role")
def _it_was_refused_naming_the_role(session: dict[str, Any]) -> None:
    decision = session["role_decision"]

    assert decision.refused
    assert str(Role.ART_DIRECTOR) in decision.reason


# -- an identity outage degrades rather than blocks -------------------------


@given("an actor resolved earlier and an identity service now unreachable")
def _an_actor_resolved_before_the_outage(session: dict[str, Any]) -> None:
    provider = a_provider(a_person(Role.ARTIST, projects=(PROJECT,)))
    clock = Ticks()
    resolver = a_resolver(provider, clock)
    resolver.resolve()
    provider.fail_with(IdentityUnavailable("cyberdyne-auth", "connection refused"))
    session.update(store=a_store(), resolver=resolver, clock=clock)


@when("that caller reads an asset")
def _that_caller_reads_an_asset(session: dict[str, Any]) -> None:
    session["resolution"] = session["resolver"].resolve()
    read_the_spec(session)
    assert session["resolution"].is_degraded, "the provider answered, so nothing degraded"


@given("a cached actor older than the permitted period")
def _a_cached_actor_past_its_ttl(session: dict[str, Any]) -> None:
    provider = a_provider(a_person(Role.ARTIST, projects=(PROJECT,)))
    clock = Ticks()
    resolver = a_resolver(provider, clock)
    resolver.resolve()
    provider.fail_with(IdentityUnavailable("cyberdyne-auth", "connection refused"))
    clock.advance(TTL_SECONDS + 1.0)
    session["resolution"] = resolver.resolve()


@when("a role-requiring action is attempted")
def _a_role_requiring_action_is_attempted_again(session: dict[str, Any]) -> None:
    session["role_decision"] = may_act_in_role(
        session["resolution"], Role.ARTIST, action="promoting an annotation to a rule"
    )


@then("it SHALL be refused as unverifiable")
def _it_was_refused_as_unverifiable(session: dict[str, Any]) -> None:
    decision = session["role_decision"]

    assert not session["resolution"].verified
    assert decision.refused
    assert UNVERIFIABLE in decision.reason


# -- a project with no mapping ---------------------------------------------


@given("a project that has no actor mapping")
def _a_project_with_no_mapping(session: dict[str, Any]) -> None:
    session["store"] = a_store()
    session["resolution"] = ActorResolver(project=PROJECT).resolve()
    session["authors"] = (WORK_EMAIL, STRANGER)


@when("an asset's specification is read")
def _an_assets_specification_is_read(session: dict[str, Any]) -> None:
    read_the_spec(session)
    session["mapping"] = session["store"].load_actor_mapping("").mapping


@then("every git author encountered SHALL resolve as unmapped")
def _every_author_is_unmapped(session: dict[str, Any]) -> None:
    mapping: ActorMapping = session["mapping"]

    assert mapping.is_empty
    for email in session["authors"]:
        resolved = resolve_git_author(mapping, email)
        assert resolved.is_unmapped
        assert UNMAPPED_MARK in resolved.display


@given("a project whose history contains two authors absent from the mapping")
def _two_authors_absent_from_the_mapping(session: dict[str, Any]) -> None:
    session["store"] = a_store(ActorMapping((RAFA,)))
    session["authors"] = (WORK_EMAIL, STRANGER, SECOND_STRANGER, STRANGER.upper())


@when("the project's unmapped authors are requested")
def _the_unmapped_authors_are_requested(session: dict[str, Any]) -> None:
    session["unmapped"] = ran(
        list_unmapped_authors(session["authors"], spec_store=session["store"], root="")
    )


@then("both emails SHALL be listed")
def _both_emails_are_listed(session: dict[str, Any]) -> None:
    found = session["unmapped"]

    assert found.emails == (STRANGER, SECOND_STRANGER), "each unmatched address, once"
    assert WORK_EMAIL not in found.emails, "a mapped author is not unmapped"


# -- claims first, the file second (D13) -----------------------------------


@given("a provider that resolves an actor together with its git author emails")
def _a_provider_that_supplies_emails(session: dict[str, Any]) -> None:
    provider = a_provider(
        a_person(Role.ARTIST, projects=(PROJECT,)), git_emails=(WORK_EMAIL, PERSONAL_EMAIL)
    )
    session["resolution"] = a_resolver(provider, Ticks()).resolve()
    session["mapping"] = ActorMapping((RAFA,))
    session["expected_emails"] = (WORK_EMAIL, PERSONAL_EMAIL)


@given("a provider that resolves an actor but supplies no git author emails")
def _a_provider_that_supplies_no_emails(session: dict[str, Any]) -> None:
    provider = a_provider(a_person(Role.ARTIST, projects=(PROJECT,)))
    session["resolution"] = a_resolver(provider, Ticks()).resolve()
    session["mapping"] = ActorMapping((RAFA,))


@given("a provider and a mapping file that bind the same subject to different git author emails")
def _a_provider_disagreeing_with_the_file(session: dict[str, Any]) -> None:
    provider = a_provider(a_person(Role.ARTIST, projects=(PROJECT,)), git_emails=(CLAIMED_EMAIL,))
    session["resolution"] = a_resolver(provider, Ticks()).resolve()
    session["mapping"] = ActorMapping((RAFA,))
    session["expected_emails"] = (CLAIMED_EMAIL,)


@when("that actor's git author identity is requested")
def _the_git_identity_of_that_actor(session: dict[str, Any]) -> None:
    session["git_identity"] = resolve_git_identity(session["resolution"], session["mapping"])
    session["without_file"] = resolve_git_identity(session["resolution"], ActorMapping())


@when("that actor is resolved")
def _that_actor_is_resolved(session: dict[str, Any]) -> None:
    session["git_identity"] = resolve_git_identity(session["resolution"], session["mapping"])


@then("the provider's emails SHALL be used")
def _the_providers_emails_were_used(session: dict[str, Any]) -> None:
    identity = session["git_identity"]

    assert identity.source is GitIdentitySource.PROVIDER
    assert identity.emails == session["expected_emails"]


@then("the mapping file SHALL NOT change the result")
def _the_file_changed_nothing(session: dict[str, Any]) -> None:
    assert session["git_identity"].emails == session["without_file"].emails
    assert session["git_identity"].violations == ()


@then("the emails SHALL come from the mapping file entry for that subject")
def _the_emails_came_from_the_file(session: dict[str, Any]) -> None:
    identity = session["git_identity"]

    assert identity.source is GitIdentitySource.MAPPING
    assert identity.emails == RAFA.emails
    assert session["without_file"].is_unmapped, "with no file there is nothing to fall back to"


@then("the system SHALL report that the mapping file entry disagrees")
def _the_disagreement_was_reported(session: dict[str, Any]) -> None:
    (violation,) = session["git_identity"].violations

    assert violation.rule_id == RULE_PROVIDER_DISAGREEMENT
    assert SUBJECT in violation.message
    assert WORK_EMAIL in violation.message
    assert CLAIMED_EMAIL in violation.message


# --------------------------------------------------------------------------
# Every name a reader sees goes through the mapping (group 3, D12, D14)
# --------------------------------------------------------------------------


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "A location answer names the person",
)
def test_a_location_answer_names_the_person() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "An unmapped owner is shown as unmapped",
)
def test_an_unmapped_owner_is_shown_as_unmapped() -> None: ...


@scenario(
    "../features/add-mcp-read-server/agent-identity.feature",
    "One person, one presentation",
)
def test_one_person_one_presentation() -> None: ...


def an_owned_asset(owner: str) -> Asset:
    """The same asset, owned by whichever address the scenario is about."""
    return Asset(id=AssetId("mech_scout"), name="Scout Mech", owner_art=owner)


def an_indexed_project(session: dict[str, Any], owner: str) -> None:
    """One asset indexed, and the project's mapping, ready for a location answer."""
    store = InMemorySpecStore()
    store.add(SPEC_PATH, an_owned_asset(owner))
    store.set_actor_mapping(ActorMapping((RAFA,)))
    index = InMemorySearchIndex()
    ran(rebuild_index(spec_store=store, search_index=index))
    session["store"] = store
    session["index"] = index


@given(
    "an asset whose art owner is recorded as `rafa@cyberdyne.com` and a mapping entry "
    "binding that email to the display name `Rafa`"
)
def _an_asset_owned_by_a_mapped_person(session: dict[str, Any]) -> None:
    an_indexed_project(session, WORK_EMAIL)


@given("an asset whose art owner is an email present in no mapping entry")
def _an_asset_owned_by_nobody_mapped(session: dict[str, Any]) -> None:
    an_indexed_project(session, STRANGER)


@when("the asset's location is requested")
def _the_assets_location_is_requested(session: dict[str, Any]) -> None:
    session["answer"] = ran(
        where_is("mech_scout", spec_store=session["store"], search_index=session["index"])
    )


@then("the response SHALL name the art owner as `Rafa`")
def _the_art_owner_is_named(session: dict[str, Any]) -> None:
    owner = session["answer"].owner(ART)

    assert owner.display == DISPLAY_NAME
    assert not owner.is_unmapped
    assert UNMAPPED_MARK not in owner.display


@then("the response SHALL show that email")
def _the_response_shows_the_email(session: dict[str, Any]) -> None:
    assert STRANGER in session["answer"].owner(ART).display


@then("SHALL mark the owner as unmapped")
def _the_owner_is_marked_unmapped(session: dict[str, Any]) -> None:
    owner = session["answer"].owner(ART)

    assert owner.is_unmapped
    assert UNMAPPED_MARK in owner.display


@given("a person who appears as an asset owner, as a commit author and as a resolved caller")
def _one_person_in_three_places(session: dict[str, Any]) -> None:
    an_indexed_project(session, WORK_EMAIL)
    provider = a_provider(a_person(Role.ARTIST, projects=(PROJECT,)))
    session["resolution"] = a_resolver(provider, Ticks()).resolve()
    session["mapping"] = ActorMapping((RAFA,))


@when("each of those is presented")
def _each_presentation_is_taken(session: dict[str, Any]) -> None:
    answer = ran(where_is("mech_scout", spec_store=session["store"], search_index=session["index"]))
    session["presentations"] = {
        "owner": answer.owner(ART).display,
        "commit author": resolve_git_author(session["mapping"], COMMITTED_AS).display,
        "caller": session["resolution"].actor.display,
    }


@then("all three SHALL show the same display name")
def _all_three_show_the_same_name(session: dict[str, Any]) -> None:
    presentations = session["presentations"]

    assert set(presentations.values()) == {DISPLAY_NAME}, presentations
