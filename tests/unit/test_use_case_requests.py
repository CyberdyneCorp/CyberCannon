"""Tasks 4.6 and 4.9 — requests as repository content, and notification that cannot bite.

Every assertion here is one of D7's consequences or one of `asset-requests`'
sentences:

* **exactly one commit per operation**, authored by the acting person — which is
  what makes the whole lifecycle reconstructible from the repository alone;
* **the round trip is lossless** — state, assignee and attribution survive being
  written and read back, which is the index-rebuild guarantee for requests
  stated at the level where it can actually be checked;
* **nothing about an asset is written** by any of it;
* **an unmapped person cannot even accept** (D7's sharper accepted cost, D8);
* **a notifier that is down changes no outcome** (D9), verified against a
  notifier that is actually down.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.application.ports.notifier import Notification, notify_quietly
from cybercanon.application.results import Conflict, Forbidden, Invalid, NotFound
from cybercanon.application.testing.notifier import InMemoryNotifier
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.use_cases.requests import (
    REQUESTS_DIR,
    RequestNotFound,
    RequestUnreadable,
    assign_request,
    from_document,
    path_for,
    raise_request,
    read_request,
    to_document,
    transition_request,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import AssetId
from cybercanon.domain.identity import ActorId
from cybercanon.domain.requests import (
    AUTHOR_WITHDRAWS,
    NEEDS_REASON,
    AssetRequest,
    Discipline,
    RequestId,
    RequestState,
)
from cybercanon.domain.requests import raise_request as build_request
from cybercanon.domain.status import Status

PROJECT = "cyberdyne-game"
SPEC = "characters/mech_scout/asset.yaml"

RAFA = ActorId("auth|rafa")
ANA = ActorId("auth|ana")

RAFA_GIT = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
ANA_GIT = GitAuthor(name="Ana", email="ana@cyberdyne.com")

REQUEST = RequestId("req-0001")
CRATE = AssetId("crate_01")
WANTED = "a supply crate for the loading dock"

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
LATER = NOON + timedelta(hours=1)


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC: b"schema_version: 1\nid: mech_scout\n"})
    built.clone(PROJECT)
    return built


@pytest.fixture
def notifier() -> InMemoryNotifier:
    return InMemoryNotifier()


def a_request(**overrides: object) -> AssetRequest:
    fields: dict[str, object] = {
        "request_id": REQUEST,
        "author": RAFA,
        "discipline": Discipline.MODELING,
        "description": WANTED,
        "at": NOON,
        "assignee": ANA,
    }
    fields.update(overrides)
    return build_request(**fields)  # type: ignore[arg-type]


def raised(
    host: InMemoryRepositoryHost, notifier: InMemoryNotifier | None = None, **overrides: object
):
    return ran(
        raise_request(
            PROJECT,
            a_request(**overrides),
            repository_host=host,
            author=RAFA_GIT,
            notifier=notifier,
            clock=lambda: NOON,
        )
    )


# --------------------------------------------------------------------------
# 4.9 — one commit per operation, attributed
# --------------------------------------------------------------------------


def test_raising_a_request_produces_exactly_one_commit_by_the_acting_person(
    host: InMemoryRepositoryHost,
) -> None:
    recorded = raised(host)

    (commit,) = host.commits(PROJECT)
    assert commit.author == RAFA_GIT
    assert commit.paths == (path_for(REQUEST),)
    assert recorded.path == f"{REQUESTS_DIR}/{REQUEST}.json"


def test_a_commit_message_names_the_request_and_what_changed(
    host: InMemoryRepositoryHost,
) -> None:
    raised(host, asset=CRATE)

    (commit,) = host.commits(PROJECT)
    assert str(REQUEST) in commit.message
    assert str(CRATE) in commit.message
    assert "raised" in commit.message


def test_each_transition_is_one_more_commit_by_whoever_caused_it(
    host: InMemoryRepositoryHost,
) -> None:
    raised(host)

    ran(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.ACCEPTED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            clock=lambda: LATER,
        )
    )

    first, second = host.commits(PROJECT)
    assert first.author == RAFA_GIT
    assert second.author == ANA_GIT


def test_reassignment_is_one_commit_and_records_who_did_it(
    host: InMemoryRepositoryHost,
) -> None:
    raised(host)

    recorded = ran(
        assign_request(
            PROJECT,
            REQUEST,
            RAFA,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            clock=lambda: LATER,
        )
    )

    assert recorded.request.assignee == RAFA
    assert recorded.request.last_event is not None
    assert recorded.request.last_event.actor == ANA
    assert recorded.request.last_event.at == LATER
    assert len(host.commits(PROJECT)) == 2


def test_a_request_is_read_back_from_the_repository_unchanged(
    host: InMemoryRepositoryHost,
) -> None:
    """The index-rebuild guarantee, at the level where it can be checked."""
    recorded = raised(host, asset=CRATE, asked_for_status=Status.VALIDATED)

    assert ran(read_request(PROJECT, REQUEST, repository_host=host)) == recorded.request


def test_a_full_lifecycle_survives_being_written_and_read_back(
    host: InMemoryRepositoryHost,
) -> None:
    raised(host)
    ran(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.ACCEPTED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            clock=lambda: LATER,
        )
    )
    ran(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.FULFILLED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            clock=lambda: LATER,
        )
    )

    stored = ran(read_request(PROJECT, REQUEST, repository_host=host))
    assert stored.state is RequestState.FULFILLED
    assert stored.assignee == ANA
    assert [event.actor for event in stored.history] == [RAFA, ANA, ANA]
    assert len(host.commits(PROJECT)) == 3


def test_no_request_operation_writes_anything_about_an_asset(
    host: InMemoryRepositoryHost,
) -> None:
    """*"A request is not a constraint"* — and the commits are the evidence."""
    raised(host, asset=CRATE)
    ran(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.ACCEPTED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            clock=lambda: LATER,
        )
    )

    touched = {path for commit in host.commits(PROJECT) for path in commit.paths}
    assert touched == {path_for(REQUEST)}
    assert host.remote_files(PROJECT)[SPEC] == b"schema_version: 1\nid: mech_scout\n"


def test_a_domain_refusal_reaches_the_caller_with_the_kind_the_domain_gave_it(
    host: InMemoryRepositoryHost,
) -> None:
    raised(host)

    declined = refused(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.DECLINED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
        )
    )
    withdrawn = refused(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.WITHDRAWN,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
        )
    )

    assert isinstance(declined, Invalid)
    assert declined.message == NEEDS_REASON
    assert isinstance(withdrawn, Forbidden)
    assert withdrawn.message == AUTHOR_WITHDRAWS


def test_a_refused_transition_writes_nothing(host: InMemoryRepositoryHost) -> None:
    raised(host)

    refused(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.DECLINED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
        )
    )

    assert len(host.commits(PROJECT)) == 1


def test_fulfilment_is_refused_against_the_assets_current_status(
    host: InMemoryRepositoryHost,
) -> None:
    raised(host, asset=CRATE, asked_for_status=Status.VALIDATED)
    ran(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.ACCEPTED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            clock=lambda: LATER,
        )
    )

    outcome = refused(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.FULFILLED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            asset_status=Status.MODELING,
        )
    )

    assert isinstance(outcome, Conflict)
    assert str(Status.MODELING) in outcome.message


def test_an_unmapped_person_cannot_even_accept(host: InMemoryRepositoryHost) -> None:
    """D7's sharper cost, accepted deliberately: no mapping, no workflow record."""
    raised(host)

    outcome = refused(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.ACCEPTED,
            actor=ANA,
            repository_host=host,
            author=None,
        )
    )

    assert isinstance(outcome, Forbidden)
    assert ".canon/actors.yaml" in outcome.message
    assert len(host.commits(PROJECT)) == 1


