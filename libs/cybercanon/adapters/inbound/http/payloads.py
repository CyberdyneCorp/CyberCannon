"""Rendering: use-case values as JSON, and not one decision among them.

Every function here takes something a use case produced and returns a mapping.
There is no branch on specification content in this module and there cannot be
one — `tests/tooling/test_http_adapter_is_a_translator.py` walks the syntax tree
of this package looking for exactly that — so a field that is absent renders as
absent, and a field whose value would have to be *decided* is not rendered at
all. A default triangle budget invented here would be the web surface quietly
disagreeing with `canon validate`, which is the failure this product exists to
prevent.

The field names deliberately match the command line's structured output
(:mod:`cybercanon.adapters.inbound.cli.payload`), because `http-api` requires
the same validation to agree across surfaces and the cheapest way to check that
is to compare the two documents. They are **not shared code**: a cross-adapter
import would make one surface's rendering a dependency of the other's, and the
agreement that matters is agreement about the *verdict*, which is shared already
— it is the same use case.
"""

from __future__ import annotations

from base64 import b64encode
from typing import Any

from cybercanon.application.ports.document_platform import CreatedDocument
from cybercanon.application.ports.preview import StoredPreview
from cybercanon.application.use_cases.annotations import (
    AnnotationListing,
    RecordedAnnotation,
    TriageQueue,
)
from cybercanon.application.use_cases.compile_spec import CompiledBriefing, CompiledSpec
from cybercanon.application.use_cases.documents import (
    DocumentListing,
    RecordedLink,
    actions_for,
)
from cybercanon.application.use_cases.hosted_repository import WriteOutcome
from cybercanon.application.use_cases.ingest_views import IngestedView, IngestionOutcome
from cybercanon.application.use_cases.lookup_assets import (
    AssetRow,
    Location,
    LocationAnswer,
    OwnerPresentation,
    SearchAnswer,
)
from cybercanon.application.use_cases.requests import (
    Dismissed,
    RecordedRequest,
    RequestListing,
    UnreadItems,
)
from cybercanon.application.use_cases.search_delegation import (
    EXACT_LABEL,
    DelegatedSearch,
    SemanticResult,
)
from cybercanon.application.use_cases.spec_lens import LensedSpec
from cybercanon.application.use_cases.validate_export import ValidationOutcome
from cybercanon.application.use_cases.view_revisions import (
    RetrievedRevision,
    RevisionComparison,
    ViewToken,
)
from cybercanon.application.use_cases.viewer import (
    ClipCoverage,
    PreviewContent,
    PreviewDescriptor,
    ResolutionListing,
)
from cybercanon.domain.annotations import Annotation, Orphan, Reply, Stroke
from cybercanon.domain.documents import (
    DocumentHistory,
    DocumentRef,
    DocumentRevision,
    LinkedDocument,
)
from cybercanon.domain.report import NotEvaluated, Report
from cybercanon.domain.requests import AssetRequest, RequestEvent
from cybercanon.domain.triage import TriageEntry, exits_for
from cybercanon.domain.views import ConceptView, ViewRevision
from cybercanon.domain.violations import SpecViolation, Violation


def asset_row(row: AssetRow) -> dict[str, Any]:
    """One line of a listing, addressed by the identifier the specification uses."""
    return {
        "asset": row.asset_id,
        "name": row.name,
        "status": row.status,
        "owners": [owner(entry) for entry in row.owners],
    }


def owner(presentation: OwnerPresentation) -> dict[str, Any]:
    return {
        "discipline": presentation.discipline,
        "display": presentation.display,
        "recorded": presentation.is_recorded,
        "unmapped": presentation.is_unmapped,
    }


def location(entry: Location) -> dict[str, Any]:
    return {"label": entry.label, "value": entry.text, "recorded": entry.is_recorded}


def lookup(answer: LocationAnswer) -> dict[str, Any]:
    """Every recorded location of one asset, with the unrecorded ones still named.

    Unrecorded entries travel rather than being filtered out, because *"where is
    the export"* answered by silence is indistinguishable from the question not
    having been asked.
    """
    return {
        "asset": answer.asset_id,
        "name": answer.name,
        "status": answer.status,
        "project": answer.project,
        "locations": [location(entry) for entry in answer.locations],
        "owners": [owner(entry) for entry in answer.owners],
        "stale": answer.stale,
        "notice": answer.notice,
    }


