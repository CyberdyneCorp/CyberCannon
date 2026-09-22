/**
 * D1 — the one ViewModel, serving both the 2D sheet and the 3D viewer.
 *
 * This is the claim `openspec/project.md` makes about the whole frontend:
 * *"Use MVVM where it pays: one `AnnotationViewModel` serving both the 2D model
 * sheet and the 3D viewer. The views' only job is to turn input into an
 * `Anchor`; threads, filtering, triage, status are written once and tested with
 * no DOM and no GPU. That is what makes 'support 2D and 3D' cost far less than
 * twice."*
 *
 * Three rules make that true rather than aspirational, and each is checked:
 *
 * * **it never inspects an anchor's form.** There is no `anchor.view`, no
 *   `anchor.part` and no `instanceof` anywhere below: an anchor arrives from a
 *   view, is carried, and is sent. `tests/annotation-view-model.test.ts` reads
 *   this module's source and fails the build over a branch on either member —
 *   grouping pins by view is the *sheet's* job, and putting it here is exactly
 *   how the 3D change would end up forking this file.
 * * **it touches no DOM type.** No `Element`, no `PointerEvent`, no canvas
 *   context. The pixel maths is `$lib/annotation/transform`'s and the input rule
 *   is `$lib/annotation/pointer`'s; a test imports this module in an environment
 *   with no DOM and exercises every operation.
 * * **server state is not held here** (D9). The listing is read through an
 *   injected :type:`AnnotationModel`, which is the query cache behind the typed
 *   client; what lives here is *client* state — selection, filter, draft text,
 *   draft strokes and pending writes — and an optimistic entry, which is
 *   removed the moment a write is known to have failed.
 *
 * The module exports a factory for tests and a singleton for the application,
 * exactly as the convention in `openspec/project.md` describes: *"ViewModel =
 * `*.svelte.ts` (module singleton + `createXxx()` factory for tests)"*.
 */

import type {
	Annotation,
	AnnotationKind,
	AnnotationListing,
	AnnotationState,
	Anchor,
	ApiResult,
	Orphan,
	PromotionTarget,
	RecordedAnnotation,
	Stroke
} from '$lib/api';
import { anchorPayload } from './anchor';
import type { ImagePoint } from './anchor';
import type { AnnotationFilter } from './filter';
import {
	DEFAULT_FILTER,
	applyFilter,
	filterQuery,
	hiddenCount,
	toggleKind,
	toggleState
} from './filter';
import type { AnnotationModel } from './model';
import type { Gesture, InputSession } from './pointer';
import { NEW_SESSION, afterGesture, intentOf } from './pointer';

/** What a person is composing: the text, the kind, the anchor and the marks. */
export interface Draft {
	readonly kind: AnnotationKind;
	readonly text: string;
	readonly anchor: Anchor | null;
	readonly strokes: readonly Stroke[];
	readonly drawing: readonly (readonly [number, number])[];
}

export const EMPTY_DRAFT: Draft = {
	kind: 'art-direction',
	text: '',
	anchor: null,
	strokes: [],
	drawing: []
};

/** Where a write is in its life. `settled` is not a state — it is the absence of one. */
export type WriteState = 'idle' | 'pending' | 'failed';

/** What an optimistic entry names as its author until the server says otherwise. */
const PROVISIONAL = 'provisional';

export class AnnotationViewModel {
	/** The asset these threads belong to, and the revision they were read at. */
	project = $state('');
	asset = $state('');
	revision = $state('');

	/** The threads as the last read produced them, plus any optimistic entry. */
	annotations = $state<readonly Annotation[]>([]);
	/** The ones that cannot be placed, with the reason a panel has to state. */
	orphans = $state<readonly Orphan[]>([]);
	/** The views this asset has, by the name an anchor keys on. */
	views = $state<readonly string[]>([]);

	filter = $state<AnnotationFilter>(DEFAULT_FILTER);
	selectedId = $state<string | null>(null);
	draft = $state<Draft>(EMPTY_DRAFT);

	/** The identifiers of annotations shown before their write has landed. */
	pending = $state<readonly string[]>([]);
	writeState = $state<WriteState>('idle');
	/** What went wrong, in the words the system used. Never invented here. */
	error = $state<string | null>(null);

	/** Whether a stylus has been used on this sheet (D10). Reset with the sheet. */
	session = $state<InputSession>(NEW_SESSION);

	#model: AnnotationModel | null = null;

	// -- wiring ---------------------------------------------------------

	/** Point this ViewModel at an asset and the Model that answers for it. */
	attach(model: AnnotationModel, project: string, asset: string): void {
		this.#model = model;
		this.project = project;
		this.asset = asset;
		this.reset();
	}

	/** Forget everything about the asset that was open. A sheet is per asset. */
	reset(): void {
		this.annotations = [];
		this.orphans = [];
		this.views = [];
		this.revision = '';
		this.filter = DEFAULT_FILTER;
		this.selectedId = null;
		this.draft = EMPTY_DRAFT;
		this.pending = [];
		this.writeState = 'idle';
		this.error = null;
		this.session = NEW_SESSION;
	}

