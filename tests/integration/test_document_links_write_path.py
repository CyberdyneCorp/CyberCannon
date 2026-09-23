"""Tasks 3.1 to 3.3 — document links against a **real git repository**.

The claims this suite makes are claims about git and about a file on disk, and
none of them is checkable against a dictionary:

* a link appears in the history **attributed to the person who made it**;
* adding one leaves every unrelated line of a hand-authored `asset.yaml`
  byte-identical — the property the artists' trust in this tool rests on;
* a project-scoped link goes through the same comment-preserving round trip over
  `.canon/project.yaml`, which the in-memory store cannot exercise because it
  has no file;
* the specification the write produced still **lints and compiles**, so a link
  can never make a file this product's own validator rejects.

The platform itself is the in-memory one: what is under test here is the write
path, and a suite that also needed a network would be two failures wearing one
name. The adapter against the real deployment is
`tests/integration/test_arche_live.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from staged_project import PROJECT, Staged, git, ready

from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.application.ports.document_platform import Credential
from cybercanon.application.testing.document_platform import InMemoryDocumentPlatform
from cybercanon.application.testing.outcomes import ran
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.documents import (
    COMMIT_PREFIX,
    DocumentWorkspace,
    create_document_for_asset,
    link_document,
    list_linked_documents,
    unlink_document,
)
from cybercanon.application.use_cases.index_assets import rebuild_index
from cybercanon.application.use_cases.lint_spec import lint_project
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.documents import DocumentRef, DocumentScope, DocumentState
from cybercanon.domain.identity import Actor, ActorId

pytestmark = pytest.mark.integration

SCOUT = "mech_scout"
SCOUT_SPEC = "characters/mech_scout/asset.yaml"
PROJECT_CONFIG = ".canon/project.yaml"

WORKSPACE = "w_production"
RATIONALE = "d_rationale"
GDD = "d_gdd"

RAFA_SUBJECT = "auth|rafa"
RAFA = GitAuthor(name="Rafa Santos", email="rafa@cyberdyne.com")
TOKEN = "token-rafa"

PROSE = (
    "The scout reads as a courier rather than as a brawler because the faction "
    "is logistics, and the triangle budget should be about forty thousand."
)

AUTHORED = b"""\
schema_version: 1
id: mech_scout
name: Scout Mech        # the id is what everything refers to, not this
status: modeling

# engineering fixed these at the kick-off, and nothing may rewrite them
constraints:
  tri_budget: 12000
  lods: [8000, 4000]
  naming: "SM_{asset}_LOD{n}"

design:
  sockets:
    - name: SOCKET_muzzle_l   # the VFX attaches here
      purpose: muzzle flash

concept:
  views: [front, side, back]

links:
  source: art/source/mech_scout.blend
"""
"""A hand-authored specification: comments, quoting, inline lists, blank lines."""

CONFIG = b"""\
schema_version: 1
name: ronin

# the standing rules the whole team works under
golden_rules:
  - Read at 25 m.
