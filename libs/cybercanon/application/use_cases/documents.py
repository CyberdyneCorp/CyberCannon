"""Linking long-form documents to an asset or a project — one commit per link.

Every operation here has the same shape as the annotation write path, and for
the same reason: a link is **authored content in the repository**, so adding one
is a commit attributed to a person, and deleting the index never loses it.

* `link_document` and `unlink_document` write the reference into the asset's
  specification (or the project's configuration) through `SpecStore`.
* `list_linked_documents` reads the references from the repository and asks the
  platform — **with the viewer's own credential** (D2) — what they currently
  are. What comes back is a :class:`~cybercanon.domain.documents.DocumentCard`,
  and a card is cache: it lives in the per-actor display cache (D3) and nowhere
  else.
* `create_document_for_asset` creates remotely and then links, in that order
  (D8), because a reference to a document that does not exist is forever and an
  orphan untitled document is visible, harmless and deletable by its creator.
* `list_document_revisions` reads the document platform's **own** version
  history. It is a read through the platform and never a copy: CyberCanon links
  to the history the platform keeps rather than keeping a second one that can
  disagree with it.

Three boundaries are structural rather than remembered:

* **No function here accepts a document body** (D9), and none can: the port has
  no method that returns one.
* **No function here writes a resolved title or summary anywhere durable.** The
  only thing that reaches `SpecStore` is a
  :class:`~cybercanon.domain.documents.DocumentRef`, which has no member that
  could hold either.
* **Nothing branches on whether the platform is configured** (D4). An absent
  platform is :class:`~cybercanon.application.ports.document_platform.NullDocumentPlatform`,
  whose answers travel the same path as an outage's.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.document_platform import (
    NO_CREDENTIAL,
    CreatedDocument,
    Credential,
    DocumentPlatform,
    NullDocumentPlatform,
    PlatformUnavailable,
    ResolvedDocument,
    UnavailabilityReason,
)
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.spec_store import (
    PROJECT_CONFIG_PATH,
    SpecDocument,
    SpecStore,
)
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.hosted_repository import (
    AuthorUnmapped,
    Edit,
    WriteConflict,
    write_back,
)
from cybercanon.application.use_cases.ingest_views import locate_asset
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import Asset
from cybercanon.domain.documents import (
    PLACEMENT_GUIDANCE,
    ContentPlacement,
    DocumentCard,
    DocumentHistory,
    DocumentRef,
    DocumentRevision,
    DocumentScope,
    DocumentState,
    LinkedDocument,
    find_document,
    linked_documents,
    ordered_refs,
    placement_of,
    unresolved_card,
    without_document,
)
from cybercanon.domain.identity import Actor
from cybercanon.domain.revisions import ContentHash, Revision

COMMIT_PREFIX = "document"
"""What every document-link commit's message begins with, so a log can filter."""

DEFAULT_CARD_TTL = timedelta(minutes=5)
"""How long a resolved card is served before it is asked for again (D3).

Short on purpose. The cache exists to keep one page render from making the same
request four times, not to remember titles: *"a document renamed at the platform
is displayed under its new title on the next view after the cache lifetime"*,
and a long lifetime would make that sentence mean *tomorrow*.
"""

WRITE_ATTEMPTS = 2
"""The ordinary attempt and one replay against what somebody else just wrote."""


# --------------------------------------------------------------------------
# Failures
# --------------------------------------------------------------------------


class AssetNotFound(OperationFailed):
    """No specification in this project declares that asset."""

    kind = FailureKind.NOT_FOUND
    identifier = "asset.not_found"

    def __init__(self, project: str, asset_id: str) -> None:
        super().__init__(f"no asset {asset_id!r} is declared in project {project!r}", asset_id)


