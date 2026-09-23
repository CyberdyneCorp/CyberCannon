"""What a document-link test has on the table, shared by the unit suite and the steps.

Its own module at the root of `tests/` for the reason `tests/views_world.py`
gives: the directories below have conftests of their own, so a shared name would
resolve to whichever pytest inserted into `sys.path` first.

The arrangement is the **real** write path with in-memory edges, exactly as
`tests/annotations_world.py` is: an in-memory repository host holding real
`asset.yaml` and `.canon/project.yaml` bytes, the adapter's own
comment-preserving reader and writer over them, the in-memory document platform
beside it, and the real use cases on top. Nothing here re-implements a rule, so
a scenario that passes here passes because the product does the thing.

Everything a scenario needs a *seam* for is a method on :class:`Documents`: the
platform unreachable, a document deleted or renamed at the source, a second
person who may not read it, a repository that refuses the write, and a
deployment with no platform configured at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from cybercanon.application.ports.document_platform import (
    NO_CREDENTIAL,
    Credential,
    DocumentPlatform,
    NullDocumentPlatform,
    UnavailabilityReason,
)
from cybercanon.application.ports.spec_store import PROJECT_CONFIG_PATH
from cybercanon.application.results import Result
from cybercanon.application.testing.document_platform import InMemoryDocumentPlatform
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.use_cases.documents import (
    CardCache,
    DocumentListing,
    DocumentWorkspace,
    RecordedLink,
    create_document_for_asset,
    link_document,
    list_document_revisions,
    list_linked_documents,
    unlink_document,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.documents import DocumentRef, DocumentScope
from cybercanon.domain.identity import Actor, ActorId
from views_world import PROJECT, SCOUT, SCOUT_DIR, RepositorySpecStore

SCOUT_SPEC = f"{SCOUT_DIR}/asset.yaml"

WORKSPACE = "w_production"

RAFA_SUBJECT = "auth|rafa"
BRUNO_SUBJECT = "auth|bruno"

RAFA_TOKEN = "token-rafa"
BRUNO_TOKEN = "token-bruno"

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
BRUNO = GitAuthor(name="Bruno", email="bruno@cyberdyne.com")

AUTHORS = {RAFA_SUBJECT: RAFA, BRUNO_SUBJECT: BRUNO}
TOKENS = {RAFA_SUBJECT: RAFA_TOKEN, BRUNO_SUBJECT: BRUNO_TOKEN}

AUTHORED = """\
schema_version: 1
id: mech_scout
name: Scout Mech      # renaming this is safe; the id is what everything refers to
status: modeling

# engineering fixed these at the kick-off
constraints:
  tri_budget: 12000
  lods: [8000, 4000]

design:
  role: scout
  sockets:
    - name: SOCKET_muzzle_l
      purpose: muzzle flash
"""
"""A hand-authored specification with a real `design` block and real comments.

The `design` block matters here rather than being scenery: *"no `design` field
SHALL have been added or altered"* is asserted against **this text**, so a link
that touched it would show up as a diff rather than as an opinion.
"""

PROJECT_CONFIG = """\
schema_version: 1
name: cyberdyne-game

# the standing rules the whole team works under
golden_rules:
  - Read at 25 m.
"""

RATIONALE = "d_rationale"
RESEARCH = "d_research"
PRIVATE = "d_private"
GDD = "d_gdd"

PROSE = (
    "The scout reads as a courier rather than as a brawler because the faction "
    "is logistics. We tried a heavier chassis in February and the team read it "
    "as a tank. The triangle budget should be about forty thousand, we think."
)
"""Several sentences of rationale — including a budget *in prose*.