"""

CORPUS = {PROJECT_CONFIG: CONFIG, SCOUT_SPEC: AUTHORED}


@pytest.fixture
def staged(tmp_path: Path) -> Staged:
    return ready(tmp_path, dict(CORPUS))


@pytest.fixture
def platform() -> InMemoryDocumentPlatform:
    platform = InMemoryDocumentPlatform()
    platform.add_actor(TOKEN, RAFA_SUBJECT)
    platform.add_document(
        WORKSPACE,
        RATIONALE,
        "mech_scout — design rationale",
        summary=PROSE,
        body=PROSE,
        readers=(RAFA_SUBJECT,),
    )
    platform.add_document(WORKSPACE, GDD, "Ronin — game design document", readers=(RAFA_SUBJECT,))
    platform.permit_creation(RAFA_SUBJECT, WORKSPACE)
    return platform


def a_workspace(staged: Staged, platform: InMemoryDocumentPlatform) -> DocumentWorkspace:
    return DocumentWorkspace(
        project=PROJECT,
        asset_id=SCOUT,
        spec_store=GitSpecStore(staged.working_copy),
        repository_host=staged.host,
        platform=platform,
        credential=Credential(TOKEN),
        actor=Actor(id=ActorId(RAFA_SUBJECT), display_name="Rafa", projects=(PROJECT,)),
        author=RAFA,
        default_workspace=WORKSPACE,
    )


def a_ref(document_id: str = RATIONALE) -> DocumentRef:
    return DocumentRef(
        workspace=WORKSPACE,
        document_id=document_id,
        url=f"https://documents.invalid/w/{WORKSPACE}/d/{document_id}",
    )


def text_of(staged: Staged, path: str) -> str:
    return (staged.working_copy / path).read_text(encoding="utf-8")


def log(staged: Staged, *arguments: str) -> str:
    return git(staged.working_copy, ["log", *arguments], staged.home)


# --------------------------------------------------------------------------
# 3.1 — the link is in the history, attributed, and the file is otherwise intact
# --------------------------------------------------------------------------


def test_a_link_appears_in_the_history_attributed_to_the_person(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    ran(link_document(a_workspace(staged, platform), a_ref()))

    assert RATIONALE in text_of(staged, SCOUT_SPEC)
    assert RAFA.email in log(staged, "-1", "--format=%ae")
    assert COMMIT_PREFIX in log(staged, "-1", "--format=%s")


def test_the_commit_reaches_the_branch_and_not_only_the_working_copy(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    ran(link_document(a_workspace(staged, platform), a_ref()))

    assert COMMIT_PREFIX in git(staged.bare, ["log", "-1", "--format=%s"], staged.home)


def test_every_unrelated_line_of_the_hand_authored_file_is_byte_identical(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    """The property this product's credibility rests on, asserted line by line."""
    before = text_of(staged, SCOUT_SPEC).splitlines()

    ran(link_document(a_workspace(staged, platform), a_ref()))

    after = text_of(staged, SCOUT_SPEC).splitlines()
    assert after[: len(before)] == before
    assert "# the VFX attaches here" in "\n".join(after[: len(before)])


