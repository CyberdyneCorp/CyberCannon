"""Task 6.4 — no durable content reaches only the index.

`hosted-repository` states it as a scenario: *"WHEN any durable content is
created or changed through the service THEN it SHALL be written to the
repository AND it SHALL survive a full index rebuild."* That is not a property
of any one use case, so asserting it on the three that exist today would leave
the fourth free to break it. This module enumerates instead.

Two enumerations, failing in opposite directions:

* :data:`WRITES` names, for every mutating operation in the domain's matrix, the
  use case that performs it — and :data:`AWAITING_A_CHANGE` names the ones no
  change has built yet, each with the change that will. A test asserts the two
  together are exactly :data:`~cybercanon.domain.policy.MUTATING`, so the day a
  write use case arrives the build fails until somebody says which operation it
  performs.
* Every entry in :data:`WRITES` is then exercised: it produces **exactly one
  commit**, and it produces that commit **without an index**. The second is the
  structural half and it is the stronger one — a use case that cannot reach the
  index cannot write to it, whatever anybody later adds to its body.

The index is not mocked here; it is *absent*. That is the cleanest statement of
the rule: these use cases take a `RepositoryHost` and do not take a
`SearchIndex`, so there is no argument through which a write could reach one.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

import pytest

from cybercanon.application.results import Result
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.use_cases import requests as request_writes
from cybercanon.application.use_cases.hosted_repository import write_back
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.identity import ActorId
from cybercanon.domain.policy import MUTATING, Operation
from cybercanon.domain.requests import (
    AssetRequest,
    Discipline,
    RequestId,
    RequestState,
)
from cybercanon.domain.requests import (
    raise_request as build_request,
)

PROJECT = "cyberdyne-game"
SPEC = "characters/mech_scout/asset.yaml"
SPEC_CONTENT = b"schema_version: 1\nid: mech_scout\n"

RAFA = ActorId("auth|rafa")
ANA = ActorId("auth|ana")
RAFA_GIT = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")

REQUEST = RequestId("req-0001")
NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

AWAITING_A_CHANGE: Mapping[Operation, str] = {
    Operation.CREATE_ANNOTATION: "add-model-sheet-2d",
    Operation.REPLY_IN_THREAD: "add-model-sheet-2d",
    Operation.RESOLVE_ISSUE: "add-model-sheet-2d",
    Operation.PROMOTE_TO_RULE: "add-model-sheet-2d",
    Operation.ACCEPT_SUGGESTED_ALIAS: "add-derived-metadata",
    Operation.TRANSITION_ASSET_STATUS: "add-model-sheet-2d",
}
"""Mutating operations no change has built a use case for yet, and which will.

Named rather than omitted. An operation that is simply missing from both tables
is indistinguishable from one somebody forgot, and this rule is exactly the kind
that is broken by forgetting.
"""


def _raise(host: InMemoryRepositoryHost) -> Result:
    return request_writes.raise_request(
        PROJECT,
        _a_request(),
        repository_host=host,
        author=RAFA_GIT,
        clock=lambda: NOON,
    )


def _decide(host: InMemoryRepositoryHost) -> Result:
    ran(_raise(host))
    return request_writes.transition_request(
        PROJECT,
        REQUEST,
        RequestState.ACCEPTED,
        actor=ANA,
        repository_host=host,
        author=RAFA_GIT,
        clock=lambda: NOON,
    )


WRITES: Mapping[Operation, Callable[[InMemoryRepositoryHost], Result]] = {
    Operation.RAISE_REQUEST: _raise,
    Operation.DECIDE_REQUEST: _decide,
}
"""Every mutating operation a use case exists for, and how to perform one."""

COMMITS_PER_OPERATION = {Operation.RAISE_REQUEST: 1, Operation.DECIDE_REQUEST: 2}
"""How many commits each scenario above leaves — deciding has to raise first."""


def _a_request(**overrides: object) -> AssetRequest:
    fields: dict[str, object] = {
        "request_id": REQUEST,
        "author": RAFA,
        "discipline": Discipline.MODELING,
        "description": "a supply crate for the loading dock",
        "at": NOON,
        "assignee": ANA,
    }
    fields.update(overrides)
    return build_request(**fields)  # type: ignore[arg-type]


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC: SPEC_CONTENT})
    built.clone(PROJECT)
    return built


# --------------------------------------------------------------------------
# The enumeration is complete, and stays complete
# --------------------------------------------------------------------------


def test_every_mutating_operation_is_either_built_or_declared_pending() -> None:
    """A new write use case fails this until somebody says what it performs."""
    declared = set(WRITES) | set(AWAITING_A_CHANGE)

    assert declared == set(MUTATING), {
        "unclassified": sorted(str(op) for op in set(MUTATING) - declared),
        "not in the matrix": sorted(str(op) for op in declared - set(MUTATING)),
    }


def test_nothing_is_both_built_and_pending() -> None:
    assert not set(WRITES) & set(AWAITING_A_CHANGE)


# --------------------------------------------------------------------------
# Each write produces a repository commit — and cannot reach an index
# --------------------------------------------------------------------------


@pytest.mark.parametrize("operation", sorted(WRITES, key=str), ids=str)
def test_the_write_produces_a_repository_commit(
    operation: Operation, host: InMemoryRepositoryHost
) -> None:
    ran(WRITES[operation](host))

    assert len(host.commits(PROJECT)) == COMMITS_PER_OPERATION[operation]


@pytest.mark.parametrize("operation", sorted(WRITES, key=str), ids=str)
def test_the_written_content_is_on_the_remote_not_only_in_the_working_copy(
    operation: Operation, host: InMemoryRepositoryHost
) -> None:
    """An edit is not applied until it is in the repository, and pushed."""
    ran(WRITES[operation](host))

    assert request_writes.path_for(REQUEST) in host.remote_files(PROJECT)
    assert host.unpushed(PROJECT) == ()


@pytest.mark.parametrize("operation", sorted(WRITES, key=str), ids=str)
def test_the_write_completes_with_no_index_anywhere_in_reach(
    operation: Operation, host: InMemoryRepositoryHost
) -> None:
    """The structural half: there is no argument a write could reach an index by."""
    outcome = WRITES[operation](host)

    ran(outcome)
    assert "search_index" not in _parameters(WRITES[operation])


@pytest.mark.parametrize(
    "use_case",
    [
        write_back,
        request_writes.raise_request,
        request_writes.assign_request,
        request_writes.transition_request,
    ],
    ids=lambda case: case.__name__,
)
def test_no_write_use_case_accepts_a_search_index(use_case: object) -> None:
    """Every writing use case takes a repository host and never an index."""
    parameters = _parameters(use_case)

    assert "repository_host" in parameters
    assert "search_index" not in parameters


def _parameters(target: object) -> frozenset[str]:
    """The names a callable accepts, following the use-case wrapper to its body."""
    body = getattr(target, "raising", target)
    return frozenset(inspect.signature(body).parameters)
