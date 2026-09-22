"""Bringing concept views into the canon — the commit is the transaction (D2).

This is the first feature in the product that **writes to a game repository from
a server**, and the order it does things in is the whole design:

    resolve the author → validate everything → stage → commit → mirror → derive

Nothing is written until every image and every slot in the request has passed
(D2), so a failure before the commit has nothing to undo; and once the commit
has landed the view *is* ingested, so a failure after it has nothing to undo
either — the mirror and the thumbnails are derivable from the repository and are
reported as pending rather than as a failed upload. That is what makes
`concept-ingestion`'s *"neither a partial commit nor an orphan blob"* structural
instead of a cleanup routine somebody has to remember to write.

Four decisions from the change's design are load-bearing here and none of them
is re-argued:

* **D5 — attribution is a precondition, not a fallback.** The acting person is
  resolved to a git author *before* a single image is inspected. No mapping, no
  ingestion, and the refusal names the missing entry.
* **D10 — creating an asset writes identity and status only.** An upload naming
  an asset that does not exist writes `id`, `name`, `status: concept` and
  nothing else, in the same commit as the image. No `design`, no `constraints`,
  empty or otherwise: a scaffolded spec is a file full of fields that constrain
  nothing, and the empty scaffold is what people leave behind.
* **D11 — writes are serialised per working copy, and the slot's current hash is
  re-checked inside the critical section.** Two artists replacing `front` within
  the same second is an ordinary Friday, and the loser gets *"this slot changed
  while you were uploading"* rather than a lost image.
* **D12 — ingestion never consults a model.** There is no `LLMPort` or
  `VisionPort` in this module's imports and there is a structural test that says
  so, because an absence enforced by absence lasts until the first person who
  thinks auto-describing on upload would be a nice touch.

What this module deliberately does **not** do is touch an existing asset's
specification. A view is a file at a deterministic path (D4), so a project's
views are discovered by walking the repository — which is also what makes the
index's hash mapping rebuildable (D3) — and *"ingestion SHALL NOT modify any
authored field"* holds because there is no code path that could.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.image_inspector import ImageInspector
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.spec_store import ProjectConfig, SpecStore
from cybercanon.application.ports.thumbnail_renderer import (
    DEFAULT_SIZES,
    ThumbnailRenderer,
)
from cybercanon.application.ports.view_index import ViewIndex, ViewRow
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.hosted_repository import (
    AuthorUnmapped,
    Edit,
    write_back,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.annotations import AnchorState, Annotation
from cybercanon.domain.asset import AssetId
from cybercanon.domain.revisions import ContentHash, Revision, blob_key
from cybercanon.domain.status import Status
from cybercanon.domain.views import (
    EXTENSIONS,
    ImageFacts,
    IngestionLimits,
    InvalidSlotName,
    ViewSlot,
    carry_forward,
    check_image,
    concept_dir,
    replacement,
    view_path,
)
from cybercanon.domain.violations import Severity, SpecViolation

SCHEMA_VERSION = 1
"""The `schema_version:` a created specification declares (D10)."""

DEFAULT_ASSET_ROOT = "assets"
"""Where an asset created *by an upload* lands when the caller names no directory.

