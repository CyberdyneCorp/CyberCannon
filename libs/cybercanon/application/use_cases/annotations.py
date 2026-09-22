"""Authoring, threading and triaging annotations — every write a commit (D4).

The decision this module implements is `add-model-sheet-2d`'s D4, and it is the
one the whole change turns on: *"Threads live in `asset.yaml`. There is no
annotation table."* Annotations look like application data, which is exactly why
the temptation to put them in PostgreSQL is strongest here — and why giving in
would produce a system where losing the database loses every open issue, with a
promoted rule sitting in git beside the argument that produced it only sometimes.

So every operation below has the same three steps and no others:

1. **read the asset's specification from the repository**, at the revision the
   working copy is serving, as bytes *and* as a parsed
   :class:`~cybercanon.domain.asset.Asset`;
2. **apply one pure domain operation** — the authoring policy, the filter, the
   triage policy, the promotion transformation — to the parsed value;
3. **write the whole file back as one attributed commit**, with D5's per-file
   precondition being the digest of the bytes step 1 read.

Three consequences are worth stating because they are decisions rather than
mechanics.

* **The bytes come from the repository host and the meaning from the spec
  store.** One source of truth for content, one parser over it. A write path
  that read the file through one port and the digest through another would have
  two answers to *what is there now*, which is the conflict this module exists
  to detect.
* **A conflict replays the operation, not the file** (D5). Two artists
  annotating the same asset is ordinary; re-reading and re-applying *the
  operation* makes both writes succeed, where re-applying the file would make
  the second one lose. A second conflict is reported with the submitted text
  preserved, because a lost annotation is worse than a visible retry.
* **Promotion is one use case producing one commit** (D6), and it is refused for
  every automated caller (D7) by :mod:`cybercanon.domain.policy`, which decides
  it for all four surfaces at once.

Nothing here knows what YAML is, what a pixel is, or what an HTTP status code
is. Rendering the edited asset back into the file preserving its comments is
:meth:`~cybercanon.application.ports.spec_store.SpecStore.edited`'s, and the
sentence a refusal prints is the domain's.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.spec_store import SpecDocument, SpecStore
from cybercanon.application.results import Result, as_result, refuse
from cybercanon.application.use_cases.hosted_repository import (
    AuthorUnmapped,
    Edit,
    WriteConflict,
    write_back,
)
from cybercanon.application.use_cases.ingest_views import locate_asset
from cybercanon.application.use_cases.requests import discipline_owners
from cybercanon.domain.actors import ActorMapping, GitAuthor
from cybercanon.domain.annotations import (
    Anchor,
    Anchor2D,
    Annotation,
    AnnotationFilter,
    AnnotationKind,
    AnnotationState,
    Orphan,
    Reply,
    Stroke,
    capped,
    marked_orphans,
    orphans,
    replaced,
    thread_of,
    without,
)
from cybercanon.domain.asset import Asset
from cybercanon.domain.identity import Actor, ActorId, ActorKind, AgentId
from cybercanon.domain.policy import Operation, Subject, decide
from cybercanon.domain.revisions import ContentHash, Revision
from cybercanon.domain.spec_checks import check_asset
from cybercanon.domain.triage import (
    Exit,
    Promotion,
    PromotionRefused,
    PromotionTarget,
    TriageEntry,
    exits_for,
    promote,
    triage_order,
)
from cybercanon.domain.views import CONCEPT_DIR, slot_of
from cybercanon.domain.violations import SpecViolation

REPLAY_ATTEMPTS = 2
"""How many times the operation is applied before a conflict is reported (D5).

