"""What every `RepositoryHost` SHALL do, whoever implements it (task 4.3).

The contract is the behaviour `hosted-repository` specifies, stated in terms no
implementation can satisfy by accident:

* a project is **provisioning** until it is cloned, and a read of one that is
  not ready is refused rather than answered empty;
* a read is **pinned to a revision**, so a read issued before a fetch and
  completed after it returns the pre-fetch content;
* a **failed fetch keeps the last good revision** and leaves the project
  serving;
* a commit is **authored by the identity it was given**, never by one the host
  invented;
* a **rejected push leaves the commit local**, which is what D6's retry
  re-evaluates, and a push that lands puts it on the remote;
* a **listing of the paths at a revision** is pinned exactly as a read is, and
  comes back in one deterministic order whoever produced it (D7);
* **recovery discards what the remote does not have and says what it discarded**;
* the **history of one path** lists newest first with the content hash at each
  revision, treats a removal as a revision of that path, and answers *no
  revisions* rather than failing for a path nobody has committed
  (`view-versioning`).

`GitRepositoryHost` joins by adding one factory (group 5 of this change); the
body below does not change, which is the whole reason it is written here rather
than against the fake.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cybercanon.application.ports.repository_host import (
    FileChange,
    ProjectNotReady,
    ProjectState,
    PushRejected,
    RepositoryHost,
    RepositoryUnavailable,
    RevisionUnreachable,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.revisions import ContentHash, Revision

PROJECT = "cyberdyne-game"
SPEC = "characters/mech_scout/asset.yaml"
OTHER = "vehicles/mule/asset.yaml"

ORIGINAL = b"schema_version: 1\nid: mech_scout\n"
EDITED = b"schema_version: 1\nid: mech_scout\nstatus: modeling\n"
OUTSIDE = b"schema_version: 1\nid: mech_scout\nstatus: validated\n"

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
MESSAGE = "mech_scout: set status to modeling"

CORPUS = {SPEC: ORIGINAL, OTHER: b"schema_version: 1\nid: mule\n"}

LATER = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
"""When a test's refresh happened, so a confirmation time is asserted not guessed."""