An existing asset is found where its `asset.yaml` already is, so this is only
ever consulted for D10's creation path. It is a parameter on every entry point
because a studio organises `characters/`, `props/` and `vehicles/` however it
likes, and a constant that could not be overridden would be this module having
an opinion about somebody else's repository layout.
"""

SLOT_INVALID = "slot.invalid"
SLOT_DUPLICATE = "slot.duplicate"
UPLOAD_EMPTY = "upload.empty"
ASSET_INVALID_ID = "asset.invalid_id"
"""Rule identifiers for the refusals this module raises rather than the domain."""


class ViewRejected(OperationFailed):
    """The request carries something this project does not accept.

    Carries **every** reason rather than the first: *"the whole request SHALL be
    rejected, naming each offending image and its reason"*, and a refusal that
    named one defect at a time would make a three-image upload a three-round
    negotiation.
    """

    kind = FailureKind.INVALID
    identifier = "view.rejected"

    def __init__(self, subject: str, violations: Sequence[SpecViolation]) -> None:
        super().__init__("; ".join(violation.message for violation in violations), subject)
        self.violations = tuple(violations)


class SlotChanged(OperationFailed):
    """Somebody replaced this slot between the request being prepared and committed.

    D11's explicit loser. A conflict rather than an invalid request: nothing
    about what was sent is wrong, and re-sending it against what is there now is
    exactly the right next move.
    """

    kind = FailureKind.CONFLICT
    identifier = "view.slot_changed"

    def __init__(self, slot: str, path: str) -> None:
        super().__init__(
            f"the {slot!r} slot changed while you were uploading; {path} is no longer "
            "the image this upload was prepared against",
            path,
        )
        self.slot = slot


class NoSuchView(OperationFailed):
    """That asset has no view in that slot — said out loud, never answered empty."""

    kind = FailureKind.NOT_FOUND
    identifier = "view.not_found"

    def __init__(self, asset_id: str, slot: str) -> None:
        super().__init__(f"asset {asset_id!r} has no view in the {slot!r} slot", slot)
        self.slot = slot


# --------------------------------------------------------------------------
# What a request carries, and what it produced
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UploadedImage:
    """One image as a request carries it: a slot name, bytes and a file name.

    `slot` is the **raw** name rather than a :class:`~cybercanon.domain.views.ViewSlot`,
    because `concept-ingestion` requires an upload to `Front View!` to be
    *rejected naming that value* — a type that refused to hold it would leave
    the refusal with nothing to name. `filename` is for messages only: format is
    decided from the content (D1), never from an extension.
    """

    slot: str
    content: bytes
    filename: str = ""

    @property
    def subject(self) -> str:
        """What a refusal calls this image."""
        return self.filename or f"the image for {self.slot!r}"


@dataclass(frozen=True)
class IngestedView:
    """One slot, after the commit: where it landed and what happened to its pins."""

    asset_id: str
    slot: ViewSlot
    path: str
    facts: ImageFacts
    replaced: bool = False
    removed_path: str = ""
    mirrored: bool = False
    carried: int = 0
    orphaned: int = 0

    @property
    def key(self) -> str:
        """Where the mirrored bytes live — derived from the digest alone (D3)."""
        return blob_key(self.facts.content_hash)

    @property
    def awaiting_mirror(self) -> bool:
        """`concept-ingestion`'s ordinary state, not an error (D2)."""
        return not self.mirrored


@dataclass(frozen=True)
class IngestionOutcome:
    """What one ingestion request did. One commit, or none at all.

    `unchanged` names the slots whose bytes were already what was uploaded:
    *"no new revision SHALL be created AND the result SHALL report the view as
    unchanged"*. A request whose every slot is unchanged produces no commit, and
    `revision` is then simply the head it was evaluated against.
    """

    project: str
    asset_id: str
    revision: Revision
    views: tuple[IngestedView, ...] = ()
    unchanged: tuple[str, ...] = ()
    created_asset: bool = False
    committed: bool = False
    commit_message: str = ""
    thumbnails_pending: bool = False
    mirror_reason: str = ""

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(view.path for view in self.views)

    @property
    def awaiting_mirror(self) -> tuple[str, ...]:
        """The views committed and not yet mirrored — reported, never failed."""
        return tuple(view.path for view in self.views if view.awaiting_mirror)

    @property
    def carried(self) -> int:
        """How many annotations survived this replacement (`view-versioning`)."""
        return sum(view.carried for view in self.views)

    @property
    def orphaned(self) -> int:
        """How many did not. Stated out loud, because the outcome is never silent."""
        return sum(view.orphaned for view in self.views)


@dataclass
class _Prepared:
    """One validated upload, before anything is written."""

    slot: ViewSlot | None
    image: UploadedImage
    facts: ImageFacts | None = None
    path: str = ""
    current_path: str = ""
    current: ContentHash | None = None
    before: ImageFacts | None = None
    violations: list[SpecViolation] = field(default_factory=list)

    @property
    def name(self) -> str:
        return str(self.slot) if self.slot is not None else self.image.slot

    @property
    def is_changed(self) -> bool:
        """Whether committing this would change anything at all."""
        return self.facts is not None and self.current != self.facts.content_hash


@dataclass(frozen=True)
class _Request:
    """Everything one ingestion needs, so each step below takes one argument."""

    project: str
    asset: AssetId
    uploads: tuple[UploadedImage, ...]
    repository_host: RepositoryHost
    spec_store: SpecStore
    image_inspector: ImageInspector
    author: GitAuthor
    limits: IngestionLimits
    blob_store: BlobStore | None
    thumbnail_renderer: ThumbnailRenderer | None
    view_index: ViewIndex | None
    subject: str
    agent: str
    asset_root: str
    name: str