That last sentence is the one the specification makes a scenario of: a document
stating a budget is not a constraint, and an export inside the *declared* budget
is valid however confidently the prose disagrees.
"""


def a_person(subject: str = RAFA_SUBJECT, name: str = "") -> Actor:
    """One resolved person entitled to this project."""
    return Actor(id=ActorId(subject), display_name=name or subject, projects=(PROJECT,))


RAFA_ACTOR = a_person(RAFA_SUBJECT, "Rafa")
BRUNO_ACTOR = a_person(BRUNO_SUBJECT, "Bruno")


@dataclass
class Documents:
    """Every port one document-link operation touches, and the seams a scenario needs."""

    host: InMemoryRepositoryHost
    spec_store: RepositorySpecStore
    platform: DocumentPlatform = field(default_factory=InMemoryDocumentPlatform)
    cache: CardCache = field(default_factory=CardCache)
    moment: datetime = field(default_factory=lambda: datetime(2026, 9, 22, 10, 0, tzinfo=UTC))
    notes: dict[str, object] = field(default_factory=dict)

    # -- the clock -------------------------------------------------------

    def clock(self) -> datetime:
        return self.moment

    def age(self, seconds: int) -> None:
        """Move the clock forward, so a cached card can outlive its lifetime."""
        self.moment += timedelta(seconds=seconds)

    # -- the workspace ---------------------------------------------------

    def workspace(
        self,
        actor: Actor = RAFA_ACTOR,
        *,
        asset_id: str = SCOUT,
        mapped: bool = True,
        credentialed: bool = True,
    ) -> DocumentWorkspace:
        return DocumentWorkspace(
            project=PROJECT,
            asset_id=asset_id,
            spec_store=self.spec_store,
            repository_host=self.host,
            platform=self.platform,
            credential=Credential(TOKENS[actor.subject]) if credentialed else NO_CREDENTIAL,
            actor=actor,
            author=AUTHORS.get(actor.subject) if mapped else None,
            default_workspace=WORKSPACE,
            clock=self.clock,
            cache=self.cache,
        )

    # -- operations ------------------------------------------------------

    def link(
        self,
        document_id: str = RATIONALE,
        *,
        actor: Actor = RAFA_ACTOR,
        scope: DocumentScope = DocumentScope.ASSET,
        url: str = "",
        mapped: bool = True,
    ) -> Result[RecordedLink]:
        return link_document(
            self.workspace(actor, mapped=mapped),
            DocumentRef(
                workspace=WORKSPACE,
                document_id=document_id,
                url=url or self.address(document_id),
            ),
            scope,
        )

    def unlink(
        self,
        document_id: str = RATIONALE,
        *,
        actor: Actor = RAFA_ACTOR,
        scope: DocumentScope = DocumentScope.ASSET,
    ) -> Result[RecordedLink]:
        return unlink_document(self.workspace(actor), document_id, scope)

    def listed(
        self, *, actor: Actor = RAFA_ACTOR, credentialed: bool = True
    ) -> Result[DocumentListing]:
        return list_linked_documents(self.workspace(actor, credentialed=credentialed))

    def revisions(self, document_id: str = RATIONALE, *, actor: Actor = RAFA_ACTOR) -> Result:
        return list_document_revisions(self.workspace(actor), document_id)

    def create(
        self, title: str = "", *, actor: Actor = RAFA_ACTOR, mapped: bool = True
    ) -> Result[RecordedLink]:
        return create_document_for_asset(self.workspace(actor, mapped=mapped), title)

    # -- seams -----------------------------------------------------------

    def unavailable(self, reason: UnavailabilityReason) -> None:
        """Make the platform fail this way for every call from now on."""
        self.platform.fail_with(reason)  # type: ignore[union-attr]

    def unconfigured(self) -> None:
        """The deployment that never set `CANON_ARCHE_ENABLED` (D4)."""
        self.platform = NullDocumentPlatform()

    def refuse_writes(self, reason: str = "the remote refused the push") -> None:
        """A repository that will not accept the commit — the D8 failure path."""
        self.host.make_unreachable(PROJECT, reason)

    # -- what landed -----------------------------------------------------

    def spec_text(self, path: str = SCOUT_SPEC) -> str:
        content = self.host.read(PROJECT, path, self.host.head(PROJECT))
        return content.decode("utf-8") if content else ""

    def project_text(self) -> str:
        return self.spec_text(PROJECT_CONFIG_PATH)

    def asset(self):
        return self.spec_store.load(SCOUT_SPEC).asset

    def address(self, document_id: str) -> str:
        return f"https://documents.invalid/w/{WORKSPACE}/d/{document_id}"


def a_world(
    *,
    spec: bytes = AUTHORED.encode(),
    config: bytes = PROJECT_CONFIG.encode(),
) -> Documents:
    """A project whose `mech_scout` is hand-authored and links nothing yet.

    The platform holds four documents: one Rafa may read, one he may not, one
    that gets deleted in the scenarios that need a deleted one, and a
    project-wide GDD. Every one of them is readable by somebody, so *"forbidden"*
    in a test means *this viewer may not*, never *nobody may*.
    """
    host = InMemoryRepositoryHost()
    host.add_project(PROJECT, {SCOUT_SPEC: spec, PROJECT_CONFIG_PATH: config})
    host.clone(PROJECT)
    platform = InMemoryDocumentPlatform()
    platform.add_actor(RAFA_TOKEN, RAFA_SUBJECT)
    platform.add_actor(BRUNO_TOKEN, BRUNO_SUBJECT)
    platform.add_document(
        WORKSPACE,
        RATIONALE,
        "mech_scout — design rationale",
        summary=PROSE,
        body=PROSE,
        readers=(RAFA_SUBJECT,),
    )
    platform.add_revision(WORKSPACE, RATIONALE, label="before retopo")
    platform.add_document(
        WORKSPACE,
        RESEARCH,
        "scout silhouette research",
        summary="Studies.",
        readers=(RAFA_SUBJECT,),
    )
    platform.add_document(WORKSPACE, PRIVATE, "unreleased faction bible", readers=(BRUNO_SUBJECT,))
    platform.add_document(WORKSPACE, GDD, "Ronin — game design document", readers=(RAFA_SUBJECT,))
    platform.permit_creation(RAFA_SUBJECT, WORKSPACE)
    return Documents(
        host=host,
        spec_store=RepositorySpecStore(host=host),
        platform=platform,
    )


def a_project_config(document_id: str = GDD) -> bytes:
    """`.canon/project.yaml` with one document linked at project scope, by hand.

    Authored as a person would author it rather than written through the use
    case, so that *reading* a project-scoped link is exercised independently of
    writing one.
    """
    return (
        PROJECT_CONFIG
        + "\ndocuments:\n"
        + f"  - workspace: {WORKSPACE}\n"
        + f"    id: {document_id}\n"
        + f"    url: https://documents.invalid/w/{WORKSPACE}/d/{document_id}\n"
        + f"    linked_by: {RAFA_SUBJECT}\n"
    ).encode()


def with_project_link(document_id: str = GDD) -> Documents:
    """A world where one document is already linked at project scope."""
    return a_world(config=a_project_config(document_id))


def with_links(world: Documents, *document_ids: str) -> Documents:
    """The same world, with these documents already linked to the asset."""
    for document_id in document_ids:
        result = world.link(document_id)
        assert getattr(result, "value", None) is not None, getattr(result, "message", result)
    return world


def a_ref(document_id: str, workspace: str = WORKSPACE) -> DocumentRef:
    return DocumentRef(
        workspace=workspace,
        document_id=document_id,
        url=f"https://documents.invalid/w/{workspace}/d/{document_id}",
    )


def without_platform(world: Documents) -> Documents:
    """The same world with no document platform configured at all (D4)."""
    return replace(world, platform=NullDocumentPlatform())
