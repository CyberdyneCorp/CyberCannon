"""Tasks 2.5 and 2.6 — freshness, and the difference between a fetch and a try.

Two properties, and the second is the one that is easy to get wrong:

* **the index is compared to the working copy, with both revisions named.** An
  index built from `r1` while the copy has moved to `r2` is stale, and saying so
  without saying which two revisions is a status nobody can act on;
* **the last successful fetch and the most recent attempt are different facts.**
  `hosted-repository` requires a failed refresh to leave the served revision and
  its confirmation time exactly where they were. That is correct, and it means a
  deployment whose fetches have failed all day looks identical to one nobody has
  pushed to — unless the attempt is recorded separately. It is.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cybercanon.application.ports.repository_host import ProjectState
from cybercanon.application.results import Ok
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.use_cases.deployment_status import (
    DeploymentJournal,
    describe_project,
    refresh_and_record,
)

PROJECT = "cyberdyne-game"
OTHER = "ironwood"
SPEC = "characters/mech_scout/asset.yaml"

START = datetime(2026, 9, 19, 9, 0, tzinfo=UTC)


class _Clock:
    """A clock that moves a minute every time somebody reads it."""

    def __init__(self, start: datetime = START) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(minutes=1)
        return self.now


def _host(*projects: str) -> InMemoryRepositoryHost:
    host = InMemoryRepositoryHost(now=START)
    for project in projects:
        host.add_project(project, {SPEC: b"id: mech_scout\n"})
        host.clone(project)
    return host


# --------------------------------------------------------------------------
# 2.5 — the index against the working copy
# --------------------------------------------------------------------------


def test_an_index_built_from_the_current_revision_is_in_sync() -> None:
    host = _host(PROJECT)
    journal = DeploymentJournal()
    journal.built(PROJECT, host.head(PROJECT).value)

    report = describe_project(PROJECT, repository_host=host, journal=journal)

    assert report.index.in_sync
    assert report.index.indexed_revision == report.index.working_copy_revision


def test_advancing_the_working_copy_without_rebuilding_reports_both_revisions() -> None:
    host = _host(PROJECT)
    journal = DeploymentJournal()
    indexed = host.head(PROJECT).value
    journal.built(PROJECT, indexed)

    host.push_to_remote(PROJECT, SPEC, b"id: mech_scout\nname: Scout\n")
    host.fetch(PROJECT, confirmed_at=START + timedelta(minutes=5))
    report = describe_project(PROJECT, repository_host=host, journal=journal)

    assert not report.index.in_sync
    assert report.index.indexed_revision == indexed
    assert report.index.working_copy_revision == host.head(PROJECT).value
    assert report.index.indexed_revision != report.index.working_copy_revision


def test_an_index_that_was_never_built_is_not_in_sync() -> None:
    """Nothing to compare is not the same as a match, and must not read as one."""
    report = describe_project(PROJECT, repository_host=_host(PROJECT), journal=DeploymentJournal())

    assert not report.index.in_sync
    assert report.index.indexed_revision == ""


def test_a_rebuild_in_progress_is_reported_as_such() -> None:
    journal = DeploymentJournal()
    journal.building(PROJECT)

    report = describe_project(PROJECT, repository_host=_host(PROJECT), journal=journal)

    assert report.index.rebuilding
    assert not describe_project(
        PROJECT, repository_host=_host(PROJECT), journal=DeploymentJournal()
    ).index.rebuilding


# --------------------------------------------------------------------------
# 2.6 — the attempt is not the success
# --------------------------------------------------------------------------


def test_a_successful_fetch_moves_both_the_success_and_the_attempt() -> None:
    host = _host(PROJECT)
    journal = DeploymentJournal()
    clock = _Clock()

    assert isinstance(
        refresh_and_record(PROJECT, repository_host=host, journal=journal, clock=clock), Ok
    )
    report = describe_project(PROJECT, repository_host=host, journal=journal)

    assert report.working_copy.attempt is not None
    assert report.working_copy.attempt.succeeded
    assert report.working_copy.last_fetch_at == report.working_copy.attempt.at


def test_consecutive_failures_leave_the_last_success_where_it_was() -> None:
    host = _host(PROJECT)
    journal = DeploymentJournal()
    clock = _Clock()
    refresh_and_record(PROJECT, repository_host=host, journal=journal, clock=clock)
    succeeded_at = describe_project(
        PROJECT, repository_host=host, journal=journal
    ).working_copy.last_fetch_at

    host.fail_next_fetch(PROJECT, times=3)
    for _ in range(3):
        refresh_and_record(PROJECT, repository_host=host, journal=journal, clock=clock)
    report = describe_project(PROJECT, repository_host=host, journal=journal)

    assert report.working_copy.last_fetch_at == succeeded_at
    assert report.working_copy.attempt is not None
    assert not report.working_copy.attempt.succeeded
    assert report.working_copy.attempt.at > succeeded_at
    assert report.working_copy.attempt.reason == "the remote is unreachable"
    assert report.working_copy.fetching == "failed"


def test_a_failing_fetch_keeps_serving_the_last_good_revision() -> None:
    """The half `hosted-repository` already required, restated where it is observed."""
    host = _host(PROJECT)
    journal = DeploymentJournal()
    revision = host.head(PROJECT).value

    host.fail_next_fetch(PROJECT, times=2)
    refresh_and_record(PROJECT, repository_host=host, journal=journal, clock=_Clock())
    report = describe_project(PROJECT, repository_host=host, journal=journal)

    assert report.working_copy.revision == revision
    assert report.working_copy.reachable


def test_nothing_attempted_yet_is_reported_as_nothing_attempted() -> None:
    report = describe_project(PROJECT, repository_host=_host(PROJECT), journal=DeploymentJournal())

    assert report.working_copy.attempt is None
    assert report.working_copy.fetching == "none"


# --------------------------------------------------------------------------
# Per project, and a working copy that is simply not there
# --------------------------------------------------------------------------


def test_each_project_carries_its_own_revision_and_fetch_times() -> None:
    host = _host(PROJECT, OTHER)
    journal = DeploymentJournal()
    clock = _Clock()
    refresh_and_record(PROJECT, repository_host=host, journal=journal, clock=clock)
    host.push_to_remote(OTHER, SPEC, b"id: other\n")
    host.fail_next_fetch(OTHER)
    refresh_and_record(OTHER, repository_host=host, journal=journal, clock=clock)

    one = describe_project(PROJECT, repository_host=host, journal=journal)
    two = describe_project(OTHER, repository_host=host, journal=journal)

    assert one.working_copy.revision != two.working_copy.revision
    assert one.working_copy.attempt is not None and one.working_copy.attempt.succeeded
    assert two.working_copy.attempt is not None and not two.working_copy.attempt.succeeded


def test_a_working_copy_that_cannot_be_reached_is_reported_unavailable() -> None:
    class Lost:
        def status(self, project: str):
            raise OSError(f"/data/worktrees/{project}: no such file or directory")

    report = describe_project(PROJECT, repository_host=Lost(), journal=DeploymentJournal())

    assert report.working_copy.state is ProjectState.UNAVAILABLE
    assert not report.working_copy.reachable
    assert "no such file" in report.working_copy.reason