@dataclass(frozen=True)
class _Target:
    """Where this asset is, and where its views go. Resolved once per request."""

    spec_path: str | None
    asset_dir: str
    revision: Revision
    annotations: tuple[Annotation, ...] = ()

    @property
    def creates_asset(self) -> bool:
        return self.spec_path is None


# --------------------------------------------------------------------------
# The use case
# --------------------------------------------------------------------------


@as_result
def ingest_views(
    project: str,
    asset_id: str,
    uploads: Sequence[UploadedImage],
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    image_inspector: ImageInspector,
    author: GitAuthor | None,
    limits: IngestionLimits | None = None,
    blob_store: BlobStore | None = None,
    thumbnail_renderer: ThumbnailRenderer | None = None,
    view_index: ViewIndex | None = None,
    subject: str = "",
    agent: str = "",
    asset_root: str = DEFAULT_ASSET_ROOT,
    name: str = "",
) -> IngestionOutcome:
    """Validate, commit, mirror and derive — in that order and no other (D2).

    `blob_store`, `thumbnail_renderer` and `view_index` are all optional, and
    their absence is a *local* wiring rather than a broken one: `canon add-view`
    stands in a working copy with none of the three, and *"with no blob storage
    configured at all, ingestion SHALL commit and the view SHALL be readable
    from the repository"* is specified behaviour rather than a degradation.
    """
    if author is None:
        raise AuthorUnmapped(subject or project, f"{asset_root}/{asset_id}")
    request = _Request(
        project=project,
        asset=_asset_id(asset_id),
        uploads=tuple(uploads),
        repository_host=repository_host,
        spec_store=spec_store,
        image_inspector=image_inspector,
        author=author,
        limits=limits or IngestionLimits(),
        blob_store=blob_store,
        thumbnail_renderer=thumbnail_renderer,
        view_index=view_index,
        subject=subject,
        agent=agent,
        asset_root=asset_root,
        name=name,
    )
    if not request.uploads:
        raise ViewRejected(asset_id, [_violation(UPLOAD_EMPTY, asset_id, _NOTHING_UPLOADED)])
    return _ingest(request)


def _ingest(request: _Request) -> IngestionOutcome:
    """The fixed order, and where the lock is held within it (D2, D11).

    **Preparation is outside the critical section and the commit is inside it**,
    which is the whole of D11: every image is inspected and every slot is
    resolved without blocking anybody, and then the slot's current hash is
    re-read *inside* the lock and compared with what the request was prepared
    against. A request prepared inside the lock could never observe a change,
    so the re-check would be a line that can never fail — which is the shape a
    concurrency guarantee takes when it does not work.

    Mirroring and derivation are outside it too, and for the ordinary reason: a
    slow object store must not hold the next artist's upload.
    """
    target = _target_of(request)
    prepared = _validated(request, target)
    changed = tuple(entry for entry in prepared if entry.is_changed)
    unchanged = tuple(entry.name for entry in prepared if not entry.is_changed)
    if not changed:
        return IngestionOutcome(
            project=request.project,
            asset_id=request.asset.value,
            revision=target.revision,
            unchanged=unchanged,
        )
    with request.repository_host.writer(request.project):
        written = _commit(request, target, changed)
    return _derived(request, written, unchanged)


def _target_of(request: _Request) -> _Target:
    """Where this asset lives at the head revision — or that it does not yet.

    Read from the **repository**, not the index: ingestion has to work on a
    laptop with no index at all, and D3 already requires every read that cannot
    find a mapping to fall back to the repository rather than report the thing
    as missing.
    """
    revision = request.repository_host.head(request.project)
    spec_path = locate_asset(request.asset.value, spec_store=request.spec_store, revision=revision)
    if spec_path is None:
        return _Target(None, f"{request.asset_root}/{request.asset}", revision)
    asset = request.spec_store.pinned(revision.value).load(spec_path).asset
    return _Target(spec_path, _directory_of(spec_path), revision, asset.annotations)


# --------------------------------------------------------------------------
# Validate — everything, before anything is written (D2)
# --------------------------------------------------------------------------


