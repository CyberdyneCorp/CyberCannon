/**
 * Tasks 4.1 to 4.4 — the shared ViewModel, with no DOM and no network anywhere.
 *
 * The whole suite runs in `environment: 'node'` (vite.config.ts), which is D1's
 * cost accepted, asserted: *"the ViewModel may not touch a DOM type, a canvas
 * context or a `three.js` object"*. If it ever does, these cases stop running,
 * which is the loudest possible failure for a boundary nobody can see.
 *
 * And **every case below runs twice** — once with a 2D anchor factory and once
 * with a 3D stub (D12). The case list is the same list, not a superset: if
 * `add-viewer-3d` has to add one, the core was not shared, and the parameters
 * here are where that shows up on day one rather than in month three.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { beforeEach, describe, expect, it } from 'vitest';
import { createAnnotationViewModel } from '../src/lib/annotation';
import type { AnnotationViewModel } from '../src/lib/annotation';
import { partAnchor, viewAnchor } from '../src/lib/annotation';
import type { AnnotationModel } from '../src/lib/annotation';
import type {
	Anchor,
	Annotation,
	AnnotationListing,
	ApiResult,
	RecordedAnnotation
} from '../src/lib/api';

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const VIEW = 'front';
const PART = 'SM_MechScout_Shoulder_L';
const RAFA = 'auth|rafa';

/** The two anchor factories D12 parameterizes the core over. */
const ANCHORS: readonly { readonly name: string; readonly make: () => Anchor }[] = [
	{ name: '2d', make: () => viewAnchor(VIEW, { u: 0.25, v: 0.4 }) as Anchor },
	{ name: '3d stub', make: () => partAnchor(PART) as Anchor }
];

function anAnnotation(id: string, anchor: Anchor, overrides: Partial<Annotation> = {}): Annotation {
	return {
		id,
		kind: 'art-direction',
		author: RAFA,
		via: null,
		attribution: RAFA,
		text: 'the pauldron reads as a backpack at 15 m',
		state: 'open',
		anchor,
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
		strokes: [],
		exits: ['promote', 'resolve'],
		...overrides
	};
}

function aListing(annotations: readonly Annotation[], revision = 'rev-1'): AnnotationListing {
	return {
		project: PROJECT,
		asset: ASSET,
		path: 'characters/mech_scout/asset.yaml',
		revision,
		annotations,
		hidden: 0,
		orphans: [],
		view_names: [VIEW],
		actor: RAFA,
		may_promote: false
	};
}

function ok<T>(data: T): ApiResult<T> {
	return { ok: true, data, freshness: null };
}

function refusal<T>(message = 'the repository is unreachable'): ApiResult<T> {
	return {
		ok: false,
		failure: {
			kind: 'unavailable',
			identifier: 'repository.unavailable',
			message,
			subject: ASSET,
			correlationId: null
		}
	};
}

/**
 * A Model that records what it was asked and answers what a test told it to.
 *
 * It is a plain object, which is the point of the interface: the ViewModel is
 * exercised with no cache, no client and no network, so a case that passes here
 * passes because of the ViewModel and not because of a fake server.
 */
class RecordingModel implements AnnotationModel {
	calls: string[] = [];
	listing: AnnotationListing = aListing([]);
	outcome: ApiResult<RecordedAnnotation> | null = null;

	async list(): Promise<ApiResult<AnnotationListing>> {
		this.calls.push('list');
		return ok(this.listing);
	}

	#write(name: string): Promise<ApiResult<RecordedAnnotation>> {
		this.calls.push(name);
		const answer =
			this.outcome ??
			ok({
				project: PROJECT,
				asset: ASSET,
				path: 'characters/mech_scout/asset.yaml',
				revision: 'rev-2',
				committed: true,
				annotation: anAnnotation('written', ANCHORS[0].make())
			});
		return Promise.resolve(answer);
	}

	create = () => this.#write('create');
	reply = () => this.#write('reply');
	edit = () => this.#write('edit');
	withdraw = () => this.#write('withdraw');
	move = () => this.#write('move');
	resolve = () => this.#write('resolve');
	reopen = () => this.#write('reopen');
	promote = () => this.#write('promote');
}