class DocumentLinkNotFound(OperationFailed):
    """No link to that document is recorded where the caller looked."""

    kind = FailureKind.NOT_FOUND
    identifier = "document_link.not_found"

    def __init__(self, subject: str, document_id: str) -> None:
        super().__init__(f"no document {document_id!r} is linked to {subject}", document_id)


class DocumentLinkConflict(OperationFailed):
    """The file moved under two attempts, and nothing was written."""

    kind = FailureKind.CONFLICT
    identifier = "document_link.conflict"

    def __init__(self, path: str) -> None:
        super().__init__(
            f"{path} changed while the link was being written; nothing was recorded",
            path,
        )


class DocumentCreatedButNotLinked(OperationFailed):
    """The document exists and the reference could not be written (D8).

    The whole point of the failure is the two attributes: an orphan document is
    only an acceptable cost if the person is told **which** document it is and
    **where** it is, so they can delete it or link it by hand.
    """

    kind = FailureKind.CONFLICT
    identifier = "document.created_but_not_linked"

    def __init__(self, created: CreatedDocument, reason: str) -> None:
        super().__init__(
            f"the document {created.title!r} was created at {created.url} but the link "
            f"could not be written into the specification: {reason}. It is not lost — "
            "open it at that address to link it by hand or delete it",
            created.document_id,
        )
        self.created = created
        self.reason = reason


# --------------------------------------------------------------------------
# The display cache — keyed by (reference, actor), never by reference (D3)
# --------------------------------------------------------------------------


@dataclass
class CardCache:
    """Resolved cards, per viewer, with a short lifetime.

    Keying by `(reference, actor)` is what makes the permission leak
    structurally impossible rather than dependent on a check nobody re-reads: a
    card Rafa resolved is stored under Rafa, and Bruno's first view is a cold
    resolve whatever Rafa already saw. The accepted cost is D3's — hit rate
    divided by team size, which at a handful of links per asset is a handful of
    requests.

    It is **rebuildable storage**: dropping it entirely changes nothing but
    latency, which is exactly what *"resolved display data is disposable"*
    requires of it.
    """

    ttl: timedelta = DEFAULT_CARD_TTL
    _entries: dict[tuple[str, str, str], tuple[datetime, DocumentCard]] = field(
        default_factory=dict
    )

    def get(self, ref: DocumentRef, actor: str, now: datetime) -> DocumentCard | None:
        """This actor's card for this reference, while it is still fresh."""
        entry = self._entries.get(self._key(ref, actor))
        if entry is None:
            return None
        resolved_at, card = entry
        if now - resolved_at >= self.ttl:
            self._entries.pop(self._key(ref, actor), None)
            return None
        return card

    def put(self, ref: DocumentRef, actor: str, card: DocumentCard, now: datetime) -> None:
        self._entries[self._key(ref, actor)] = (now, card)

    def clear(self) -> None:
        """Throw the whole cache away. Nothing durable is lost, by construction."""
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)

    @staticmethod
    def _key(ref: DocumentRef, actor: str) -> tuple[str, str, str]:
        return (ref.workspace, ref.document_id, actor)