	/** Take a listing a route already read, without asking for it again. */
	hydrate(listing: AnnotationListing): void {
		this.project = listing.project;
		this.asset = listing.asset;
		this.revision = listing.revision;
		this.annotations = listing.annotations;
		this.orphans = listing.orphans;
		this.views = listing.view_names;
		this.pending = [];
	}

	// -- reading --------------------------------------------------------

	/** Ask the Model for this asset's threads, unfiltered, and hold the answer. */
	async load(): Promise<void> {
		const answer = await this.#read();
		if (answer === null) return;
		if (!answer.ok) {
			this.error = answer.failure.message;
			return;
		}
		this.error = null;
		this.hydrate(answer.data);
	}

	async #read(): Promise<ApiResult<AnnotationListing> | null> {
		if (this.#model === null) return null;
		return this.#model.list(this.project, this.asset, {}, this.revision);
	}

	/** The annotations the current filter wants, in the order they were read. */
	get visible(): readonly Annotation[] {
		return applyFilter(this.filter, this.annotations);
	}

	/** How many the current filter is keeping off the views (`model-sheet-2d`). */
	get hidden(): number {
		return hiddenCount(this.filter, this.annotations);
	}

	/** The annotations a surface may draw. An orphan is listed and never placed. */
	get placeable(): readonly Annotation[] {
		return this.visible.filter((annotation) => annotation.anchor_state !== 'orphaned');
	}

	get selected(): Annotation | null {
		return this.annotations.find((entry) => entry.id === this.selectedId) ?? null;
	}

	/** The exits the selected thread is offered — the system's answer, not ours. */
	get exits(): readonly string[] {
		return this.selected?.exits ?? [];
	}

	get isComposing(): boolean {
		return this.draft.anchor !== null;
	}

	// -- selection and filtering ----------------------------------------

	/** Exactly one annotation is selected at a time (`model-sheet-2d`). */
	select(id: string | null): void {
		this.selectedId = id;
	}

	setFilter(filter: AnnotationFilter): void {
		this.filter = filter;
	}

	toggleKind(kind: AnnotationKind): void {
		this.filter = toggleKind(this.filter, kind);
	}

	toggleState(state: AnnotationState): void {
		this.filter = toggleState(this.filter, state);
	}

	// -- composing ------------------------------------------------------

	/**
	 * Begin an annotation at this anchor.
	 *
	 * The anchor is whatever the view produced. Nothing here asks what shape it
	 * is, which is the whole of D1: the 3D viewer calls this with an anchor of
	 * its own and adds no code anywhere in this file.
	 */
	compose(anchor: Anchor): void {
		this.draft = { ...EMPTY_DRAFT, kind: this.draft.kind, anchor };
		this.selectedId = null;
		this.error = null;
	}

	setDraftText(text: string): void {
		this.draft = { ...this.draft, text };
	}

	setDraftKind(kind: AnnotationKind): void {
		this.draft = { ...this.draft, kind };
	}

	/** Throw the composition away. Nothing was recorded, so nothing is left. */
	discard(): void {
		this.draft = EMPTY_DRAFT;
		this.error = null;
	}

	// -- the scribble layer (D8) ----------------------------------------

	beginStroke(point: ImagePoint): void {
		this.draft = { ...this.draft, drawing: [[point.u, point.v]] };
	}

	extendStroke(point: ImagePoint): void {
		if (this.draft.drawing.length === 0) return;
		this.draft = { ...this.draft, drawing: [...this.draft.drawing, [point.u, point.v]] };
	}

	/** Close the stroke being drawn. A tap is not a mark, so it is dropped. */
	endStroke(): void {
		const drawn = this.draft.drawing;
		const strokes = drawn.length > 1 ? [...this.draft.strokes, drawn] : this.draft.strokes;
		this.draft = { ...this.draft, strokes, drawing: [] };
	}

	/** Undo the most recent stroke, which is the only stroke operation offered. */
	undoStroke(): void {
		this.draft = { ...this.draft, strokes: this.draft.strokes.slice(0, -1), drawing: [] };
	}

	// -- the input rule (D10) -------------------------------------------

	/** What this gesture is for, and remember a stylus once one has been used. */
	gesture(gesture: Gesture): 'place' | 'draw' | 'navigate' {
		const intent = intentOf(this.session, gesture);
		this.session = afterGesture(this.session, gesture);
		return intent;
	}

	// -- writing --------------------------------------------------------