def _validated(request: _Request, target: _Target) -> tuple[_Prepared, ...]:
    """Every image and every slot. One pass, collecting every reason."""
    prepared = [_prepare(request, target, upload) for upload in request.uploads]
    violations = [violation for entry in prepared for violation in entry.violations]
    violations.extend(_duplicate_slots(prepared))
    if violations:
        raise ViewRejected(request.asset.value, violations)
    return tuple(prepared)


def _prepare(request: _Request, target: _Target, upload: UploadedImage) -> _Prepared:
    """One upload: its slot, its facts, where it would land and what is there now."""
    slot = _slot_of(upload.slot)
    if slot is None:
        return _Prepared(
            slot=None,
            image=upload,
            violations=[_violation(SLOT_INVALID, upload.slot, str(InvalidSlotName(upload.slot)))],
        )
    facts = request.image_inspector.inspect(upload.content, name=upload.subject)
    entry = _Prepared(slot=slot, image=upload, facts=facts)
    entry.violations.extend(check_image(facts, request.limits, upload.subject))
    entry.path = view_path(target.asset_dir, slot, facts.format)
    entry.current_path, entry.current, entry.before = _existing(request, target, slot)
    return entry


def _existing(
    request: _Request, target: _Target, slot: ViewSlot
) -> tuple[str, ContentHash | None, ImageFacts | None]:
    """What this slot holds now: its path, its digest and its facts, or nothing.

    Every extension the slot could be written under is looked for, because a
    replacement in a different format lands on a different path (D4) and a
    lookup that only tried the incoming format would see an empty slot and
    create a second file for the same view.
    """
    for candidate in _candidate_paths(target.asset_dir, slot):
        content = request.repository_host.read(request.project, candidate, target.revision)
        if content is not None:
            return (candidate, ContentHash.of(content), _facts_of(request, candidate, content))
    return ("", None, None)


def _candidate_paths(asset_dir: str, slot: ViewSlot) -> tuple[str, ...]:
    """Every path this slot could currently occupy, in a deterministic order."""
    directory = concept_dir(asset_dir)
    return tuple(
        f"{directory}/{slot}.{extension}" for extension in sorted(set(EXTENSIONS.values()))
    )


def _facts_of(request: _Request, path: str, content: bytes) -> ImageFacts | None:
    """The superseded image's facts, or ``None`` when they cannot be read.

    ``None`` rather than a raise: an image already in the repository that this
    inspector cannot read is not a reason to refuse somebody's upload, and the
    carry-forward rule simply has nothing to compare against — which orphans,
    because *carried* is a claim and that one cannot be made.
    """
    try:
        return request.image_inspector.inspect(content, name=path)
    except OperationFailed:
        return None


# --------------------------------------------------------------------------
# Stage and commit — once, or not at all (D2, D11)
# --------------------------------------------------------------------------


def _commit(request: _Request, target: _Target, prepared: Sequence[_Prepared]) -> IngestionOutcome:
    """D11's re-check, then one commit carrying every file in the request.

    The re-check asks the repository rather than trusting the read the request
    was prepared from, which is the only way *"the slot's current hash is
    re-checked before committing"* means anything.
    """
    _recheck(request, prepared)
    edits = [*_specification_edit(request, target), *_view_edits(prepared)]
    message = _message(request, prepared)
    outcome = write_back.raising(
        request.project,
        edits,
        repository_host=request.repository_host,
        author=request.author,
        message=message,
        subject=request.subject,
        agent=request.agent,
    )
    return IngestionOutcome(
        project=request.project,
        asset_id=request.asset.value,
        revision=outcome.revision,
        views=tuple(_ingested(request, target, entry) for entry in prepared),
        created_asset=target.creates_asset,
        committed=True,
        commit_message=message,
    )


def _recheck(request: _Request, prepared: Sequence[_Prepared]) -> None:
    """Refuse if anything moved since the request was prepared (D11).

    Re-read at the head *now* rather than at the revision the request was
    prepared against: the point is to notice a commit that landed in between,
    and a re-read pinned to the old revision would answer what the old revision
    held, which is what the request already knows.
    """
    head = request.repository_host.head(request.project)
    for entry in prepared:
        if not entry.current_path:
            continue
        content = request.repository_host.read(request.project, entry.current_path, head)
        if content is None or ContentHash.of(content) != entry.current:
            raise SlotChanged(entry.name, entry.current_path)