def search(answer: SearchAnswer) -> dict[str, Any]:
    """What a term matched, in the cascade's order — which is the ranking (D9)."""
    return {
        "term": answer.term,
        "project": answer.project,
        "assets": list(answer.asset_ids),
        "recorded_as_miss": answer.recorded_as_miss,
    }


def semantic_group(answer: DelegatedSearch) -> dict[str, Any]:
    """The approximate half of a search, beside the page carrying the exact half.

    It is always present, and that is the point: a group that was asked for and
    came back empty, a group the routing gate never asked for, and a group the
    platform could not answer are three different things, and a response that
    omitted the field when there was nothing in it would render all three as
    the same blank space. `available` plus `reason` distinguishes them, and
    `notice` is the sentence a person reads.

    Every passage names its document and carries the address it is opened at,
    and none of them carries an asset identifier: a semantic hit is not an
    asset record, so there is no field here a client could mistake for one.
    """
    group = answer.semantic
    return {
        "semantic": {
            "label": group.label,
            "approximate": group.is_approximate,
            "delegated": group.delegated,
            "available": group.is_available,
            "reason": str(group.reason) if group.reason is not None else None,
            "notice": group.notice,
            "results": [passage(found) for found in group.results],
        },
        "exact_label": EXACT_LABEL,
    }


def passage(found: SemanticResult) -> dict[str, Any]:
    """One approximate passage: its text, the document it came from, and its address."""
    return {
        "document": found.document_id,
        "workspace": found.workspace,
        "title": found.document_title,
        "source": found.source,
        "url": found.url,
        "text": found.text,
        "provenance": str(found.provenance),
    }


def lensed(spec: LensedSpec) -> dict[str, Any]:
    """One compiled specification as a discipline sees it.

    `full` travels beside `body` for the reason the use case states: a reader
    that took a projection for the whole truth would model against a subset.
    """
    return {
        "asset": spec.asset_id,
        "source": spec.source,
        "lens": str(spec.lens) if spec.lens else None,
        "body": spec.body,
        "full": spec.full,
        "notice": spec.notice,
    }


def compiled(spec: CompiledSpec) -> dict[str, Any]:
    """An asset's compiled briefing — the same text the command line writes."""
    return {"asset": spec.asset_id, "source": spec.source, "text": spec.text}


def project_briefing(briefing: CompiledBriefing) -> dict[str, Any]:
    """The project's standing rules, with no asset in them."""
    return {"project": briefing.project, "text": briefing.text}


def validation(outcome: ValidationOutcome) -> dict[str, Any]:
    """One export against its governing specification, as data.

    The verdict, its violations and the rules that could not be evaluated are
    three distinct fields, exactly as they are on the command line: folding the
    third into the second would tell a client a rule failed when it never ran.
    """
    return {
        "spec": outcome.spec_path,
        "passed": outcome.passed,
        **report(outcome.report),
        "spec_warnings": [spec_violation(warning) for warning in outcome.spec_warnings],
    }


def report(value: Report) -> dict[str, Any]:
    return {
        "asset": value.asset_id,
        "export": value.export,
        "export_format": str(value.export_format),
        "outcome": value.outcome,
        "violations": [violation(entry) for entry in value.violations],
        "not_evaluated": [not_evaluated(entry) for entry in value.not_evaluated],
        "passed_rules": list(value.passed_rules),
    }


def violation(entry: Violation) -> dict[str, Any]:
    return {
        "rule_id": entry.rule_id,
        "severity": str(entry.severity),
        "subject": entry.subject,
        "observed": entry.observed,
        "expected": entry.expected,
        "message": entry.message,
    }


def spec_violation(entry: SpecViolation) -> dict[str, Any]:
    return {
        "rule_id": entry.rule_id,
        "severity": str(entry.severity),
        "subject": entry.subject,
        "observed": entry.observed,
        "expected": entry.expected,
        "message": entry.message,
    }


