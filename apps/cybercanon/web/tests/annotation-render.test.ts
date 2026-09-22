/**
 * Tasks 5.1, 5.8, 5.9, 6.1 and 6.2 — the sheet, the panel and the pass, rendered.
 *
 * The arrangement is decided in `annotation-sheet.test.ts` and in the ViewModel
 * suite; this is the other half of the same requirements, and it is a different
 * half. *"No promotion action SHALL be offered"* is a claim about a screen, and
 * a ViewModel that answered `mayPromote === false` would satisfy every
 * assertion about the data behind a panel that rendered the button anyway.
 *
 * Svelte renders these with no DOM and no browser, which is why they can live
 * in the suite `just check` runs constantly.
 */

import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import ModelSheet from '../src/lib/components/ModelSheet.svelte';
import ThreadPanel from '../src/lib/components/ThreadPanel.svelte';
import TriagePass from '../src/lib/components/TriagePass.svelte';
import { createAnnotationViewModel, viewAnchor } from '../src/lib/annotation';
import type { AnnotationViewModel } from '../src/lib/annotation';
import { SHEET_EMPTY } from '../src/lib/asset';
import type { Annotation, AnnotationListing, TriageEntry, TriageQueue } from '../src/lib/api';

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const RAFA = 'auth|rafa';
const ANA = 'auth|ana';

function anAnnotation(id: string, over: Partial<Annotation> = {}): Annotation {
	return {
		id,
		kind: 'art-direction',
		author: RAFA,
		via: null,
		attribution: RAFA,
		text: 'the pauldron reads as a backpack at 15 m',
		state: 'open',
		anchor: viewAnchor('front', { u: 0.25, v: 0.4 })!,
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
		...over
	};
}

function aListing(over: Partial<AnnotationListing> = {}): AnnotationListing {
	return {
		project: PROJECT,
		asset: ASSET,
		path: 'characters/mech_scout/asset.yaml',
		revision: 'rev-1',
		annotations: [anAnnotation('an_1')],
		hidden: 0,
		orphans: [],
		view_names: ['front', 'side', 'back'],
		actor: RAFA,
		may_promote: false,
		...over
	};
}

function aModel(listing: AnnotationListing): AnnotationViewModel {
	const model = createAnnotationViewModel();
	model.hydrate(listing);
	return model;
}

function sheetHtml(listing: AnnotationListing, options: Record<string, unknown> = {}): string {
	return render(ModelSheet, {
		props: { model: aModel(listing), listing, ...options }
	}).body;
}

// --------------------------------------------------------------------------
// 5.1 — the views an asset has, and the state when it has none
// --------------------------------------------------------------------------

describe('the sheet presents an asset’s views without inventing any (5.1)', () => {
	it('presents every view, each identified by the name an anchor keys on', () => {
		const html = sheetHtml(aListing());

		for (const view of ['front', 'side', 'back']) {
			expect(html).toContain(`data-view="${view}"`);
		}
	});

	it('states that an asset has no views, and still presents its threads', () => {
		const html = sheetHtml(aListing({ view_names: [] }));

		expect(html).toContain('data-empty="views"');
		expect(html).toContain(SHEET_EMPTY);
		expect(html).toContain('the pauldron reads as a backpack');
	});

	it('draws a pin for an annotation and none for an orphan (5.9)', () => {
		const orphaned = anAnnotation('an_2', { anchor_state: 'orphaned' });
		const html = sheetHtml(
			aListing({
				annotations: [anAnnotation('an_1'), orphaned],
				orphans: [
					{
						id: 'an_2',
						subject: 'back',
						reason: 'the view it was anchored to is no longer part of this asset',
						annotation: orphaned
					}
				]
			})
		);

		expect(html).toContain('data-annotation="an_1"');
		expect(html).toContain('data-orphan="an_2"');
		expect(html).toContain('no longer part of this asset');
		expect(html).not.toContain('class="pin" data-kind="art-direction" data-annotation="an_2"');
	});

	it('reports how many annotations the current filter is hiding (5.6)', () => {
		const html = sheetHtml(
			aListing({
				annotations: [anAnnotation('an_1'), anAnnotation('an_2', { state: 'resolved' })]
			})
		);

		expect(html).toContain('data-hidden="1"');
		expect(html).toContain('1 hidden by this filter');
	});
});

// --------------------------------------------------------------------------
// 5.8 — the thread panel offers only the exits the person may take
// --------------------------------------------------------------------------

function panelHtml(listing: AnnotationListing, options: Record<string, unknown> = {}): string {
	const model = aModel(listing);
	model.select('an_1');
	return render(ThreadPanel, { props: { model, ...options } }).body;
}