# --------------------------------------------------------------------------
# What an operation is given, and what comes back
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentWorkspace:
    """Everything one document-link operation needs, so each step takes one argument."""

    project: str
    asset_id: str
    spec_store: SpecStore
    repository_host: RepositoryHost | None = None
    platform: DocumentPlatform = field(default_factory=NullDocumentPlatform)
    credential: Credential = NO_CREDENTIAL
    actor: Actor | None = None
    author: GitAuthor | None = None
    agent: str = ""
    default_workspace: str = ""
    """The platform workspace a newly created document is made in.

    Configuration rather than repository content, for the reason `project.md`
    gives for every other address: a workspace identifier read out of a file a
    commit can change is an address that stops working after a commit.
    """

    clock: Clock = system_clock
    cache: CardCache = field(default_factory=CardCache)

    @property
    def subject_id(self) -> str:
        """The identity subject a link is attributed to, and the cache is keyed by."""
        return self.actor.subject if self.actor is not None else ""

    def now(self) -> datetime:
        return self.clock()

    def stamp(self) -> str:
        """The moment this operation happened, as the file records it."""
        return self.now().replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class DocumentListing:
    """One asset's links — its own and the project's — as this viewer sees them.

    `unavailable_reason` is the distinguishing half of *"the feature reports
    itself unavailable and names the reason"*: the entries are always present
    and always openable, and this says why none of them carries a title.
    """

    project: str
    asset_id: str
    path: str = ""
    entries: tuple[LinkedDocument, ...] = ()
    unavailable_reason: UnavailabilityReason | None = None
    actor: str = ""
    guidance: str = PLACEMENT_GUIDANCE

    @property
    def is_available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def asset_links(self) -> tuple[LinkedDocument, ...]:
        return tuple(entry for entry in self.entries if entry.scope is DocumentScope.ASSET)

    @property
    def project_links(self) -> tuple[LinkedDocument, ...]:
        return tuple(entry for entry in self.entries if entry.scope is DocumentScope.PROJECT)

    @property
    def refs(self) -> tuple[DocumentRef, ...]:
        return tuple(entry.ref for entry in self.entries)

    def entry(self, document_id: str) -> LinkedDocument | None:
        return next((entry for entry in self.entries if entry.ref.document_id == document_id), None)


@dataclass(frozen=True)
class RecordedLink:
    """A link as it now stands, and the commit that recorded it."""

    project: str
    scope: DocumentScope
    path: str
    ref: DocumentRef
    revision: str = ""
    committed: bool = True
    created: CreatedDocument | None = None

    @property
    def document_id(self) -> str:
        return self.ref.document_id


# --------------------------------------------------------------------------
# What a person may do with a linked document — two things, and no third
# --------------------------------------------------------------------------

OPEN = "open"
UNLINK = "unlink"

AVAILABLE_ACTIONS: tuple[str, ...] = (OPEN, UNLINK)
"""*"The only available actions SHALL be opening it at the document platform and
removing the link."*

A closed tuple rather than a convention, so a surface that offered an editor
would have to add a member here and explain why — which is the review D9 wants
to happen.
"""


def actions_for(entry: LinkedDocument) -> tuple[str, ...]:
    """What may be done to this link from inside CyberCanon.

    The same two whatever the link's scope or state: a forbidden or deleted link
    is still openable — the platform says what it says — and still removable.
    There is no branch here because there is no third action to branch towards.
    """
    return AVAILABLE_ACTIONS if entry.ref.url else ()


def where_to_write(statement: str) -> ContentPlacement:
    """Where this statement belongs — the golden rule, asked at authoring time."""
    return placement_of(statement)


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@as_result
def list_linked_documents(workspace: DocumentWorkspace) -> DocumentListing:
    """Every document linked to this asset and to its project, in a fixed order.

    The repository half never depends on the platform half: the references are
    read first and completely, and a platform that is down, unconfigured or
    refusing the credential changes what each entry *says about itself* and
    nothing about which entries there are.
    """
    loaded = _load(workspace)
    project = workspace.spec_store.load_project(loaded.path)
    cards, reason = _cards(workspace, (*loaded.asset.documents, *project.documents))
    return DocumentListing(
        project=workspace.project,
        asset_id=workspace.asset_id,
        path=loaded.path,
        entries=linked_documents(loaded.asset.documents, project.documents, cards),
        unavailable_reason=reason,
        actor=workspace.subject_id,
    )