describe.each(ANCHORS)('the shared annotation ViewModel ($name)', ({ make }) => {
	let model: AnnotationViewModel;
	let server: RecordingModel;

	beforeEach(() => {
		server = new RecordingModel();
		model = createAnnotationViewModel();
		model.attach(server, PROJECT, ASSET);
	});

	// -- 4.1: every operation, with no DOM anywhere ----------------------

	it('runs in an environment with no DOM at all', () => {
		expect(typeof globalThis.document).toBe('undefined');
		expect(typeof globalThis.window).toBe('undefined');
	});

	it('holds an asset, a filter, a selection and a draft', () => {
		expect(model.project).toBe(PROJECT);
		expect(model.asset).toBe(ASSET);
		expect(model.filter.states).toEqual(['open']);
		expect(model.selectedId).toBeNull();
		expect(model.isComposing).toBe(false);
	});

	it('takes a listing a route already read', () => {
		model.hydrate(aListing([anAnnotation('an_1', make())]));

		expect(model.annotations).toHaveLength(1);
		expect(model.revision).toBe('rev-1');
		expect(model.views).toEqual([VIEW]);
	});

	it('selects exactly one annotation at a time', () => {
		model.hydrate(aListing([anAnnotation('an_1', make()), anAnnotation('an_2', make())]));

		model.select('an_1');
		expect(model.selected?.id).toBe('an_1');
		model.select('an_2');
		expect(model.selected?.id).toBe('an_2');
		model.select(null);
		expect(model.selected).toBeNull();
	});

	it('composes a draft at whatever anchor a view produced', () => {
		model.compose(make());

		expect(model.isComposing).toBe(true);
		expect(model.draft.anchor).toEqual(make());
	});

	it('records the text and the kind a person chose', () => {
		model.compose(make());
		model.setDraftText('the knee reads as a joint');
		model.setDraftKind('technical');

		expect(model.draft.text).toBe('the knee reads as a joint');
		expect(model.draft.kind).toBe('technical');
	});

	it('draws a stroke, undoes the last one and discards the whole scribble', () => {
		model.compose(make());
		model.beginStroke({ u: 0.1, v: 0.1 });
		model.extendStroke({ u: 0.2, v: 0.2 });
		model.endStroke();
		model.beginStroke({ u: 0.5, v: 0.5 });
		model.extendStroke({ u: 0.6, v: 0.6 });
		model.endStroke();

		expect(model.draft.strokes).toHaveLength(2);
		model.undoStroke();
		expect(model.draft.strokes).toHaveLength(1);
		model.discard();
		expect(model.draft.strokes).toHaveLength(0);
		expect(model.isComposing).toBe(false);
	});

	it('drops a tap: a stroke with one point is not a mark', () => {
		model.compose(make());
		model.beginStroke({ u: 0.1, v: 0.1 });
		model.endStroke();

		expect(model.draft.strokes).toHaveLength(0);
	});

	it('performs every write through the Model it was handed', async () => {
		model.hydrate(aListing([anAnnotation('an_1', make())]));
		model.select('an_1');

		await model.reply('re_1', 'agreed');
		await model.edit('reworded');
		await model.move(make());
		await model.resolve('fixed');
		await model.reopen();
		await model.promote('a durable rule', 'concept.silhouette_rules');
		await model.withdraw();

		expect(server.calls).toContain('reply');
		expect(server.calls).toContain('edit');
		expect(server.calls).toContain('move');
		expect(server.calls).toContain('resolve');
		expect(server.calls).toContain('reopen');
		expect(server.calls).toContain('promote');
		expect(server.calls).toContain('withdraw');
	});

	it('does nothing at all when no annotation is selected', async () => {
		expect(await model.reply('re_1', 'agreed')).toBe(false);
		expect(await model.promote('a rule', 'constraints')).toBe(false);
		expect(server.calls).toEqual([]);
	});

	// -- 4.4: optimistic insert, and what a failure undoes ---------------

	it('presents a placed pin immediately, before the write has landed', async () => {
		model.compose(make());
		model.setDraftText('the pauldron reads as a backpack');

		const pending = model.submit('an_new');
		expect(model.annotations.map((entry) => entry.id)).toContain('an_new');
		expect(model.pending).toContain('an_new');
		await pending;
	});

	it('removes the pin and preserves the draft when the write fails', async () => {
		server.outcome = refusal();
		model.compose(make());
		model.setDraftText('the pauldron reads as a backpack');

		const landed = await model.submit('an_new');

		expect(landed).toBe(false);
		expect(model.annotations.map((entry) => entry.id)).not.toContain('an_new');
		expect(model.draft.text).toBe('the pauldron reads as a backpack');
		expect(model.draft.anchor).not.toBeNull();
		expect(model.error).toBe('the repository is unreachable');
		expect(model.writeState).toBe('failed');
	});

	it('clears the draft and re-reads the repository once the write lands', async () => {
		server.listing = aListing([anAnnotation('an_new', make())], 'rev-2');
		model.compose(make());
		model.setDraftText('the pauldron reads as a backpack');

		await model.submit('an_new');
		await Promise.resolve();

		expect(model.draft.text).toBe('');
		expect(server.calls).toContain('list');
	});

	it('a reload agrees with the repository after a failed placement', async () => {
		server.outcome = refusal();
		model.compose(make());
		model.setDraftText('never recorded');
		await model.submit('an_ghost');

		server.outcome = null;
		server.listing = aListing([anAnnotation('an_1', make())]);
		await model.load();

		expect(model.annotations.map((entry) => entry.id)).toEqual(['an_1']);
		expect(model.pending).toEqual([]);
	});

	it('refuses to submit a draft with no text and one with no anchor', async () => {
		expect(await model.submit('an_new')).toBe(false);
		model.compose(make());
		expect(await model.submit('an_new')).toBe(false);
		expect(server.calls).toEqual([]);
	});

	// -- filtering, shared with every other surface ----------------------

	it('shows open annotations of every kind by default', () => {
		model.hydrate(
			aListing([
				anAnnotation('an_1', make(), { kind: 'technical' }),
				anAnnotation('an_2', make(), { kind: 'design' }),
				anAnnotation('an_3', make(), { state: 'resolved' })
			])
		);

		expect(model.visible.map((entry) => entry.id)).toEqual(['an_1', 'an_2']);
		expect(model.hidden).toBe(1);
	});

	it('combines the kind and the state filters', () => {
		model.hydrate(
			aListing([
				anAnnotation('an_1', make(), { kind: 'technical' }),
				anAnnotation('an_2', make(), { kind: 'technical', state: 'resolved' }),
				anAnnotation('an_3', make(), { kind: 'design' })
			])
		);

		model.setFilter({ kinds: ['technical'], states: ['open'], orphans: true });

		expect(model.visible.map((entry) => entry.id)).toEqual(['an_1']);
		expect(model.hidden).toBe(2);
	});

	it('lists an orphan and never offers it as placeable', () => {
		model.hydrate(
			aListing([
				anAnnotation('an_1', make()),
				anAnnotation('an_2', make(), { anchor_state: 'orphaned' })
			])
		);

		expect(model.visible.map((entry) => entry.id)).toEqual(['an_1', 'an_2']);
		expect(model.placeable.map((entry) => entry.id)).toEqual(['an_1']);
	});

	it('offers exactly the exits the system named, and no others', () => {
		model.hydrate(aListing([anAnnotation('an_1', make(), { exits: ['promote', 'resolve'] })]));
		model.select('an_1');

		expect(model.exits).toEqual(['promote', 'resolve']);
	});

	it('offers nothing for an annotation that already took an exit', () => {
		model.hydrate(aListing([anAnnotation('an_1', make(), { state: 'resolved', exits: [] })]));
		model.select('an_1');

		expect(model.exits).toEqual([]);
	});

	// -- D10: the input rule, decided by the ViewModel's session ---------

	it('places a pin for a finger until a stylus has been seen', () => {
		expect(model.gesture({ kind: 'touch', point: { x: 1, y: 1 } })).toBe('place');
	});

	it('navigates with a finger once a stylus has been used', () => {
		model.gesture({ kind: 'pen', point: { x: 1, y: 1 } });

		expect(model.gesture({ kind: 'touch', point: { x: 1, y: 1 } })).toBe('navigate');
	});

	it('forgets the stylus when the sheet is reset', () => {
		model.gesture({ kind: 'pen', point: { x: 1, y: 1 } });
		model.reset();

		expect(model.gesture({ kind: 'touch', point: { x: 1, y: 1 } })).toBe('place');
	});
});