def written(outcome: WriteOutcome) -> dict[str, Any]:
    """One applied edit: the commit it became, and where it landed.

    The revision is the one the push produced, so a caller composing its next
    edit has the value it must declare — which is what keeps the revision
    precondition a round trip rather than a guess.
    """
    return {
        "project": outcome.project,
        "revision": outcome.revision.value,
        "paths": list(outcome.paths),
        "author": outcome.commit.author.email,
        "message": outcome.commit.message,
        "attempts": outcome.attempts,
    }


# --------------------------------------------------------------------------
# Asset requests (D7) — repository content, rendered like any other read
# --------------------------------------------------------------------------


def asset_request(request: AssetRequest) -> dict[str, Any]:
    """One request, whole: what was asked, who owns it, and everything it did.

    The history travels with it rather than behind a second address, because it
    *is* the request — D7 keeps the state history in the file, and a caller that
    had to ask twice would be able to render a state nobody was attributed for.
    """
    return {
        "id": str(request.id),
        "author": str(request.author),
        "discipline": str(request.discipline),
        "description": request.description,
        "asset": _named(request.asset),
        "asked_for": _named(request.asked_for_status),
        "assignee": _named(request.assignee),
        "state": str(request.state),
        "terminal": request.is_terminal,
        "needs_owner": request.needs_owner,
        "history": [request_event(event) for event in request.history],
    }


def request_event(event: RequestEvent) -> dict[str, Any]:
    """One thing that happened to a request: what, who, when."""
    return {
        "kind": str(event.kind),
        "actor": str(event.actor),
        "at": event.at.isoformat(),
        "state": _named(event.state),
        "assignee": _named(event.assignee),
        "reason": event.reason,
    }


def recorded_request(recorded: RecordedRequest) -> dict[str, Any]:
    """A request as it now stands, and the commit that recorded it (D7).

    The revision is the commit the transition became, so *"every transition is a
    commit"* is visible to the caller rather than only to `git log`.
    """
    return {"request": asset_request(recorded.request), "revision": recorded.revision}


def request_listing(listing: RequestListing) -> dict[str, Any]:
    """Every request a project holds, with the files that would not read named."""
    return {
        "project": listing.project,
        "requests": [asset_request(request) for request in listing.requests],
        "unreadable": [
            {"path": entry.path, "reason": entry.reason} for entry in listing.unreadable
        ],
    }


def unread_items(items: UnreadItems) -> dict[str, Any]:
    """One person's unread items, counted — never anybody else's (D9)."""
    return {
        "project": items.project,
        "actor": str(items.actor),
        "count": items.count,
        "items": [asset_request(request) for request in items.items],
    }


def dismissal(dismissed: Dismissed) -> dict[str, Any]:
    """One person saying they have seen one item, and when."""
    return {
        "project": dismissed.project,
        "actor": str(dismissed.actor),
        "request": str(dismissed.request_id),
        "at": dismissed.at.isoformat(),
    }


def _named(value: Any) -> str | None:
    """How an optional identifier renders: its own spelling, or nothing at all."""
    return str(value) if value is not None else None


def not_evaluated(entry: NotEvaluated) -> dict[str, Any]:
    return {
        "rule_id": entry.rule_id,
        "missing_fact": entry.missing_fact.label,
        "reason": entry.reason,
    }


# --------------------------------------------------------------------------
# Concept views (add-concept-ingestion)
# --------------------------------------------------------------------------


def ingested_view(view: IngestedView) -> dict[str, Any]:
    """One ingested slot, including the content hash of what was committed (D8).

    The hash is always rendered, because a view reference that omitted it could
    not be recognised as superseded — which is the whole of the freshness
    requirement, and the reason `view_reference` exists one layer down.
    """
    return {
        "asset": view.asset_id,
        "slot": str(view.slot),
        "path": view.path,
        "content_hash": view.facts.content_hash.labelled,
        "key": view.key,
        "replaced": view.replaced,
        "removed_path": view.removed_path or None,
        "mirrored": view.mirrored,
        "annotations_carried": view.carried,
        "annotations_orphaned": view.orphaned,
    }