describe('the thread panel (5.8)', () => {
	it('presents the text, the kind, the state, the attribution and the replies', () => {
		const html = panelHtml(
			aListing({
				annotations: [
					anAnnotation('an_1', {
						replies: [
							{
								id: 're_1',
								author: ANA,
								via: null,
								attribution: ANA,
								text: 'agreed, it needs a harder edge',
								at: '2026-09-22T10:00:00',
								edited_at: null
							}
						]
					})
				]
			})
		);

		expect(html).toContain('art-direction');
		expect(html).toContain('the pauldron reads as a backpack');
		expect(html).toContain('data-state="open"');
		expect(html).toContain(RAFA);
		expect(html).toContain('agreed, it needs a harder edge');
	});

	it('renders an agent-performed attribution as the system produced it', () => {
		const html = panelHtml(
			aListing({
				annotations: [
					anAnnotation('an_1', { via: 'blender-agent', attribution: 'rafa, via blender-agent' })
				]
			})
		);

		expect(html).toContain('rafa, via blender-agent');
	});

	it('offers no promotion to a person who may not promote', () => {
		const html = panelHtml(aListing(), { mayPromote: false, actor: RAFA });

		expect(html).not.toContain('Promote');
	});

	it('offers promotion, and names the destination, to a person who may', () => {
		const html = panelHtml(aListing({ may_promote: true }), { mayPromote: true, actor: RAFA });

		expect(html).toContain('Promote');
		expect(html).toContain('concept.silhouette_rules');
		expect(html).toContain('This will be written to');
	});

	it('offers edit and withdraw on a person’s own contribution only', () => {
		const mine = panelHtml(aListing(), { actor: RAFA });
		const theirs = panelHtml(aListing(), { actor: ANA });

		expect(mine).toContain('Withdraw');
		expect(theirs).not.toContain('Withdraw');
	});

	it('offers resolve while the annotation is open, and reopen once it is not', () => {
		const open = panelHtml(aListing(), { actor: RAFA });
		const settled = panelHtml(
			aListing({ annotations: [anAnnotation('an_1', { state: 'resolved', exits: [] })] }),
			{ actor: RAFA }
		);

		expect(open).toContain('Resolve');
		expect(settled).toContain('Reopen');
		expect(settled).not.toContain('>Resolve<');
	});
});

// --------------------------------------------------------------------------
// 6.1 and 6.2 — the art director's pass
// --------------------------------------------------------------------------

function anEntry(asset: string, id: string, over: Partial<TriageEntry> = {}): TriageEntry {
	return {
		asset,
		kind: 'art-direction',
		same_kind_on_asset: 1,
		same_kind_in_project: 1,
		replies: 0,
		age_seconds: 0,
		discipline_owner: null,
		annotation: anAnnotation(id),
		...over
	};
}

function queueHtml(queue: TriageQueue): string {
	return render(TriagePass, {
		props: {
			queue,
			address: { project: queue.project, kind: '', asset: '', owner: '' }
		}
	}).body;
}

describe('the triage pass (6.1)', () => {
	const queue: TriageQueue = {
		project: PROJECT,
		entries: [
			anEntry(ASSET, 'an_1', { same_kind_on_asset: 4, same_kind_in_project: 5, replies: 6 }),
			anEntry('mule', 'mu_1', { age_seconds: 90_000 })
		],
		unreadable: []
	};

	it('shows each entry’s same-kind counts, its reply count and its age', () => {
		const html = queueHtml(queue);

		expect(html).toContain('data-annotation="an_1"');
		expect(html).toContain('>4<');
		expect(html).toContain('>5<');
		expect(html).toContain('>6<');
		expect(html).toContain('1d');
	});

	it('presents the entries in the order the queue gave them, and re-sorts nothing', () => {
		const html = queueHtml(queue);

		expect(html.indexOf('data-annotation="an_1"')).toBeLessThan(
			html.indexOf('data-annotation="mu_1"')
		);
	});

	it('offers the three kinds as filters, in the address', () => {
		const html = queueHtml(queue);

		expect(html).toContain(`href="/p/${PROJECT}/triage?kind=art-direction"`);
		expect(html).toContain(`href="/p/${PROJECT}/triage?kind=technical"`);
	});

	it('links each entry to the sheet the annotation lives on', () => {
		const html = queueHtml(queue);

		expect(html).toContain(`/p/${PROJECT}/a/${ASSET}?surface=sheet`);
	});

	it('names an unassigned discipline owner rather than showing nothing', () => {
		expect(queueHtml(queue)).toContain('unassigned');
	});
});

// --------------------------------------------------------------------------
// 6.2 — the promotion flow, from the pass to the panel
// --------------------------------------------------------------------------

describe('the promotion flow reaches the thread it is about (6.2)', () => {
	const queue: TriageQueue = {
		project: PROJECT,
		entries: [anEntry(ASSET, 'an_1')],
		unreadable: []
	};

	it('links a queue row to the sheet, opened on that exact annotation', () => {
		const html = queueHtml(queue);

		expect(html).toContain(
			`/p/${PROJECT}/a/${ASSET}?surface=sheet&amp;annotation=an_1`
		);
	});

	it('opens the sheet with that thread already selected', () => {
		const listing = aListing({ may_promote: true });
		const model = aModel(listing);

		const html = render(ModelSheet, {
			props: { model, listing, selected: 'an_1', mayPromote: true, actor: RAFA }
		}).body;

		expect(model.selectedId).toBe('an_1');
		expect(html).toContain('Promote');
		expect(html).toContain('concept.silhouette_rules');
	});

	it('states the destination before the promotion is submitted', () => {
		const html = panelHtml(aListing({ may_promote: true }), { mayPromote: true, actor: RAFA });

		expect(html).toContain('This will be written to');
		expect(html.indexOf('This will be written to')).toBeLessThan(html.indexOf('>Promote<'));
	});
});