Two, and deliberately not more: the first attempt is the ordinary one, the
second is the replay against what somebody else just wrote, and a third would
be a busy-wait dressed up as resilience. *"A second failure is reported to the
person with their text preserved."*
"""


# --------------------------------------------------------------------------
# Failures — each one means something different to the caller
# --------------------------------------------------------------------------


class AnnotationRejected(OperationFailed):
    """The request is not a valid annotation, or the policy refuses it.

    It carries the kind the decision gave it, so the domain never learns what a
    status code is and no surface re-derives the distinction from a message.
    """

    identifier = "annotation.rejected"

    def __init__(self, subject: str, reason: str, kind: FailureKind) -> None:
        super().__init__(reason, subject)
        self.kind = kind  # type: ignore[misc]


class AnnotationNotFound(OperationFailed):
    """No annotation with that identifier is recorded on that asset."""

    kind = FailureKind.NOT_FOUND
    identifier = "annotation.not_found"

    def __init__(self, asset_id: str, annotation_id: str) -> None:
        super().__init__(
            f"no annotation {annotation_id!r} is recorded on {asset_id!r}", annotation_id
        )


class AssetNotFound(OperationFailed):
    """No specification in this project declares that asset."""

    kind = FailureKind.NOT_FOUND
    identifier = "asset.not_found"

    def __init__(self, project: str, asset_id: str) -> None:
        super().__init__(f"no asset {asset_id!r} is declared in project {project!r}", asset_id)


class AnnotationConflict(OperationFailed):
    """The specification moved under two attempts; the submitted text comes back.

    *"A second failure is reported to the person with their text preserved"* —
    so the text is an attribute rather than only a sentence, and a surface can
    hand it straight back to the composer that produced it.
    """

    kind = FailureKind.CONFLICT
    identifier = "annotation.conflict"

    def __init__(self, asset_id: str, text: str) -> None:
        super().__init__(
            f"{asset_id} changed while this was being written; nothing was recorded, "
            "and the text was kept so it can be submitted again",
            asset_id,
        )
        self.text = text


class PromotionInvalid(OperationFailed):
    """The rule would produce a specification this product's own validator rejects.

    *"The system SHALL NOT write a specification file that its own validator
    rejects."* The violations travel with the refusal, because the promoter has
    to be told what to change rather than that something is wrong.
    """

    kind = FailureKind.INVALID
    identifier = "promotion.invalid"

    def __init__(self, asset_id: str, violations: Sequence[SpecViolation]) -> None:
        listed = "; ".join(violation.message for violation in violations)
        super().__init__(
            f"promoting this rule would make {asset_id}'s specification invalid: {listed}",
            asset_id,
        )
        self.violations = tuple(violations)


# --------------------------------------------------------------------------
# What a caller submits, and what comes back
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Draft:
    """One annotation as the person composing it described it.

    `id` is **client-generated**, and that is D5's idempotency key rather than a
    convenience: a retried request carrying the same identifier must produce one
    annotation, and the only value both sides of a dropped response agree on is
    the one the client chose before it sent anything.
    """

    id: str
    kind: AnnotationKind
    text: str
    anchor: Anchor
    strokes: tuple[Stroke, ...] = ()
    authored_against: str = ""


@dataclass(frozen=True)
class RecordedAnnotation:
    """An annotation as it now stands, and the commit that recorded it."""

    project: str
    asset_id: str
    path: str
    annotation: Annotation
    revision: str
    committed: bool = True

    @property
    def id(self) -> str:
        return self.annotation.id


@dataclass(frozen=True)
class AnnotationListing:
    """Every annotation of one asset a filter asked for, and what it hid.

    Both anchor forms come back through this one shape with the same fields
    present, which is `annotation-authoring`'s *"a mixed list is uniform"* made
    structural: there is no second listing type for the other medium to drift
    into.
    """

    project: str
    asset_id: str
    path: str
    revision: str
    annotations: tuple[Annotation, ...] = ()
    hidden: int = 0
    orphaned: tuple[Orphan, ...] = ()
    views: tuple[str, ...] = ()
    actor: str = ""
    """Who this listing was read as, so a surface knows whose contributions are whose.

    `annotation-authoring` lets a person edit and withdraw *their own*, and the
    panel has to know which those are without asking a second question. It is
    the subject the credential resolved to, never a body field.
    """

    may_promote: bool = False
    """Whether this person may promote on this project — the domain's answer.

    `model-sheet-2d` requires the panel to offer promotion *"only to a person
    permitted to promote"*, and the only authority on that is
    :mod:`cybercanon.domain.policy`. A client that inferred it from a role claim
    would be a second opinion about a permission, which is how a surface starts
    offering an action the system then refuses.
    """

    @property
    def placeable(self) -> tuple[Annotation, ...]:
        """The ones a surface may draw — an orphan is listed and never placed."""
        return tuple(entry for entry in self.annotations if not entry.is_orphaned)


@dataclass(frozen=True)
class TriageQueue:
    """The project's open annotations, ordered for the art director's pass."""

    project: str
    entries: tuple[TriageEntry, ...] = ()
    unreadable: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class Workspace:
    """Everything one annotation operation needs, so each step takes one argument."""

    project: str
    asset_id: str
    repository_host: RepositoryHost
    spec_store: SpecStore
    actor: Actor
    author: GitAuthor | None
    via: AgentId | None = None
    agent: str = ""
    clock: Clock = system_clock
    parts: tuple[str, ...] | None = None

    @property
    def subject_id(self) -> str:
        """The identity subject a contribution is attributed to."""
        return self.actor.subject

    @property
    def instrument(self) -> str:
        """The agent that acted, as the file records it. Empty for a person."""
        return str(self.via) if self.via is not None else ""

    def now(self) -> str:
        """The moment this operation happened, as the file records it."""
        return _stamp(self.clock())


@dataclass(frozen=True)
class Loaded:
    """The asset this operation acts on: its path, its bytes and its meaning."""

    path: str
    document: SpecDocument
    revision: Revision
    views: tuple[str, ...]

    @property
    def asset(self) -> Asset:
        return self.document.asset

    @property
    def based_on(self) -> ContentHash:
        return ContentHash.of(self.document.content)


type Apply = Callable[[Loaded], tuple[Asset, Annotation]]
"""One domain operation over a freshly-read asset, replayable after a conflict."""


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@as_result
def list_annotations(
    workspace: Workspace,
    annotation_filter: AnnotationFilter | None = None,
) -> AnnotationListing:
    """One asset's annotations, filtered, with both anchor forms treated alike.

    The filter is applied by the domain and the orphan marking is the domain's
    too, so the sheet, the viewer, the command line and the agent surface all
    answer the same question the same way — which is `model-sheet-2d`'s
    *"filtering agrees across surfaces"* without a second implementation to keep
    in step.
    """
    wanted = annotation_filter or AnnotationFilter.every()
    loaded = _load(workspace)
    marked = marked_orphans(loaded.asset.annotations, loaded.views, workspace.parts)
    return AnnotationListing(
        project=workspace.project,
        asset_id=workspace.asset_id,
        path=loaded.path,
        revision=loaded.revision.value,
        annotations=wanted.apply(marked),
        hidden=wanted.hidden(marked),
        orphaned=orphans(marked, loaded.views, workspace.parts),
        views=loaded.views,
        actor=workspace.subject_id,
        may_promote=_may_promote(workspace),
    )


def _may_promote(workspace: Workspace) -> bool:
    """Whether this caller may take the promotion exit at all, decided in the domain."""
    return bool(
        decide(
            workspace.actor,
            Operation.PROMOTE_TO_RULE,
            Subject(
                project=workspace.project,
                has_git_identity=workspace.author is not None,
                description=workspace.asset_id,
            ),
            via=workspace.via,
        )
    )


@as_result
def available_exits(workspace: Workspace, annotation_id: str) -> tuple[Exit, ...]:
    """The exits this annotation is offered — two, or none once it took one."""
    loaded = _load(workspace)
    return exits_for(_annotation(loaded, workspace, annotation_id))


# --------------------------------------------------------------------------
# Authoring
# --------------------------------------------------------------------------


@as_result
def create_annotation(workspace: Workspace, draft: Draft) -> RecordedAnnotation:
    """Record one annotation against one durable anchor, as one commit.

    The anchor is checked against what the asset *has* before anything is
    written, and a request naming a view the asset does not have is refused
    naming it — never attached to another view, which is the silently
    mis-placed annotation `project.md` forbids by name.
    """

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        _permitted(workspace, loaded, Operation.CREATE_ANNOTATION)
        _anchored(loaded, workspace, draft.anchor)
        annotation = Annotation(
            id=draft.id,
            author=workspace.subject_id,
            kind=draft.kind,
            text=_stated(draft.text, "an annotation"),
            target=draft.anchor,
            authored_against=draft.authored_against,
            via=workspace.instrument,
            strokes=capped(draft.strokes),
            created_at=workspace.now(),
        )
        return replace(
            loaded.asset, annotations=(*loaded.asset.annotations, annotation)
        ), annotation

    existing = _already_recorded(workspace, draft.id)
    if existing is not None:
        return existing
    return _write(workspace, apply, _summary(draft.text), f"annotation {draft.id} created")


@as_result
def reply_to_annotation(
    workspace: Workspace, annotation_id: str, reply_id: str, text: str
) -> RecordedAnnotation:
    """Add one contribution to a thread — no anchor, no kind, no exit of its own."""

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        _permitted(workspace, loaded, Operation.REPLY_IN_THREAD)
        annotation = _annotation(loaded, workspace, annotation_id)
        if any(reply.id == reply_id for reply in annotation.replies):
            return loaded.asset, annotation
        replied = annotation.with_reply(
            Reply(
                id=reply_id,
                author=workspace.subject_id,
                text=_stated(text, "a reply"),
                at=workspace.now(),
                via=workspace.instrument,
            )
        )
        return _with(loaded.asset, replied), replied

    return _write(workspace, apply, _summary(text), f"annotation {annotation_id} replied to")


@as_result
def edit_annotation(workspace: Workspace, annotation_id: str, text: str) -> RecordedAnnotation:
    """Re-word one's own annotation. The author and the anchor are not parameters."""

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        annotation = _annotation(loaded, workspace, annotation_id)
        _permitted(workspace, loaded, Operation.EDIT_CONTRIBUTION, annotation)
        edited = annotation.with_text(_stated(text, "an annotation"), workspace.now())
        return _with(loaded.asset, edited), edited

    return _write(workspace, apply, _summary(text), f"annotation {annotation_id} edited")


