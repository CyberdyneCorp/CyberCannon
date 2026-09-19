"""Tasks 4.7, 4.8 and 4.10 — refresh, write-back and rebuild, over the fake host.

Three use cases, and each is tested against the behaviour its specification
sentence promises rather than against the shape of its implementation:

* a refresh advances the served revision and records when it was confirmed, and
  a refresh that could not reach the remote changes neither and leaves the
  project available (`hosted-repository`);
* a write-back applies cleanly, refuses a stale hash, survives a rejected push
  by re-evaluating rather than forcing (D6), and reports a conflict when the
  attempts run out — leaving nothing committed locally;
* a rebuild is an operation over the working copy, and a read never triggers one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.ports.repository_host import ProjectState
from cybercanon.application.results import Conflict, Forbidden, Unavailable
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.hosted_repository import (
    AuthorUnmapped,
    Edit,
    WriteConflict,
    rebuild_project_index,
    refresh_project,
    served_after,
    write_back,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.revisions import ContentHash

PROJECT = "cyberdyne-game"
SPEC = "characters/mech_scout/asset.yaml"
OTHER = "vehicles/mule/asset.yaml"

ORIGINAL = b"schema_version: 1\nid: mech_scout\n"
EDITED = b"schema_version: 1\nid: mech_scout\nstatus: modeling\n"
OUTSIDE = b"schema_version: 1\nid: mech_scout\nstatus: validated\n"
MULE = b"schema_version: 1\nid: mule\n"

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
MESSAGE = "mech_scout: set status to modeling"

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
LATER = NOON + timedelta(hours=1)
INTERVAL = timedelta(minutes=5)


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    """A cloned project holding two specifications."""
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC: ORIGINAL, OTHER: MULE})
    built.clone(PROJECT)
    return built


def an_edit(based_on: bytes | None = ORIGINAL) -> Edit:
    return Edit(
        path=SPEC,
        content=EDITED,
        based_on=ContentHash.of(based_on) if based_on is not None else None,
    )


# --------------------------------------------------------------------------
# 4.7 — refresh_project
# --------------------------------------------------------------------------


def test_a_refresh_advances_the_served_revision_and_records_the_confirmation(
    host: InMemoryRepositoryHost,
) -> None:
    before = host.head(PROJECT)
    host.push_to_remote(PROJECT, SPEC, OUTSIDE)

    outcome = ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(NOON)))

    assert outcome.refreshed
    assert outcome.served.revision != before
    assert outcome.served.confirmed_at == NOON
    assert host.status(PROJECT).served == outcome.served


def test_a_failed_refresh_leaves_the_served_revision_unchanged_and_the_project_available(
    host: InMemoryRepositoryHost,
) -> None:
    """`hosted-repository`: the last good revision keeps answering."""
    before = host.status(PROJECT).served
    host.push_to_remote(PROJECT, SPEC, OUTSIDE)
    host.fail_next_fetch(PROJECT)

    outcome = ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(NOON)))

    assert not outcome.refreshed
    assert outcome.served == before
    assert "unreachable" in outcome.reason
    assert host.status(PROJECT).state is ProjectState.READY


def test_a_failed_refresh_still_serves_the_content_it_had(
    host: InMemoryRepositoryHost,
) -> None:
    host.push_to_remote(PROJECT, SPEC, OUTSIDE)
    host.fail_next_fetch(PROJECT)

    outcome = ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(NOON)))

    assert host.read(PROJECT, SPEC, outcome.served.revision) == ORIGINAL


def test_the_served_revision_after_a_failed_refresh_is_the_previous_one(
    host: InMemoryRepositoryHost,
) -> None:
    previous = host.status(PROJECT).served
    assert previous is not None
    host.fail_next_fetch(PROJECT)

    outcome = ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(NOON)))

    assert served_after(outcome, previous) == previous


def test_staleness_is_arithmetic_over_the_confirmation_time(
    host: InMemoryRepositoryHost,
) -> None:
    """Surfaced rather than hidden: the response carries what a reader needs."""
    outcome = ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(NOON)))

    assert not outcome.may_be_stale(NOON + INTERVAL, INTERVAL)
    assert outcome.may_be_stale(LATER, INTERVAL)


def test_a_project_that_is_not_ready_is_reported_rather_than_refreshed() -> None:
    not_cloned = InMemoryRepositoryHost()
    not_cloned.add_project(PROJECT, {SPEC: ORIGINAL})

    outcome = refused(refresh_project(PROJECT, repository_host=not_cloned))

    assert isinstance(outcome, Unavailable)
    assert "provisioning" in outcome.message


# --------------------------------------------------------------------------
# 4.8 — write_back
# --------------------------------------------------------------------------


def test_a_clean_edit_becomes_one_pushed_commit(host: InMemoryRepositoryHost) -> None:
    written = ran(
        write_back(PROJECT, [an_edit()], repository_host=host, author=RAFA, message=MESSAGE)
    )

    assert written.attempts == 1
    assert written.paths == (SPEC,)
    assert written.commit.author == RAFA
    assert host.remote_files(PROJECT)[SPEC] == EDITED
    assert host.unpushed(PROJECT) == ()


def test_an_edit_composed_against_stale_content_is_refused_as_conflicting(
    host: InMemoryRepositoryHost,
) -> None:
    """D5's precondition, per file, by the digest the edit was composed against."""
    host.push_to_remote(PROJECT, SPEC, OUTSIDE)
    host.fetch(PROJECT, confirmed_at=NOON)

    outcome = refused(
        write_back(PROJECT, [an_edit()], repository_host=host, author=RAFA, message=MESSAGE)
    )

    assert isinstance(outcome, Conflict)
    assert outcome.identifier == WriteConflict.identifier
    assert outcome.subject == SPEC
    assert host.remote_files(PROJECT)[SPEC] == OUTSIDE