def ingested(outcome: IngestionOutcome) -> dict[str, Any]:
    """What one upload did: the commit, the views, and every pending derived step."""
    return {
        "project": outcome.project,
        "asset": outcome.asset_id,
        "revision": outcome.revision.value,
        "committed": outcome.committed,
        "created_asset": outcome.created_asset,
        "message": outcome.commit_message,
        "views": [ingested_view(view) for view in outcome.views],
        "unchanged": list(outcome.unchanged),
        "awaiting_mirror": list(outcome.awaiting_mirror),
        "mirror_reason": outcome.mirror_reason,
        "thumbnails_pending": outcome.thumbnails_pending,
        "annotations_carried": outcome.carried,
        "annotations_orphaned": outcome.orphaned,
    }


def view_revision(entry: ViewRevision) -> dict[str, Any]:
    """One entry of a revision listing: identifier, person, time, content hash."""
    return {
        "revision": entry.revision,
        "author": entry.author,
        "at": entry.at.isoformat(),
        "content_hash": entry.content_hash.labelled if entry.content_hash else None,
        "dimensions": entry.dimensions,
        "byte_size": entry.byte_size,
        "current": entry.is_current,
        "removed": entry.removed,
    }


def view_history(view: ConceptView) -> dict[str, Any]:
    """A view's revisions, newest first, and whether that is all of them.

    `complete` and `truncated_before` travel together because
    `view-versioning` forbids presenting a truncated list as the whole history:
    a client that received only the list would have no way to know.
    """
    return {
        "asset": view.asset_id,
        "slot": str(view.slot),
        "path": view.path,
        "removed": view.is_removed,
        "complete": view.is_complete,
        "truncated_before": view.truncated_before or None,
        "revisions": [view_revision(entry) for entry in view.revisions],
    }


def view_revision_image(retrieved: RetrievedRevision) -> dict[str, Any]:
    """One revision's image, base64, labelled with what it is.

    `historical` is carried as its own field rather than left to be derived from
    `current`, because *"it SHALL be labelled historical together with its
    identifier"* is a statement about the answer, not about what a reader can
    work out.
    """
    return {
        "asset": retrieved.asset_id,
        "slot": str(retrieved.slot),
        "revision": retrieved.revision,
        "author": retrieved.author,
        "content_hash": retrieved.content_hash.labelled,
        "current": retrieved.is_current,
        "historical": retrieved.historical,
        "label": retrieved.label,
        "content": b64encode(retrieved.content).decode("ascii"),
    }


def compared_revision(entry) -> dict[str, Any]:
    """One side of a comparison — every field the specification enumerates."""
    return {
        "revision": entry.revision,
        "author": entry.author,
        "at": entry.at,
        "dimensions": entry.dimensions,
        "byte_size": entry.byte_size,
        "content_hash": entry.content_hash,
        "current": entry.is_current,
    }


def view_comparison(comparison: RevisionComparison) -> dict[str, Any]:
    """Two revisions, older first whichever order they were asked for."""
    return {
        "asset": comparison.asset_id,
        "slot": str(comparison.slot),
        "older": compared_revision(comparison.older),
        "newer": compared_revision(comparison.newer),
        "identical": comparison.identical,
    }


def view_token(token: ViewToken) -> dict[str, Any]:
    """What a surface polls to learn whether what it shows is still current (D8)."""
    return {
        "asset": token.asset_id,
        "slot": token.slot,
        "revision": token.revision,
        "content_hash": token.identity or None,
    }


__all__ = [
    "asset_request",
    "asset_row",
    "compared_revision",
    "compiled",
    "dismissal",
    "ingested",
    "ingested_view",
    "lensed",
    "location",
    "lookup",
    "not_evaluated",
    "owner",
    "project_briefing",
    "recorded_request",
    "report",
    "request_event",
    "request_listing",
    "search",
    "spec_violation",
    "unread_items",
    "validation",
    "view_comparison",
    "view_history",
    "view_revision",
    "view_revision_image",
    "view_token",
    "violation",
    "written",
]


# --------------------------------------------------------------------------
# Annotations, threads and the triage queue (add-model-sheet-2d)
# --------------------------------------------------------------------------


