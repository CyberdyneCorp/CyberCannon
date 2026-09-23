/**
 * The shapes the `http-api` surface renders, as types.
 *
 * Every field here is one `libs/cybercanon/adapters/inbound/http/payloads.py`
 * writes, spelled the same way. Within a version the surface only *adds*, so a
 * field this file does not know about is ignored rather than rejected — which
 * is what lets the backend ship an optional field without breaking a client
 * written against the version before it.
 */

export const SURFACE_VERSION = 'v1';

/** The six outcomes the domain can express. There is no seventh. */
export const FAILURE_KINDS = [
	'not_found',
	'forbidden',
	'unauthenticated',
	'invalid',
	'conflict',
	'unavailable'
] as const;
export type FailureKind = (typeof FAILURE_KINDS)[number];

/** What a read states about the revision it was served from (`hosted-repository`). */
export interface Freshness {
	readonly revision: string;
	readonly confirmedAt: string;
	readonly mayBeStale: boolean;
}

export interface Failure {
	readonly kind: FailureKind;
	readonly identifier: string;
	readonly message: string;
	readonly subject: string | null;
	readonly correlationId: string | null;
}

export type ApiResult<T> =
	| {
			readonly ok: true;
			readonly data: T;
			readonly freshness: Freshness | null;
			/**
			 * Envelope fields this client has no named type for.
			 *
			 * The surface's envelope is an open map that evolves additively within
			 * a version, so a field arriving beside `data` is not an error and is
			 * not silently the truth either: it is kept here, and a caller that
			 * knows what one means reads it through its own typed reader. The
			 * delegated search's approximate group is the first of them.
			 */
			readonly beside?: Readonly<Record<string, unknown>>;
	  }
	| { readonly ok: false; readonly failure: Failure };

/** One approximately retrieved passage, and the document it came from. */
export interface Passage {
	readonly document: string;
	readonly workspace: string;
	readonly title: string;
	readonly source: string;
	readonly url: string;
	readonly text: string;
	readonly provenance: string;
}

/**
 * The approximate half of a search, as the surface states it.
 *
 * Always present in a search response, empty or not, because a group that came
 * back empty, one the routing gate never asked for and one the platform could
 * not answer are three different things and a missing field renders all three
 * as the same blank space.
 */
export interface SemanticGroup {
	readonly label: string;
	readonly approximate: boolean;
	readonly delegated: boolean;
	readonly available: boolean;
	readonly reason: string | null;
	readonly notice: string;
	readonly results: readonly Passage[];
}

export interface Page<T> {
	readonly items: readonly T[];
	readonly next_token: string | null;
	readonly page_size: number;
	readonly total: number;
}

export interface Owner {
	readonly discipline: string;
	readonly display: string;
	readonly recorded: boolean;
	readonly unmapped: boolean;
}

export interface AssetRow {
	readonly asset: string;
	readonly name: string;
	readonly status: string;
	readonly owners: readonly Owner[];
}

export interface Location {
	readonly label: string;
	readonly value: string;
	readonly recorded: boolean;
}

export interface LocationAnswer {
	readonly asset: string;
	readonly name: string;
	readonly status: string;
	readonly project: string;
	readonly locations: readonly Location[];
	readonly owners: readonly Owner[];
	readonly stale: boolean;
	readonly notice: string;
}

/** One search result, and the pass of the cascade that found it (`asset-lookup`). */
export interface SearchHit {
	readonly asset: string;
	readonly name: string;
	readonly matched: string;
}

export interface LensedSpec {
	readonly asset: string;
	readonly source: string;
	readonly lens: string | null;
	readonly body: string;
	readonly full: string;
	readonly notice: string;
}

export interface CompiledSpec {
	readonly asset: string;
	readonly source: string;
	readonly text: string;
}

export interface ProjectBriefing {
	readonly project: string;
	readonly text: string;
}

export interface Violation {
	readonly rule_id: string;
	readonly severity: string;
	readonly subject: string;
	readonly observed: string;
	readonly expected: string;
	readonly message: string;
}

export interface NotEvaluated {
	readonly rule_id: string;
	readonly missing_fact: string;
	readonly reason: string;
}