@as_result
def delete_annotation(workspace: Workspace, annotation_id: str) -> RecordedAnnotation:
    """Withdraw one's own untouched annotation.

    A thread that has replies is refused: it takes one of its two exits
    instead, so that a conversation always ends in a decision rather than in a
    deletion nobody can review.
    """

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        annotation = _annotation(loaded, workspace, annotation_id)
        _permitted(workspace, loaded, Operation.WITHDRAW_CONTRIBUTION, annotation)
        if annotation.has_replies:
            raise AnnotationRejected(
                annotation_id,
                f"annotation {annotation_id!r} has replies and cannot be deleted; "
                "resolve it or promote it instead",
                FailureKind.CONFLICT,
            )
        return replace(
            loaded.asset, annotations=without(loaded.asset.annotations, annotation_id)
        ), annotation

    return _write(workspace, apply, "", f"annotation {annotation_id} withdrawn")


@as_result
def move_annotation(workspace: Workspace, annotation_id: str, anchor: Anchor) -> RecordedAnnotation:
    """Move one's own annotation to another anchor of the same form, and record it."""

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        annotation = _annotation(loaded, workspace, annotation_id)
        _permitted(workspace, loaded, Operation.MOVE_ANNOTATION, annotation)
        _same_form(annotation, anchor)
        _anchored(loaded, workspace, anchor)
        moved = annotation.moved_to(anchor, by=workspace.subject_id, at=workspace.now())
        return _with(loaded.asset, moved), moved

    return _write(workspace, apply, "", f"annotation {annotation_id} moved")