def anchor(target: Any) -> dict[str, Any]:
    """Both anchor forms in one shape, so a mixed list renders uniformly.

    `annotation-authoring` requires *"both forms returned by the same filter
    with the same fields present"*, so the renderer writes the members each form
    carries and never a second document shape for the other medium.
    """
    return _present(
        {
            "view": getattr(target, "view", None),
            "u": getattr(target, "u", None),
            "v": getattr(target, "v", None),
            "part": getattr(target, "part", None),
            "bone": getattr(target, "bone", None),
            "point": _triple(getattr(target, "point", None)),
            "normal": _triple(getattr(target, "normal", None)),
            "camera": _camera(getattr(target, "camera", None)),
            "clip": getattr(target, "clip", None),
            "t": getattr(target, "t", None),
            "durable_key": target.durable_key,
        }
    )


def _triple(value: Any) -> list[float] | None:
    return None if value is None else [float(part) for part in value]


def _camera(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "position": _triple(value.position),
        "target": _triple(value.target),
        "fov_deg": value.fov_deg,
    }


def _present(fields: dict[str, Any]) -> dict[str, Any]:
    """The members that carry something. An absent one is absent, never invented."""
    return {name: value for name, value in fields.items() if value is not None}


def reply(entry: Reply) -> dict[str, Any]:
    """One contribution to a thread — no anchor, no kind, no exit of its own."""
    return {
        "id": entry.id,
        "author": entry.author,
        "via": entry.via or None,
        "attribution": entry.attribution,
        "text": entry.text,
        "at": entry.at,
        "edited_at": entry.edited_at or None,
    }


def stroke(mark: Stroke) -> list[list[float]]:
    """One freehand mark as ordered normalized pairs — never pixels (D8)."""
    return [[point[0], point[1]] for point in mark.points]


def annotation(entry: Annotation) -> dict[str, Any]:
    """One annotation, with the attribution rendered as the person and the agent.

    `author_kind` and `observation_kind` travel because `mcp-write-surface`
    requires agent authorship to be visible *"wherever an annotation is
    presented to a person"* — a triage view included — and a client that had to
    infer it from `via` would be inferring it from a field an agent is allowed
    to leave empty.
    """
    return {
        "id": entry.id,
        "kind": str(entry.kind),
        "author": entry.author,
        "via": entry.via or None,
        "attribution": entry.attribution,
        "author_kind": str(entry.author_kind),
        "observation_kind": str(entry.observation_kind) if entry.observation_kind else None,
        "text": entry.text,
        "state": str(entry.state),
        "anchor": anchor(entry.target),
        "anchor_state": str(entry.anchor_state),
        "authored_against": entry.authored_against or None,
        "created_at": entry.created_at or None,
        "edited_at": entry.edited_at or None,
        "moved_by": entry.moved_by or None,
        "moved_at": entry.moved_at or None,
        "closed_by": entry.closed_by or None,
        "closed_at": entry.closed_at or None,
        "closing_text": entry.closing_text or None,
        "replies": [reply(contribution) for contribution in entry.replies],
        "strokes": [stroke(mark) for mark in entry.strokes],
        "exits": [str(offered) for offered in exits_for(entry)],
    }


def orphan(entry: Orphan) -> dict[str, Any]:
    """An orphan and the reason it cannot be placed, which a panel has to state."""
    return {
        "id": entry.annotation.id,
        "subject": entry.subject,
        "reason": entry.reason,
        "annotation": annotation(entry.annotation),
    }


def annotation_listing(listing: AnnotationListing) -> dict[str, Any]:
    """One asset's annotations as a filter asked for them, and what it hid."""
    return {
        "project": listing.project,
        "asset": listing.asset_id,
        "path": listing.path,
        "revision": listing.revision,
        "annotations": [annotation(entry) for entry in listing.annotations],
        "hidden": listing.hidden,
        "orphans": [orphan(entry) for entry in listing.orphaned],
        "view_names": list(listing.views),
        "actor": listing.actor,
        "may_promote": listing.may_promote,
    }


