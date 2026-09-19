"""Step definitions for `hosted-repository` — the working copy, groups 4 and 5.

Group 4 builds the port and the use cases: `RepositoryHost` (clone, fetch,
resolve, read at a revision, commit as an author, push, recover),
`refresh_project`, and `write_back` with D5's per-file precondition and D6's
bounded retry. Everything bound here is answerable by that code against the
in-memory host, which is the point of having a port at all — the isolation D3
gives a read is a property of *holding a revision*, not of any particular git
invocation, so a fake that models a remote, a working copy and an unpushed queue
exercises it exactly.

Group 5 adds the adapter and the surfaces over it, and its scenarios come in
here: the notification endpoint (through the real application and a real HMAC),
provisioning reported to a listing rather than faked as an empty one, the
revision and staleness stated on every read, the agent recorded beside the
person who authored, and recovery of a working copy that has been deleted.

**That last one runs against real git**, because it is the only scenario in this
file that is about a volume rather than about the model: "the working copy has
been deleted from the service's storage" is not a state the fake can be in. The
rest stay on the fake deliberately — the port conformance suite is what holds the
two implementations to one behaviour, and a BDD scenario re-proving that would
just be slower.

The scenarios still in `tests/bdd/pending.txt` are the three that need an index:
dropping it, rebuilding it, and repository content winning over it. They are
group 6.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, scenario, then, when

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.webhooks import (
    SIGNATURE_HEADER,
    WEBHOOK_PATH,
    Notice,
    RepositoryNotifications,
    signature_for,
)
from cybercanon.adapters.outbound.git import commands
from cybercanon.adapters.outbound.git.repository_host import GitRepositoryHost, ProjectRemote
from cybercanon.application.ports.clock import fixed_clock
from cybercanon.application.ports.repository_host import FileChange, ProjectState
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.results import Conflict, Forbidden, Unavailable, succeeded
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.repository_host import EPOCH, InMemoryRepositoryHost
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.hosted_repository import (
    AGENT_TRAILER,
    DEFAULT_INTERVAL,
    Edit,
    edit_message,
    read_at_revision,
    rebuild_project_index,
    refresh_project,
    write_back,
)
from cybercanon.application.use_cases.lookup_assets import list_assets
from cybercanon.application.use_cases.requests import (
    REQUESTS_DIR,
    raise_request,
    read_request,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.identity import ActorId
from cybercanon.domain.requests import Discipline, RequestId
from cybercanon.domain.requests import raise_request as build_request
from cybercanon.domain.revisions import ContentHash
from cybercanon.domain.status import Status

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

MESSAGE = edit_message("mech_scout", "set status to modeling")

BRANCH = "main"
WEBHOOK_SECRET = "a-configured-webhook-secret"


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
    """The agent is carried when the scenario named one, and is empty otherwise.

    One step for both scenarios rather than two phrasings of the same sentence:
    the spec says "it is written back" in each, and a step that differed would be
    a fork of the spec by another route.
    """
    copy["written"] = ran(written(host, copy["edit"], agent=copy.get("agent", "")))


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


# --------------------------------------------------------------------------
# Group 5 — the hosted working copy: provisioning, notification, staleness,
# attribution and recovery of a working copy that is really on a disk.
# --------------------------------------------------------------------------


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Provisioning is reported, not faked",
)
def test_provisioning_is_reported_not_faked() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "Notification triggers a refresh"
)
def test_notification_triggers_a_refresh() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Unauthenticated notification is ignored",
)
def test_unauthenticated_notification_is_ignored() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Revision and confirmation time are stated",
)
def test_revision_and_confirmation_time_are_stated() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "Staleness is surfaced, not hidden"
)
def test_staleness_is_surfaced_not_hidden() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Commit message identifies the change",
)
def test_commit_message_identifies_the_change() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "Agent-performed write names both"
)
def test_agent_performed_write_names_both() -> None: ...


@scenario("../features/add-web-backend/hosted-repository.feature", "Deleted working copy recovers")
def test_deleted_working_copy_recovers() -> None: ...


# --------------------------------------------------------------------------
# Provisioning is a state, never an empty listing
# --------------------------------------------------------------------------


@given("a project whose working copy is still being obtained")
def _a_project_still_cloning(copy: dict[str, Any]) -> None:
    """Configured and not yet cloned — the state a restart or a new project is in."""
    provisioning = InMemoryRepositoryHost()
    provisioning.add_project(PROJECT, {SCOUT: SCOUT_CONTENT})
    copy["provisioning"] = provisioning


@when("its assets are listed")
def _its_assets_are_listed(copy: dict[str, Any]) -> None:
    copy["listing"] = read_at_revision(
        PROJECT,
        lambda pinned: pinned.specs_under(""),
        repository_host=copy["provisioning"],
        spec_store=InMemorySpecStore(),
    )


@then("the response SHALL report the project as not yet ready")
def _reported_as_not_yet_ready(copy: dict[str, Any]) -> None:
    listing = copy["listing"]

    assert isinstance(listing, Unavailable)
    assert "provisioning" in listing.message


@then("SHALL NOT report an empty asset list")
def _no_empty_asset_list(copy: dict[str, Any]) -> None:
    """A refusal carries no listing at all, which is the point: no empty answer."""
    assert not succeeded(copy["listing"])
    assert not hasattr(copy["listing"], "value")


# --------------------------------------------------------------------------
# The notification endpoint (D4)
# --------------------------------------------------------------------------


def _notified(copy: dict[str, Any], host: InMemoryRepositoryHost, *, signature: str | None):
    """Post one notification at the real endpoint, wired to the real refresh."""
    asked: list[str] = []

    def refresh(project: str) -> None:
        asked.append(project)
        ran(refresh_project(project, repository_host=host, clock=fixed_clock(LATER)))

    application = build_app(
        notifications=RepositoryNotifications(
            secret=WEBHOOK_SECRET, branches={PROJECT: BRANCH}, refresh=refresh
        )
    )
    body = f'{{"project": "{PROJECT}", "ref": "refs/heads/{BRANCH}"}}'.encode()
    offered = signature_for(WEBHOOK_SECRET, body) if signature is None else signature
    with TestClient(application) as client:
        copy["response"] = client.post(
            WEBHOOK_PATH, content=body, headers={SIGNATURE_HEADER: offered}
        )
    copy["asked"] = tuple(asked)


@given("a new commit on a project's configured branch")
def _a_new_commit_on_the_branch(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["before"] = host.head(PROJECT)
    host.push_to_remote(PROJECT, SCOUT, OUTSIDE)


@when("an authenticated notification for that project is received")
def _an_authenticated_notification(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    _notified(copy, host, signature=None)


@then("the working copy SHALL be refreshed to include that commit")
def _the_commit_arrived(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert copy["asked"] == (PROJECT,)
    assert host.head(PROJECT) != copy["before"]
    assert host.read(PROJECT, SCOUT, host.head(PROJECT)) == OUTSIDE


@when("a notification arrives without a valid authentication of its origin")
def _an_unauthenticated_notification(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["before"] = host.head(PROJECT)
    host.push_to_remote(PROJECT, SCOUT, OUTSIDE)
    _notified(copy, host, signature="sha256=not-the-signature")


@then("it SHALL be ignored")
def _the_notification_was_ignored(copy: dict[str, Any]) -> None:
    assert copy["response"].json()["outcome"] == Notice.UNAUTHENTICATED.value


@then("no refresh SHALL occur")
def _nothing_was_refreshed(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert copy["asked"] == ()
    assert host.head(PROJECT) == copy["before"]


# --------------------------------------------------------------------------
# Every read states its revision, its confirmation and its staleness
# --------------------------------------------------------------------------


@given("refreshes have been failing for longer than the configured interval")
def _refreshes_have_been_failing(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    host.fail_next_fetch(PROJECT, times=3)
    copy["now"] = EPOCH + 2 * DEFAULT_INTERVAL
    copy["outage"] = ran(
        refresh_project(PROJECT, repository_host=host, clock=fixed_clock(copy["now"]))
    )


@when("specification content is read")
def _specification_content_is_read(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    now = copy.get("now", EPOCH)
    store = InMemorySpecStore()
    store.add(SCOUT, Asset(id=AssetId("mech_scout"), name="Scout Mech"))
    store.snapshot(host.head(PROJECT).value)
    copy["served"] = ran(
        read_at_revision(
            PROJECT,
            lambda pinned: pinned.specs_under(""),
            repository_host=host,
            spec_store=store,
            clock=fixed_clock(now),
            interval=DEFAULT_INTERVAL,
        )
    )


@then("the response SHALL name the revision it was produced from")
def _the_revision_is_named(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert copy["served"].revision == host.head(PROJECT)


@then("SHALL state when that revision was last confirmed against the remote")
def _the_confirmation_time_is_stated(copy: dict[str, Any]) -> None:
    served = copy["served"]

    assert served.confirmed_at == EPOCH
    assert not served.may_be_stale


@then("the response SHALL indicate that the content may be stale")
def _the_content_may_be_stale(copy: dict[str, Any]) -> None:
    assert not copy["outage"].refreshed
    assert copy["served"].may_be_stale


# --------------------------------------------------------------------------
# What a commit says, and who it says performed it
# --------------------------------------------------------------------------


@when("an edit is written back")
def _an_edit_is_written_back(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["written"] = ran(written(host, an_edit()))


@then("its commit message SHALL name the asset and describe what changed")
def _the_message_names_the_asset(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    (commit,) = host.commits(PROJECT)

    assert commit.message == edit_message("mech_scout", "set status to modeling")
    assert commit.message.startswith("mech_scout")
    assert "set status to modeling" in commit.message


@given("an edit performed by an agent acting as a person")
def _an_agent_performed_edit(copy: dict[str, Any]) -> None:
    copy["edit"] = an_edit()
    copy["agent"] = "blender-agent"


@then("the commit SHALL be authored by that person")
def _authored_by_the_person(host: InMemoryRepositoryHost) -> None:
    (commit,) = host.commits(PROJECT)

    assert commit.author == RAFA


@then("the record SHALL also identify the agent that performed it")
def _the_agent_is_recorded(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    (commit,) = host.commits(PROJECT)

    assert f"{AGENT_TRAILER}: {copy['agent']}" in commit.message
    assert commit.author != GitAuthor(name=copy["agent"], email=copy["agent"])


# --------------------------------------------------------------------------
# A working copy that is really on a disk, and really gone
# --------------------------------------------------------------------------


@given("a project whose working copy has been deleted from the service's storage")
def _a_deleted_working_copy(copy: dict[str, Any], tmp_path: Path) -> None:
    """The one scenario here that is about the volume rather than about the model."""
    on_disk = _real_project(tmp_path)
    on_disk.clone(PROJECT)
    shutil.rmtree(on_disk.path(PROJECT))
    copy["on_disk"] = on_disk


@when("the project is next read")
def _the_project_is_next_read(copy: dict[str, Any]) -> None:
    on_disk = copy["on_disk"]
    copy["state_before"] = on_disk.status(PROJECT).state
    copy["head"] = on_disk.head(PROJECT)


@then("the working copy SHALL be restored from the remote")
def _the_working_copy_was_restored(copy: dict[str, Any]) -> None:
    on_disk = copy["on_disk"]

    assert copy["state_before"] is ProjectState.RECOVERING
    assert on_disk.status(PROJECT).state is ProjectState.READY


@then("every specification present in the repository SHALL be readable again")
def _every_specification_reads_again(copy: dict[str, Any]) -> None:
    on_disk, revision = copy["on_disk"], copy["head"]

    assert on_disk.read(PROJECT, SCOUT, revision) == SCOUT_CONTENT
    assert on_disk.read(PROJECT, MULE, revision) == MULE_CONTENT


def _real_project(tmp_path: Path) -> GitRepositoryHost:
    """A bare remote holding the corpus, and a host configured to serve it."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    environment = {"HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null"}
    run = partial(commands.run, environment=environment)
    run(None, ["init", "--quiet", "--bare", f"--initial-branch={BRANCH}", str(bare)])
    run(None, ["clone", "--quiet", str(bare), str(seed)])
    for path, content in {SCOUT: SCOUT_CONTENT, MULE: MULE_CONTENT}.items():
        (seed / path).parent.mkdir(parents=True, exist_ok=True)
        (seed / path).write_bytes(content)
    run(seed, ["add", "--all"])
    run(
        seed,
        ["-c", "user.name=Seed", "-c", "user.email=seed@example.com", "commit", "-qm", "seed"],
    )
    run(seed, ["push", "--quiet", "origin", f"HEAD:refs/heads/{BRANCH}"])
    return GitRepositoryHost(
        tmp_path / "working-copies",
        [ProjectRemote(project=PROJECT, url=str(bare), branch=BRANCH)],
        environment=environment,
    )