def test_an_edit_that_asserts_a_new_file_conflicts_when_one_is_there(
    host: InMemoryRepositoryHost,
) -> None:
    outcome = refused(
        write_back(
            PROJECT,
            [Edit(path=SPEC, content=EDITED, based_on=None)],
            repository_host=host,
            author=RAFA,
            message=MESSAGE,
        )
    )

    assert isinstance(outcome, Conflict)


def test_a_new_file_is_written_when_nothing_is_there(host: InMemoryRepositoryHost) -> None:
    written = ran(
        write_back(
            PROJECT,
            [Edit(path="props/crate/asset.yaml", content=b"id: crate\n", based_on=None)],
            repository_host=host,
            author=RAFA,
            message="crate: created",
        )
    )

    assert written.paths == ("props/crate/asset.yaml",)


def test_a_rejected_push_is_retried_against_the_new_tip_and_succeeds(
    host: InMemoryRepositoryHost,
) -> None:
    """D6: if their commit did not touch this file, the retry succeeds invisibly."""
    host.reject_next_pushes(PROJECT, times=1)

    written = ran(
        write_back(PROJECT, [an_edit()], repository_host=host, author=RAFA, message=MESSAGE)
    )

    assert written.attempts == 2
    assert host.remote_files(PROJECT)[SPEC] == EDITED


def test_exhausting_the_attempts_is_reported_as_a_conflict(
    host: InMemoryRepositoryHost,
) -> None:
    """Reporting a false conflict is safe; forcing is not."""
    host.reject_next_pushes(PROJECT, times=5)

    outcome = refused(
        write_back(
            PROJECT,
            [an_edit()],
            repository_host=host,
            author=RAFA,
            message=MESSAGE,
            attempts=3,
        )
    )

    assert isinstance(outcome, Conflict)
    assert "3 attempts" in outcome.message


def test_an_exhausted_write_leaves_no_local_only_commit(
    host: InMemoryRepositoryHost,
) -> None:
    host.reject_next_pushes(PROJECT, times=5)

    refused(
        write_back(
            PROJECT, [an_edit()], repository_host=host, author=RAFA, message=MESSAGE, attempts=2
        )
    )

    assert host.unpushed(PROJECT) == ()
    assert host.remote_files(PROJECT)[SPEC] == ORIGINAL


def test_an_unmapped_person_is_refused_naming_the_missing_mapping(
    host: InMemoryRepositoryHost,
) -> None:
    """D8: no mapping, no write — and never a commit under a service identity."""
    outcome = refused(
        write_back(
            PROJECT,
            [an_edit()],
            repository_host=host,
            author=None,
            message=MESSAGE,
            subject="auth|newcomer",
        )
    )

    assert isinstance(outcome, Forbidden)
    assert outcome.identifier == AuthorUnmapped.identifier
    assert ".canon/actors.yaml" in outcome.message
    assert "auth|newcomer" in outcome.message
    assert host.commits(PROJECT) == ()


def test_an_edit_that_changes_nothing_is_refused(host: InMemoryRepositoryHost) -> None:
    assert refused(write_back(PROJECT, [], repository_host=host, author=RAFA, message=MESSAGE))


def test_two_edits_to_different_files_are_one_commit(host: InMemoryRepositoryHost) -> None:
    """One *logical* edit is one commit, however many files it touches (D2)."""
    written = ran(
        write_back(
            PROJECT,
            [
                an_edit(),
                Edit(
                    path=OTHER,
                    content=b"id: mule\nstatus: concept\n",
                    based_on=ContentHash.of(MULE),
                ),
            ],
            repository_host=host,
            author=RAFA,
            message=MESSAGE,
        )
    )

    assert len(host.commits(PROJECT)) == 1
    assert set(written.paths) == {SPEC, OTHER}


# --------------------------------------------------------------------------
# 4.10 — rebuild_project_index
# --------------------------------------------------------------------------


def a_store() -> InMemorySpecStore:
    store = InMemorySpecStore()
    store.add(SPEC, Asset(id=AssetId("mech_scout"), name="Scout Mech"))
    store.add(OTHER, Asset(id=AssetId("mule"), name="Mule Hauler"))
    return store


def test_a_rebuild_reads_the_working_copy_at_the_revision_it_serves(
    host: InMemoryRepositoryHost,
) -> None:
    store = a_store()
    store.snapshot(host.head(PROJECT).value)
    index = InMemorySearchIndex()

    report = ran(
        rebuild_project_index(PROJECT, repository_host=host, spec_store=store, search_index=index)
    )

    assert report.indexed_count == 2
    assert {entry.asset_id for entry in index.list_assets()} == {"mech_scout", "mule"}


def test_a_rebuild_of_a_project_that_is_not_ready_is_refused() -> None:
    not_cloned = InMemoryRepositoryHost()
    not_cloned.add_project(PROJECT, {SPEC: ORIGINAL})

    outcome = refused(
        rebuild_project_index(
            PROJECT,
            repository_host=not_cloned,
            spec_store=a_store(),
            search_index=InMemorySearchIndex(),
        )
    )

    assert isinstance(outcome, Unavailable)


def test_a_rebuild_cannot_observe_content_added_after_its_revision(
    host: InMemoryRepositoryHost,
) -> None:
    """The isolation D3 gives every read, applied to the one that reads everything."""
    store = a_store()
    store.snapshot(host.head(PROJECT).value)
    store.add("props/crate/asset.yaml", Asset(id=AssetId("crate"), name="Supply Crate"))
    index = InMemorySearchIndex()

    report = ran(
        rebuild_project_index(PROJECT, repository_host=host, spec_store=store, search_index=index)
    )

    assert report.indexed_count == 2