export interface Report {
	readonly asset: string;
	readonly export: string;
	readonly export_format: string;
	readonly outcome: string;
	readonly violations: readonly Violation[];
	readonly not_evaluated: readonly NotEvaluated[];
	readonly passed_rules: readonly string[];
}

export type ValidationOutcome = Report & {
	readonly spec: string;
	readonly passed: boolean;
	readonly spec_warnings: readonly Violation[];
};

export interface RequestEvent {
	readonly kind: string;
	readonly actor: string;
	readonly at: string;
	readonly state: string | null;
	readonly assignee: string | null;
	readonly reason: string;
}

export interface AssetRequest {
	readonly id: string;
	readonly author: string;
	readonly discipline: string;
	readonly description: string;
	readonly asset: string | null;
	readonly asked_for: string | null;
	readonly assignee: string | null;
	readonly state: string;
	readonly terminal: boolean;
	readonly needs_owner: boolean;
	readonly history: readonly RequestEvent[];
}

export interface RecordedRequest {
	readonly request: AssetRequest;
	readonly revision: string;
}

export interface RequestListing {
	readonly project: string;
	readonly requests: readonly AssetRequest[];
	readonly unreadable: readonly {
		readonly path: string;
		readonly reason: string;
	}[];
}

export interface UnreadItems {
	readonly project: string;
	readonly actor: string;
	readonly count: number;
	readonly items: readonly AssetRequest[];
}

export interface Dismissal {
	readonly project: string;
	readonly actor: string;
	readonly request: string;
	readonly at: string;
}

export interface WriteOutcome {
	readonly project: string;
	readonly revision: string;
	readonly paths: readonly string[];
	readonly author: string;
	readonly message: string;
	readonly attempts: number;
}

/**
 * One project as `/status` reports it.
 *
 * This is the only place the surface names a project without being told which
 * one to look at, so it is where the application learns which projects a person
 * may switch between. That the *operational* endpoint is where that answer
 * lives is a gap in `http-api` — there is no read that simply lists the
 * projects an actor is entitled to — and it is recorded here rather than worked
 * around: the endpoint is authenticated, it applies the same `READ_PROJECT`
 * decision every read applies, and it names the entitled projects and no
 * others, so consuming it reveals nothing a listing would not.
 */
export interface ProjectStatus {
	readonly project: string;
	readonly working_copy: {
		readonly state: string;
		readonly revision: string | null;
		readonly last_fetch_at: string | null;
		readonly reason: string;
	};
	readonly index: {
		readonly indexed_revision: string | null;
		readonly working_copy_revision: string | null;
		readonly in_sync: boolean;
		readonly rebuilding: boolean;
	};
}

export interface StatusReport {
	readonly projects: readonly ProjectStatus[];
}

// --------------------------------------------------------------------------
// Annotations, threads and the triage queue (add-model-sheet-2d)
// --------------------------------------------------------------------------

/** The three kinds an annotation can declare. A closed set, as the domain has it. */
export const ANNOTATION_KINDS = ['art-direction', 'technical', 'design'] as const;
export type AnnotationKind = (typeof ANNOTATION_KINDS)[number];

/** The open state, and the two exits. There is no fourth. */
export const ANNOTATION_STATES = ['open', 'promoted', 'resolved'] as const;
export type AnnotationState = (typeof ANNOTATION_STATES)[number];

/** Whether an anchor still resolves. Independent of the exit state, deliberately. */
export type AnchorState = 'carried' | 'orphaned';

/** The two destinations a promotion may name. */
export const PROMOTION_TARGETS = ['constraints', 'concept.silhouette_rules'] as const;
export type PromotionTarget = (typeof PROMOTION_TARGETS)[number];

export function isAnnotationKind(value: string): value is AnnotationKind {
	return (ANNOTATION_KINDS as readonly string[]).includes(value);
}

export function isAnnotationState(value: string): value is AnnotationState {
	return (ANNOTATION_STATES as readonly string[]).includes(value);
}

/**
 * One anchor, in the one shape the surface renders both forms in.
 *
 * `annotation-authoring` requires a mixed list to come back *"by the same
 * filter with the same fields present"*, so there is deliberately no union
 * here: the members a form does not carry are simply absent, and `durableKey`
 * is what identifies it whichever form it is — which is what lets the shared
 * ViewModel never ask.
 */