# --------------------------------------------------------------------------
# The index is derived, and the repository is what survives (group 6)
# --------------------------------------------------------------------------
#
# Three scenarios, one rule: *"Every answer the service gives SHALL be derivable
# from the working copy alone."* They are bound against the in-memory host and
# the in-memory index rather than against PostgreSQL, deliberately — the port
# conformance suite is what holds the fake and `PostgresSearchIndex` to one
# behaviour, and `tests/integration/test_postgres_index.py` runs the same
# drop-and-rebuild drill against a real server and a real working copy. A BDD
# scenario re-proving either would only be slower.


@scenario(
    "../features/add-web-backend/hosted-repository.feature",
    "Repository content wins over service storage",
)
def test_repository_content_wins_over_service_storage() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "Dropping the index loses no answer"
)
def test_dropping_the_index_loses_no_answer() -> None: ...


@scenario(
    "../features/add-web-backend/hosted-repository.feature", "No write reaches only the index"
)
def test_no_write_reaches_only_the_index() -> None: ...


SCOUT_ASSET = Asset(id=AssetId("mech_scout"), name="Scout Mech", status=Status.MODELING)
MULE_ASSET = Asset(id=AssetId("mule"), name="Mule Hauler", status=Status.CONCEPT)

SEARCH_TERMS = ("mech_scout", "mule", "scout", "nothing-matches-this")

