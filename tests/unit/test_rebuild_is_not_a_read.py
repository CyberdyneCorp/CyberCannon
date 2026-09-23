"""Task 4.10 — a rebuild is an operation, and no read may be one.

`hosted-repository` says it twice, in opposite directions: the service SHALL
provide an operation that discards the index and rebuilds it, and *"an ordinary
read SHALL NOT trigger a full index rebuild"*. The second is the one that is
easy to break by being helpful — a lookup that finds an empty index and quietly
repopulates it looks like a kindness and is a read that rewrites the index under
whoever else is reading it.

Two halves, deliberately different in kind:

* **structural** — a walk of the syntax tree of every read use case, asserting
  none of them names a rebuild. It catches the helpful call before it is ever
  exercised, including on the paths a test happens not to cover.
* **behavioural** — a read against an empty index answers from what is there
  (which is nothing) and leaves the index exactly as empty as it found it.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases import (
    annotations,
    blob_mirror,
    compile_spec,
    derived_metadata,
    diff_spec,
    documents,
    hosted_repository,
    lookup_assets,
    search_delegation,
    spec_lens,
    validate_export,
    validation_records,
    view_mirror,
    view_revisions,
    viewer,
)
from cybercanon.domain.asset import Asset, AssetId

REBUILDS = frozenset({"rebuild_index", "rebuild_project_index"})
"""The two names that mean *rewrite the whole index*."""

READ_MODULES = (
    annotations,
    blob_mirror,
    compile_spec,
    derived_metadata,
    diff_spec,
    documents,
    lookup_assets,
    search_delegation,
    spec_lens,
    validate_export,
    validation_records,
    view_mirror,
    view_revisions,
    viewer,
)
"""Every module a read goes through. A rebuild called from one is the defect.

`annotations` is here for its two reads — one asset's threads and the project's
triage queue — and the queue is the one worth guarding: D11 makes it derivable
from the repository alone with the index as an accelerator, which is exactly the
shape that tempts somebody to repopulate an empty index on the way past.

`blob_mirror` is here because listing an asset's views and issuing a link to one
are reads, and the mirroring pass beside them is exactly the kind of expensive
operation a helpful read would reach for on finding an object missing.
`validation_records` is here for the same reason: it is the reader an index
rebuild uses to restore a validated export (G2), and a reader that rebuilt would
be a recursion rather than a kindness. `view_revisions` and `view_mirror` join
them with concept ingestion: a view's history is a read over the repository, and
the mirroring pass beside it is the same expensive operation a helpful read
would reach for on finding an object missing. `documents` is here because
listing an asset's linked documents is a read over the repository whose display
cache is rebuildable — precisely the shape that tempts a helpful repopulation.
`search_delegation` is here because it is the read that meets an empty answer
most often: a query that matched nothing is exactly where a helpful
implementation would offer to rebuild before delegating, and a search that
rewrote the index would make *"the same query returns the same results"* false
for whoever else was reading it.
`derived_metadata` is here because its reads are the ones most likely to meet
an index with nothing in it: looking for a record keyed by an image's content
hash and finding none is the ordinary case the first time anybody describes an
asset, and a rebuild reached for at that moment would rewrite every row in the
project on the way to generating one description.
`viewer` is here because every
function in it is a read — the preview descriptor, the preview's bytes and the
anchor resolutions — and the descriptor is precisely the shape that tempts a
rebuild: it asks which export validated most recently, and an empty index is
the first thing a helpful implementation would offer to repopulate.
"""

SPEC_PATH = "characters/mech_scout/asset.yaml"


def _called_names(module: object) -> set[str]:
    """Every name this module calls, however it spells the call."""
    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
            if isinstance(node.func.value, ast.Name):
                called.add(node.func.value.id)
    return called


@pytest.mark.parametrize("module", READ_MODULES, ids=lambda module: module.__name__)
def test_no_read_use_case_calls_a_rebuild(module: object) -> None:
    reached = _called_names(module) & REBUILDS

    assert not reached, (
        f"{module.__name__} calls {sorted(reached)}. A rebuild is an operation "
        "(`hosted-repository`): a read that repopulates the index rewrites it "
        "under everybody else reading it."
    )


def test_the_guard_is_over_something_that_could_fail() -> None:
    """A guard over nothing passes for the wrong reason."""
    called = _called_names(hosted_repository)

    assert "rebuild_index" in called
    assert "rebuild_project_index" in {
        node.name
        for node in ast.walk(ast.parse(inspect.getsource(hosted_repository)))
        if isinstance(node, ast.FunctionDef)
    }


def test_the_read_modules_are_the_ones_on_disk(repo_root: Path) -> None:
    """A read module added without being listed here would not be guarded."""
    directory = repo_root / "libs" / "cybercanon" / "application" / "use_cases"
    listed = {module.__name__.rsplit(".", 1)[-1] for module in READ_MODULES}
    present = {path.stem for path in directory.glob("*.py")} - {"__init__"}

    assert listed <= present
    assert present - listed == {
        "authenticate",
        "briefing",
        "prompts",
        "deployment_status",
        "hosted_repository",
        "idempotency",
        "index_assets",
        "lint_spec",
        "requests",
        "resolve_actor",
        "service_health",
        "ingest_views",
        "observations",
        "sign_in",
        "validation_worker",
    }


def test_a_lookup_against_an_empty_index_leaves_it_empty() -> None:
    """The behavioural half: a read answers from what is there, and adds nothing."""
    store = InMemorySpecStore()
    store.add(SPEC_PATH, Asset(id=AssetId("mech_scout"), name="Scout Mech"))
    index = InMemorySearchIndex()

    refused(lookup_assets.where_is("mech_scout", spec_store=store, search_index=index))

    assert index.list_assets() == ()


def test_a_listing_against_an_empty_index_stays_empty() -> None:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, Asset(id=AssetId("mech_scout"), name="Scout Mech"))
    index = InMemorySearchIndex()

    listing = ran(lookup_assets.list_assets(spec_store=store, search_index=index))

    assert listing.rows == ()
    assert index.list_assets() == ()