NOTHING_REANCHORS_ITSELF = (
    "re-anchoring an orphaned annotation is a person's decision: an automated "
    "caller may act on a person's behalf, never on its own"
)
"""Why an automation-only caller is refused a re-anchor (`anchor-resolution`).

*"Re-anchoring SHALL NOT be performed automatically and SHALL NOT be available
to an automated caller acting on its own."* The refusal is here rather than in
the surface because every surface would otherwise have to remember it, and the
one that forgot would be the one that quietly relocated a pin.
"""


@as_result
def reanchor_annotation(
    workspace: Workspace, annotation_id: str, anchor: Anchor
) -> RecordedAnnotation:
    """A person re-anchors an orphan onto a subject the current export has.

    What this cannot do is what makes it safe, and every one of them is a
    signature rather than a promise: it takes no text, so the words are
    untouched; it takes no state, so the exit is untouched; it takes no author,
    so the attribution is the acting person's and nobody else's; and it has no
    parameter that could hold a candidate part, so nothing here can choose one
    (`anchor-resolution`: *"the annotation SHALL remain orphaned until a person
    re-anchors it"*).

    There is deliberately no promotion path through it either — promotion is
    :func:`promote_annotation`, it is `ART_DIRECTOR`-only, and it is refused for
    every automated caller by :mod:`cybercanon.domain.policy` before a role is
    consulted.

    **Which row of G4 this authorizes against, and why it is not the move row.**
    G4's matrix has no row for re-anchoring, and the two candidates behave very
    differently. `MOVE_ANNOTATION` is *its author may*, which would make an
    orphan unrescuable the week its author leaves — and an orphan is precisely
    the annotation whose author is most likely to be gone. `CREATE_ANNOTATION`
    is *"any actor with project write access, independent of their role"*, which
    is the same rule the 2D re-anchor in
    :mod:`cybercanon.application.use_cases.view_revisions` already applies: a
    mapped git identity, and nothing about whose thread it is. Re-anchoring
    writes an anchor and changes nothing a person said, so it is authorized as
    writing one. `anchor-resolution` says only *"a person"*, so this is the
    reading that makes the requirement satisfiable rather than the one that
    makes it narrower than anybody asked for.
    """

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        annotation = _annotation(loaded, workspace, annotation_id)
        _by_a_person(workspace, annotation)
        _permitted(workspace, loaded, Operation.CREATE_ANNOTATION)
        _same_form(annotation, anchor)
        _anchored(loaded, workspace, anchor)
        rescued = annotation.reanchored(
            anchor,
            revision=loaded.revision.value,
            by=workspace.subject_id,
            at=workspace.now(),
        )
        return _with(loaded.asset, rescued), rescued

    return _write(
        workspace,
        apply,
        "",
        f"annotation {annotation_id} re-anchored to {anchor.durable_key}",
    )


def _by_a_person(workspace: Workspace, annotation: Annotation) -> None:
    """Refuse a caller that is an automation rather than a person's instrument.

    `via` is fine and is recorded: *"the recorded change SHALL name both that
    person and the caller"*. What is refused is the credential with no person
    behind it at all, which is the only shape *"acting on its own"* can take.
    """
    if workspace.actor.kind is ActorKind.AUTOMATION:
        raise AnnotationRejected(annotation.id, NOTHING_REANCHORS_ITSELF, FailureKind.FORBIDDEN)


# --------------------------------------------------------------------------
# The two exits
# --------------------------------------------------------------------------