REQUESTED = "a supply crate for the loading dock"


def _repository_store(host: InMemoryRepositoryHost) -> InMemorySpecStore:
    """A spec store over what the repository holds, snapshotted at its head."""
    store = InMemorySpecStore()
    store.add(SCOUT, SCOUT_ASSET)
    store.add(MULE, MULE_ASSET)
    store.snapshot(host.head(PROJECT).value)
    return store


def _rebuild(
    host: InMemoryRepositoryHost, store: InMemorySpecStore, index: InMemorySearchIndex
) -> None:
    """Rebuild from the working copy, at whatever revision it is serving now."""
    store.snapshot(host.head(PROJECT).value)
    ran(rebuild_project_index(PROJECT, repository_host=host, spec_store=store, search_index=index))


def _answers(
    host: InMemoryRepositoryHost, store: InMemorySpecStore, index: InMemorySearchIndex
) -> dict[str, Any]:
    """Every lookup, listing, search and read this project can answer."""
    return {
        "listing": index.list_assets(),
        "lookups": {entry.asset_id: index.get(entry.asset_id) for entry in index.list_assets()},
        "searches": {term: index.search(term) for term in SEARCH_TERMS},
        "reads": {path: host.read(PROJECT, path, host.head(PROJECT)) for path in (SCOUT, MULE)},
        "requests": sorted(
            path for path in host.remote_files(PROJECT) if path.startswith(REQUESTS_DIR)
        ),
    }