class RepositoryHostContract:
    """The behaviour every repository host shares."""

    # -- provisioning ----------------------------------------------------

    def test_a_project_is_provisioning_until_it_is_cloned(
        self, implementation: RepositoryHost
    ) -> None:
        implementation.add_project(PROJECT, dict(CORPUS))

        assert implementation.status(PROJECT).state is ProjectState.PROVISIONING

    def test_a_project_that_is_not_ready_refuses_a_read_rather_than_answering_empty(
        self, implementation: RepositoryHost
    ) -> None:
        """`hosted-repository`: provisioning is reported, never faked as no assets."""
        implementation.add_project(PROJECT, dict(CORPUS))

        with pytest.raises(ProjectNotReady):
            implementation.head(PROJECT)

    def test_cloning_makes_a_project_ready_and_names_the_revision_it_serves(
        self, implementation: RepositoryHost
    ) -> None:
        implementation.add_project(PROJECT, dict(CORPUS))

        status = implementation.clone(PROJECT)

        assert status.is_ready
        assert status.served is not None
        assert status.served.revision == implementation.head(PROJECT)

    def test_an_unreachable_remote_is_reported_with_its_reason(
        self, implementation: RepositoryHost
    ) -> None:
        implementation.add_project(PROJECT, dict(CORPUS))
        implementation.make_unreachable(PROJECT, "the credential was rejected")

        status = implementation.clone(PROJECT)

        assert status.state is ProjectState.UNAVAILABLE
        assert "credential" in status.reason

    # -- reading at a revision (D3) --------------------------------------

    def test_a_read_at_a_revision_answers_that_revisions_content(
        self, implementation: RepositoryHost
    ) -> None:
        ready = _ready(implementation)

        assert implementation.read(PROJECT, SPEC, ready) == ORIGINAL

    def test_an_absent_file_reads_as_absent_rather_than_failing(
        self, implementation: RepositoryHost
    ) -> None:
        """A new file's precondition is that it does not exist (D5)."""
        ready = _ready(implementation)

        assert implementation.read(PROJECT, "props/crate/asset.yaml", ready) is None

    def test_a_revision_the_repository_cannot_reach_is_named(
        self, implementation: RepositoryHost
    ) -> None:
        _ready(implementation)

        with pytest.raises(RevisionUnreachable):
            implementation.read(PROJECT, SPEC, Revision("no-such-revision"))

    def test_a_read_held_across_a_fetch_still_answers_the_pre_fetch_content(
        self, implementation: RepositoryHost
    ) -> None:
        """The isolation D3 makes structural: a reader holds a revision, not a tree."""
        before = _ready(implementation)
        implementation.push_to_remote(PROJECT, SPEC, OUTSIDE)
        implementation.fetch(PROJECT, confirmed_at=LATER)

        assert implementation.read(PROJECT, SPEC, before) == ORIGINAL

    def test_the_paths_at_a_revision_are_listed_in_one_deterministic_order(
        self, implementation: RepositoryHost
    ) -> None:
        """The enumeration a listing of repository content stands on (D7)."""
        ready = _ready(implementation)

        assert implementation.paths_at(PROJECT, ready) == tuple(sorted(CORPUS))

    def test_a_listing_at_an_unreachable_revision_is_named_rather_than_empty(
        self, implementation: RepositoryHost
    ) -> None:
        _ready(implementation)

        with pytest.raises(RevisionUnreachable):
            implementation.paths_at(PROJECT, Revision("no-such-revision"))

    def test_a_listing_is_pinned_to_its_revision_exactly_as_a_read_is(
        self, implementation: RepositoryHost
    ) -> None:
        before = _ready(implementation)
        implementation.push_to_remote(PROJECT, "props/crate/asset.yaml", ORIGINAL)
        after = implementation.fetch(PROJECT, confirmed_at=LATER).revision

        assert "props/crate/asset.yaml" not in implementation.paths_at(PROJECT, before)
        assert "props/crate/asset.yaml" in implementation.paths_at(PROJECT, after)

    # -- fetching (D4) ---------------------------------------------------

    def test_a_fetch_sees_a_commit_pushed_directly_to_the_remote(
        self, implementation: RepositoryHost
    ) -> None:
        _ready(implementation)
        implementation.push_to_remote(PROJECT, SPEC, OUTSIDE)

        served = implementation.fetch(PROJECT, confirmed_at=LATER)

        assert served.confirmed_at == LATER
        assert implementation.read(PROJECT, SPEC, served.revision) == OUTSIDE

    def test_a_failed_fetch_is_named_and_leaves_the_served_revision_alone(
        self, implementation: RepositoryHost
    ) -> None:
        served = _ready(implementation)
        implementation.fail_next_fetch(PROJECT)

        with pytest.raises(RepositoryUnavailable):
            implementation.fetch(PROJECT, confirmed_at=LATER)

        assert implementation.head(PROJECT) == served
        assert implementation.status(PROJECT).state is ProjectState.READY

    # -- committing and pushing (D2, D6, D8) -----------------------------

    def test_a_commit_is_authored_by_the_identity_it_was_given(
        self, implementation: RepositoryHost
    ) -> None:
        _ready(implementation)

        commit = _commit(implementation)

        assert commit.author == RAFA
        assert commit.message == MESSAGE
        assert commit.paths == (SPEC,)

    def test_one_edit_becomes_one_pushed_commit(self, implementation: RepositoryHost) -> None:
        _ready(implementation)
        commit = _commit(implementation)

        pushed = implementation.push(PROJECT)

        assert pushed == commit.revision
        assert implementation.remote_files(PROJECT)[SPEC] == EDITED
        assert implementation.unpushed(PROJECT) == ()

    def test_a_rejected_push_leaves_the_commit_unpushed(
        self, implementation: RepositoryHost
    ) -> None:
        """D6's signal: the remote advanced, so the edit is re-evaluated, not forced."""
        _ready(implementation)
        _commit(implementation)
        implementation.reject_next_pushes(PROJECT)

        with pytest.raises(PushRejected):
            implementation.push(PROJECT)

        assert implementation.unpushed(PROJECT)
        assert implementation.remote_files(PROJECT)[SPEC] == ORIGINAL

    def test_a_removal_is_an_ordinary_change(self, implementation: RepositoryHost) -> None:
        _ready(implementation)
        implementation.commit(
            PROJECT, [FileChange(path=OTHER, content=None)], author=RAFA, message="drop the mule"
        )
        implementation.push(PROJECT)

        assert OTHER not in implementation.remote_files(PROJECT)

    # -- recovery --------------------------------------------------------

    def test_recovery_resets_to_the_remote_and_reports_what_it_discarded(
        self, implementation: RepositoryHost
    ) -> None:
        _ready(implementation)
        stranded = _commit(implementation)
        implementation.reject_next_pushes(PROJECT)
        with pytest.raises(PushRejected):
            implementation.push(PROJECT)

        recovery = implementation.recover(PROJECT)

        assert recovery.discarded == (stranded.revision.value,)
        assert recovery.state is ProjectState.READY
        assert implementation.read(PROJECT, SPEC, implementation.head(PROJECT)) == ORIGINAL

    def test_recovery_of_an_untouched_project_discards_nothing(
        self, implementation: RepositoryHost
    ) -> None:
        _ready(implementation)

        assert not implementation.recover(PROJECT).discarded_anything

    # -- the history of one path (`view-versioning`) ----------------------

    def test_a_paths_history_is_newest_first_with_the_content_at_each_revision(
        self, implementation: RepositoryHost
    ) -> None:
        """A concept view is a file, so its revisions are git's revisions of a path."""
        _ready(implementation)
        _commit(implementation)
        implementation.push(PROJECT)

        history = implementation.history(PROJECT, SPEC)

        assert history.path == SPEC
        assert history.revisions[0].content == ContentHash.of(EDITED)
        assert history.revisions[0].author == RAFA
        assert history.is_complete

    def test_a_removal_is_a_revision_of_the_path_it_removed(
        self, implementation: RepositoryHost
    ) -> None:
        """*"Removing a view SHALL likewise be recorded as a revision."*"""
        _ready(implementation)
        implementation.commit(
            PROJECT, [FileChange(path=OTHER, content=None)], author=RAFA, message="drop the mule"
        )
        implementation.push(PROJECT)

        history = implementation.history(PROJECT, OTHER)

        assert history.revisions[0].is_removal
        assert history.revisions[0].content is None

    def test_a_path_that_was_never_committed_has_no_revisions_rather_than_failing(
        self, implementation: RepositoryHost
    ) -> None:
        """*This file has no revisions* and *no such project* are different questions."""
        _ready(implementation)

        assert implementation.history(PROJECT, "props/nothing/asset.yaml").revisions == ()

    def test_a_history_is_bounded_when_a_limit_is_given(
        self, implementation: RepositoryHost
    ) -> None:
        _ready(implementation)
        _commit(implementation)
        implementation.push(PROJECT)

        assert len(implementation.history(PROJECT, SPEC, 1).revisions) == 1

    # -- the precondition D5 is built on ---------------------------------

    def test_the_digest_of_what_was_read_is_what_an_edit_is_composed_against(
        self, implementation: RepositoryHost
    ) -> None:
        ready = _ready(implementation)
        content = implementation.read(PROJECT, SPEC, ready)

        assert content is not None
        assert ContentHash.of(content) == ContentHash.of(ORIGINAL)


def _ready(implementation: RepositoryHost) -> Revision:
    """A cloned project holding the corpus, and the revision it serves."""
    implementation.add_project(PROJECT, dict(CORPUS))
    implementation.clone(PROJECT)
    return implementation.head(PROJECT)


def _commit(implementation: RepositoryHost):
    return implementation.commit(
        PROJECT,
        [FileChange(path=SPEC, content=EDITED, based_on=ContentHash.of(ORIGINAL))],
        author=RAFA,
        message=MESSAGE,
    )
