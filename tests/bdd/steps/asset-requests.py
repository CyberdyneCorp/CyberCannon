"""Step definitions for `asset-requests` — the ask with an owner and an ending.

Groups 3 and 4 of `add-web-backend` build this capability's two halves. The
domain (:mod:`cybercanon.domain.requests`) decides what a request *is*: its
shape, its transition table, the decline-with-a-reason and author-only-withdraw
rules, the assignment cascade, and the fulfilment precondition that reads the
asset's status and can never write it. The application
(:mod:`cybercanon.application.use_cases.requests`) makes each of those a commit
in the project's repository (D7), authored by the acting person (D8), followed
by a notification that cannot change what happened (D9).

Everything bound here runs against the in-memory repository host, so a full
lifecycle — raise, assign, accept, fulfil — is exercised with no git, no disk
and no network, exactly as the validator suite is exercised with no mesh file.

Four of this capability's scenarios stay in `tests/bdd/pending.txt` until the
groups that earn them: the two about unread items and dismissal need the derived
notification query of group 10 (D9), and the index-rebuild scenario needs the
PostgreSQL index of group 6.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.results import Conflict, Forbidden, Invalid, succeeded
from cybercanon.application.testing.notifier import InMemoryNotifier
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.use_cases.requests import (
    assign_request,
    path_for,
    raise_request,
    read_request,
    transition_request,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.policy import Operation, Subject, decide
from cybercanon.domain.requests import (
    AUTHOR_WITHDRAWS,
    NEEDS_DESCRIPTION,
    NEEDS_REASON,
    Discipline,
    DisciplineOwners,
    RequestId,
    RequestState,
    assignee_for,
    link_to_asset,
)
from cybercanon.domain.requests import raise_request as build_request
from cybercanon.domain.status import Status

PROJECT = "cyberdyne-game"
SPEC_PATH = "characters/mech_scout/asset.yaml"
SPEC_CONTENT = b"schema_version: 1\nid: mech_scout\n"

RAFA = ActorId("auth|rafa")
ANA = ActorId("auth|ana")
SAM = ActorId("auth|sam")

RAFA_GIT = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
ANA_GIT = GitAuthor(name="Ana", email="ana@cyberdyne.com")

REQUEST = RequestId("req-0001")
CRATE = AssetId("crate_01")
WANTED = "a supply crate for the loading dock, one metre cubed"

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
LATER = NOON + timedelta(hours=1)


@pytest.fixture
def ask() -> dict[str, Any]:
    """What this scenario set up, and what the request model answered."""
    return {}


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    """A cloned project holding one specification and no requests."""
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC_PATH: SPEC_CONTENT})
    built.clone(PROJECT)
    return built


def a_request(**overrides: Any):
    fields: dict[str, Any] = {
        "request_id": REQUEST,
        "author": RAFA,
        "discipline": Discipline.MODELING,
        "description": WANTED,
        "at": NOON,
    }
    fields.update(overrides)
    return build_request(**fields)


def record(host: InMemoryRepositoryHost, **overrides: Any):
    return raise_request(
        PROJECT,
        a_request(**overrides),
        repository_host=host,
        author=RAFA_GIT,
        clock=lambda: NOON,
    )


def move(
    host: InMemoryRepositoryHost,
    to: RequestState,
    *,
    actor: ActorId = ANA,
    author: GitAuthor | None = ANA_GIT,
    **extra: Any,
):
    return transition_request(
        PROJECT,
        REQUEST,
        to,
        actor=actor,
        repository_host=host,
        author=author,
        clock=lambda: LATER,
        **extra,
    )


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario("../features/add-web-backend/asset-requests.feature", "Request against an existing asset")
def test_request_against_an_existing_asset() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature",
    "Request for something that does not exist yet",
)
def test_request_for_something_that_does_not_exist_yet() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature",
    "Linking a request to a newly created asset",
)
def test_linking_a_request_to_a_newly_created_asset() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature", "A request states what is needed and why"
)
def test_a_request_states_what_is_needed_and_why() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature",
    "Assignment follows the asset's discipline owner",
)
def test_assignment_follows_the_assets_discipline_owner() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature",
    "Assignment falls back to the project's discipline owner",
)
def test_assignment_falls_back_to_the_projects_discipline_owner() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature",
    "No owner means unassigned, not misassigned",
)
def test_no_owner_means_unassigned_not_misassigned() -> None: ...


@scenario("../features/add-web-backend/asset-requests.feature", "Reassignment is attributed")
def test_reassignment_is_attributed() -> None: ...


@scenario("../features/add-web-backend/asset-requests.feature", "Invalid transition is refused")
def test_invalid_transition_is_refused() -> None: ...


@scenario("../features/add-web-backend/asset-requests.feature", "Declining states a reason")
def test_declining_states_a_reason() -> None: ...


@scenario("../features/add-web-backend/asset-requests.feature", "Only the author withdraws")
def test_only_the_author_withdraws() -> None: ...


@scenario("../features/add-web-backend/asset-requests.feature", "Every transition is attributed")
def test_every_transition_is_attributed() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature", "Request state does not move asset status"
)
def test_request_state_does_not_move_asset_status() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature", "Asset status does not move request state"
)
def test_asset_status_does_not_move_request_state() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature", "Fulfilment requires the asked-for status"
)
def test_fulfilment_requires_the_asked_for_status() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature",
    "Fulfilment succeeds once the status is reached",
)
def test_fulfilment_succeeds_once_the_status_is_reached() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature",
    "A request that could not be persisted did not happen",
)
def test_a_request_that_could_not_be_persisted_did_not_happen() -> None: ...


@scenario("../features/add-web-backend/asset-requests.feature", "A reader may ask")
def test_a_reader_may_ask() -> None: ...


@scenario("../features/add-web-backend/asset-requests.feature", "An unrelated actor may not decide")
def test_an_unrelated_actor_may_not_decide() -> None: ...


@scenario("../features/add-web-backend/asset-requests.feature", "A request is not a constraint")
def test_a_request_is_not_a_constraint() -> None: ...


@scenario(
    "../features/add-web-backend/asset-requests.feature",
    "Notification failure does not reverse the action",
)
def test_notification_failure_does_not_reverse_the_action() -> None: ...


# --------------------------------------------------------------------------
# Targeting an asset, or none yet
# --------------------------------------------------------------------------


@given("an asset with a specification")
def _an_asset_with_a_specification(ask: dict[str, Any]) -> None:
    ask["asset"] = Asset(id=CRATE, name="Supply Crate")


@when("a person raises a request against it")
def _a_request_against_it(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["recorded"] = ran(record(host, asset=CRATE))


@then("the request SHALL be recorded referencing that asset")
def _it_references_that_asset(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert ask["recorded"].request.asset == CRATE
    assert ran(read_request(PROJECT, REQUEST, repository_host=host)).asset == CRATE


@when("a person raises a request describing an asset that has no specification")
def _a_request_for_nothing_yet(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["before"] = set(host.remote_files(PROJECT))
    ask["recorded"] = ran(record(host))


@then("the request SHALL be recorded without an asset reference")
def _it_references_no_asset(ask: dict[str, Any]) -> None:
    assert ask["recorded"].request.asset is None
    assert ask["recorded"].request.description == WANTED


@then("no specification SHALL be created")
def _no_specification_was_created(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    written = set(host.remote_files(PROJECT)) - ask["before"]

    assert written == {path_for(REQUEST)}
    assert not any(path.endswith("asset.yaml") for path in written)


@given("an open request with no asset reference")
def _an_open_unlinked_request(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["recorded"] = ran(record(host))


@when("a person associates it with a newly created asset")
def _it_is_associated(ask: dict[str, Any]) -> None:
    ask["linked"] = link_to_asset(ask["recorded"].request, CRATE, actor=RAFA, at=LATER)


@then("the request SHALL reference that asset thereafter")
def _it_references_the_new_asset(ask: dict[str, Any]) -> None:
    assert ask["linked"].asset == CRATE
    assert ask["linked"].state is RequestState.OPEN


@when("a request is raised without a description of what is needed")
def _a_request_with_no_description(ask: dict[str, Any]) -> None:
    try:
        a_request(description="   ")
    except ValueError as rejected:
        ask["rejected"] = rejected


@then("it SHALL be rejected as invalid")
def _it_was_rejected_as_invalid(ask: dict[str, Any]) -> None:
    assert NEEDS_DESCRIPTION in str(ask["rejected"])


# --------------------------------------------------------------------------
# Assignment by discipline
# --------------------------------------------------------------------------


@given("an asset whose modelling owner is a given person")
def _an_asset_with_a_modelling_owner(ask: dict[str, Any]) -> None:
    ask["on_asset"] = DisciplineOwners(art=ANA)


@when("a modelling request is raised against it")
def _a_modelling_request(ask: dict[str, Any]) -> None:
    ask["assignee"] = assignee_for(Discipline.MODELING, on_asset=ask.get("on_asset"), author=RAFA)


@then("the request SHALL be assigned to that person")
def _it_is_assigned_to_that_person(ask: dict[str, Any]) -> None:
    assert ask["assignee"] == ANA


@given("a request for an asset that does not exist yet")
def _a_request_with_no_asset(ask: dict[str, Any]) -> None:
    ask["on_asset"] = None


@when("it names a discipline for which the project declares an owner")
def _the_project_declares_an_owner(ask: dict[str, Any]) -> None:
    ask["assignee"] = assignee_for(
        Discipline.MODELING,
        on_asset=ask.get("on_asset"),
        on_project=DisciplineOwners(art=SAM),
        author=RAFA,
    )


@then("it SHALL be assigned to that person")
def _it_is_assigned_to_the_project_owner(ask: dict[str, Any]) -> None:
    assert ask["assignee"] == SAM


@given("a discipline with no owner on the asset and none on the project")
def _a_discipline_nobody_owns(ask: dict[str, Any]) -> None:
    ask["on_asset"] = DisciplineOwners()
    ask["on_project"] = DisciplineOwners()


@when("a request for it is raised")
def _a_request_for_an_unowned_discipline(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["assignee"] = assignee_for(
        Discipline.CODE,
        on_asset=ask["on_asset"],
        on_project=ask["on_project"],
        author=RAFA,
    )
    ask["recorded"] = ran(record(host, discipline=Discipline.CODE, assignee=ask["assignee"]))


@then("the request SHALL be recorded as unassigned")
def _it_is_unassigned(ask: dict[str, Any]) -> None:
    assert ask["assignee"] is None
    assert ask["recorded"].request.assignee is None
    assert ask["recorded"].request.assignee != RAFA


@then("SHALL be reported as needing an owner")
def _it_needs_an_owner(ask: dict[str, Any]) -> None:
    assert ask["recorded"].request.needs_owner


@when("a request is reassigned to another person")
def _it_is_reassigned(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ran(record(host, assignee=ANA))
    ask["recorded"] = ran(
        assign_request(
            PROJECT,
            REQUEST,
            SAM,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            clock=lambda: LATER,
        )
    )


@then("the change SHALL record who reassigned it and when")
def _the_reassignment_is_attributed(ask: dict[str, Any]) -> None:
    last = ask["recorded"].request.last_event

    assert last is not None
    assert last.actor == ANA
    assert last.at == LATER
    assert last.assignee == SAM


# --------------------------------------------------------------------------
# The lifecycle
# --------------------------------------------------------------------------


@given("a request in the `fulfilled` state")
def _a_fulfilled_request(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ran(record(host, assignee=ANA))
    ran(move(host, RequestState.ACCEPTED))
    ask["recorded"] = ran(move(host, RequestState.FULFILLED))


@when("a transition back to `open` is attempted")
def _back_to_open(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["refusal"] = refused(move(host, RequestState.OPEN))


@then("it SHALL be refused")
def _it_was_refused(ask: dict[str, Any]) -> None:
    assert isinstance(ask["refusal"], Conflict)


@then("the request SHALL remain `fulfilled`")
def _it_is_still_fulfilled(host: InMemoryRepositoryHost) -> None:
    assert ran(read_request(PROJECT, REQUEST, repository_host=host)).state is (
        RequestState.FULFILLED
    )


@when("a request is declined without a reason")
def _declined_with_no_reason(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ran(record(host, assignee=ANA))
    ask["refusal"] = refused(move(host, RequestState.DECLINED))


@then("the transition SHALL be refused")
def _the_transition_was_refused(ask: dict[str, Any]) -> None:
    assert isinstance(ask["refusal"], Invalid)
    assert ask["refusal"].message == NEEDS_REASON


@given("a request raised by one person")
def _a_request_by_one_person(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["recorded"] = ran(record(host, assignee=ANA))


@when("another person attempts to withdraw it")
def _another_person_withdraws(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["refusal"] = refused(move(host, RequestState.WITHDRAWN, actor=ANA))


@then("the attempt SHALL be refused")
def _the_attempt_was_refused(ask: dict[str, Any]) -> None:
    refusal = ask["refusal"]

    assert isinstance(refusal, Forbidden)
    assert refusal.message == AUTHOR_WITHDRAWS


@when("a request changes state")
def _a_request_changes_state(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ran(record(host, assignee=ANA))
    ask["recorded"] = ran(move(host, RequestState.ACCEPTED))


@then("the record SHALL identify the person who caused the change and when")
def _the_change_is_attributed(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    stored = ran(read_request(PROJECT, REQUEST, repository_host=host))
    last = stored.history[-1]

    assert last.actor == ANA
    assert last.at == LATER
    assert last.state is RequestState.ACCEPTED


# --------------------------------------------------------------------------
# Observing the asset lifecycle, never driving it
# --------------------------------------------------------------------------


@given("an asset in the `modeling` status with an accepted request against it")
def _an_accepted_request_against_a_modelling_asset(
    ask: dict[str, Any], host: InMemoryRepositoryHost
) -> None:
    ask["asset"] = Asset(id=CRATE, name="Supply Crate", status=Status.MODELING)
    ran(record(host, asset=CRATE, assignee=ANA))
    ran(move(host, RequestState.ACCEPTED))


@when("the request is marked `fulfilled`")
def _it_is_marked_fulfilled(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    asset = ask.get("asset")
    outcome = move(
        host,
        RequestState.FULFILLED,
        asset_status=asset.status if asset is not None else None,
    )
    ask["outcome"] = outcome
    if not succeeded(outcome):
        ask["refusal"] = outcome


@then("the asset's status SHALL be unchanged")
def _the_asset_did_not_move(ask: dict[str, Any]) -> None:
    assert ask["asset"].status is Status.MODELING
    assert ask["asset"] == Asset(id=CRATE, name="Supply Crate", status=Status.MODELING)


@given("an open request against an asset")
def _an_open_request_against_an_asset(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["asset"] = Asset(id=CRATE, name="Supply Crate", status=Status.MODELING)
    ask["recorded"] = ran(record(host, asset=CRATE, assignee=ANA))


@when("the asset's status advances")
def _the_asset_advances(ask: dict[str, Any]) -> None:
    ask["asset"] = Asset(id=CRATE, name="Supply Crate", status=Status.VALIDATED)


@then("the request SHALL remain `open`")
def _the_request_is_still_open(host: InMemoryRepositoryHost) -> None:
    assert ran(read_request(PROJECT, REQUEST, repository_host=host)).state is RequestState.OPEN


@given("a request asking for an asset to reach `validated` and an asset in `modeling`")
def _a_request_asking_for_validated(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["asset"] = Asset(id=CRATE, name="Supply Crate", status=Status.MODELING)
    ran(record(host, asset=CRATE, assignee=ANA, asked_for_status=Status.VALIDATED))
    ran(move(host, RequestState.ACCEPTED))


@then("the transition SHALL be refused naming the asset's current status")
def _refused_naming_the_current_status(ask: dict[str, Any]) -> None:
    refusal = ask["refusal"]

    assert isinstance(refusal, Conflict)
    assert str(Status.MODELING) in refusal.message
    assert str(Status.VALIDATED) in refusal.message


@given("the same request and an asset that has reached `validated`")
def _the_same_request_and_a_validated_asset(
    ask: dict[str, Any], host: InMemoryRepositoryHost
) -> None:
    ask["asset"] = Asset(id=CRATE, name="Supply Crate", status=Status.VALIDATED)
    ran(record(host, asset=CRATE, assignee=ANA, asked_for_status=Status.VALIDATED))
    ran(move(host, RequestState.ACCEPTED))


@then("the transition SHALL succeed")
def _the_transition_succeeded(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert ran(ask["outcome"]).request.state is RequestState.FULFILLED
    assert ran(read_request(PROJECT, REQUEST, repository_host=host)).state is (
        RequestState.FULFILLED
    )


# --------------------------------------------------------------------------
# Durability, permission, and what a request is not
# --------------------------------------------------------------------------


@given("a request whose persistence to the repository failed")
def _a_request_that_could_not_be_written(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.reject_next_pushes(PROJECT, times=9)
    ask["refusal"] = refused(record(host))


@when("the project's requests are listed")
def _the_requests_are_listed(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["stored"] = host.remote_files(PROJECT)


@then("that request SHALL NOT appear")
def _it_does_not_appear(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert path_for(REQUEST) not in ask["stored"]
    assert refused(read_request(PROJECT, REQUEST, repository_host=host))


@then("its author SHALL have been told it was not recorded")
def _the_author_was_told(ask: dict[str, Any]) -> None:
    assert isinstance(ask["refusal"], Conflict)
    assert ask["refusal"].message


@given("an actor permitted only to read a project")
def _a_reader(ask: dict[str, Any]) -> None:
    ask["actor"] = Actor(id=RAFA, display_name="Rafa", projects=(PROJECT,))


@when("they raise a request")
def _they_raise_a_request(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["decision"] = decide(ask["actor"], Operation.RAISE_REQUEST, Subject(project=PROJECT))
    if ask["decision"].allowed:
        ask["recorded"] = ran(record(host))


@then("it SHALL be recorded")
def _it_was_recorded(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert ask["decision"].allowed
    assert ran(read_request(PROJECT, REQUEST, repository_host=host)) == ask["recorded"].request


@given("an actor who is neither the assignee nor a holder of the responsible role")
def _an_unrelated_actor(ask: dict[str, Any]) -> None:
    ask["actor"] = Actor(id=SAM, display_name="Sam", projects=(PROJECT,))
    ask["subject"] = Subject(project=PROJECT, assignee=ANA, description=f"request {REQUEST}")


@when("they attempt to accept a request")
def _they_attempt_to_accept(ask: dict[str, Any]) -> None:
    ask["decision"] = decide(ask["actor"], Operation.DECIDE_REQUEST, ask["subject"])


@then("the attempt SHALL be refused naming the required role")
def _refused_naming_the_role(ask: dict[str, Any]) -> None:
    decision = ask["decision"]

    assert decision.refused
    assert str(Role.ART_DIRECTOR) in decision.reason


@when("a request is raised, accepted or fulfilled")
def _the_whole_lifecycle_runs(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ask["before"] = dict(host.remote_files(PROJECT))
    ran(record(host, asset=CRATE, assignee=ANA))
    ran(move(host, RequestState.ACCEPTED))
    ran(move(host, RequestState.FULFILLED))
    ask["after"] = dict(host.remote_files(PROJECT))


@then(
    "no constraint, silhouette rule or other durable specification content SHALL be "
    "created or changed by that act alone"
)
def _no_specification_content_changed(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    changed = {path for path, content in ask["after"].items() if ask["before"].get(path) != content}

    assert changed == {path_for(REQUEST)}
    assert ask["after"][SPEC_PATH] == SPEC_CONTENT
    assert {path for commit in host.commits(PROJECT) for path in commit.paths} == {
        path_for(REQUEST)
    }


# --------------------------------------------------------------------------
# Notification never reverses anything (D9)
# --------------------------------------------------------------------------


@given("notification recording is failing")
def _a_failing_notifier(ask: dict[str, Any]) -> None:
    notifier = InMemoryNotifier()
    notifier.fail_with(ConnectionError("the notifier is down"))
    ask["notifier"] = notifier


@when("a request is accepted")
def _a_request_is_accepted(ask: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ran(record(host, assignee=ANA))
    ask["outcome"] = transition_request(
        PROJECT,
        REQUEST,
        RequestState.ACCEPTED,
        actor=ANA,
        repository_host=host,
        author=ANA_GIT,
        notifier=ask["notifier"],
        clock=lambda: LATER,
    )


@then("the acceptance SHALL stand")
def _the_acceptance_stands(host: InMemoryRepositoryHost) -> None:
    assert ran(read_request(PROJECT, REQUEST, repository_host=host)).state is (
        RequestState.ACCEPTED
    )


@then("the caller SHALL NOT receive a failure")
def _the_caller_saw_no_failure(ask: dict[str, Any]) -> None:
    assert succeeded(ask["outcome"])
    assert ask["notifier"].recorded == ()
