"""Tasks 2.1-2.4 — the operation matrix, decided from an actor and nothing else.

Every test here builds its actors by hand. That is the property `auth-integration`
asks for in so many words — *"an authorization decision SHALL be produced from
that actor's identifier and roles alone"* — and it is why the whole suite runs
with no identity service, no HTTP and no database: there is no seam through
which one could be reached, so no test has to arrange for its absence.

`test_no_decision_opens_a_network_connection` makes the claim mechanical rather
than architectural, the same way `agent-identity`'s suite does: sockets are
taken away and the matrix is walked end to end.
"""

from __future__ import annotations

import socket

import pytest

from cybercanon.domain.authorization import WRONG_TENANT, may_author_durable_content
from cybercanon.domain.identity import (
    Actor,
    ActorId,
    AgentId,
    Role,
    automation_actor,
    local_actor,
)
from cybercanon.domain.policy import (
    HUMAN_ONLY,
    MUTATING,
    NEEDS_GIT_IDENTITY,
    NEEDS_GIT_MAPPING,
    READ_ONLY,
    REQUIRES_PERSON,
    Operation,
    Subject,
    decide,
    declares_human_only,
    requires_person,
)
from cybercanon.domain.tenancy import ProjectRef, Tenant

PROJECT = "cyberdyne-game"
CYBERDYNE = Tenant("cyberdyne")
OTHER_TENANT = Tenant("ironwood-studios")

RAFA = ActorId("auth|rafa")
ANA = ActorId("auth|ana")
NOBODY = ActorId("auth|stranger")

BLENDER = AgentId("blender-agent")

HERE = Subject(project=PROJECT)


def a_person(*roles: Role, tenant: Tenant | None = None, actor_id: ActorId = RAFA) -> Actor:
    return Actor(
        id=actor_id,
        display_name=actor_id.value,
        roles=roles,
        projects=(PROJECT,),
        tenant=tenant,
    )


def a_robot(*roles: Role) -> Actor:
    """A service credential holding whatever roles the test wants it to hold."""
    return automation_actor(projects=(PROJECT,), roles=roles)


# --------------------------------------------------------------------------
# 2.1 — tenancy, refused by policy alone
# --------------------------------------------------------------------------


def test_a_project_outside_the_actors_tenant_is_refused() -> None:
    elsewhere = Subject(project=ProjectRef(PROJECT, tenant=OTHER_TENANT))

    decision = decide(a_person(tenant=CYBERDYNE), Operation.READ_PROJECT, elsewhere)

    assert decision.refused
    assert WRONG_TENANT in decision.reason


def test_the_actors_own_tenant_is_admitted() -> None:
    mine = Subject(project=ProjectRef(PROJECT, tenant=CYBERDYNE))

    assert decide(a_person(tenant=CYBERDYNE), Operation.READ_PROJECT, mine).allowed


def test_a_tenant_refusal_does_not_say_whether_the_project_exists() -> None:
    """The same sentence either way, so nobody enumerates another organisation."""
    known = Subject(project=ProjectRef(PROJECT, tenant=OTHER_TENANT))
    invented = Subject(project=ProjectRef("no-such-project", tenant=OTHER_TENANT))
    actor = a_person(tenant=CYBERDYNE)

    assert WRONG_TENANT in decide(actor, Operation.READ_PROJECT, known).reason
    assert WRONG_TENANT in decide(actor, Operation.READ_PROJECT, invented).reason


def test_tenancy_is_checked_before_entitlement() -> None:
    """A cross-tenant address is refused even for a project the actor holds."""
    actor = Actor(
        id=RAFA,
        display_name="Rafa",
        projects=(PROJECT,),
        tenant=CYBERDYNE,
        roles=(Role.ART_DIRECTOR,),
    )
    elsewhere = Subject(project=ProjectRef(PROJECT, tenant=OTHER_TENANT))

    assert WRONG_TENANT in decide(actor, Operation.PROMOTE_TO_RULE, elsewhere).reason


def test_the_stable_subject_identifier_is_the_actor_id() -> None:
    assert a_person().subject == RAFA.value