export interface Anchor {
	readonly view?: string;
	readonly u?: number;
	readonly v?: number;
	readonly part?: string;
	readonly bone?: string;
	readonly point?: readonly number[];
	readonly normal?: readonly number[];
	readonly camera?: Camera;
	/**
	 * The clip that was on screen, and how far through it, as viewing hints (D9).
	 *
	 * `t` is a **proportion of the clip's duration**, never a frame index: frame
	 * indices are meaningless across a frame-rate change, and there is
	 * deliberately no member here that could hold one. Neither is part of the
	 * durable key — removing the clip from a later export does not orphan the
	 * annotation.
	 */
	readonly clip?: string;
	readonly t?: number;
	readonly durable_key: string;
}

/** The viewing angle an annotation was authored from, so it can be restored. */
export interface Camera {
	readonly position: readonly number[];
	readonly target: readonly number[];
	readonly fov_deg: number;
}

export interface Reply {
	readonly id: string;
	readonly author: string;
	readonly via: string | null;
	readonly attribution: string;
	readonly text: string;
	readonly at: string;
	readonly edited_at: string | null;
}

/** One freehand mark: ordered `[u, v]` pairs in the anchored view's image space. */
export type Stroke = readonly (readonly [number, number])[];

export interface Annotation {
	readonly id: string;
	readonly kind: AnnotationKind;
	readonly author: string;
	readonly via: string | null;
	readonly attribution: string;
	readonly text: string;
	readonly state: AnnotationState;
	readonly anchor: Anchor;
	readonly anchor_state: AnchorState;
	readonly authored_against: string | null;
	readonly created_at: string | null;
	readonly edited_at: string | null;
	readonly moved_by: string | null;
	readonly moved_at: string | null;
	readonly closed_by: string | null;
	readonly closed_at: string | null;
	readonly closing_text: string | null;
	readonly replies: readonly Reply[];
	readonly strokes: readonly Stroke[];
	/** The exits this annotation is offered. Exactly two, or none once it took one. */
	readonly exits: readonly string[];
}

export interface Orphan {
	readonly id: string;
	readonly subject: string;
	readonly reason: string;
	readonly annotation: Annotation;
}

export interface AnnotationListing {
	readonly project: string;
	readonly asset: string;
	readonly path: string;
	readonly revision: string;
	readonly annotations: readonly Annotation[];
	readonly hidden: number;
	readonly orphans: readonly Orphan[];
	readonly view_names: readonly string[];
	/** Who this was read as, so a panel knows whose contributions are whose. */
	readonly actor: string;
	/**
	 * Whether this person may take the promotion exit — the domain's answer.
	 *
	 * `model-sheet-2d` requires the panel to offer promotion *"only to a person
	 * permitted to promote"*, and a client that inferred it from a role claim
	 * would be a second opinion about a permission. Hiding it is a courtesy;
	 * the refusal is the guarantee.
	 */
	readonly may_promote: boolean;
}

export interface RecordedAnnotation {
	readonly project: string;
	readonly asset: string;
	readonly path: string;
	readonly revision: string;
	readonly committed: boolean;
	readonly annotation: Annotation;
}

export interface TriageEntry {
	readonly asset: string;
	readonly kind: AnnotationKind;
	readonly same_kind_on_asset: number;
	readonly same_kind_in_project: number;
	readonly replies: number;
	readonly age_seconds: number;
	readonly discipline_owner: string | null;
	readonly annotation: Annotation;
}

export interface TriageQueue {
	readonly project: string;
	readonly entries: readonly TriageEntry[];
	readonly unreadable: readonly string[];
}


// --------------------------------------------------------------------------
// The 3D viewer (add-viewer-3d)
// --------------------------------------------------------------------------

/** Why an asset has no preview. Three reasons, as the use case distinguishes them. */
export const NO_PREVIEW_REASONS = [
	'no_export_recorded',
	'no_successful_validation',
	'emission_failed'
] as const;
export type NoPreviewReason = (typeof NO_PREVIEW_REASONS)[number];

/** What became of one declared design state against the clips on hand (D8). */
export type StateCoverage = 'satisfied' | 'no clip' | 'declared unanimated';

export interface CoveredState {
	readonly state: string;
	readonly clip: string | null;
	readonly coverage: StateCoverage;
}