def _view_edits(prepared: Sequence[_Prepared]) -> list[Edit]:
    """The writes, plus the removal a format change turns a replacement into (D4)."""
    edits: list[Edit] = []
    for entry in prepared:
        removed, written = replacement(entry.current_path or None, entry.path)
        if removed is not None:
            edits.append(Edit(path=removed, content=None, based_on=entry.current))
        edits.append(
            Edit(
                path=written,
                content=entry.image.content,
                based_on=entry.current if removed is None else None,
            )
        )
    return edits


def _specification_edit(request: _Request, target: _Target) -> list[Edit]:
    """D10's minimal specification, or nothing at all when the asset exists.

    Nothing at all is the important half: an existing asset's `asset.yaml` is
    not in the edit list, so *"ingestion SHALL NOT modify any authored field"*
    is a property of the code rather than a rule somebody keeps.
    """
    if not target.creates_asset:
        return []
    return [
        Edit(
            path=f"{target.asset_dir}/asset.yaml",
            content=minimal_specification(request.asset, request.name),
            based_on=None,
        )
    ]


def _ingested(request: _Request, target: _Target, entry: _Prepared) -> IngestedView:
    """One committed slot, with the carry-or-orphan counts it produced (D6)."""
    assert entry.slot is not None and entry.facts is not None
    carried, orphaned = _annotation_outcome(target, entry)
    removed, _ = replacement(entry.current_path or None, entry.path)
    return IngestedView(
        asset_id=request.asset.value,
        slot=entry.slot,
        path=entry.path,
        facts=entry.facts,
        replaced=entry.current is not None,
        removed_path=removed or "",
        carried=carried,
        orphaned=orphaned,
    )


def _annotation_outcome(target: _Target, entry: _Prepared) -> tuple[int, int]:
    """How many pins this replacement carried and how many it orphaned.

    Nothing is written: the state is derived from the two revisions' aspect
    ratios exactly as D6 states it, and reporting it is *"the outcome is never
    silent"*. Nothing here can touch an exit state, which is D7.
    """
    assert entry.facts is not None
    if entry.current is None:
        return (0, 0)
    anchored = annotations_on(target.annotations, entry.name)
    if not anchored:
        return (0, 0)
    if entry.before is None:
        return (0, len(anchored))
    state = carry_forward(entry.before, entry.facts)
    carried = len(anchored) if state is AnchorState.CARRIED else 0
    return (carried, len(anchored) - carried)


def annotations_on(annotations: Sequence[Annotation], slot: str) -> tuple[Annotation, ...]:
    """The annotations anchored to one view slot, whatever anchor form they use."""
    return tuple(
        annotation for annotation in annotations if getattr(annotation.target, "view", None) == slot
    )


# --------------------------------------------------------------------------
# Mirror and derive — after the commit and never before it (D2)
# --------------------------------------------------------------------------


def _derived(
    request: _Request, written: IngestionOutcome, unchanged: tuple[str, ...]
) -> IngestionOutcome:
    """Both steps guarded, because the guard *is* the requirement.

    *"A subsequent mirroring or thumbnail failure SHALL be reported as a pending
    derived step and SHALL NOT be reported as a failed upload."*
    """
    mirrored, reason = _mirror(request, written)
    pending = _derive(request, written)
    return dataclass_replace(
        written,
        views=mirrored,
        unchanged=unchanged,
        thumbnails_pending=pending,
        mirror_reason=reason,
    )


def _mirror(request: _Request, written: IngestionOutcome) -> tuple[tuple[IngestedView, ...], str]:
    """Put the committed bytes in the mirror, or say why they are not there yet."""
    if request.blob_store is None:
        return (written.views, NO_BLOB_STORAGE)
    try:
        return (tuple(_mirrored(request, view, written.revision) for view in written.views), "")
    except Exception as failure:  # an unreachable mirror delays a mirror, never a view
        return (written.views, str(failure))


def _mirrored(request: _Request, view: IngestedView, revision: Revision) -> IngestedView:
    """One view into blob storage and, when there is one, into the index (D3)."""
    assert request.blob_store is not None
    content = request.repository_host.read(request.project, view.path, revision)
    if content is None:  # pragma: no cover — the commit that just landed wrote it
        return view
    stored = request.blob_store.put(content)
    _record(request, view, revision, stored.digest, stored.size_bytes)
    return dataclass_replace(view, mirrored=True)