@as_result
def resolve_annotation(
    workspace: Workspace, annotation_id: str, conclusion: str = ""
) -> RecordedAnnotation:
    """Exit two: a transient issue, addressed, and out of the compiled briefing.

    An annotation whose conclusion is that nothing needs changing is resolved
    *with that conclusion as its closing text*, which is why `conclusion` is a
    parameter and why there is no third terminal state to record it as.
    """

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        annotation = _annotation(loaded, workspace, annotation_id)
        _permitted(workspace, loaded, Operation.RESOLVE_ISSUE, annotation)
        _open(annotation)
        resolved = annotation.resolved(
            by=workspace.subject_id, at=workspace.now(), conclusion=conclusion
        )
        return _with(loaded.asset, resolved), resolved

    return _write(workspace, apply, conclusion, f"annotation {annotation_id} resolved")


@as_result
def reopen_annotation(workspace: Workspace, annotation_id: str) -> RecordedAnnotation:
    """Back into the open set and the triage queue — unless its content is a rule."""

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        annotation = _annotation(loaded, workspace, annotation_id)
        _permitted(workspace, loaded, Operation.REOPEN_ISSUE, annotation)
        if annotation.is_promoted:
            raise AnnotationRejected(
                annotation_id,
                f"annotation {annotation_id!r} was promoted and its content is now a "
                "rule; change the rule, which is an ordinary specification change",
                FailureKind.CONFLICT,
            )
        reopened = annotation.reopened(by=workspace.subject_id, at=workspace.now())
        return _with(loaded.asset, reopened), reopened

    return _write(workspace, apply, "", f"annotation {annotation_id} reopened")


@as_result
def promote_annotation(
    workspace: Workspace,
    annotation_id: str,
    rule_text: str,
    target: PromotionTarget | None,
) -> RecordedAnnotation:
    """Exit one: the content becomes a durable rule and the thread is retired (D6).

    One operation and one commit containing both edits. The resulting
    specification is checked before anything is written, so the system never
    commits a file its own validator rejects — which would strand the asset for
    everyone running `canon validate` against it.
    """
    if target is None:
        raise AnnotationRejected(annotation_id, _NO_DESTINATION, FailureKind.INVALID)

    def apply(loaded: Loaded) -> tuple[Asset, Annotation]:
        annotation = _annotation(loaded, workspace, annotation_id)
        _permitted(workspace, loaded, Operation.PROMOTE_TO_RULE, annotation)
        _open(annotation)
        promotion = _promotion(loaded, annotation_id, rule_text, target, workspace)
        _valid(promotion, workspace)
        return promotion.asset, promotion.annotation

    return _write(
        workspace,
        apply,
        rule_text,
        f"annotation {annotation_id} promoted into {target}",
    )


def _promotion(
    loaded: Loaded,
    annotation_id: str,
    rule_text: str,
    target: PromotionTarget,
    workspace: Workspace,
) -> Promotion:
    """The domain's transformation, with its refusal in the outcome vocabulary."""
    try:
        return promote(
            loaded.asset,
            annotation_id,
            rule_text,
            target,
            by=workspace.subject_id,
            at=workspace.now(),
        )
    except PromotionRefused as refusal:
        raise AnnotationRejected(
            refusal.subject or annotation_id, refusal.reason, FailureKind.INVALID
        ) from refusal


def _valid(promotion: Promotion, workspace: Workspace) -> None:
    """The resulting specification, checked before a byte of it is written."""
    violations = tuple(finding for finding in check_asset(promotion.asset) if finding.is_error)
    if violations:
        raise PromotionInvalid(workspace.asset_id, violations)


_NO_DESTINATION = (
    "a promotion states where the rule belongs; the destinations are "
    "`constraints` and `concept.silhouette_rules`"
)


# --------------------------------------------------------------------------
# The triage queue (D11)
# --------------------------------------------------------------------------


@as_result
def list_triage_queue(
    project: str,
    *,
    spec_store: SpecStore,
    repository_host: RepositoryHost | None = None,
    kinds: Iterable[AnnotationKind] = (),
    asset_id: str = "",
    owner: str = "",
    root: str = "",
    clock: Clock = system_clock,
) -> TriageQueue:
    """Every open annotation of a project, ordered so recurring feedback rises.

    Computed from specifications through `SpecStore` and from nothing else, so
    *"the queue SHALL be derivable from the repository alone"* is the real
    implementation rather than a fallback nobody exercises. An index accelerates
    it; it never answers it.
    """
    store = _pinned(spec_store, project, repository_host)
    mapping = store.load_actor_mapping(root).mapping
    now = clock()
    assets = tuple(_readable(store, path) for path in store.specs_under(root))
    open_by_asset = {
        path: tuple(entry for entry in asset.annotations if entry.is_open)
        for path, asset in assets
        if asset is not None
    }
    entries = _entries(assets, open_by_asset, mapping, now)
    wanted = _queue_filter(entries, kinds, asset_id, owner)
    return TriageQueue(
        project=project,
        entries=triage_order(wanted),
        unreadable=tuple(path for path, asset in assets if asset is None),
    )


