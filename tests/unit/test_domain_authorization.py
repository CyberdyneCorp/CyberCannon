"""Tasks 1.2 and 1.4 — what a resolved actor may read, and what no agent may write.

Both policies are pure functions of value objects, so both are asserted with the
socket module taken away: `agent-identity` requires an authorization decision to
be producible with no identity service reachable, and the only way to prove that
is to make a connection fail the test.
"""

from __future__ import annotations

import socket

import pytest

from cybercanon.domain.authorization import (
    may_author_durable_content,
    may_read_project,
)
from cybercanon.domain.identity import (
    Actor,
    ActorId,
    AgentId,
    Role,
    local_actor,
    unmapped_actor,
)

PROJECT = "cyberdyne-game"
OTHER_PROJECT = "another-game"
BLENDER = AgentId("blender-agent")


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No identity service, no network — the condition the decision runs under."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("an authorization decision opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def a_person(*roles: Role, projects: tuple[str, ...] = (PROJECT,)) -> Actor:
    return Actor(id=ActorId("auth|rafa"), display_name="Rafa", roles=roles, projects=projects)


# --------------------------------------------------------------------------
# Read entitlement (task 1.2)
# --------------------------------------------------------------------------


def test_an_entitled_actor_may_read_the_project(offline: None) -> None:
    decision = may_read_project(a_person(Role.ARTIST), PROJECT)

    assert decision.allowed
    assert decision


def test_an_unentitled_actor_is_refused_and_told_which_project(offline: None) -> None:
    decision = may_read_project(a_person(Role.ART_DIRECTOR), OTHER_PROJECT)

    assert decision.refused
    assert not decision
    assert "Rafa" in decision.reason
    assert OTHER_PROJECT in decision.reason


def test_the_local_actor_reads_the_project_on_this_machine(offline: None) -> None:
    """D4 — no credential configured, and the read still happens."""
    assert may_read_project(local_actor(PROJECT), PROJECT).allowed


def test_the_local_actor_is_still_confined_to_that_project(offline: None) -> None:
    assert may_read_project(local_actor(PROJECT), OTHER_PROJECT).refused


def test_an_unmapped_actor_reads_nothing(offline: None) -> None:
    decision = may_read_project(unmapped_actor("stranger@example.com"), PROJECT)

    assert decision.refused
    assert "stranger@example.com" in decision.reason
    assert "unmapped" in decision.reason


def test_roles_do_not_widen_a_read(offline: None) -> None:
    """Holding every role is not entitlement to a project nobody granted."""
    every_role = a_person(*Role, projects=())

    assert may_read_project(every_role, PROJECT).refused


def test_the_decision_is_produced_from_the_actor_alone(offline: None) -> None:
    """The same value in, the same answer out — nothing external is consulted."""
    actor = a_person(Role.ARTIST)

    first = may_read_project(actor, PROJECT)
    second = may_read_project(actor, PROJECT)

    assert first == second


# --------------------------------------------------------------------------
# Durable content (task 1.4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", list(Role), ids=lambda role: role.value)
def test_an_automated_caller_may_not_author_durable_content_for_any_role(
    role: Role, offline: None
) -> None:
    """Refused *regardless of the roles held by the actor it acts as*."""
    decision = may_author_durable_content(a_person(role), via=BLENDER)

    assert decision.refused
    assert "blender-agent" in decision.reason
    assert "unattainable" in decision.reason, "the refusal names the exit that is open"


def test_an_agent_acting_for_an_art_director_is_refused_like_any_other(offline: None) -> None:
    """Promotion is prohibited, not delegated — the director's agent is an agent."""
    director = a_person(Role.ART_DIRECTOR)

    assert may_author_durable_content(director, via=BLENDER).refused
    assert may_author_durable_content(director, via=AgentId("claude-code")).refused


def test_a_person_acting_directly_is_not_refused_by_this_policy(offline: None) -> None:
    """The rule is about automation, not about authorship in general."""
    assert may_author_durable_content(a_person(Role.ART_DIRECTOR)).allowed


def test_the_policy_never_consults_the_roles(offline: None) -> None:
    """Every role gives the same answer, which is what 'regardless' means."""
    answers = {may_author_durable_content(a_person(role), via=BLENDER).allowed for role in Role}

    assert answers == {False}
