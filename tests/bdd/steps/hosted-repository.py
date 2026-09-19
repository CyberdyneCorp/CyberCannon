"""Step definitions for `hosted-repository` — the working copy, from group 4.

Group 4 builds the port and the use cases: `RepositoryHost` (clone, fetch,
resolve, read at a revision, commit as an author, push, recover),
`refresh_project`, and `write_back` with D5's per-file precondition and D6's
bounded retry. Everything bound here is answerable by that code against the
in-memory host, which is the point of having a port at all — the isolation D3
gives a read is a property of *holding a revision*, not of any particular git
invocation, so a fake that models a remote, a working copy and an unpushed queue
exercises it exactly.

The scenarios still in `tests/bdd/pending.txt` are the ones that need the real
`GitRepositoryHost` and the surfaces over it, which are groups 5 to 9: the
webhook, the staleness stated on a specification read, provisioning reported to
a listing, recovery of a deleted working copy on disk, and the index guarantees
that need an index.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.ports.repository_host import FileChange, ProjectState
from cybercanon.application.results import Conflict, Forbidden, succeeded
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.hosted_repository import Edit, refresh_project, write_back
from cybercanon.application.use_cases.lookup_assets import list_assets
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.revisions import ContentHash

PROJECT = "cyberdyne-game"
SCOUT = "characters/mech_scout/asset.yaml"
MULE = "vehicles/mule/asset.yaml"

SCOUT_CONTENT = b"schema_version: 1\nid: mech_scout\nstatus: concept\n"
MULE_CONTENT = b"schema_version: 1\nid: mule\nstatus: concept\n"

RAFA_EDIT = b"schema_version: 1\nid: mech_scout\nstatus: modeling\n"
ANA_EDIT = b"schema_version: 1\nid: mech_scout\nstatus: approved\n"
OUTSIDE = b"schema_version: 1\nid: mech_scout\nstatus: validated\n"
MULE_EDIT = b"schema_version: 1\nid: mule\nstatus: modeling\n"

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
ANA = GitAuthor(name="Ana", email="ana@cyberdyne.com")

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
LATER = NOON + timedelta(hours=1)

MESSAGE = "mech_scout: set status to modeling"


@pytest.fixture
def copy() -> dict[str, Any]:
    """What this scenario staged, and what the working copy answered."""
    return {}


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    """A cloned project holding two specifications."""
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SCOUT: SCOUT_CONTENT, MULE: MULE_CONTENT})
    built.clone(PROJECT)
    return built


def an_edit(path: str = SCOUT, content: bytes = RAFA_EDIT, based_on: bytes = SCOUT_CONTENT):
    return Edit(path=path, content=content, based_on=ContentHash.of(based_on))


def written(
    host: InMemoryRepositoryHost, edit: Edit, author: GitAuthor | None = RAFA, **extra: Any
):
    return write_back(
        PROJECT, [edit], repository_host=host, author=author, message=MESSAGE, **extra
    )


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "An edit not in the repository is not applied",
)
def test_an_edit_not_in_the_repository_is_not_applied() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Rebuild is an operation, not a side effect",
)
def test_rebuild_is_an_operation_not_a_side_effect() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Rejected credential is reported with its reason",
)
def test_rejected_credential_is_reported_with_its_reason() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Scheduled refresh covers a missed notification",
)
def test_scheduled_refresh_covers_a_missed_notification() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "A failed refresh keeps the last good revision",
)
def test_a_failed_refresh_keeps_the_last_good_revision() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "No partial tree is ever observed"
)
def test_no_partial_tree_is_ever_observed() -> None: ...


@scenario("../features/add-web-backend/hosted-repository.feature", "A refresh does not fail a read")
def test_a_refresh_does_not_fail_a_read() -> None: ...


@scenario("../features/add-web-backend/hosted-repository.feature", "Multi-file reads agree")
def test_multi_file_reads_agree() -> None: ...


@scenario("../features/add-web-backend/hosted-repository.feature", "One edit, one pushed commit")
def test_one_edit_one_pushed_commit() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "A local commit that cannot be pushed is not reported as applied",
)
def test_a_local_commit_that_cannot_be_pushed_is_not_reported_as_applied() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Commit author is the person who made the edit",
)
def test_commit_author_is_the_person_who_made_the_edit() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Unmapped person is refused, not substituted",
)
def test_unmapped_person_is_refused_not_substituted() -> None: ...


@scenario("../features/add-web-backend/hosted-repository.feature", "Second writer is refused")
def test_second_writer_is_refused() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "An outside commit conflicts too"
)
def test_an_outside_commit_conflicts_too() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "Non-overlapping edits both succeed"
)
def test_non_overlapping_edits_both_succeed() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "A rejected push does not silently retry into a conflict",
)
def test_a_rejected_push_does_not_silently_retry_into_a_conflict() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "Divergence resolves toward the remote"
)
def test_divergence_resolves_toward_the_remote() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Recovery does not resurrect refused edits",
)
def test_recovery_does_not_resurrect_refused_edits() -> None: ...


# --------------------------------------------------------------------------
# The repository is what was applied
# --------------------------------------------------------------------------


@given("an accepted edit whose commit could not be recorded in the repository")
def _an_edit_that_never_landed(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.reject_next_pushes(PROJECT, times=9)
    copy["refusal"] = refused(written(host, an_edit(), attempts=2))


@when("the same content is read afterwards")
def _the_content_is_read_again(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["read"] = host.read(PROJECT, SCOUT, host.head(PROJECT))


@then("the read SHALL return the pre-edit content")
def _the_pre_edit_content_is_returned(copy: dict[str, Any]) -> None:
    assert copy["read"] == SCOUT_CONTENT


@then("the caller SHALL have been told the edit did not apply")
def _the_caller_was_told(copy: dict[str, Any]) -> None:
    assert isinstance(copy["refusal"], Conflict)
    assert copy["refusal"].message


@when("an ordinary read is served")
def _an_ordinary_read(copy: dict[str, Any]) -> None:
    store = InMemorySpecStore()
    store.add(SCOUT, Asset(id=AssetId("mech_scout"), name="Scout Mech"))
    copy["index"] = InMemorySearchIndex()
    copy["listing"] = ran(list_assets(spec_store=store, search_index=copy["index"]))


@then("it SHALL NOT trigger a full index rebuild")
def _no_rebuild_was_triggered(copy: dict[str, Any]) -> None:
    assert copy["listing"].rows == ()
    assert copy["index"].list_assets() == ()


# --------------------------------------------------------------------------
# Provisioning and refreshing
# --------------------------------------------------------------------------


@given("a project whose repository credential is rejected by the remote")
def _a_rejected_credential(host: InMemoryRepositoryHost) -> None:
    host.make_unreachable(PROJECT, "the credential was rejected")


@when("the project is read")
def _the_project_is_read(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["status"] = host.clone(PROJECT)


@then("the response SHALL report the project as unavailable naming the credential as the reason")
def _unavailable_naming_the_credential(copy: dict[str, Any]) -> None:
    status = copy["status"]

    assert status.state is ProjectState.UNAVAILABLE
    assert "credential" in status.reason


@given("a notification that was never delivered")
def _a_missed_notification(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["before"] = host.head(PROJECT)
    host.push_to_remote(PROJECT, SCOUT, OUTSIDE)


@when("the configured interval elapses")
def _the_interval_elapses(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["refresh"] = ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(LATER)))


@then("the working copy SHALL be refreshed and include the missed commits")
def _the_missed_commits_arrived(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    refresh = copy["refresh"]

    assert refresh.refreshed
    assert refresh.served.revision != copy["before"]
    assert host.read(PROJECT, SCOUT, refresh.served.revision) == OUTSIDE


@given("a working copy at a known revision")
def _a_known_revision(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["served"] = host.status(PROJECT).served


@when("a refresh fails because the remote is unreachable")
def _the_refresh_fails(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.push_to_remote(PROJECT, SCOUT, OUTSIDE)
    host.fail_next_fetch(PROJECT)
    copy["refresh"] = ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(LATER)))


@then("reads SHALL continue to be served from the last good revision")
def _still_the_last_good_revision(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    refresh = copy["refresh"]

    assert not refresh.refreshed
    assert refresh.served == copy["served"]
    assert host.read(PROJECT, SCOUT, refresh.served.revision) == SCOUT_CONTENT


@then("the project SHALL NOT be reported as unavailable")
def _the_project_is_still_available(host: InMemoryRepositoryHost) -> None:
    assert host.status(PROJECT).state is ProjectState.READY


# --------------------------------------------------------------------------
# Reads are isolated from a refresh (D3)
# --------------------------------------------------------------------------


@given("a refresh that is in progress")
def _a_refresh_in_progress(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    """The reader resolved its revision; the remote then moved under it."""
    copy["held"] = host.head(PROJECT)
    host.push_to_remote(PROJECT, SCOUT, OUTSIDE)
    host.push_to_remote(PROJECT, MULE, MULE_EDIT)


@when("a specification is read")
def _a_specification_is_read(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(LATER)))
    copy["read"] = host.read(PROJECT, SCOUT, copy["held"])


@then("the content returned SHALL correspond to exactly one revision")
def _one_revision_of_content(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert copy["read"] == SCOUT_CONTENT
    assert host.read(PROJECT, MULE, copy["held"]) == MULE_CONTENT


@when("any read is issued")
def _any_read_is_issued(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(LATER)))
    copy["read"] = host.read(PROJECT, SCOUT, copy["held"])


@then("it SHALL be served rather than refused")
def _it_was_served(copy: dict[str, Any]) -> None:
    assert copy["read"] is not None


@given("a compiled briefing assembled from several specification files")
def _a_briefing_from_several_files(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["held"] = host.head(PROJECT)
    copy["first"] = host.read(PROJECT, SCOUT, copy["held"])


@when("a refresh lands between two of those file reads")
def _a_refresh_lands_mid_read(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.push_to_remote(PROJECT, MULE, MULE_EDIT)
    ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(LATER)))
    copy["second"] = host.read(PROJECT, MULE, copy["held"])


@then("the briefing SHALL be produced from a single revision")
def _the_briefing_is_one_revision(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert copy["first"] == SCOUT_CONTENT
    assert copy["second"] == MULE_CONTENT
    assert host.head(PROJECT) != copy["held"]


# --------------------------------------------------------------------------
# Write-back (D2, D8)
# --------------------------------------------------------------------------


@given("an accepted edit to one specification")
def _an_accepted_edit(copy: dict[str, Any]) -> None:
    copy["edit"] = an_edit()


@when("it is written back")
def _it_is_written_back(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["written"] = ran(written(host, copy["edit"]))


@then("the configured branch SHALL contain exactly one new commit for it")
def _exactly_one_commit(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert len(host.commits(PROJECT)) == 1
    assert copy["written"].paths == (SCOUT,)


@then("that commit SHALL be present on the remote")
def _the_commit_is_on_the_remote(host: InMemoryRepositoryHost) -> None:
    assert host.remote_files(PROJECT)[SCOUT] == RAFA_EDIT
    assert host.unpushed(PROJECT) == ()


@given("an edit committed to the working copy")
def _an_edit_committed_locally(copy: dict[str, Any]) -> None:
    copy["edit"] = an_edit()


@when("pushing it to the remote fails")
def _the_push_fails(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.reject_next_pushes(PROJECT, times=9)
    copy["refusal"] = refused(written(host, copy["edit"], attempts=2))


@then("the caller SHALL be told the edit did not apply")
def _the_caller_was_told_it_did_not_apply(copy: dict[str, Any]) -> None:
    assert isinstance(copy["refusal"], Conflict)


@then("the working copy SHALL be returned to the remote's state")
def _the_working_copy_matches_the_remote(host: InMemoryRepositoryHost) -> None:
    assert host.unpushed(PROJECT) == ()
    assert host.remote_files(PROJECT)[SCOUT] == SCOUT_CONTENT
    assert host.read(PROJECT, SCOUT, host.head(PROJECT)) == SCOUT_CONTENT


@given("an acting person mapped to a git identity")
def _a_mapped_person(copy: dict[str, Any]) -> None:
    copy["author"] = RAFA


@when("their edit is written back")
def _their_edit_is_written_back(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["written"] = ran(written(host, an_edit(), author=copy["author"]))


@then("the commit's author SHALL be that git identity")
def _the_author_is_that_identity(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    (commit,) = host.commits(PROJECT)

    assert commit.author == RAFA
    assert copy["written"].commit.author == RAFA


@given("an acting person with no entry in the actors mapping")
def _an_unmapped_person(copy: dict[str, Any]) -> None:
    copy["author"] = None
    copy["subject"] = "auth|newcomer"


@when("they attempt an edit")
def _they_attempt_an_edit(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["refusal"] = refused(written(host, an_edit(), author=None, subject=copy["subject"]))


@then("the edit SHALL be refused naming the missing mapping")
def _refused_naming_the_mapping(copy: dict[str, Any]) -> None:
    refusal = copy["refusal"]

    assert isinstance(refusal, Forbidden)
    assert ".canon/actors.yaml" in refusal.message
    assert copy["subject"] in refusal.message


@then("no commit SHALL be created")
def _no_commit_was_created(host: InMemoryRepositoryHost) -> None:
    assert host.commits(PROJECT) == ()


# --------------------------------------------------------------------------
# Conflicts (D5, D6)
# --------------------------------------------------------------------------


@given("two people who read the same specification at the same revision")
def _two_people_at_one_revision(copy: dict[str, Any]) -> None:
    copy["based_on"] = SCOUT_CONTENT


@when(
    "the first writes successfully and the second submits an edit composed against the "
    "original revision"
)
def _the_second_writer_submits(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["first"] = ran(written(host, an_edit(content=RAFA_EDIT), author=RAFA))
    copy["refusal"] = refused(
        written(host, an_edit(content=ANA_EDIT, based_on=copy["based_on"]), author=ANA)
    )


@then("the second edit SHALL be refused as conflicting")
def _the_second_was_refused(copy: dict[str, Any]) -> None:
    assert isinstance(copy["refusal"], Conflict)
    assert copy["refusal"].subject == SCOUT


@then("the first person's change SHALL remain intact")
def _the_first_change_stands(host: InMemoryRepositoryHost) -> None:
    assert host.remote_files(PROJECT)[SCOUT] == RAFA_EDIT


@given("a specification changed by a commit pushed directly to the repository")
def _an_outside_commit(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.push_to_remote(PROJECT, SCOUT, OUTSIDE)
    ran(refresh_project(PROJECT, repository_host=host, clock=fixed_clock(LATER)))


@when("an edit composed before that commit is submitted")
def _an_edit_from_before(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["refusal"] = refused(written(host, an_edit()))


@then("it SHALL be refused as conflicting")
def _it_was_refused_as_conflicting(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert isinstance(copy["refusal"], Conflict)
    assert host.remote_files(PROJECT)[SCOUT] == OUTSIDE


@given("two edits to different specifications composed at the same revision")
def _two_edits_to_different_files(copy: dict[str, Any]) -> None:
    copy["edits"] = (
        an_edit(content=RAFA_EDIT),
        an_edit(path=MULE, content=MULE_EDIT, based_on=MULE_CONTENT),
    )


@when("both are submitted")
def _both_are_submitted(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    first, second = copy["edits"]
    copy["outcomes"] = (
        written(host, first, author=RAFA),
        written(host, second, author=ANA),
    )


@then("both SHALL be applied")
def _both_were_applied(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert all(succeeded(outcome) for outcome in copy["outcomes"])
    assert host.remote_files(PROJECT)[SCOUT] == RAFA_EDIT
    assert host.remote_files(PROJECT)[MULE] == MULE_EDIT


@given("a push rejected because the remote advanced")
def _a_rejected_push(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.reject_next_pushes(PROJECT, times=1)


@when("the service re-evaluates the edit against the new remote state")
def _the_edit_is_re_evaluated(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["untouched"] = written(host, an_edit(path=MULE, content=MULE_EDIT, based_on=MULE_CONTENT))
    host.reject_next_pushes(PROJECT, times=1)
    host.push_to_remote(PROJECT, SCOUT, OUTSIDE)
    copy["moved"] = written(host, an_edit())


@then("it SHALL apply the edit only if its content is still unchanged")
def _the_untouched_edit_applied(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert succeeded(copy["untouched"])
    assert host.remote_files(PROJECT)[MULE] == MULE_EDIT


@then("SHALL otherwise refuse it as conflicting")
def _the_moved_edit_was_refused(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert isinstance(copy["moved"], Conflict)
    assert host.remote_files(PROJECT)[SCOUT] == OUTSIDE


# --------------------------------------------------------------------------
# Recovery
# --------------------------------------------------------------------------


@given("a working copy carrying local commits absent from the remote branch")
def _a_diverged_working_copy(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    """Committed and never pushed — the state `write_back` itself refuses to leave.

    Staged through the port rather than through the use case on purpose: D2
    forbids leaving an edit committed locally, so `write_back` recovers before
    it returns. Divergence is therefore something *else* produced — a crashed
    process, an operator, a half-finished run — and recovery has to handle it.
    """
    host.commit(PROJECT, [FileChange(path=SCOUT, content=RAFA_EDIT)], author=RAFA, message=MESSAGE)
    copy["stranded"] = host.unpushed(PROJECT)


@when("recovery runs")
def _recovery_runs(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["recovery"] = host.recover(PROJECT)


@then("the working copy SHALL be reset to the remote branch")
def _reset_to_the_remote(host: InMemoryRepositoryHost) -> None:
    assert host.read(PROJECT, SCOUT, host.head(PROJECT)) == SCOUT_CONTENT
    assert host.unpushed(PROJECT) == ()


@then("the discarded local commits SHALL be reported")
def _the_discarded_commits_are_reported(copy: dict[str, Any]) -> None:
    assert copy["recovery"].discarded_anything
    assert copy["recovery"].discarded == tuple(commit.revision.value for commit in copy["stranded"])


@given("an edit that was refused because it could not be pushed")
def _a_refused_edit(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.reject_next_pushes(PROJECT, times=9)
    copy["refusal"] = refused(written(host, an_edit(), attempts=2))


@when("the working copy is recovered")
def _the_working_copy_is_recovered(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["recovery"] = host.recover(PROJECT)


@then("that edit SHALL NOT appear in the restored content")
def _the_refused_edit_is_gone(host: InMemoryRepositoryHost) -> None:
    assert host.read(PROJECT, SCOUT, host.head(PROJECT)) == SCOUT_CONTENT
    assert host.remote_files(PROJECT)[SCOUT] == SCOUT_CONTENT