@as_result
def list_document_revisions(workspace: DocumentWorkspace, document_id: str) -> DocumentHistory:
    """The linked document's own version history, read through the platform.

    Nothing is stored. `document-platform` keeps the body, the history and the
    comments at the platform, and this surfaces the history it already keeps so
    that *"versioned long-form design documentation"* is met by linking to a
    real history rather than by inventing a second one here.
    """
    listing = list_linked_documents.raising(workspace)
    entry = listing.entry(document_id)
    if entry is None:
        raise DocumentLinkNotFound(workspace.asset_id, document_id)
    if entry.state is not DocumentState.READABLE:
        return DocumentHistory(ref=entry.ref, state=entry.state)
    return DocumentHistory(
        ref=entry.ref,
        revisions=_revisions(workspace, entry.ref),
        state=DocumentState.READABLE,
    )


def _revisions(workspace: DocumentWorkspace, ref: DocumentRef) -> tuple[DocumentRevision, ...]:
    try:
        return tuple(workspace.platform.revisions(ref, workspace.credential))
    except PlatformUnavailable:
        return ()


def _cards(
    workspace: DocumentWorkspace, refs: Sequence[DocumentRef]
) -> tuple[dict[tuple[str, str], DocumentCard], UnavailabilityReason | None]:
    """This viewer's card per reference, from the cache or from the platform (D3)."""
    if not refs:
        return {}, None
    now = workspace.now()
    actor = workspace.subject_id
    cached = {
        ref.key: card for ref in refs if (card := workspace.cache.get(ref, actor, now)) is not None
    }
    cold = ordered_refs(ref for ref in refs if ref.key not in cached)
    if not cold:
        return cached, None
    resolved, reason = _resolve(workspace, cold)
    for ref in cold:
        card = _card(ref, resolved.get(ref.key), reason, workspace.stamp())
        cached[ref.key] = card
        if card.state is DocumentState.READABLE:
            workspace.cache.put(ref, actor, card, now)
    return cached, reason


def _resolve(
    workspace: DocumentWorkspace, refs: Sequence[DocumentRef]
) -> tuple[dict[tuple[str, str], ResolvedDocument], UnavailabilityReason | None]:
    """Ask the platform, and turn *it did not answer at all* into a reason."""
    try:
        answers = workspace.platform.resolve(tuple(refs), workspace.credential)
    except PlatformUnavailable as unavailable:
        return {}, unavailable.reason
    return {answer.key: answer for answer in answers}, None


def _card(
    ref: DocumentRef,
    resolved: ResolvedDocument | None,
    reason: UnavailabilityReason | None,
    stamp: str,
) -> DocumentCard:
    """One reference as a card. A card never carries more than its state allows."""
    if resolved is None:
        return unresolved_card(ref, reason.state if reason else DocumentState.UNREACHABLE)
    return DocumentCard(
        ref=ref,
        title=resolved.title,
        summary=resolved.summary,
        state=resolved.state,
        resolved_at=stamp,
    )


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


@as_result
def link_document(
    workspace: DocumentWorkspace,
    ref: DocumentRef,
    scope: DocumentScope = DocumentScope.ASSET,
) -> RecordedLink:
    """Record one reference as authored content, attributed to the acting person.

    Nothing is fetched: linking a document does not ask the platform whether it
    exists, because a link to a document the viewer cannot see is a perfectly
    ordinary thing to author and a check here would refuse it.
    """
    attributed = ref.attributed(workspace.subject_id, workspace.stamp())
    if scope is DocumentScope.PROJECT:
        return _write_project(
            workspace, _added(attributed), attributed, f"linked {ref.document_id}"
        )
    return _write_asset(
        workspace,
        lambda asset: replace(asset, documents=_added(attributed)(asset.documents)),
        f"linked {ref.document_id}",
        attributed,
    )