// --------------------------------------------------------------------------
// 4.2 — the structural half: no branch on an anchor's form
// --------------------------------------------------------------------------

const SOURCE = readFileSync(
	fileURLToPath(
		new URL('../src/lib/annotation/annotation-view-model.svelte.ts', import.meta.url)
	),
	'utf-8'
);

/** The members only one anchor form has. A branch on either is a fork waiting. */
const FORM_SPECIFIC = ['.view', '.part', '.bone', '.normal', "'view'", "'part'"];

/**
 * The module with its comments removed.
 *
 * The prose in this file says what it must not do, in the words it must not
 * use, which is exactly right for a reader and exactly wrong for a grep. So the
 * check reads the code.
 */
const CODE = SOURCE.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');

describe('the ViewModel is anchor-agnostic by construction (4.2)', () => {
	it.each(FORM_SPECIFIC)('never reads %s off an anchor', (member) => {
		expect(CODE.includes(`anchor${member}`)).toBe(false);
	});

	it('names neither anchor type', () => {
		expect(CODE).not.toContain('Anchor2D');
		expect(CODE).not.toContain('Anchor3D');
	});

	it('touches no DOM type', () => {
		for (const named of ['HTMLElement', 'PointerEvent', 'CanvasRenderingContext', 'document.']) {
			expect(CODE).not.toContain(named);
		}
	});

	it('is the module the singleton and the factory both come from', () => {
		expect(SOURCE).toContain('export function createAnnotationViewModel');
		expect(SOURCE).toContain('export const annotationViewModel');
	});
});