def test_the_file_carries_the_reference_and_none_of_the_document_s_body(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    workspace = a_workspace(staged, platform)
    ran(link_document(workspace, a_ref()))
    ran(list_linked_documents(workspace))  # resolve the card, so a leak has something to leak

    text = text_of(staged, SCOUT_SPEC)
    assert "courier" not in text
    assert "design rationale" not in text
    assert "forty thousand" not in text


def test_the_written_specification_still_lints_and_compiles(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    """*"The system SHALL NOT write a specification its own validator rejects."*"""
    ran(link_document(a_workspace(staged, platform), a_ref()))

    report = ran(lint_project("", spec_store=GitSpecStore(staged.working_copy)))
    compiled = ran(compile_spec(SCOUT_SPEC, spec_store=GitSpecStore(staged.working_copy)))

    assert not [finding for finding in report.findings if finding.violation.is_error]
    assert f"/d/{RATIONALE}" in compiled.text
    assert "design rationale" not in compiled.text


# --------------------------------------------------------------------------
# 3.2 — removing a link
# --------------------------------------------------------------------------


def test_unlinking_removes_the_reference_and_leaves_the_rest_of_the_file(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    workspace = a_workspace(staged, platform)
    before = text_of(staged, SCOUT_SPEC)
    ran(link_document(workspace, a_ref()))

    ran(unlink_document(workspace, RATIONALE))

    assert RATIONALE not in text_of(staged, SCOUT_SPEC)
    assert text_of(staged, SCOUT_SPEC).splitlines() == before.splitlines()
    assert platform.exists(WORKSPACE, RATIONALE), "the document itself is untouched"


# --------------------------------------------------------------------------
# 3.3 — project scope, over the real `.canon/project.yaml`
# --------------------------------------------------------------------------


def test_a_project_scoped_link_is_written_into_the_project_configuration(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    workspace = a_workspace(staged, platform)

    ran(link_document(workspace, a_ref(GDD), DocumentScope.PROJECT))

    config = text_of(staged, PROJECT_CONFIG)
    assert GDD in config
    assert "# the standing rules the whole team works under" in config
    assert "Read at 25 m." in config
    assert GDD not in text_of(staged, SCOUT_SPEC)


def test_a_project_scoped_link_is_listed_from_an_asset_and_distinguished(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    workspace = a_workspace(staged, platform)
    ran(link_document(workspace, a_ref(GDD), DocumentScope.PROJECT))
    ran(link_document(workspace, a_ref()))

    listing = ran(list_linked_documents(a_workspace(staged, platform)))

    assert [entry.ref.document_id for entry in listing.asset_links] == [RATIONALE]
    assert [entry.ref.document_id for entry in listing.project_links] == [GDD]
    assert all(entry.state is DocumentState.READABLE for entry in listing.entries)


def test_a_project_scoped_link_can_be_removed_again(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    workspace = a_workspace(staged, platform)
    ran(link_document(workspace, a_ref(GDD), DocumentScope.PROJECT))

    ran(unlink_document(a_workspace(staged, platform), GDD, DocumentScope.PROJECT))

    assert GDD not in text_of(staged, PROJECT_CONFIG)
    assert "Read at 25 m." in text_of(staged, PROJECT_CONFIG)


# --------------------------------------------------------------------------
# 3.8 — create and link, over a real repository
# --------------------------------------------------------------------------


def test_creating_a_document_commits_the_link_it_produced(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    recorded = ran(create_document_for_asset(a_workspace(staged, platform), ""))

    assert recorded.created is not None
    assert recorded.created.document_id in text_of(staged, SCOUT_SPEC)
    assert "mech_scout" in recorded.created.title
    assert COMMIT_PREFIX in log(staged, "-1", "--format=%s")


# --------------------------------------------------------------------------
# 3.9 — the rebuildable guarantee, against a real repository and a real index
# --------------------------------------------------------------------------


def test_destroying_every_rebuildable_store_loses_no_link(
    staged: Staged, platform: InMemoryDocumentPlatform, tmp_path: Path
) -> None:
    """Task 3.9 — the links are repository content; everything else is cache.

    The task says *"delete the document-card table"*, and there is no such
    table: D1 puts resolved display data in rebuildable storage, and the
    rebuildable storage a card lives in is the per-actor
    :class:`~cybercanon.application.use_cases.documents.CardCache`. So this
    destroys **both** halves of what is rebuildable — the cards *and* the search
    index — rebuilds the index by re-scanning the repository, and asserts the
    listing is the same one. The git repository is untouched throughout, which
    is the point: the references were never anywhere else.
    """
    workspace = a_workspace(staged, platform)
    ran(link_document(workspace, a_ref(RATIONALE)))
    ran(link_document(workspace, a_ref(GDD), DocumentScope.PROJECT))

    before = ran(list_linked_documents(workspace))
    assert workspace.cache.size > 0
    assert [entry.card.title for entry in before.entries] == [
        "mech_scout — design rationale",
        "Ronin — game design document",
    ]

    store = GitSpecStore(staged.working_copy)
    index = InMemorySearchIndex()
    ran(rebuild_index("", spec_store=store, search_index=index, project=PROJECT))

    # Destroy both halves of what is rebuildable: a brand-new index — the
    # deleted table — and the cards. Nothing here touches the repository.
    index = InMemorySearchIndex()
    workspace.cache.clear()
    ran(rebuild_index("", spec_store=store, search_index=index, project=PROJECT))

    after = ran(list_linked_documents(workspace))
    assert [entry.ref for entry in after.entries] == [entry.ref for entry in before.entries]
    assert [entry.scope for entry in after.entries] == [entry.scope for entry in before.entries]
    assert [entry.card.title for entry in after.entries] == [
        entry.card.title for entry in before.entries
    ]
    assert index.list_assets(project=PROJECT) != ()


def test_the_titles_are_resolved_again_rather_than_remembered(
    staged: Staged, platform: InMemoryDocumentPlatform
) -> None:
    """*"Their titles SHALL be resolved again from the document platform."*

    Asserted by making the platform disagree with what the cache held: a
    rename between the two listings shows through, which it could not do if
    anything durable were holding the old title.
    """
    workspace = a_workspace(staged, platform)
    ran(link_document(workspace, a_ref(RATIONALE)))
    ran(list_linked_documents(workspace))

    workspace.cache.clear()
    platform.rename(WORKSPACE, RATIONALE, "mech_scout — why it is a courier")

    after = ran(list_linked_documents(workspace))
    assert after.entries[0].card.title == "mech_scout — why it is a courier"
    assert RATIONALE in text_of(staged, SCOUT_SPEC)
    assert "why it is a courier" not in text_of(staged, SCOUT_SPEC)