@as_result
def unlink_document(
    workspace: DocumentWorkspace,
    document_id: str,
    scope: DocumentScope = DocumentScope.ASSET,
) -> RecordedLink:
    """Remove one reference. The document at the platform is never touched.

    There is no call to the platform on this path at all — not a delete, not a
    notification — which is *"the document at the document platform SHALL NOT be
    modified or deleted"* asserted by the absence of a line rather than by a
    comment.
    """
    if scope is DocumentScope.PROJECT:
        return _unlink_project(workspace, document_id)
    loaded = _load(workspace)
    existing = find_document(loaded.asset.documents, document_id)
    if existing is None:
        raise DocumentLinkNotFound(workspace.asset_id, document_id)
    return _write_asset(
        workspace,
        lambda asset: replace(asset, documents=without_document(asset.documents, document_id)),
        f"unlinked {document_id}",
        existing,
    )


@as_result
def create_document_for_asset(workspace: DocumentWorkspace, title: str = "") -> RecordedLink:
    """Create an empty, pre-titled document and link it, in that order (D8).

    A creation the platform refuses writes nothing at all, and a link that fails
    after a successful creation reports the created document by name and
    address. The reverse order — reserve a reference, then create — would put a
    link to a non-existent document into git, where it lives forever.
    """
    created = _create(workspace, title or default_title(workspace.asset_id))
    ref = DocumentRef(
        workspace=created.workspace,
        document_id=created.document_id,
        url=created.url,
        linked_by=workspace.subject_id,
        linked_at=workspace.stamp(),
    )
    try:
        recorded = _write_asset(
            workspace,
            lambda asset: replace(asset, documents=_added(ref)(asset.documents)),
            f"linked {ref.document_id}",
            ref,
        )
    except OperationFailed as failure:
        raise DocumentCreatedButNotLinked(created, failure.message) from failure
    return replace(recorded, created=created)


def default_title(asset_id: str) -> str:
    """What a document created from an asset page is called before anybody types.

    *"Pre-titled from the asset's identity"* — the asset id and nothing
    generated: a title assembled from a model would be derived content sitting
    in the one place the golden rule says derived content must not be.
    """
    return f"{asset_id} — design document"


def _create(workspace: DocumentWorkspace, title: str) -> CreatedDocument:
    """The one write this integration has (D10), under the person's own authority."""
    return workspace.platform.create(workspace.default_workspace, title, workspace.credential)


def _added(ref: DocumentRef) -> Callable[[Sequence[DocumentRef]], tuple[DocumentRef, ...]]:
    """Append this reference, replacing any earlier link to the same document."""

    def apply(existing: Sequence[DocumentRef]) -> tuple[DocumentRef, ...]:
        return ordered_refs((*without_document(existing, ref.document_id), ref))

    return apply


# --------------------------------------------------------------------------
# The two write paths — an asset's file, and the project's configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Loaded:
    """The asset this operation acts on: its path, its bytes and its meaning."""

    path: str
    document: SpecDocument
    revision: Revision

    @property
    def asset(self) -> Asset:
        return self.document.asset

    @property
    def based_on(self) -> ContentHash:
        return ContentHash.of(self.document.content)


def _load(workspace: DocumentWorkspace) -> _Loaded:
    """Where this asset is, and exactly what its file holds right now."""
    host = _host(workspace)
    revision = host.head(workspace.project)
    path = locate_asset(workspace.asset_id, spec_store=workspace.spec_store, revision=revision)
    if path is None:
        raise AssetNotFound(workspace.project, workspace.asset_id)
    content = host.read(workspace.project, path, revision)
    if content is None:
        raise AssetNotFound(workspace.project, workspace.asset_id)
    return _Loaded(
        path=path,
        document=workspace.spec_store.parse_document(path, content),
        revision=revision,
    )


def _host(workspace: DocumentWorkspace) -> RepositoryHost:
    if workspace.repository_host is None:
        raise AuthorUnmapped(workspace.subject_id, workspace.asset_id)
    return workspace.repository_host


