"""Tasks 3.1-3.6 — the request lifecycle, pure and with no asset moving under it.

Every rule `asset-requests` states about a request's shape, its transitions, its
assignment and its relationship to the asset lifecycle is decided in
:mod:`cybercanon.domain.requests`, so every test here is a function call with no
store, no clock and no surface. The clock is a parameter for exactly that
reason: the domain does not read one.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.domain import asset as asset_module
from cybercanon.domain import requests as requests_module
from cybercanon.domain import status as status_module
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.identity import ActorId
from cybercanon.domain.requests import (
    AUTHOR_WITHDRAWS,
    NEEDS_DESCRIPTION,
    NEEDS_REASON,
    TRANSITIONS,
    AssetRequest,
    Discipline,
    DisciplineOwners,
    EventKind,
    RefusalKind,
    RequestEvent,
    RequestId,
    RequestState,
    assignee_for,
    link_to_asset,
    may_transition,
    owners_declared_by,
    raise_request,
    reassign,
    transition,
)
from cybercanon.domain.status import Status

RAFA = ActorId("auth|rafa")
ANA = ActorId("auth|ana")
SAM = ActorId("auth|sam")

CRATE = AssetId("crate_01")
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)

WANTED = "a supply crate for the loading dock, one metre cubed"


def a_request(**overrides: object) -> AssetRequest:
    fields: dict[str, object] = {
        "request_id": RequestId("req-001"),
        "author": RAFA,
        "discipline": Discipline.MODELING,
        "description": WANTED,
        "at": NOW,
    }
    fields.update(overrides)
    return raise_request(**fields)  # type: ignore[arg-type]


def accepted(**overrides: object) -> AssetRequest:
    return transition(a_request(**overrides), RequestState.ACCEPTED, actor=ANA, at=LATER)


# --------------------------------------------------------------------------
# 3.1 — the shape of a request
# --------------------------------------------------------------------------


def test_a_request_records_what_is_needed_from_whom_and_by_whom() -> None:
    request = a_request(asset=CRATE)

    assert request.asset == CRATE
    assert request.author == RAFA
    assert request.discipline is Discipline.MODELING
    assert request.state is RequestState.OPEN


def test_a_request_may_name_no_asset_at_all() -> None:
    """The case the capability exists for: an asset that does not exist yet."""
    assert a_request().asset is None


@pytest.mark.parametrize("description", ["", "   ", "\n"])
def test_a_request_with_no_description_is_rejected(description: str) -> None:
    with pytest.raises(ValueError, match=NEEDS_DESCRIPTION):
        a_request(description=description)


def test_raising_records_who_raised_it_and_when() -> None:
    (raised,) = a_request().history

    assert raised.kind is EventKind.RAISED
    assert raised.actor == RAFA
    assert raised.at == NOW


def test_a_request_event_names_an_actor_and_a_time() -> None:
    """No default actor, for the same reason `Attribution` has none (D5)."""
    with pytest.raises(ValueError, match="names the actor"):
        RequestEvent(kind=EventKind.RAISED, actor="rafa", at=NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="when it happened"):
        RequestEvent(kind=EventKind.RAISED, actor=RAFA, at="yesterday")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["", " padded", "has space"])
def test_a_request_id_is_a_non_empty_unpadded_word(value: str) -> None:
    with pytest.raises(ValueError, match="request id"):
        RequestId(value)


def test_a_request_id_renders_as_its_value() -> None:
    assert str(RequestId("req-001")) == "req-001"


def test_linking_to_a_newly_created_asset_changes_only_the_request() -> None:
    linked = link_to_asset(a_request(), CRATE, actor=RAFA, at=LATER)

    assert linked.asset == CRATE
    assert linked.state is RequestState.OPEN
    assert linked.last_event is not None
    assert linked.last_event.kind is EventKind.LINKED


# --------------------------------------------------------------------------
# 3.2 — the transition table
# --------------------------------------------------------------------------


def test_the_table_is_the_lifecycle_the_specification_writes() -> None:
    assert TRANSITIONS[RequestState.OPEN] == frozenset(
        {RequestState.ACCEPTED, RequestState.DECLINED, RequestState.WITHDRAWN}
    )
    assert TRANSITIONS[RequestState.ACCEPTED] == frozenset(
        {RequestState.FULFILLED, RequestState.DECLINED, RequestState.WITHDRAWN}
    )


@pytest.mark.parametrize(
    "state", [RequestState.FULFILLED, RequestState.DECLINED, RequestState.WITHDRAWN]
)
def test_three_states_are_terminal(state: RequestState) -> None:
    assert state.is_terminal


@pytest.mark.parametrize("state", [RequestState.OPEN, RequestState.ACCEPTED])
def test_the_live_states_are_not_terminal(state: RequestState) -> None:
    assert not state.is_terminal


def test_every_disallowed_transition_is_refused() -> None:
    """The whole product of the state set, checked against the table."""
    for origin in RequestState:
        request = AssetRequest(
            id=RequestId("req-001"),
            author=RAFA,
            discipline=Discipline.MODELING,
            description=WANTED,
            state=origin,
        )
        for target in RequestState:
            permitted = target in TRANSITIONS[origin]
            decision = may_transition(request, target, actor=RAFA, reason="because")
            assert decision.allowed is permitted, f"{origin} -> {target}"


def test_fulfilled_never_returns_to_open() -> None:
    fulfilled = transition(accepted(), RequestState.FULFILLED, actor=ANA, at=LATER)

    decision = may_transition(fulfilled, RequestState.OPEN, actor=ANA)

    assert decision.refused
    assert decision.kind is RefusalKind.CONFLICT
    assert fulfilled.state is RequestState.FULFILLED


def test_applying_a_refused_transition_raises_rather_than_applying_it() -> None:
    fulfilled = transition(accepted(), RequestState.FULFILLED, actor=ANA, at=LATER)

    with pytest.raises(ValueError, match="may not become"):
        transition(fulfilled, RequestState.OPEN, actor=ANA, at=LATER)


def test_a_state_is_read_back_from_its_written_form() -> None:
    assert RequestState.from_value("accepted") is RequestState.ACCEPTED
    assert RequestState.from_value("nonsense") is None
    assert RequestState.values()[0] == "open"


def test_a_discipline_is_read_back_from_its_written_form() -> None:
    assert Discipline.from_value(" Modeling ") is Discipline.MODELING
    assert Discipline.from_value("marketing") is None
    assert Discipline.values() == ("design", "art", "modeling", "code")


def test_every_transition_is_attributed_and_timed() -> None:
    declined = transition(
        a_request(), RequestState.DECLINED, actor=ANA, at=LATER, reason="out of scope"
    )

    last = declined.last_event
    assert last is not None
    assert last.kind is EventKind.TRANSITIONED
    assert last.actor == ANA
    assert last.at == LATER
    assert last.reason == "out of scope"


# --------------------------------------------------------------------------
# 3.3 — declining states a reason, and only the author withdraws
# --------------------------------------------------------------------------


def test_declining_without_a_reason_is_refused() -> None:
    decision = may_transition(a_request(), RequestState.DECLINED, actor=ANA)

    assert decision.refused
    assert decision.reason == NEEDS_REASON
    assert decision.kind is RefusalKind.INVALID


def test_declining_with_a_reason_is_permitted() -> None:
    assert may_transition(a_request(), RequestState.DECLINED, actor=ANA, reason="duplicate")


def test_another_person_may_not_withdraw_a_request() -> None:
    decision = may_transition(a_request(), RequestState.WITHDRAWN, actor=ANA)

    assert decision.refused
    assert decision.reason == AUTHOR_WITHDRAWS
    assert decision.kind is RefusalKind.FORBIDDEN


def test_the_author_withdraws_their_own_request() -> None:
    withdrawn = transition(a_request(), RequestState.WITHDRAWN, actor=RAFA, at=LATER)

    assert withdrawn.state is RequestState.WITHDRAWN
    assert withdrawn.is_terminal


# --------------------------------------------------------------------------
# 3.4 — assignment resolution
# --------------------------------------------------------------------------


def test_assignment_follows_the_assets_discipline_owner() -> None:
    on_asset = DisciplineOwners(art=ANA)

    assert assignee_for(Discipline.MODELING, on_asset=on_asset, author=RAFA) == ANA


def test_assignment_falls_back_to_the_projects_discipline_owner() -> None:
    assert (
        assignee_for(
            Discipline.MODELING,
            on_asset=DisciplineOwners(),
            on_project=DisciplineOwners(art=SAM),
            author=RAFA,
        )
        == SAM
    )


def test_the_asset_owner_wins_over_the_project_owner() -> None:
    assert (
        assignee_for(
            Discipline.MODELING,
            on_asset=DisciplineOwners(art=ANA),
            on_project=DisciplineOwners(art=SAM),
            author=RAFA,
        )
        == ANA
    )


def test_no_owner_anywhere_means_unassigned_and_never_the_author() -> None:
    resolved = assignee_for(Discipline.CODE, on_asset=None, on_project=None, author=RAFA)

    assert resolved is None
    assert resolved != RAFA


def test_an_unassigned_request_reports_that_it_needs_an_owner() -> None:
    assert a_request().needs_owner


def test_an_assigned_request_needs_nobody() -> None:
    assert not a_request(assignee=ANA).needs_owner


def test_a_terminal_request_needs_nobody_either() -> None:
    withdrawn = transition(a_request(), RequestState.WITHDRAWN, actor=RAFA, at=LATER)

    assert not withdrawn.needs_owner


@pytest.mark.parametrize(
    ("discipline", "owners", "expected"),
    [
        (Discipline.ART, DisciplineOwners(art=ANA), ANA),
        (Discipline.MODELING, DisciplineOwners(art=ANA), ANA),
        (Discipline.DESIGN, DisciplineOwners(design=SAM), SAM),
        (Discipline.CODE, DisciplineOwners(code=SAM), SAM),
        (Discipline.CODE, DisciplineOwners(art=ANA), None),
    ],
)
def test_each_discipline_reads_the_owner_the_format_declares(
    discipline: Discipline, owners: DisciplineOwners, expected: ActorId | None
) -> None:
    assert owners.owner_of(discipline) == expected


def test_owners_are_resolved_through_the_mapping_and_never_guessed() -> None:
    """An address nobody bound resolves to nobody, which is D8's rule (D14)."""
    asset = Asset(
        id=CRATE,
        name="Supply Crate",
        owner_art="ana@cyberdyne.com",
        owner_code="stranger@elsewhere.io",
    )

    owners = owners_declared_by(asset, {"ana@cyberdyne.com": ANA})

    assert owners.art == ANA
    assert owners.code is None
    assert owners.design is None