def test_a_request_nobody_recorded_is_not_found(host: InMemoryRepositoryHost) -> None:
    outcome = refused(read_request(PROJECT, RequestId("req-9999"), repository_host=host))

    assert isinstance(outcome, NotFound)
    assert outcome.identifier == RequestNotFound.identifier


def test_a_request_whose_commit_did_not_land_does_not_appear(
    host: InMemoryRepositoryHost,
) -> None:
    """*"A request that could not be persisted did not happen."*"""
    host.reject_next_pushes(PROJECT, times=9)

    outcome = refused(
        raise_request(
            PROJECT,
            a_request(),
            repository_host=host,
            author=RAFA_GIT,
            clock=lambda: NOON,
        )
    )

    assert isinstance(outcome, Conflict)
    assert refused(read_request(PROJECT, REQUEST, repository_host=host))


# --------------------------------------------------------------------------
# The document (D7)
# --------------------------------------------------------------------------


def test_the_document_round_trips_every_field() -> None:
    request = a_request(asset=CRATE, asked_for_status=Status.VALIDATED)

    assert from_document(to_document(request)) == request


def test_the_document_round_trips_a_request_with_nothing_optional_set() -> None:
    request = a_request(asset=None, assignee=None)

    assert from_document(to_document(request)) == request


def test_the_document_is_deterministic() -> None:
    """A renderer that reordered fields would make the history unreadable."""
    request = a_request()

    assert to_document(request) == to_document(request)
    assert to_document(request).endswith(b"\n")