def _write_asset(
    workspace: DocumentWorkspace,
    apply: Callable[[Asset], Asset],
    summary: str,
    ref: DocumentRef,
) -> RecordedLink:
    """One edit to one specification file, as one attributed commit."""
    if workspace.author is None:
        raise AuthorUnmapped(workspace.subject_id, workspace.asset_id)
    for attempt in range(1, WRITE_ATTEMPTS + 1):
        loaded = _load(workspace)
        asset = apply(loaded.asset)
        if asset == loaded.asset:
            return RecordedLink(
                project=workspace.project,
                scope=DocumentScope.ASSET,
                path=loaded.path,
                ref=ref,
                revision=loaded.revision.value,
                committed=False,
            )
        content = workspace.spec_store.edited(loaded.document, asset)
        try:
            written = _commit(workspace, loaded.path, content, loaded.based_on, summary)
        except WriteConflict:
            if attempt == WRITE_ATTEMPTS:
                raise DocumentLinkConflict(loaded.path) from None
            continue
        return RecordedLink(
            project=workspace.project,
            scope=DocumentScope.ASSET,
            path=loaded.path,
            ref=ref,
            revision=written,
        )
    raise DocumentLinkConflict(workspace.asset_id)  # pragma: no cover - the loop is total


def _write_project(
    workspace: DocumentWorkspace,
    apply: Callable[[Sequence[DocumentRef]], tuple[DocumentRef, ...]],
    ref: DocumentRef,
    summary: str,
) -> RecordedLink:
    """One edit to `.canon/project.yaml`, as one attributed commit."""
    if workspace.author is None:
        raise AuthorUnmapped(workspace.subject_id, PROJECT_CONFIG_PATH)
    host = _host(workspace)
    revision = host.head(workspace.project)
    content = host.read(workspace.project, PROJECT_CONFIG_PATH, revision)
    existing = workspace.spec_store.load_project("").documents
    documents = apply(existing)
    edited = workspace.spec_store.edited_project(content or b"", documents)
    written = _commit(
        workspace,
        PROJECT_CONFIG_PATH,
        edited,
        ContentHash.of(content) if content is not None else None,
        summary,
    )
    return RecordedLink(
        project=workspace.project,
        scope=DocumentScope.PROJECT,
        path=PROJECT_CONFIG_PATH,
        ref=ref,
        revision=written,
    )


def _unlink_project(workspace: DocumentWorkspace, document_id: str) -> RecordedLink:
    existing = workspace.spec_store.load_project("").documents
    ref = find_document(existing, document_id)
    if ref is None:
        raise DocumentLinkNotFound(workspace.project, document_id)
    return _write_project(
        workspace,
        lambda refs: without_document(refs, document_id),
        ref,
        f"unlinked {document_id}",
    )


def _commit(
    workspace: DocumentWorkspace,
    path: str,
    content: bytes,
    based_on: ContentHash | None,
    summary: str,
) -> str:
    written = write_back.raising(
        workspace.project,
        [Edit(path=path, content=content, based_on=based_on)],
        repository_host=_host(workspace),
        author=workspace.author,
        message=commit_message(workspace.asset_id, summary),
        subject=workspace.subject_id,
        agent=workspace.agent,
    )
    return written.revision.value


def commit_message(asset_id: str, summary: str) -> str:
    """`document(mech_scout): linked d_1` — filterable in a log and in a blame."""
    return f"{COMMIT_PREFIX}({asset_id}): {summary}"


__all__ = [
    "AVAILABLE_ACTIONS",
    "COMMIT_PREFIX",
    "DEFAULT_CARD_TTL",
    "OPEN",
    "UNLINK",
    "WRITE_ATTEMPTS",
    "AssetNotFound",
    "CardCache",
    "DocumentCreatedButNotLinked",
    "DocumentLinkConflict",
    "DocumentLinkNotFound",
    "DocumentListing",
    "DocumentWorkspace",
    "RecordedLink",
    "actions_for",
    "commit_message",
    "create_document_for_asset",
    "default_title",
    "link_document",
    "list_document_revisions",
    "list_linked_documents",
    "unlink_document",
    "where_to_write",
]
