"""The revision history of a concept view — reads over git, and nothing invented.

A view is a file in the repository (D4), so its history *is* git's history of
one path. This module is therefore deliberately thin: listing, retrieving and
comparing revisions are four reads over
:meth:`~cybercanon.application.ports.repository_host.RepositoryHost.history`,
and the only rules in it are the ones `view-versioning` states in so many words.

Five of them, and each is a sentence rather than a convenience:

* **Nothing destroys.** A replacement writes the same path and a removal is a
  revision like any other, so there is no operation here — and none in
  ingestion — that can make an earlier revision unreachable.
* **Exactly one current revision, unless the view was removed.** Then none is,
  and the listing says the view was removed rather than that it never existed.
* **A historical revision is labelled historical**, and an identifier that names
  no revision of this view produces an explicit not-found naming it — *"never
  the current revision as a fallback"*, which is the failure mode that would
  make a superseded image look current.
* **Comparison presents the older revision first** regardless of argument order,
  and comparing a revision with itself reports the two as identical rather than
  failing.
* **Truncated history is reported, never presented as complete.** A shallow
  working copy lists what it has and names the point earlier revisions are
  unavailable from.

And one that is not about history at all: **the carry-or-orphan state of an
annotation is derived, never stored** (D6, D7). It is a pure function of the
aspect ratios along the chain of revisions from the one the annotation was
authored against to the current one, so it cannot drift from the images, it
survives an index rebuild by construction, and ingestion does not have to write
to `asset.yaml` — which is what lets *"ingestion SHALL NOT modify any authored
field"* and *"the resulting state SHALL be visible on the annotation"* both be
true. The one thing that *is* durable is a **re-anchoring**, because a person
did it: it is repository content, written as one file under `.canon/`, exactly
as an asset request is.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.image_inspector import ImageInspector
from cybercanon.application.ports.repository_host import (
    FileHistory,
    FileRevision,
    RepositoryHost,
)
from cybercanon.application.ports.spec_store import ProjectConfig, SpecStore
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.hosted_repository import (
    AuthorUnmapped,
    Edit,
    write_back,
)
from cybercanon.application.use_cases.ingest_views import (
    DEFAULT_ASSET_ROOT,
    NoSuchView,
    annotations_on,
    locate_asset,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.annotations import AnchorState, Annotation
from cybercanon.domain.revisions import ContentHash, Revision
from cybercanon.domain.views import (
    DEFAULT_ASPECT_TOLERANCE,
    EXTENSIONS,
    ConceptView,
    ImageFacts,
    InvalidSlotName,
    ViewRevision,
    ViewSlot,
    concept_dir,
    marked_current,
)

REANCHOR_DIR = ".canon/reanchors"
"""Where a re-anchoring is recorded — repository content, like a request (D7).

A person moved a pin, so the record of it is durable, attributed and reviewable.
It is *not* written into `asset.yaml`, because ingestion and triage must be able
to run without rewriting an authored file, and because the annotation's text and
exit state — the things a person wrote — stay exactly where they were.
"""

DOCUMENT_VERSION = 1
"""Bumped only by a change the previous reader cannot read."""

DEFAULT_FRESHNESS_INTERVAL = timedelta(seconds=15)
"""How long a surface may show a view before it must re-check its token (D8).