def test_reassignment_records_who_reassigned_it_and_when() -> None:
    moved = reassign(a_request(assignee=ANA), SAM, actor=RAFA, at=LATER)

    assert moved.assignee == SAM
    assert moved.last_event is not None
    assert moved.last_event.kind is EventKind.ASSIGNED
    assert moved.last_event.actor == RAFA
    assert moved.last_event.at == LATER


# --------------------------------------------------------------------------
# 3.5 — the fulfilment precondition
# --------------------------------------------------------------------------


def test_fulfilment_is_refused_naming_the_assets_current_status() -> None:
    request = accepted(asset=CRATE, asked_for_status=Status.VALIDATED)

    decision = may_transition(
        request, RequestState.FULFILLED, actor=ANA, asset_status=Status.MODELING
    )

    assert decision.refused
    assert decision.kind is RefusalKind.CONFLICT
    assert str(Status.MODELING) in decision.reason
    assert str(Status.VALIDATED) in decision.reason
    assert str(CRATE) in decision.reason


def test_fulfilment_succeeds_once_the_status_is_reached() -> None:
    request = accepted(asset=CRATE, asked_for_status=Status.VALIDATED)

    fulfilled = transition(
        request, RequestState.FULFILLED, actor=ANA, at=LATER, asset_status=Status.VALIDATED
    )

    assert fulfilled.state is RequestState.FULFILLED


