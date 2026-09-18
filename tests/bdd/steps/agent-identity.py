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

The rest of this capability's scenarios stay in `tests/bdd/pending.txt` until the
groups that earn them: the resolution chain and the claims-before-file
precedence (group 2), the presentation of owners through `where_is` and the
listings (group 3), and the recorded observation an agent's report becomes
(`add-mcp-writes`).
"""

from __future__ import annotations

import socket
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.domain.actor_checks import (
    RULE_DUPLICATE_EMAIL,
    RULE_DUPLICATE_SUBJECT,
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