# --------------------------------------------------------------------------
# 2.2 — the matrix, as pure functions over (actor, operation, subject)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("operation", sorted(READ_ONLY, key=str))
def test_reads_are_never_role_gated(operation: Operation) -> None:
    """G4's first two rows: search, lookup, compile and validate are reads."""
    assert decide(a_person(), operation, HERE).allowed


@pytest.mark.parametrize("operation", sorted(Operation, key=str))
def test_an_unentitled_actor_is_refused_everything(operation: Operation) -> None:
    stranger = Actor(id=NOBODY, display_name="stranger", projects=("another-game",))

    assert decide(stranger, operation, HERE).refused


def test_the_local_unauthenticated_actor_reads_the_project_it_stands_in() -> None:
    assert decide(local_actor(PROJECT), Operation.READ_PROJECT, HERE).allowed


def test_the_local_actor_holds_no_role_so_it_promotes_nothing() -> None:
    decision = decide(local_actor(PROJECT), Operation.PROMOTE_TO_RULE, HERE)

    assert decision.refused
    assert str(Role.ART_DIRECTOR) in decision.reason


@pytest.mark.parametrize(
    "operation",
    [Operation.CREATE_ANNOTATION, Operation.REPLY_IN_THREAD, Operation.RAISE_REQUEST],
)
def test_any_reader_with_a_mapped_identity_may_ask_and_annotate(operation: Operation) -> None:
    assert decide(a_person(), operation, HERE).allowed


def test_promotion_is_art_director_only() -> None:
    assert decide(a_person(Role.ARTIST), Operation.PROMOTE_TO_RULE, HERE).refused
    assert decide(a_person(Role.ART_DIRECTOR), Operation.PROMOTE_TO_RULE, HERE).allowed


def test_an_issue_is_resolved_by_its_author_or_the_art_director() -> None:
    mine = Subject(project=PROJECT, author=RAFA)

    assert decide(a_person(), Operation.RESOLVE_ISSUE, mine).allowed
    assert decide(a_person(actor_id=ANA), Operation.RESOLVE_ISSUE, mine).refused
    assert decide(a_person(Role.ART_DIRECTOR, actor_id=ANA), Operation.RESOLVE_ISSUE, mine).allowed


@pytest.mark.parametrize(
    "operation", [Operation.ACCEPT_SUGGESTED_ALIAS, Operation.TRANSITION_ASSET_STATUS]
)
def test_the_discipline_owner_or_the_art_director_decides(operation: Operation) -> None:
    owned = Subject(project=PROJECT, discipline_owner=RAFA)

    assert decide(a_person(), operation, owned).allowed
    assert decide(a_person(actor_id=ANA), operation, owned).refused
    assert decide(a_person(Role.ART_DIRECTOR, actor_id=ANA), operation, owned).allowed


def test_a_request_is_decided_by_its_assignee_the_owner_or_the_art_director() -> None:
    assigned = Subject(project=PROJECT, assignee=ANA, discipline_owner=RAFA)

    assert decide(a_person(actor_id=ANA), Operation.DECIDE_REQUEST, assigned).allowed
    assert decide(a_person(), Operation.DECIDE_REQUEST, assigned).allowed
    assert decide(a_person(actor_id=NOBODY), Operation.DECIDE_REQUEST, assigned).refused


def test_an_unrelated_actor_is_refused_a_decision_naming_the_required_role() -> None:
    """`asset-requests`: refused *"with a message naming what would be required"*."""
    assigned = Subject(project=PROJECT, assignee=ANA, description="request crate-01")
    outsider = Actor(id=NOBODY, display_name="Sam", projects=(PROJECT,))

    decision = decide(outsider, Operation.DECIDE_REQUEST, assigned)

    assert decision.refused
    assert str(Role.ART_DIRECTOR) in decision.reason
    assert "request crate-01" in decision.reason