def recorded_annotation(recorded: RecordedAnnotation) -> dict[str, Any]:
    """What a write produced: the annotation, the file and the commit."""
    return {
        "project": recorded.project,
        "asset": recorded.asset_id,
        "path": recorded.path,
        "revision": recorded.revision,
        "committed": recorded.committed,
        "annotation": annotation(recorded.annotation),
    }


def triage_entry(entry: TriageEntry) -> dict[str, Any]:
    """One queue entry: the four signals a promotion pass reads, and no text rule."""
    return {
        "asset": entry.asset,
        "kind": str(entry.kind),
        "same_kind_on_asset": entry.same_kind_on_asset,
        "same_kind_in_project": entry.same_kind_in_project,
        "replies": entry.replies,
        "age_seconds": entry.age_seconds,
        "discipline_owner": entry.discipline_owner or None,
        "annotation": annotation(entry.annotation),
    }


def triage_queue(queue: TriageQueue) -> dict[str, Any]:
    """The project's open annotations, already ordered by the domain."""
    return {
        "project": queue.project,
        "entries": [triage_entry(entry) for entry in queue.entries],
        "unreadable": list(queue.unreadable),
    }


# --------------------------------------------------------------------------
# The 3D viewer (add-viewer-3d)
# --------------------------------------------------------------------------


def preview_descriptor(descriptor: PreviewDescriptor) -> dict[str, Any]:
    """What to load and what it is, with every absence stated rather than implied.

    `source_export` is a **path**, carried so the viewer can say which export is
    on screen. It is not an address: nothing in this document, and no route this
    surface registers, resolves to a working export (D7).
    """
    return {
        "project": descriptor.project,
        "asset": descriptor.asset_id,
        "path": descriptor.path,
        "revision": descriptor.revision,
        "preview": _stored_preview(descriptor.preview),
        "source_export": descriptor.source_export or None,
        "latest_validated_export": descriptor.latest_validated_export or None,
        "derived_from_latest": descriptor.derived_from_latest,
        # The figures are named by the use case (`SourceCounts.reported`), not
        # here: a surface that spelled `triangles` would be a surface one `if`
        # away from comparing it against a budget, and the guard in
        # `tests/tooling/test_rule_logic_stays_in_the_domain.py` says so.
        "counts": dict(descriptor.counts.reported),
        "source_visuals": _source_visuals(descriptor),
        "parts": list(descriptor.parts),
        "clips": list(descriptor.clips),
        "coverage": _coverage(descriptor.coverage),
        "absent": descriptor.absent.name.lower() if descriptor.absent else None,
        "reason": descriptor.reason or None,
    }


def _source_visuals(descriptor: PreviewDescriptor) -> dict[str, Any] | None:
    visuals = descriptor.source_visuals
    if visuals is None:
        return None
    return {
        "textures": [
            {
                "material": texture.material,
                "channel": texture.channel,
                "width": texture.width,
                "height": texture.height,
            }
            for texture in visuals.textures
        ]
    }


def _stored_preview(preview: StoredPreview | None) -> dict[str, Any] | None:
    if preview is None:
        return None
    return {
        "key": preview.key,
        "source_export": preview.source_export,
        "size_bytes": preview.size_bytes,
        "content_type": preview.content_type,
    }


def _coverage(coverage: ClipCoverage) -> dict[str, Any]:
    """Every declared state, and every clip no declared state claims (D8).

    The states travel as one list in declaration order rather than as three,
    because `animation-playback` requires a state with no clip to be *listed
    rather than omitted* and a renderer that read three lists would be free to
    render two of them.
    """
    return {
        "states": [
            {"state": entry.state, "clip": entry.clip or None, "coverage": str(entry.coverage)}
            for entry in coverage.states
        ],
        "unclaimed": list(coverage.unclaimed),
    }


def preview_content(content: PreviewContent) -> dict[str, Any]:
    """The preview's bytes, base64, exactly as the store holds them."""
    return {
        "asset": content.asset_id,
        "preview": content.key,
        "source_export": content.source_export or None,
        "content_type": content.content_type,
        "size_bytes": content.size_bytes,
        "content": b64encode(content.content).decode("ascii"),
    }