Configuration whose *behaviour* is specified and whose number is not: the
requirement is that a replaced view becomes visible within a bounded interval or
is marked stale, and this is the bound a deployment that configured none gets.
"""


class InvalidSlot(OperationFailed):
    """The caller named something that is not a slot. Refused naming the value."""

    kind = FailureKind.INVALID
    identifier = "slot.invalid"

    def __init__(self, value: str) -> None:
        super().__init__(str(InvalidSlotName(value)), value)
        self.value = value


class NoSuchRevision(OperationFailed):
    """That identifier names no revision of this view. Named, never substituted.

    *"An identifier that names no revision of that view SHALL produce an
    explicit not-found result naming the identifier, never the current revision
    as a fallback."* Answering with the current image would be the one behaviour
    that makes a superseded revision look current.
    """

    kind = FailureKind.NOT_FOUND
    identifier = "view.revision_not_found"

    def __init__(self, slot: str, revision: str) -> None:
        super().__init__(f"{revision!r} names no revision of the {slot!r} view", revision)
        self.slot = slot
        self.revision = revision


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


@as_result
def list_view_revisions(
    project: str,
    asset_id: str,
    slot: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    image_inspector: ImageInspector | None = None,
    asset_root: str = DEFAULT_ASSET_ROOT,
) -> ConceptView:
    """Every revision of one view, newest first, from the repository alone.

    *"Listing, retrieving and comparing revisions SHALL depend only on the
    repository and SHALL succeed with every mirrored blob and every thumbnail
    deleted."* There is no blob store in this signature, which is the strongest
    form of that promise available.

    Every path the slot could occupy is walked, not just the current one: a view
    whose format changed moved path (D4), and a history that only followed the
    current extension would silently drop everything before the change.
    """
    named = _slot(slot)
    revision = repository_host.head(project)
    asset_dir = _asset_dir(asset_id, spec_store, revision, asset_root)
    histories = [
        repository_host.history(project, path, None) for path in _candidate_paths(asset_dir, named)
    ]
    entries = _merged(histories)
    if not entries:
        raise NoSuchView(asset_id, str(named))
    return ConceptView(
        asset_id=asset_id,
        slot=named,
        path=_current_path(entries),
        revisions=marked_current(
            tuple(
                _revision_of(project, path, entry, repository_host, image_inspector)
                for path, entry in entries
            )
        ),
        truncated_before=_truncated(histories),
    )


def _merged(histories: Sequence[FileHistory]) -> tuple[tuple[str, FileRevision], ...]:
    """Every revision across every path this slot has occupied, newest first.

    Ordered by the moment the commit was authored, because two paths' histories
    are two lists and the only thing that orders them against each other is
    time. Ties keep the order git gave them, which is stable for one path.
    """
    paired = [(history.path, entry) for history in histories for entry in history.revisions]
    return tuple(sorted(paired, key=lambda pair: pair[1].at, reverse=True))


def _current_path(entries: Sequence[tuple[str, FileRevision]]) -> str:
    """The path the view occupies now, or the one it last occupied if removed."""
    return entries[0][0] if entries else ""


def _truncated(histories: Sequence[FileHistory]) -> str:
    """The point earlier revisions are unavailable from, across every path."""
    return next((history.truncated_before for history in histories if history.truncated_before), "")


def _revision_of(
    project: str,
    path: str,
    entry: FileRevision,
    repository_host: RepositoryHost,
    image_inspector: ImageInspector | None,
) -> ViewRevision:
    """One git revision as a view revision, with its pixels when they can be read.

    The dimensions are read lazily and optionally: a listing needs identifier,
    person, time and content hash, and a comparison needs pixels too. A caller
    that wired no inspector gets the four the listing promises rather than a
    failure over the two it did not ask for.
    """
    facts = _facts_at(project, path, entry, repository_host, image_inspector)
    return ViewRevision(
        revision=entry.revision.value,
        author=str(entry.author),
        at=entry.at,
        content_hash=entry.content,
        width=facts.width if facts else 0,
        height=facts.height if facts else 0,
        byte_size=entry.byte_size,
        removed=entry.is_removal,
    )


def _facts_at(
    project: str,
    path: str,
    entry: FileRevision,
    repository_host: RepositoryHost,
    image_inspector: ImageInspector | None,
) -> ImageFacts | None:
    """The image at that revision, or ``None`` when it cannot or need not be read."""
    if image_inspector is None or entry.is_removal:
        return None
    content = repository_host.read(project, path, entry.revision)
    if content is None:
        return None
    try:
        return image_inspector.inspect(content, name=path)
    except OperationFailed:
        return None


# --------------------------------------------------------------------------
# Retrieving one
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievedRevision:
    """One revision's image, labelled with what it is.

    `historical` is the label the specification asks for by name, and it is a
    field rather than something a surface derives: a renderer that had to work
    out whether the bytes it was handed are current is a renderer that will one
    day get it wrong.
    """

    asset_id: str
    slot: ViewSlot
    revision: str
    content: bytes
    content_hash: ContentHash
    author: str
    is_current: bool

    @property
    def historical(self) -> bool:
        return not self.is_current

    @property
    def label(self) -> str:
        return "current" if self.is_current else f"historical ({self.revision})"


@as_result
def get_view_revision(
    project: str,
    asset_id: str,
    slot: str,
    revision: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    asset_root: str = DEFAULT_ASSET_ROOT,
) -> RetrievedRevision:
    """The image at one revision of one view, labelled historical unless it is current."""
    view = list_view_revisions.raising(
        project,
        asset_id,
        slot,
        repository_host=repository_host,
        spec_store=spec_store,
        asset_root=asset_root,
    )
    entry = view.revision(revision)
    if entry is None or entry.removed:
        raise NoSuchRevision(str(view.slot), revision)
    path = _path_of(project, view, entry, repository_host, spec_store, asset_root, asset_id)
    content = repository_host.read(project, path, Revision(entry.revision))
    if content is None:  # pragma: no cover — the history said this revision has it
        raise NoSuchRevision(str(view.slot), revision)
    assert entry.content_hash is not None
    return RetrievedRevision(
        asset_id=asset_id,
        slot=view.slot,
        revision=entry.revision,
        content=content,
        content_hash=entry.content_hash,
        author=entry.author,
        is_current=entry.is_current,
    )


def _path_of(
    project: str,
    view: ConceptView,
    entry: ViewRevision,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    asset_root: str,
    asset_id: str,
) -> str:
    """Which path held the view at that revision — the format may have changed (D4)."""
    head = repository_host.head(project)
    asset_dir = _asset_dir(asset_id, spec_store, head, asset_root)
    for candidate in _candidate_paths(asset_dir, view.slot):
        if repository_host.read(project, candidate, Revision(entry.revision)) is not None:
            return candidate
    return view.path


# --------------------------------------------------------------------------
# Comparing two
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparedRevision:
    """One side of a comparison: everything the specification enumerates."""

    revision: str
    author: str
    at: str
    dimensions: str
    byte_size: int
    content_hash: str
    is_current: bool


@dataclass(frozen=True)
class RevisionComparison:
    """Two revisions of one view, older first regardless of how they were asked for."""

    asset_id: str
    slot: ViewSlot
    older: ComparedRevision
    newer: ComparedRevision
    identical: bool = False


@as_result
def compare_view_revisions(
    project: str,
    asset_id: str,
    slot: str,
    first: str,
    second: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    image_inspector: ImageInspector | None = None,
    asset_root: str = DEFAULT_ASSET_ROOT,
) -> RevisionComparison:
    """Compare any two revisions of one view, whether or not either is current.

    The older one is presented first *regardless of the order the two were
    requested in*, which is why the listing decides the order rather than the
    arguments: a comparison whose layout depended on how a caller typed it would
    be two different answers to one question.
    """
    view = list_view_revisions.raising(
        project,
        asset_id,
        slot,
        repository_host=repository_host,
        spec_store=spec_store,
        image_inspector=image_inspector,
        asset_root=asset_root,
    )
    left, right = _found(view, first), _found(view, second)
    order = [entry.revision for entry in view.revisions]
    older, newer = (
        (left, right)
        if order.index(left.revision) >= order.index(right.revision)
        else (right, left)
    )
    return RevisionComparison(
        asset_id=asset_id,
        slot=view.slot,
        older=_compared(older),
        newer=_compared(newer),
        identical=first == second,
    )


def _found(view: ConceptView, revision: str) -> ViewRevision:
    entry = view.revision(revision)
    if entry is None:
        raise NoSuchRevision(str(view.slot), revision)
    return entry


def _compared(entry: ViewRevision) -> ComparedRevision:
    return ComparedRevision(
        revision=entry.revision,
        author=entry.author,
        at=entry.at.isoformat(),
        dimensions=entry.dimensions,
        byte_size=entry.byte_size,
        content_hash=entry.content_hash.labelled if entry.content_hash else "",
        is_current=entry.is_current,
    )


# --------------------------------------------------------------------------
# Freshness (D8)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ViewToken:
    """What a surface compares to find out whether what it is showing is current.

    The content hash of the revision being shown, and the revision it came from.
    A token the surface could not obtain is ``None``, and that is the whole of
    *"it SHALL mark the view as stale rather than assert that it is current"* —
    the absence is the answer.
    """

    asset_id: str
    slot: str
    revision: str
    content_hash: ContentHash | None

    @property
    def identity(self) -> str:
        """The one string a client caches against."""
        return self.content_hash.labelled if self.content_hash else ""


@dataclass(frozen=True)
class PresentedView:
    """A view as a surface is showing it, and whether that is still the truth."""

    shown: ContentHash
    token: ViewToken | None
    interval: timedelta = DEFAULT_FRESHNESS_INTERVAL

    @property
    def is_stale(self) -> bool:
        """True when freshness could not be established. Never asserted current."""
        return self.token is None or self.token.content_hash is None

    @property
    def is_superseded(self) -> bool:
        """True when the repository has moved on from what is on the screen."""
        return (
            not self.is_stale and self.token is not None and self.token.content_hash != self.shown
        )

    @property
    def is_current(self) -> bool:
        """Only ever true when a token was read and it matches what is shown."""
        return not self.is_stale and not self.is_superseded


@as_result
def current_view_token(
    project: str,
    asset_id: str,
    slot: str,
    *,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    asset_root: str = DEFAULT_ASSET_ROOT,
) -> ViewToken:
    """The content hash of the view's current revision (D8).

    A polled read rather than a pushed one, and deliberately: the observable
    requirement is satisfiable with no new infrastructure, and a push transport
    would carry this same token unchanged if one is ever wanted.
    """
    view = list_view_revisions.raising(
        project,
        asset_id,
        slot,
        repository_host=repository_host,
        spec_store=spec_store,
        asset_root=asset_root,
    )
    current = view.current
    return ViewToken(
        asset_id=asset_id,
        slot=str(view.slot),
        revision=current.revision if current else "",
        content_hash=current.content_hash if current else None,
    )


def freshness_interval_of(project: ProjectConfig) -> timedelta:
    """How long a surface may show a view before re-checking its token (D8).

    Configuration, with the behaviour specified and only the number open. A
    project that declared none is measured against
    :data:`DEFAULT_FRESHNESS_INTERVAL`.
    """
    declared = project.ingestion
    if declared is None or declared.freshness_seconds is None:
        return DEFAULT_FRESHNESS_INTERVAL
    return timedelta(seconds=declared.freshness_seconds)


def aspect_tolerance_of(project: ProjectConfig) -> float:
    """How far two aspect ratios may differ and still carry a pin (D6)."""
    declared = project.ingestion
    if declared is None or declared.aspect_tolerance is None:
        return DEFAULT_ASPECT_TOLERANCE
    return declared.aspect_tolerance


# --------------------------------------------------------------------------
# Annotations across a replacement (D6, D7)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AnchoredAnnotation:
    """One annotation with its anchor state resolved against the current revision.

    Two states and no third (D7): the exit state travels untouched on
    `annotation`, and nothing in this module can write it — none of these
    functions takes one.
    """

    annotation: Annotation
    anchor_state: AnchorState
    authored_against: str
    reanchored_by: str = ""
    reanchored_at: str = ""

    @property
    def is_orphaned(self) -> bool:
        return self.anchor_state is AnchorState.ORPHANED

    @property
    def is_open(self) -> bool:
        """Orphaning is not an exit: an orphan is still open and still owes one."""
        return self.annotation.is_open


def anchor_state_for(
    annotation: Annotation,
    view: ConceptView,
    *,
    reanchoring: Reanchoring | None = None,
    tolerance: float = DEFAULT_ASPECT_TOLERANCE,
) -> AnchoredAnnotation:
    """Whether this annotation's anchor still resolves, derived from the history.

    The walk is D6 applied at every step rather than once: an annotation is
    carried only if **every** replacement between the revision it was authored
    against and the current one kept the aspect ratio. Comparing only the two
    ends would call a crop-and-crop-back chain carried, which is precisely the
    silently mis-placed pin the anchoring rule exists to prevent.

    A re-anchoring moves the starting point, which is why *"nothing re-anchors
    itself"* holds: without one, the orphaning step stays in the chain forever.
    """
    start = reanchoring.revision if reanchoring else annotation.authored_against
    state = _walk(view, start, tolerance)
    return AnchoredAnnotation(
        annotation=annotation,
        anchor_state=state,
        authored_against=start,
        reanchored_by=reanchoring.by if reanchoring else "",
        reanchored_at=reanchoring.at if reanchoring else "",
    )


def _walk(view: ConceptView, authored_against: str, tolerance: float) -> AnchorState:
    """Every replacement from the authoring revision forwards, oldest first."""
    ordered = list(reversed(view.revisions))
    positions = [entry.revision for entry in ordered]
    if authored_against not in positions:
        return AnchorState.ORPHANED
    for before, after in zip(
        ordered[positions.index(authored_against) :],
        ordered[positions.index(authored_against) + 1 :],
        strict=False,
    ):
        if not _same_shape(before, after, tolerance):
            return AnchorState.ORPHANED
    return AnchorState.CARRIED


def _same_shape(before: ViewRevision, after: ViewRevision, tolerance: float) -> bool:
    """Whether two recorded revisions have the same aspect ratio (D6).

    A revision whose pixels could not be read — a removal, or a listing built
    with no inspector — is not the same shape as anything: *carried* is a claim,
    and a claim that cannot be checked is not one that gets made.
    """
    if not before.height or not after.height:
        return False
    return abs(after.width / after.height - before.width / before.height) <= tolerance


def resolve_anchors(
    annotations: Sequence[Annotation],
    view: ConceptView,
    reanchorings: Sequence[Reanchoring] = (),
    tolerance: float = DEFAULT_ASPECT_TOLERANCE,
) -> tuple[AnchoredAnnotation, ...]:
    """Every annotation on this view, with its anchor state resolved."""
    by_id = {record.annotation_id: record for record in reanchorings}
    return tuple(
        anchor_state_for(
            annotation, view, reanchoring=by_id.get(annotation.id), tolerance=tolerance
        )
        for annotation in annotations_on(annotations, str(view.slot))
    )


# --------------------------------------------------------------------------
# Re-anchoring — a human action, recorded (`view-versioning`)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Reanchoring:
    """One person moving one orphan onto one revision, on a named date.

    Repository content, like an asset request, and for the same reason: it is
    machine-written workflow state that must survive an index rebuild and must
    be attributable. What it deliberately does not carry is the annotation's
    text or exit state — those stay where the person wrote them.
    """

    annotation_id: str
    asset_id: str
    slot: str
    revision: str
    u: float
    v: float
    by: str
    at: str

    def as_document(self) -> bytes:
        """The file this is written as. Sorted keys, so a rewrite diffs cleanly."""
        return (
            json.dumps(
                {
                    "version": DOCUMENT_VERSION,
                    "annotation": self.annotation_id,
                    "asset": self.asset_id,
                    "slot": self.slot,
                    "revision": self.revision,
                    "u": self.u,
                    "v": self.v,
                    "by": self.by,
                    "at": self.at,
                },
                sort_keys=True,
                indent=2,
            ).encode("utf-8")
            + b"\n"
        )

    @classmethod
    def from_document(cls, content: bytes) -> Reanchoring | None:
        """That file back, or ``None`` when it is not one of ours."""
        try:
            fields = json.loads(content)
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(fields, dict):
            return None
        return cls(
            annotation_id=str(fields.get("annotation", "")),
            asset_id=str(fields.get("asset", "")),
            slot=str(fields.get("slot", "")),
            revision=str(fields.get("revision", "")),
            u=float(fields.get("u", 0.0)),
            v=float(fields.get("v", 0.0)),
            by=str(fields.get("by", "")),
            at=str(fields.get("at", "")),
        )


def reanchor_path(asset_id: str, annotation_id: str) -> str:
    """The one file a re-anchoring lives in, for its whole life."""
    return f"{REANCHOR_DIR}/{asset_id}/{annotation_id}.json"


@dataclass(frozen=True)
class ReanchorOutcome:
    """The annotation as it now reads, and the record that made it read that way."""

    annotation: Annotation
    record: Reanchoring
    revision: Revision


@as_result
def reanchor_annotation(
    project: str,
    asset_id: str,
    annotation: Annotation,
    *,
    u: float,
    v: float,
    repository_host: RepositoryHost,
    spec_store: SpecStore,
    author: GitAuthor | None,
    by: str,
    at: str,
    slot: str = "",
    subject: str = "",
    agent: str = "",
    asset_root: str = DEFAULT_ASSET_ROOT,
) -> ReanchorOutcome:
    """A person re-anchors an orphan onto the current revision of its view.

    Three things this cannot do, and each is a signature rather than a promise:
    it cannot change the annotation's text, it cannot change its exit state, and
    it cannot happen without a person — `by` and `at` are required arguments, so
    there is no way to call this on a timer and have it look like somebody's
    decision.
    """
    if author is None:
        raise AuthorUnmapped(subject or project, reanchor_path(asset_id, annotation.id))
    named = slot or getattr(annotation.target, "view", "")
    view = list_view_revisions.raising(
        project,
        asset_id,
        named,
        repository_host=repository_host,
        spec_store=spec_store,
        asset_root=asset_root,
    )
    current = view.current
    if current is None:
        raise NoSuchView(asset_id, str(view.slot))
    record = Reanchoring(
        annotation_id=annotation.id,
        asset_id=asset_id,
        slot=str(view.slot),
        revision=current.revision,
        u=u,
        v=v,
        by=by,
        at=at,
    )
    outcome = write_back.raising(
        project,
        [Edit(path=reanchor_path(asset_id, annotation.id), content=record.as_document())],
        repository_host=repository_host,
        author=author,
        message=f"{asset_id}: re-anchor annotation {annotation.id} to {view.slot}",
        subject=subject,
        agent=agent,
    )
    return ReanchorOutcome(
        annotation=_reanchored(annotation, record),
        record=record,
        revision=outcome.revision,
    )


def _reanchored(annotation: Annotation, record: Reanchoring) -> Annotation:
    """The domain move, with the anchor rebuilt at the position the person chose."""
    from cybercanon.domain.annotations import Anchor2D

    return annotation.reanchored(
        Anchor2D(view=record.slot, u=record.u, v=record.v),
        revision=record.revision,
        by=record.by,
        at=record.at,
    )


@as_result
def list_reanchorings(
    project: str,
    asset_id: str,
    *,
    repository_host: RepositoryHost,
) -> tuple[Reanchoring, ...]:
    """Every recorded re-anchoring for one asset, read from the repository."""
    revision = repository_host.head(project)
    prefix = f"{REANCHOR_DIR}/{asset_id}/"
    found = [
        Reanchoring.from_document(repository_host.read(project, path, revision) or b"")
        for path in repository_host.paths_at(project, revision)
        if path.startswith(prefix)
    ]
    return tuple(record for record in found if record is not None)


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def _slot(name: str) -> ViewSlot:
    try:
        return ViewSlot(name)
    except InvalidSlotName as error:
        raise InvalidSlot(name) from error


def _asset_dir(asset_id: str, spec_store: SpecStore, revision: Revision, asset_root: str) -> str:
    spec_path = locate_asset(asset_id, spec_store=spec_store, revision=revision)
    if spec_path is None:
        return f"{asset_root}/{asset_id}"
    head, _, _ = spec_path.rpartition("/")
    return head


def _candidate_paths(asset_dir: str, slot: ViewSlot) -> tuple[str, ...]:
    directory = concept_dir(asset_dir)
    return tuple(
        f"{directory}/{slot}.{extension}" for extension in sorted(set(EXTENSIONS.values()))
    )


__all__ = [
    "DEFAULT_FRESHNESS_INTERVAL",
    "DOCUMENT_VERSION",
    "REANCHOR_DIR",
    "AnchoredAnnotation",
    "ComparedRevision",
    "InvalidSlot",
    "NoSuchRevision",
    "PresentedView",
    "ReanchorOutcome",
    "Reanchoring",
    "RetrievedRevision",
    "RevisionComparison",
    "ViewToken",
    "anchor_state_for",
    "aspect_tolerance_of",
    "compare_view_revisions",
    "current_view_token",
    "freshness_interval_of",
    "get_view_revision",
    "list_reanchorings",
    "list_view_revisions",
    "reanchor_annotation",
    "reanchor_path",
    "resolve_anchors",
]
