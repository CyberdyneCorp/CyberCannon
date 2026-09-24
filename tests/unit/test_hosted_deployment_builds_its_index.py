"""The index a hosted deployment serves from, and the fact nothing ever built it.

`hosted-repository` requires that *"the service SHALL provide an operation that
discards the entire index and rebuilds it from the working copy"*. The operation
was written, tested and exported — and no adapter ever called it. The read
surface lists assets from the index, the background pass only ever *updated*
rows that already existed, and so a hosted deployment cloned its repository,
validated exports against it, and served an empty asset list for ever.

The first real deployment reported exactly that: `mech_scout` committed in the
game repository, and "this project has no assets yet" in the browser. Nothing
was broken in any single component; the wire between two of them had never been
run.

The requirement's own scenarios did not catch it, and the reason is worth
keeping in view. They assert that the rebuild *behaves correctly when called* —
dropping the index loses no answer, no write reaches only the index — and, in
the third, that *"an ordinary read SHALL NOT trigger a full index rebuild"*.
Never rebuilding at all satisfies every one of them. Nothing asserted the
operation was reachable, so the tests below assert reachability rather than
behaviour: that a pass over a cloned project leaves rows where a read will find
them, and that `/status` then agrees.
"""

from __future__ import annotations

import pytest

from cybercanon.adapters.wiring.background import indexed_first
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.repository_host import ProjectState
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.deployment_status import (
    DeploymentJournal,
    WorkingCopyStatus,
    index_freshness,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints

PROJECT = "ronin"
SPEC = "characters/mech_scout/asset.yaml"
SPEC_BYTES = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\n"


@pytest.fixture
def host() -> InMemoryRepositoryHost:
    built = InMemoryRepositoryHost()
    built.add_project(PROJECT, {SPEC: SPEC_BYTES})
    built.clone(PROJECT)
    return built


@pytest.fixture
def store(host: InMemoryRepositoryHost) -> InMemorySpecStore:
    built = InMemorySpecStore()
    built.add(
        SPEC,
        Asset(
            id=AssetId("mech_scout"),
            name="Scout Mech",
            constraints=Constraints(tri_budget=12000),
        ),
    )
    built.snapshot(host.head(PROJECT).value)
    return built


@pytest.fixture
def index() -> InMemorySearchIndex:
    return InMemorySearchIndex()


@pytest.fixture
def container(store: InMemorySpecStore, index: InMemorySearchIndex) -> Container:
    return Container(
        spec_store=store,
        mesh_inspector=InMemoryMeshInspector(),
        search_index=index,
        project_id=PROJECT,
    )


def _pass(container: Container, host: InMemoryRepositoryHost, journal: DeploymentJournal) -> None:
    """One background pass, with nothing after the index step."""
    indexed_first(lambda project: None, container=container, repository_host=host, journal=journal)(
        PROJECT
    )


def test_a_pass_over_a_cloned_project_leaves_the_asset_where_a_read_will_find_it(
    container: Container, host: InMemoryRepositoryHost, index: InMemorySearchIndex
) -> None:
    """The defect, stated as the thing a person saw: an empty browser.

    This is the assertion that was missing. Every component worked; nothing
    joined them.
    """
    assert index.list_assets(project=PROJECT) == ()

    _pass(container, host, DeploymentJournal())

    assert [entry.asset_id for entry in index.list_assets(project=PROJECT)] == ["mech_scout"]


def test_status_reports_the_index_in_sync_once_a_pass_has_run(
    container: Container, host: InMemoryRepositoryHost
) -> None:
    """The second half of the same defect, and the one `/status` published.

    `indexed_revision` is recorded by the rebuild and read by the status
    surface. With nothing calling the rebuild it stayed empty, so `in_sync` was
    false on a deployment whose index was, by then, perfectly current.
    """
    journal = DeploymentJournal()
    served = host.head(PROJECT).value
    copy = WorkingCopyStatus(project=PROJECT, state=ProjectState.READY, revision=served)

    assert not index_freshness(PROJECT, working_copy=copy, journal=journal).in_sync

    _pass(container, host, journal)

    freshness = index_freshness(PROJECT, working_copy=copy, journal=journal)
    assert freshness.in_sync
    assert freshness.indexed_revision == served


def test_a_second_pass_over_an_unchanged_revision_does_not_rebuild_again(
    container: Container, host: InMemoryRepositoryHost, index: InMemorySearchIndex
) -> None:
    """Rebuilding is conditional, not a thing every pass does.

    The condition is the same comparison `/status` publishes, so "the index is
    current" means one thing in this deployment rather than two.
    """
    journal = DeploymentJournal()
    _pass(container, host, journal)
    index.clear()

    _pass(container, host, journal)

    assert index.list_assets(project=PROJECT) == ()


def test_a_process_that_holds_no_record_rebuilds_rather_than_assuming(
    container: Container, host: InMemoryRepositoryHost, index: InMemorySearchIndex
) -> None:
    """A restart cannot know what a previous process built, so it checks.

    The journal is per-process by design. An instance that came up holding an
    index built by an instance that is gone must not serve it as current on
    trust — which is also what makes an out-of-band recovery self-heal.
    """
    _pass(container, host, DeploymentJournal())
    index.clear()

    _pass(container, host, DeploymentJournal())

    assert [entry.asset_id for entry in index.list_assets(project=PROJECT)] == ["mech_scout"]