export interface ClipCoverage {
	readonly states: readonly CoveredState[];
	/** Clips the preview carries that no declared state requires. Listed, never an error. */
	readonly unclaimed: readonly string[];
}

export interface StoredPreview {
	readonly key: string;
	readonly source_export: string;
	readonly size_bytes: number;
	readonly content_type: string;
}

/**
 * Everything the viewer needs before it loads anything.
 *
 * `source_export` is a path the viewer *states*; it is not an address, and no
 * route this surface publishes resolves to one (D7).
 */
export interface PreviewDescriptor {
	readonly project: string;
	readonly asset: string;
	readonly path: string;
	readonly revision: string;
	readonly preview: StoredPreview | null;
	readonly source_export: string | null;
	readonly latest_validated_export: string | null;
	readonly derived_from_latest: boolean;
	readonly counts: {
		readonly triangles: number | null;
		readonly objects: number | null;
		readonly materials: number | null;
	};
	readonly parts: readonly string[];
	readonly clips: readonly string[];
	readonly coverage: ClipCoverage;
	readonly absent: NoPreviewReason | null;
	readonly reason: string | null;
}

/** The preview's bytes, base64, exactly as the store holds them. */
export interface PreviewContent {
	readonly asset: string;
	readonly preview: string;
	readonly source_export: string | null;
	readonly content_type: string;
	readonly size_bytes: number;
	readonly content: string;
}

export interface AnchorResolutionRow {
	readonly id: string;
	readonly outcome: 'resolved' | 'partial' | 'orphaned';
	readonly part: string;
	readonly bone: string | null;
	readonly reason: string | null;
}

export interface AnchorResolutions {
	readonly project: string;
	readonly asset: string;
	readonly export: string | null;
	readonly revision: string;
	readonly orphaned: number;
	readonly resolutions: readonly AnchorResolutionRow[];
}

/**
 * One document linked to an asset or to its project, as this viewer sees it.
 *
 * There is no `body` here and there cannot be one: `document-platform` keeps
 * the document's contents, its history and its comments at the platform, and a
 * field able to hold prose would be the mirror D1 refuses. `title` and
 * `summary` are empty for a document the viewer may not read — the surface
 * empties them, so nothing here has to remember to.
 */
export interface LinkedDocument {
	readonly document: string;
	readonly workspace: string;
	readonly url: string;
	readonly linked_by: string;
	readonly linked_at: string;
	readonly scope: 'asset' | 'project';
	readonly state: 'readable' | 'unreachable' | 'missing' | 'forbidden';
	readonly resolved: boolean;
	readonly title: string;
	readonly summary: string;
	readonly display_title: string;
	readonly resolved_at: string;
	readonly actions: readonly string[];
}

/**
 * An asset's links, its project's, and why none of them carries a title.
 *
 * `available` and `reason` are the distinguishing half of *"reports itself
 * unavailable and names the reason"*; `guidance` is the sentence shown where a
 * person chooses whether a statement belongs in the specification or in the
 * document.
 */
export interface DocumentListing {
	readonly project: string;
	readonly asset: string;
	readonly path: string;
	readonly available: boolean;
	readonly reason: string | null;
	readonly guidance: string;
	readonly links: readonly LinkedDocument[];
}

/** One entry of a linked document's history, as the platform reports it. */
export interface DocumentRevision {
	readonly id: string;
	readonly seq: number;
	readonly created_at: string;
	readonly label: string;
	readonly name: string;
}

/** A linked document's own version history — read, never copied. */
export interface DocumentHistory {
	readonly reference: {
		readonly document: string;
		readonly workspace: string;
		readonly url: string;
		readonly linked_by: string;
		readonly linked_at: string;
	};
	readonly state: string;
	readonly readable: boolean;
	readonly revisions: readonly DocumentRevision[];
}

/** A link as it now stands, and the commit that recorded it. */
export interface RecordedLink {
	readonly project: string;
	readonly scope: 'asset' | 'project';
	readonly path: string;
	readonly revision: string;
	readonly committed: boolean;
	readonly reference: DocumentHistory['reference'];
	readonly created: {
		readonly document: string;
		readonly workspace: string;
		readonly url: string;
		readonly title: string;
	} | null;
}