def anchor_resolutions(listing: ResolutionListing) -> dict[str, Any]:
    """Each mesh-anchored annotation's standing, and the orphan count beside it."""
    return {
        "project": listing.project,
        "asset": listing.asset_id,
        "export": listing.export or None,
        "revision": listing.revision,
        "orphaned": listing.orphan_count,
        "resolutions": [
            {
                "id": entry.id,
                "outcome": str(entry.resolution.outcome),
                "part": entry.resolution.part,
                "bone": entry.resolution.bone or None,
                "reason": entry.resolution.reason or None,
            }
            for entry in listing.entries
        ],
    }


# --------------------------------------------------------------------------
# Linked documents (`document-platform`)
# --------------------------------------------------------------------------


def document_reference(ref: DocumentRef) -> dict[str, Any]:
    """A link exactly as the repository holds it — five members, and no title.

    A resolved title is cache and lives on the card beside this, never here, so
    a client that stored a reference cannot end up holding a name the platform
    has since changed (D1).
    """
    return {
        "document": ref.document_id,
        "workspace": ref.workspace,
        "url": ref.url,
        "linked_by": ref.linked_by,
        "linked_at": ref.linked_at,
    }


def linked_document(entry: LinkedDocument) -> dict[str, Any]:
    """One entry of an asset's link list: the reference, its scope, its state.

    `title` and `summary` come off the card, which the domain has already
    emptied for a forbidden document — so there is no rule here about what a
    viewer may see, and there cannot be one that disagrees with the domain's.
    """
    return {
        **document_reference(entry.ref),
        "scope": str(entry.scope),
        "state": str(entry.state),
        "resolved": entry.is_resolved,
        "title": entry.card.title,
        "summary": entry.card.summary,
        "display_title": entry.card.display_title,
        "resolved_at": entry.card.resolved_at,
        "actions": list(actions_for(entry)),
    }


def document_listing(listing: DocumentListing) -> dict[str, Any]:
    """Every link an asset carries, its own and its project's, as this viewer sees it.

    `available` and `reason` are the distinguishing half of *"the feature
    reports itself unavailable and names the reason"*: the entries are present
    and openable whatever the platform is doing, and this says why none of them
    carries a title. `guidance` is the sentence the authoring surface shows at
    the point somebody chooses where to write a statement, and it travels with
    the listing so that every surface shows the same one.
    """
    return {
        "project": listing.project,
        "asset": listing.asset_id,
        "path": listing.path,
        "available": listing.is_available,
        "reason": str(listing.unavailable_reason)
        if listing.unavailable_reason is not None
        else None,
        "guidance": listing.guidance,
        "links": [linked_document(entry) for entry in listing.entries],
    }


def created_document(created: CreatedDocument) -> dict[str, Any]:
    """The document that now exists at the platform, named so it is never lost."""
    return {
        "document": created.document_id,
        "workspace": created.workspace,
        "url": created.url,
        "title": created.title,
    }


def recorded_link(recorded: RecordedLink) -> dict[str, Any]:
    """A link as it now stands, and the commit that recorded it."""
    return {
        "project": recorded.project,
        "scope": str(recorded.scope),
        "path": recorded.path,
        "revision": recorded.revision,
        "committed": recorded.committed,
        "reference": document_reference(recorded.ref),
        "created": created_document(recorded.created) if recorded.created is not None else None,
    }


def document_revision(revision: DocumentRevision) -> dict[str, Any]:
    """One entry of a linked document's history. Metadata only — never a body."""
    return {
        "id": revision.id,
        "seq": revision.seq,
        "created_at": revision.created_at,
        "label": revision.label,
        "name": revision.name,
    }


def document_history(history: DocumentHistory) -> dict[str, Any]:
    """The platform's own version history, read and not copied.

    An unreadable document answers with its state and an empty series rather
    than with a refusal, because *one* link the viewer may not see is not a
    reason for the asset's page to fail.
    """
    return {
        "reference": document_reference(history.ref),
        "state": str(history.state),
        "readable": history.is_readable,
        "revisions": [document_revision(revision) for revision in history.revisions],
    }