@pytest.mark.parametrize("operation", sorted(NEEDS_GIT_MAPPING, key=str))
def test_a_person_with_no_git_identity_may_read_but_not_write(operation: Operation) -> None:
    """D7's accepted cost: no mapping entry, no commit, therefore no write."""
    unmapped = Subject(project=PROJECT, has_git_identity=False, author=RAFA, assignee=RAFA)

    assert decide(a_person(Role.ART_DIRECTOR), Operation.READ_PROJECT, unmapped).allowed
    assert NEEDS_GIT_IDENTITY in decide(a_person(Role.ART_DIRECTOR), operation, unmapped).reason


def test_every_mutating_operation_has_a_rule() -> None:
    """A missing rule is a `KeyError` at a caller; this makes it a failing build."""
    for operation in MUTATING:
        assert decide(a_person(Role.ART_DIRECTOR), operation, HERE) is not None


def test_no_decision_opens_a_network_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proving "no identity service" requires a connection to fail the test."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("an authorization decision opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    for operation in Operation:
        decide(a_person(Role.ART_DIRECTOR), operation, HERE)


def test_two_identically_shaped_actors_receive_the_same_decision() -> None:
    """`auth-integration`: a resolved actor and a constructed one are one thing."""
    resolved = Actor(id=RAFA, display_name="Rafa", roles=(Role.ARTIST,), projects=(PROJECT,))
    constructed = Actor(id=RAFA, display_name="Rafa", roles=(Role.ARTIST,), projects=(PROJECT,))

    for operation in Operation:
        assert decide(resolved, operation, HERE) == decide(constructed, operation, HERE)


# --------------------------------------------------------------------------
# 2.3-2.4 — the human-only registry (D13)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("operation", sorted(MUTATING, key=str))
def test_every_mutating_operation_declares_whether_it_needs_a_person(
    operation: Operation,
) -> None:
    """D13: an absence cannot be enforced by absence, so each one declares."""
    assert declares_human_only(operation)
    assert requires_person(operation) is (operation in HUMAN_ONLY)


def test_the_registry_covers_promotion_and_acceptance() -> None:
    assert requires_person(Operation.PROMOTE_TO_RULE)
    assert requires_person(Operation.ACCEPT_SUGGESTED_ALIAS)


def test_a_read_needs_no_person() -> None:
    assert not requires_person(Operation.READ_PROJECT)
    assert declares_human_only(Operation.READ_PROJECT)


@pytest.mark.parametrize("operation", [Operation.PROMOTE_TO_RULE, Operation.ACCEPT_SUGGESTED_ALIAS])
def test_automation_holding_every_role_is_still_refused(operation: Operation) -> None:
    """The point is not that automation holds nothing. It is that roles do not help."""
    every_role = a_robot(*Role)

    decision = decide(every_role, operation, Subject(project=PROJECT, discipline_owner=RAFA))

    assert decision.refused
    assert REQUIRES_PERSON in decision.reason


@pytest.mark.parametrize("operation", [Operation.PROMOTE_TO_RULE, Operation.ACCEPT_SUGGESTED_ALIAS])
def test_an_agent_acting_as_an_art_director_is_refused_too(operation: Operation) -> None:
    """`project.md`: *"not even for an art director's agent"*."""
    decision = decide(
        a_person(Role.ART_DIRECTOR),
        operation,
        Subject(project=PROJECT, discipline_owner=RAFA),
        via=BLENDER,
    )

    assert decision.refused
    assert str(BLENDER) in decision.reason
    assert REQUIRES_PERSON in decision.reason


def test_automation_may_still_read() -> None:
    """Refusing background work everything would break the scheduled refresh."""
    assert decide(a_robot(), Operation.READ_PROJECT, HERE).allowed


def test_automation_may_not_author_durable_content_even_with_no_agent_named() -> None:
    decision = may_author_durable_content(a_robot(*Role))

    assert decision.refused
    assert "automation" in decision.reason


def test_a_person_acting_directly_may_author_durable_content() -> None:
    assert may_author_durable_content(a_person(Role.ART_DIRECTOR)).allowed


def test_the_operation_vocabulary_is_nameable() -> None:
    """A refusal names an operation, so the set has to be printable."""
    assert Operation.values()[0] == "read_project"
    assert str(Operation.PROMOTE_TO_RULE) == "promote_to_rule"