	/**
	 * Record the composed annotation, showing it at once and removing it if the
	 * write fails.
	 *
	 * *"A pin SHALL appear on the view as soon as it is placed, without waiting
	 * for the write to complete. When the write fails, the pin SHALL be removed
	 * and the failure SHALL be reported with the text preserved."* Both halves
	 * are here, and the draft is only cleared on the success path.
	 */
	async submit(id: string): Promise<boolean> {
		const draft = this.draft;
		if (this.#model === null || draft.anchor === null || !draft.text.trim()) return false;
		this.#optimistic(provisional(id, draft));
		const outcome = await this.#model.create(this.project, this.asset, {
			id,
			kind: draft.kind,
			text: draft.text,
			anchor: anchorPayload(draft.anchor),
			strokes: draft.strokes
		});
		return this.#settled(id, outcome, () => {
			this.draft = EMPTY_DRAFT;
			this.selectedId = id;
		});
	}

	async reply(replyId: string, text: string): Promise<boolean> {
		return this.#onSelected((model, project, asset, id) =>
			model.reply(project, asset, id, { id: replyId, text })
		);
	}

	async edit(text: string): Promise<boolean> {
		return this.#onSelected((model, project, asset, id) =>
			model.edit(project, asset, id, { text })
		);
	}

	async withdraw(): Promise<boolean> {
		const id = this.selectedId;
		const gone = await this.#onSelected((model, project, asset, selected) =>
			model.withdraw(project, asset, selected)
		);
		if (gone && this.selectedId === id) this.selectedId = null;
		return gone;
	}

	/** Move the selected annotation to another anchor the view produced. */
	async move(anchor: Anchor): Promise<boolean> {
		return this.#onSelected((model, project, asset, id) =>
			model.move(project, asset, id, { anchor: anchorPayload(anchor) })
		);
	}

	async resolve(conclusion = ''): Promise<boolean> {
		return this.#onSelected((model, project, asset, id) =>
			model.resolve(project, asset, id, { conclusion })
		);
	}

	async reopen(): Promise<boolean> {
		return this.#onSelected((model, project, asset, id) => model.reopen(project, asset, id));
	}

	/**
	 * Promote the selected thread into a durable rule.
	 *
	 * Offered only to somebody who may promote, and refused by the system for
	 * anybody else — `model-sheet-2d` requires both, and this method is the
	 * second one: it sends the request and reports whatever came back.
	 */
	async promote(rule: string, destination: PromotionTarget): Promise<boolean> {
		return this.#onSelected((model, project, asset, id) =>
			model.promote(project, asset, id, { rule, destination })
		);
	}

	// -- the shared half of every write ---------------------------------

	async #onSelected(
		perform: (
			model: AnnotationModel,
			project: string,
			asset: string,
			id: string
		) => Promise<ApiResult<RecordedAnnotation>>
	): Promise<boolean> {
		const id = this.selectedId;
		if (this.#model === null || id === null) return false;
		this.writeState = 'pending';
		const outcome = await perform(this.#model, this.project, this.asset, id);
		return this.#settled(id, outcome);
	}

	#optimistic(entry: Annotation): void {
		this.annotations = [...this.annotations, entry];
		this.pending = [...this.pending, entry.id];
		this.writeState = 'pending';
		this.error = null;
	}

	/**
	 * What a write leaves behind, whichever way it went.
	 *
	 * On failure the optimistic entry goes and the draft stays, which is the
	 * specified behaviour; the list is then re-read so that what is presented is
	 * what the repository holds and not what this client hoped.
	 */
	#settled(
		id: string,
		outcome: ApiResult<RecordedAnnotation>,
		onRecorded: () => void = () => {}
	): boolean {
		this.pending = this.pending.filter((entry) => entry !== id);
		if (!outcome.ok) {
			this.annotations = this.annotations.filter((entry) => entry.id !== id);
			this.writeState = 'failed';
			this.error = outcome.failure.message;
			return false;
		}
		this.writeState = 'idle';
		this.error = null;
		this.revision = outcome.data.revision;
		onRecorded();
		void this.load();
		return true;
	}
}

/**
 * The annotation a pin shows before the repository has confirmed it.
 *
 * Everything the surface needs to draw it and nothing it could not know: the
 * author and the attribution are the server's to decide, so they are empty
 * rather than guessed, and the entry is replaced by the recorded one — or
 * removed — the moment the write settles.
 */
function provisional(id: string, draft: Draft): Annotation {
	return {
		id,
		kind: draft.kind,
		author: PROVISIONAL,
		via: null,
		attribution: PROVISIONAL,
		text: draft.text,
		state: 'open',
		anchor: draft.anchor as Anchor,
		anchor_state: 'carried',
		authored_against: null,
		created_at: null,
		edited_at: null,
		moved_by: null,
		moved_at: null,
		closed_by: null,
		closed_at: null,
		closing_text: null,
		replies: [],
		strokes: draft.strokes,
		exits: []
	};
}

/** A ViewModel of its own, for a test or a second surface mounted side by side. */
export function createAnnotationViewModel(): AnnotationViewModel {
	return new AnnotationViewModel();
}

/** The one the application uses. A second instance is a second copy of the state. */
export const annotationViewModel = createAnnotationViewModel();

export { filterQuery };