def _record(
    request: _Request,
    view: IngestedView,
    revision: Revision,
    digest: ContentHash,
    byte_size: int,
) -> None:
    """The hash → (asset, slot, revision) row D3 puts in the rebuildable index."""
    if request.view_index is None:
        return
    request.view_index.record(
        ViewRow(
            project=request.project,
            asset_id=view.asset_id,
            slot=str(view.slot),
            revision=revision.value,
            path=view.path,
            digest=digest,
            byte_size=byte_size,
        )
    )


def _derive(request: _Request, written: IngestionOutcome) -> bool:
    """Derive thumbnails into blob storage. Never into the working copy (D9).

    There is no path in :meth:`ThumbnailRenderer.derive`'s signature and none
    here, so *"no thumbnail file SHALL appear in the repository working copy or
    in the commit"* is a property of the types rather than of a `.gitignore`.
    """
    if request.thumbnail_renderer is None or request.blob_store is None:
        return False
    try:
        for view in written.views:
            content = request.repository_host.read(request.project, view.path, written.revision)
            for thumbnail in request.thumbnail_renderer.derive(content or b"", DEFAULT_SIZES):
                request.blob_store.put(thumbnail.content, content_type=thumbnail.content_type)
    except Exception:  # a failed derivation is a pending step, not a failed upload
        return True
    return False


NO_BLOB_STORAGE = "no blob storage is configured for this project"
"""Why a committed view is not mirrored when nothing was wired. Not a failure."""


# --------------------------------------------------------------------------
# Removing a view — a revision like any other (`view-versioning`)
# --------------------------------------------------------------------------


@as_result
def remove_view(
    project: str,
    asset_id: str,
    slot: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    author: GitAuthor | None,
    subject: str = "",
    agent: str = "",
    asset_root: str = DEFAULT_ASSET_ROOT,
) -> IngestionOutcome:
    """Remove a slot's file, recording the removal as a revision of that view.

    *"Removing a view SHALL likewise be recorded as a revision, after which
    earlier revisions SHALL still be retrievable."* A deletion in git is a
    commit that touches the path, so the history keeps answering and nothing
    this module does can make an earlier revision unreachable.
    """
    if author is None:
        raise AuthorUnmapped(subject or project, f"{asset_root}/{asset_id}")
    named = _slot_of(slot)
    if named is None:
        raise ViewRejected(asset_id, [_violation(SLOT_INVALID, slot, str(InvalidSlotName(slot)))])
    with repository_host.writer(project):
        revision = repository_host.head(project)
        spec_path = locate_asset(asset_id, spec_store=spec_store, revision=revision)
        asset_dir = _directory_of(spec_path) if spec_path else f"{asset_root}/{asset_id}"
        path, digest = _held(project, asset_dir, named, repository_host, revision)
        outcome = write_back.raising(
            project,
            [Edit(path=path, content=None, based_on=digest)],
            repository_host=repository_host,
            author=author,
            message=f"{asset_id}: remove concept view {named}",
            subject=subject,
            agent=agent,
        )
        return IngestionOutcome(
            project=project,
            asset_id=asset_id,
            revision=outcome.revision,
            committed=True,
            commit_message=outcome.commit.message,
        )


def _held(
    project: str,
    asset_dir: str,
    slot: ViewSlot,
    repository_host: RepositoryHost,
    revision: Revision,
) -> tuple[str, ContentHash]:
    """The path this slot currently occupies, or an explicit not-found."""
    for candidate in _candidate_paths(asset_dir, slot):
        content = repository_host.read(project, candidate, revision)
        if content is not None:
            return (candidate, ContentHash.of(content))
    raise NoSuchView(asset_dir, str(slot))


# --------------------------------------------------------------------------
# Locating and creating an asset
# --------------------------------------------------------------------------


def locate_asset(asset_id: str, *, spec_store: SpecStore, revision: Revision) -> str | None:
    """The specification file this asset is written in, or ``None``.

    From the repository rather than the index, deliberately: ingestion has to
    work on a laptop with no index at all (`canon add-view`), and D3 already
    requires every read that cannot find a mapping to fall back to the
    repository rather than report the thing as missing. The index is an
    accelerator here, not an authority.
    """
    pinned = spec_store.pinned(revision.value)
    for path in pinned.specs_under(""):
        try:
            loaded = pinned.load(path)
        except OperationFailed:  # an unreadable spec is somebody else's finding
            continue
        if loaded.asset.id.value == asset_id:
            return path
    return None