def test_a_hand_broken_document_is_reported_rather_than_guessed() -> None:
    outcome = refused(_as_result(lambda: from_document(b"{not json", path_for(REQUEST))))

    assert outcome.identifier == RequestUnreadable.identifier


def _as_result(operation):
    from cybercanon.application.results import attempt

    return attempt(operation)


# --------------------------------------------------------------------------
# 4.6 — notification never changes an outcome (D9)
# --------------------------------------------------------------------------


def test_the_assignee_and_the_author_are_both_told(
    host: InMemoryRepositoryHost, notifier: InMemoryNotifier
) -> None:
    raised(host, notifier=notifier)

    assert {item.recipient for item in notifier.recorded} == {RAFA, ANA}
    assert all(item.subject == str(REQUEST) for item in notifier.recorded)


def test_an_acceptance_stands_while_the_notifier_is_failing(
    host: InMemoryRepositoryHost, notifier: InMemoryNotifier
) -> None:
    """`asset-requests`: the acceptance stands and the caller sees no failure."""
    raised(host)
    notifier.fail_with(ConnectionError("the notifier is down"))

    recorded = ran(
        transition_request(
            PROJECT,
            REQUEST,
            RequestState.ACCEPTED,
            actor=ANA,
            repository_host=host,
            author=ANA_GIT,
            notifier=notifier,
            clock=lambda: LATER,
        )
    )

    assert recorded.request.state is RequestState.ACCEPTED
    assert ran(read_request(PROJECT, REQUEST, repository_host=host)).state is RequestState.ACCEPTED


def test_a_failing_notifier_says_so_without_raising() -> None:
    notifier = InMemoryNotifier()
    notifier.fail_with(RuntimeError("down"))

    assert not notify_quietly(notifier, _a_notification())


def test_no_notifier_at_all_is_not_a_failure() -> None:
    """A container wired without one records nothing and refuses nothing."""
    assert not notify_quietly(None, _a_notification())


def test_a_working_notifier_records_and_says_so() -> None:
    notifier = InMemoryNotifier()

    assert notify_quietly(notifier, _a_notification())
    assert notifier.for_actor(ANA) == notifier.recorded


def _a_notification() -> Notification:
    return Notification(recipient=ANA, subject=str(REQUEST), summary="a crate", at=NOON)