def test_a_request_that_asked_for_no_status_fulfils_without_one() -> None:
    assert may_transition(accepted(), RequestState.FULFILLED, actor=ANA)


def test_an_unknown_asset_status_is_reported_rather_than_assumed() -> None:
    request = accepted(asked_for_status=Status.VALIDATED)

    decision = may_transition(request, RequestState.FULFILLED, actor=ANA, asset_status=None)

    assert decision.refused
    assert "unknown" in decision.reason
    assert "the asset" in decision.reason


# --------------------------------------------------------------------------
# 3.6 — the lifecycles observe each other and drive nothing
# --------------------------------------------------------------------------


def test_a_request_transition_leaves_the_asset_exactly_as_it_was() -> None:
    asset = Asset(id=CRATE, name="Supply Crate", status=Status.MODELING)
    request = accepted(asset=CRATE, asked_for_status=Status.MODELING)

    transition(request, RequestState.FULFILLED, actor=ANA, at=LATER, asset_status=asset.status)

    assert asset.status is Status.MODELING
    assert asset == Asset(id=CRATE, name="Supply Crate", status=Status.MODELING)


def test_advancing_the_assets_status_leaves_the_request_exactly_as_it_was() -> None:
    request = a_request(asset=CRATE)

    advanced = Asset(id=CRATE, name="Supply Crate", status=Status.VALIDATED)

    assert advanced.status is Status.VALIDATED
    assert request.state is RequestState.OPEN
    assert request == a_request(asset=CRATE)


def test_no_request_function_hands_back_an_asset_or_a_status() -> None:
    """Structural, because a behavioural test only covers the paths somebody wrote."""
    returned = {
        name: inspect.signature(member).return_annotation
        for name, member in vars(requests_module).items()
        if inspect.isfunction(member) and not name.startswith("_")
    }

    offenders = {
        name: annotation
        for name, annotation in returned.items()
        if _names_asset_state(str(annotation))
    }
    assert not offenders, f"a request function returns asset state: {offenders}"


def _names_asset_state(annotation: str) -> bool:
    """Whether a return annotation hands back asset state rather than request state."""
    asset = "Asset" in annotation and "AssetRequest" not in annotation
    status = "Status" in annotation and "RequestState" not in annotation
    return asset or status


def test_the_asset_lifecycle_does_not_know_requests_exist() -> None:
    """The other direction of 3.6, and the reason it cannot regress by accident."""
    for module in (asset_module, status_module):
        source = inspect.getsource(module)
        assert "requests" not in source, f"{module.__name__} reaches into the request model"


def test_a_refusal_kind_and_an_event_kind_are_nameable() -> None:
    """Both travel into a record and into a message, so both print as their value."""
    assert str(RefusalKind.CONFLICT) == "conflict"
    assert str(EventKind.TRANSITIONED) == "transitioned"