def minimal_specification(asset: AssetId, name: str = "") -> bytes:
    """D10's whole output: identity, a name, and `status: concept`.

    Rendered here rather than through the YAML adapter for the reason
    :mod:`cybercanon.application.use_cases.requests` renders its documents in
    the application: four scalar fields need no round-trip writer, and reaching
    for one would put a third-party parser in a layer that must not have it. The
    moment a *person* edits this file, the adapter's round-trip reader and
    writer take over and preserve whatever they find.

    What is not here is the point. No `design`, no `constraints`, not even
    empty: the golden rule says every declared field must constrain art,
    constrain code or be checkable, an empty block does none of the three, and
    an empty scaffold is what people leave behind.
    """
    return (
        f"schema_version: {SCHEMA_VERSION}\n"
        f"id: {asset}\n"
        f"name: {name or asset}\n"
        f"status: {Status.CONCEPT}\n"
    ).encode()


def limits_of(project: ProjectConfig) -> IngestionLimits:
    """What this project accepts, merged over the defaults in the domain.

    One merge, in one place: `.canon/project.yaml` is read by the store, turned
    into neutral optional values by the adapter, and combined with the defaults
    by :meth:`~cybercanon.domain.views.IngestionLimits.declared`. A second place
    that filled in a default would be a second set of defaults.
    """
    declared = project.ingestion
    if declared is None:
        return IngestionLimits()
    return IngestionLimits.declared(
        accepted_formats=declared.accepted_formats,
        max_bytes=declared.max_bytes,
        max_dimension=declared.max_dimension,
    )


def view_reference(view: IngestedView, revision: Revision) -> dict[str, str]:
    """A view's presented identity, including the content hash shown (D8).

    *"A view's presented identity SHALL include the content hash of the revision
    being shown, so that a cached image can be recognised as superseded."* One
    function, so that no surface invents its own shape and drops the hash.
    """
    return {
        "asset": view.asset_id,
        "slot": str(view.slot),
        "path": view.path,
        "revision": revision.value,
        "content_hash": view.facts.content_hash.labelled,
        "key": view.key,
    }


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------

_NOTHING_UPLOADED = "an ingestion request carries at least one image"


def _slot_of(name: str) -> ViewSlot | None:
    try:
        return ViewSlot(name)
    except InvalidSlotName:
        return None


def _violation(rule_id: str, observed: str, message: str) -> SpecViolation:
    return SpecViolation(
        rule_id=rule_id,
        severity=Severity.ERROR,
        subject=observed,
        message=message,
        observed=observed,
    )


def _duplicate_slots(prepared: Sequence[_Prepared]) -> list[SpecViolation]:
    """Two images claiming one slot is a request nobody can satisfy."""
    seen: set[str] = set()
    found: list[SpecViolation] = []
    for entry in prepared:
        if entry.slot is None:
            continue
        name = entry.name
        if name in seen:
            found.append(
                _violation(
                    SLOT_DUPLICATE,
                    name,
                    f"two images in this request name the slot {name!r}; "
                    "a slot holds exactly one view",
                )
            )
        seen.add(name)
    return found


def _asset_id(asset_id: str) -> AssetId:
    try:
        return AssetId(asset_id)
    except ValueError as error:
        raise ViewRejected(
            asset_id, [_violation(ASSET_INVALID_ID, asset_id, str(error))]
        ) from error


def _message(request: _Request, prepared: Sequence[_Prepared]) -> str:
    """*"The commit message SHALL name the asset and every slot written."*"""
    slots = ", ".join(sorted(entry.name for entry in prepared))
    return f"{request.asset}: concept views {slots}"


def _directory_of(spec_path: str) -> str:
    head, _, _ = spec_path.rpartition("/")
    return head


__all__ = [
    "ASSET_INVALID_ID",
    "DEFAULT_ASSET_ROOT",
    "NO_BLOB_STORAGE",
    "SCHEMA_VERSION",
    "SLOT_DUPLICATE",
    "SLOT_INVALID",
    "UPLOAD_EMPTY",
    "IngestedView",
    "IngestionOutcome",
    "NoSuchView",
    "SlotChanged",
    "UploadedImage",
    "ViewRejected",
    "annotations_on",
    "ingest_views",
    "limits_of",
    "locate_asset",
    "minimal_specification",
    "remove_view",
    "view_reference",
]