def _readable(store: SpecStore, path: str) -> tuple[str, Asset | None]:
    """One specification, or the fact that it could not be read.

    A file nobody can parse is named rather than skipped: a queue that quietly
    omitted an asset would tell an art director that a project is clean when one
    of its files is broken.
    """
    try:
        return path, store.load(path).asset
    except OperationFailed:
        return path, None


def _entries(
    assets: Sequence[tuple[str, Asset | None]],
    open_by_asset: dict[str, tuple[Annotation, ...]],
    mapping: ActorMapping,
    now: datetime,
) -> tuple[TriageEntry, ...]:
    """One entry per open annotation, carrying the four signals the pass reads."""
    across = _counts(entry for annotations in open_by_asset.values() for entry in annotations)
    built: list[TriageEntry] = []
    for path, asset in assets:
        if asset is None:
            continue
        here = _counts(open_by_asset[path])
        owners = discipline_owners(asset, mapping)
        built.extend(
            TriageEntry(
                asset=asset.id.value,
                annotation=annotation,
                same_kind_on_asset=here[annotation.kind],
                same_kind_in_project=across[annotation.kind],
                age_seconds=_age(annotation, now),
                discipline_owner=_owner_for(owners, annotation.kind),
            )
            for annotation in open_by_asset[path]
        )
    return tuple(built)


def _counts(annotations: Iterable[Annotation]) -> dict[AnnotationKind, int]:
    """How many open annotations of each kind there are, kinds with none included."""
    tally = dict.fromkeys(AnnotationKind, 0)
    for annotation in annotations:
        tally[annotation.kind] += 1
    return tally


def _owner_for(owners: object, kind: AnnotationKind) -> str:
    """Whose discipline this feedback belongs to, as the queue reports it."""
    field = _OWNER_FIELDS[kind]
    owner = getattr(owners, field, None)
    return str(owner) if owner else ""


_OWNER_FIELDS = {
    AnnotationKind.ART_DIRECTION: "art",
    AnnotationKind.DESIGN: "design",
    AnnotationKind.TECHNICAL: "code",
}
"""Which declared owner each kind of feedback belongs to.

Art direction is the art owner's, design the designer's, and a technical
annotation the code owner's — the same three owners `asset.yaml` declares, so
the queue's discipline filter and the specification's ownership cannot disagree.
"""


def _age(annotation: Annotation, now: datetime) -> float:
    """How long this has been waiting, in seconds. Unstamped is age zero.

    Zero rather than a guess: an annotation written before this change carries
    no creation time, and inventing one would put it at the top or the bottom of
    every pass depending on which way somebody rounded.
    """
    created = _parsed(annotation.created_at)
    if created is None:
        return 0.0
    return max((now - created).total_seconds(), 0.0)


def _queue_filter(
    entries: Sequence[TriageEntry],
    kinds: Iterable[AnnotationKind],
    asset_id: str,
    owner: str,
) -> tuple[TriageEntry, ...]:
    """The three filters a pass uses, combining — kind, asset and discipline owner."""
    wanted = frozenset(kinds)
    return tuple(
        entry
        for entry in entries
        if (not wanted or entry.kind in wanted)
        and (not asset_id or entry.asset == asset_id)
        and (not owner or entry.discipline_owner == owner)
    )


# --------------------------------------------------------------------------
# The shared machinery: read, apply, commit, replay
# --------------------------------------------------------------------------


def _write(workspace: Workspace, apply: Apply, text: str, summary: str) -> RecordedAnnotation:
    """D5's loop: read, apply the operation, commit against what was read.

    A conflict re-reads and re-applies **the operation**, which is what lets two
    people annotate one asset at the same second and both succeed. Replaying the
    *file* would make the second write lose, and locking the file would fail
    badly the first time a browser tab closed mid-edit.
    """
    if workspace.author is None:
        raise AuthorUnmapped(workspace.subject_id, workspace.asset_id)
    for attempt in range(1, REPLAY_ATTEMPTS + 1):
        loaded = _load(workspace)
        asset, annotation = apply(loaded)
        try:
            return _commit(workspace, loaded, asset, annotation, summary)
        except WriteConflict:
            if attempt == REPLAY_ATTEMPTS:
                raise AnnotationConflict(workspace.asset_id, text) from None
    raise AnnotationConflict(workspace.asset_id, text)  # pragma: no cover - loop is total