@given("the repository and the service's own storage disagree about a specification's content")
def _the_index_disagrees_with_the_repository(
    copy: dict[str, Any], host: InMemoryRepositoryHost
) -> None:
    """A row the index kept saying one thing while the repository says another."""
    store = _repository_store(host)
    index = InMemorySearchIndex()
    index.upsert(
        IndexedAsset(asset_id="mech_scout", name="Something Else", status="approved", project="")
    )
    copy["store"], copy["index"] = store, index


@when("that specification is read")
def _that_specification_is_read(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["read"] = ran(
        read_at_revision(
            PROJECT,
            lambda store: store.load(SCOUT).asset,
            repository_host=host,
            spec_store=copy["store"],
        )
    )


@then("the repository's content SHALL be returned")
def _the_repositorys_content_is_returned(copy: dict[str, Any]) -> None:
    served, indexed = copy["read"].value, copy["index"].get("mech_scout")

    assert served == SCOUT_ASSET
    assert indexed is not None
    assert indexed.name != served.name, "the disagreement was not real"


@given("a project whose assets, requests, statuses and links have been read and recorded")
def _a_project_whose_answers_were_recorded(
    copy: dict[str, Any], host: InMemoryRepositoryHost
) -> None:
    store = _repository_store(host)
    index = InMemorySearchIndex()
    ran(
        raise_request(
            PROJECT,
            build_request(
                request_id=RequestId("req-0001"),
                author=ActorId("auth|rafa"),
                discipline=Discipline.MODELING,
                description=REQUESTED,
                at=NOON,
            ),
            repository_host=host,
            author=RAFA,
            clock=lambda: NOON,
        )
    )
    _rebuild(host, store, index)
    copy["store"], copy["index"] = store, index
    copy["before"] = _answers(host, store, index)


@when("the index is dropped entirely and rebuilt from the working copy")
def _the_index_is_dropped_and_rebuilt(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    index = copy["index"]
    index.clear()
    assert index.list_assets() == (), "the drop did not drop anything"
    _rebuild(host, copy["store"], index)


@then(
    "every previously answerable lookup, listing, search and read SHALL return the same "
    "result as before"
)
def _every_answer_is_unchanged(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    assert _answers(host, copy["store"], copy["index"]) == copy["before"]


@when("any durable content is created or changed through the service")
def _durable_content_is_created(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    """A request is durable content, and every write goes the same way it does."""
    copy["store"], copy["index"] = _repository_store(host), InMemorySearchIndex()
    copy["recorded"] = ran(
        raise_request(
            PROJECT,
            build_request(
                request_id=RequestId("req-0002"),
                author=ActorId("auth|rafa"),
                discipline=Discipline.MODELING,
                description=REQUESTED,
                at=NOON,
            ),
            repository_host=host,
            author=RAFA,
            clock=lambda: NOON,
        )
    )


@then("it SHALL be written to the repository")
def _it_was_written_to_the_repository(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    written_path = copy["recorded"].path

    assert written_path in host.remote_files(PROJECT)
    assert host.unpushed(PROJECT) == ()


@then("it SHALL survive a full index rebuild")
def _it_survives_a_rebuild(copy: dict[str, Any], host: InMemoryRepositoryHost) -> None:
    copy["index"].clear()
    _rebuild(host, copy["store"], copy["index"])

    read = ran(read_request(PROJECT, RequestId("req-0002"), repository_host=host))
    assert read.description == REQUESTED