def _commit(
    workspace: Workspace,
    loaded: Loaded,
    asset: Asset,
    annotation: Annotation,
    summary: str,
) -> RecordedAnnotation:
    """One logical edit as one attributed, legible commit.

    An operation that changed nothing — a retried reply, a move to where the pin
    already is — writes nothing at all, so a repeat is quiet rather than a
    second commit saying the same thing.
    """
    if asset == loaded.asset:
        return RecordedAnnotation(
            project=workspace.project,
            asset_id=workspace.asset_id,
            path=loaded.path,
            annotation=annotation,
            revision=loaded.revision.value,
            committed=False,
        )
    content = workspace.spec_store.edited(loaded.document, asset)
    written = write_back.raising(
        workspace.project,
        [Edit(path=loaded.path, content=content, based_on=loaded.based_on)],
        repository_host=workspace.repository_host,
        author=workspace.author,
        message=commit_message(workspace.asset_id, summary),
        subject=workspace.subject_id,
        agent=workspace.agent,
    )
    return RecordedAnnotation(
        project=workspace.project,
        asset_id=workspace.asset_id,
        path=loaded.path,
        annotation=annotation,
        revision=written.revision.value,
    )


COMMIT_PREFIX = "annotation"
"""What every annotation commit's message begins with.

The change's risk register asks for it in so many words — *"annotation commits
carry a distinct message prefix naming the asset and annotation id, so they are
filterable in a log and in a blame"* — and one commit per reply is only bearable
if `git log --grep` can separate them from the specification edits.
"""


def commit_message(asset_id: str, summary: str) -> str:
    """`annotation(mech_scout): annotation an_1 created` — filterable, and legible."""
    return f"{COMMIT_PREFIX}({asset_id}): {summary}"


def _load(workspace: Workspace) -> Loaded:
    """Where this asset is, what its file holds, and which views it has.

    The bytes come from the repository host at the head revision, and the
    meaning from the spec store's parse of exactly those bytes — one content,
    one parser, so *what is there now* has a single answer.
    """
    revision = workspace.repository_host.head(workspace.project)
    path = locate_asset(workspace.asset_id, spec_store=workspace.spec_store, revision=revision)
    if path is None:
        raise AssetNotFound(workspace.project, workspace.asset_id)
    content = workspace.repository_host.read(workspace.project, path, revision)
    if content is None:
        raise AssetNotFound(workspace.project, workspace.asset_id)
    document = workspace.spec_store.parse_document(path, content)
    return Loaded(
        path=path,
        document=document,
        revision=revision,
        views=_views(workspace, path, document.asset, revision),
    )


def _views(workspace: Workspace, path: str, asset: Asset, revision: Revision) -> tuple[str, ...]:
    """Every view this asset has: the ones it declares and the ones it holds.

    Both, and the union is deliberate. `concept.silhouette_rules`' neighbour
    `concept.views` is authored, while `concept-ingestion` writes a view as a
    *file* beside the specification without touching an authored field — so an
    asset can hold `concept/front.png` and declare nothing. A check that read
    only the declaration would refuse a pin on an image the artist is looking
    at, which is the first thing anybody would try.
    """
    declared = asset.concept.views if asset.concept else ()
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    prefix = f"{directory}/{CONCEPT_DIR}/" if directory else f"{CONCEPT_DIR}/"
    found = (
        slot_of(candidate)
        for candidate in workspace.repository_host.paths_at(workspace.project, revision)
        if candidate.startswith(prefix)
    )
    return tuple(dict.fromkeys((*declared, *(str(slot) for slot in found if slot))))


def _already_recorded(workspace: Workspace, annotation_id: str) -> RecordedAnnotation | None:
    """D5's idempotency: a retried create with the same id produces one annotation."""
    loaded = _load(workspace)
    annotation = thread_of(loaded.asset.annotations, annotation_id)
    if annotation is None:
        return None
    return RecordedAnnotation(
        project=workspace.project,
        asset_id=workspace.asset_id,
        path=loaded.path,
        annotation=annotation,
        revision=loaded.revision.value,
        committed=False,
    )


def _annotation(loaded: Loaded, workspace: Workspace, annotation_id: str) -> Annotation:
    """The annotation this operation names, or the refusal that it is not there."""
    annotation = thread_of(loaded.asset.annotations, annotation_id)
    if annotation is None:
        raise AnnotationNotFound(workspace.asset_id, annotation_id)
    return annotation


def _with(asset: Asset, annotation: Annotation) -> Asset:
    """The asset with one annotation replaced in place, keeping the file's order."""
    return replace(asset, annotations=replaced(asset.annotations, annotation))


def _open(annotation: Annotation) -> None:
    """Refuse a second exit, naming the one it already took."""
    if annotation.has_exited:
        raise AnnotationRejected(
            annotation.id,
            f"annotation {annotation.id!r} is already {annotation.state}; "
            "reopen it before taking the other exit",
            FailureKind.CONFLICT,
        )


def _permitted(
    workspace: Workspace,
    loaded: Loaded,
    operation: Operation,
    annotation: Annotation | None = None,
) -> None:
    """The matrix, asked once per operation and never re-decided here."""
    decision = decide(
        workspace.actor,
        operation,
        Subject(
            project=workspace.project,
            author=_actor_id(annotation.author) if annotation else None,
            discipline_owner=_discipline_owner(workspace, loaded, annotation),
            has_git_identity=workspace.author is not None,
            description=f"annotation {annotation.id}" if annotation else workspace.asset_id,
        ),
        via=workspace.via,
    )
    if decision.refused:
        raise AnnotationRejected(
            annotation.id if annotation else workspace.asset_id,
            decision.reason,
            FailureKind.FORBIDDEN,
        )


def _discipline_owner(
    workspace: Workspace, loaded: Loaded, annotation: Annotation | None
) -> ActorId | None:
    """Who owns the discipline this feedback belongs to, resolved to an actor."""
    if annotation is None:
        return None
    mapping = workspace.spec_store.load_actor_mapping(loaded.path).mapping
    owners = discipline_owners(loaded.asset, mapping)
    return getattr(owners, _OWNER_FIELDS[annotation.kind], None)


def _anchored(loaded: Loaded, workspace: Workspace, anchor: Anchor) -> None:
    """Refuse an anchor naming a subject this asset does not have, naming it."""
    if isinstance(anchor, Anchor2D) and anchor.view not in loaded.views:
        raise AnnotationRejected(
            anchor.view,
            f"{workspace.asset_id} has no view named {anchor.view!r}; "
            f"its views are {_listed(loaded.views)}",
            FailureKind.NOT_FOUND,
        )
    if (
        not isinstance(anchor, Anchor2D)
        and workspace.parts is not None
        and anchor.part not in workspace.parts
    ):
        raise AnnotationRejected(
            anchor.part,
            f"{workspace.asset_id} has no part named {anchor.part!r}; "
            f"its parts are {_listed(workspace.parts)}",
            FailureKind.NOT_FOUND,
        )


def _same_form(annotation: Annotation, anchor: Anchor) -> None:
    """A move stays in the same medium: *"a different anchor of the same form"*."""
    if isinstance(annotation.target, Anchor2D) != isinstance(anchor, Anchor2D):
        raise AnnotationRejected(
            annotation.id,
            f"annotation {annotation.id!r} cannot be moved between anchor forms; "
            "a 2D pin moves within the views and a 3D pin between parts",
            FailureKind.INVALID,
        )


def _listed(names: Sequence[str]) -> str:
    return ", ".join(names) if names else "none"


def _stated(text: str, what: str) -> str:
    """Refuse an empty contribution rather than record one nobody wrote."""
    stated = text.strip()
    if not stated:
        raise AnnotationRejected(
            "text", f"{what} says something; this one is empty", FailureKind.INVALID
        )
    return stated


def _summary(text: str) -> str:
    return text


def _stamp(moment: datetime) -> str:
    """How a time is written into the file: ISO-8601, to the second, in UTC."""
    return moment.replace(microsecond=0).isoformat()


def _parsed(stamp: str) -> datetime | None:
    """A recorded time, or ``None`` when the file carries none or a broken one."""
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def _actor_id(subject: str) -> ActorId | None:
    """An identity subject as the type policy compares, or ``None``."""
    try:
        return ActorId(subject)
    except ValueError:
        return None


def _pinned(
    spec_store: SpecStore, project: str, repository_host: RepositoryHost | None
) -> SpecStore:
    """The store, pinned to the revision the project serves when there is one (D3)."""
    if repository_host is None:
        return spec_store
    return spec_store.pinned(repository_host.head(project).value)


def kind_of(declared: str) -> AnnotationKind | None:
    """The kind this text names, or ``None`` — the one place a surface parses one."""
    return next((member for member in AnnotationKind if member.value == declared.strip()), None)


def state_of(declared: str) -> AnnotationState | None:
    """The exit state this text names, or ``None``."""
    return next((member for member in AnnotationState if member.value == declared.strip()), None)


def refused(identifier: str, message: str, subject: str = "") -> Result[None]:
    """A refusal a surface composed for itself, in the one vocabulary (D10)."""
    return refuse(FailureKind.INVALID, identifier, message, subject)


__all__ = [
    "COMMIT_PREFIX",
    "NOTHING_REANCHORS_ITSELF",
    "REPLAY_ATTEMPTS",
    "AnnotationConflict",
    "AnnotationListing",
    "AnnotationNotFound",
    "AnnotationRejected",
    "AssetNotFound",
    "Draft",
    "Loaded",
    "PromotionInvalid",
    "RecordedAnnotation",
    "TriageQueue",
    "Workspace",
    "available_exits",
    "commit_message",
    "create_annotation",
    "delete_annotation",
    "edit_annotation",
    "kind_of",
    "list_annotations",
    "list_triage_queue",
    "move_annotation",
    "promote_annotation",
    "reanchor_annotation",
    "refused",
    "reopen_annotation",
    "reply_to_annotation",
    "resolve_annotation",
    "state_of",
]
