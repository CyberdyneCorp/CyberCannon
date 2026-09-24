/**
 * Group 6 and 7 — the viewer rendered, over the *same* ViewModel as the sheet.
 *
 * The arrangement is decided next door and this is the other half: *"an
 * annotation filtered out in the 2D surface is filtered out in the viewer under
 * the same filter"* is a claim about two screens, and a ViewModel that answered
 * correctly would satisfy every assertion about the data behind a screen that
 * rendered something else.
 *
 * Svelte renders these with no DOM, no GPU and no browser — which is exactly
 * D11's claim about what the annotation half needs, made into the suite that
 * checks it.
 */

import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import Viewer3D from '../src/lib/components/Viewer3D.svelte';
import ModelSheet from '../src/lib/components/ModelSheet.svelte';
import AnimationTransport from '../src/lib/components/AnimationTransport.svelte';
import { createAnnotationViewModel, partAnchor, viewAnchor } from '../src/lib/annotation';
import type { AnnotationViewModel } from '../src/lib/annotation';
import type {
	AnchorResolutions,
	Annotation,
	AnnotationListing,
	ClipCoverage,
	PreviewDescriptor
} from '../src/lib/api';
import {
	ANCHOR_UNAVAILABLE,
	NO_RENDERING,
	SUPERSEDED,
	UNAVAILABLE,
	UNLOADABLE
} from '../src/lib/viewer/presentation';
import { STOPPED } from '../src/lib/viewer/clips';

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const RAFA = 'auth|rafa';
const EXPORT = 'characters/mech_scout/exports/mech_scout.glb';
const SHOULDER = 'SM_MechScout_Shoulder_L';
const WALK = 'A_mech_scout_walk';

const COVERAGE: ClipCoverage = {
	states: [
		{ state: 'walk', clip: WALK, coverage: 'satisfied' },
		{ state: 'fire', clip: 'A_mech_scout_fire', coverage: 'no clip' },
		{ state: 'destroyed', clip: null, coverage: 'declared unanimated' }
	],
	unclaimed: ['A_mech_scout_test']
};

function anAnnotation(id: string, over: Partial<Annotation> = {}): Annotation {
	return {
		id,
		kind: 'art-direction',
		author: RAFA,
		via: null,
		attribution: RAFA,
		text: `finding ${id}`,
		state: 'open',
		anchor: partAnchor(SHOULDER)!,
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
		view_names: ['front'],
		actor: RAFA,
		may_promote: false,
		...over
	};
}

function aDescriptor(over: Partial<PreviewDescriptor> = {}): PreviewDescriptor {
	return {
		project: PROJECT,
		asset: ASSET,
		path: 'characters/mech_scout/asset.yaml',
		revision: 'rev-7',
		preview: {
			key: 'previews/mech_scout.glb',
			source_export: EXPORT,
			size_bytes: 24,
			content_type: 'model/gltf-binary'
		},
		source_export: EXPORT,
		latest_validated_export: EXPORT,
		derived_from_latest: true,
		counts: { triangles: 14310, objects: 3, materials: 2 },
		parts: [SHOULDER],
		clips: [WALK],
		coverage: COVERAGE,
		absent: null,
		reason: null,
		...over
	};
}

const RESOLUTIONS: AnchorResolutions = {
	project: PROJECT,
	asset: ASSET,
	export: EXPORT,
	revision: 'rev-1',
	orphaned: 2,
	resolutions: []
};

/** A Model that records what was asked of it. No network, no cache, no browser. */
function aGateway(calls: string[]) {
	const record = (verb: string) => async (project: string, asset: string, id: string) => {
		calls.push(`${verb} ${project}/${asset}/${id}`);
		return {
			ok: true as const,
			data: {
				project,
				asset,
				path: '',
				revision: 'rev-2',
				committed: true,
				annotation: anAnnotation(id, { state: 'resolved' as const })
			},
			freshness: null
		};
	};
	return {
		list: async () => ({ ok: true as const, data: aListing(), freshness: null }),
		create: record('create'),
		reply: record('reply'),
		edit: record('edit'),
		withdraw: record('withdraw'),
		move: record('move'),
		resolve: record('resolve'),
		reopen: record('reopen'),
		promote: record('promote')
	} as never;
}

function aModel(listing: AnnotationListing): AnnotationViewModel {
	const model = createAnnotationViewModel();
	model.hydrate(listing);
	return model;
}

function viewerHtml(
	listing: AnnotationListing,
	descriptor: PreviewDescriptor = aDescriptor(),
	options: Record<string, unknown> = {}
): string {
	return render(Viewer3D, {
		props: {
			model: aModel(listing),
			listing,
			descriptor,
			resolutions: RESOLUTIONS,
			probe: () => true,
			...options
		}
	}).body;
}

describe('7.1 — the viewer states its provenance', () => {
	it('names the export it is showing and the revision it is against', () => {
		const html = viewerHtml(aListing());

		expect(html).toContain(EXPORT);
		expect(html).toContain('rev-7');
	});

	it('says when the preview is not derived from the latest validated export', () => {
		const html = viewerHtml(
			aListing(),
			aDescriptor({ derived_from_latest: false, latest_validated_export: 'exports/newer.glb' })
		);

		expect(html).toContain(SUPERSEDED);
	});
});

describe('7.2 — the counts on screen are the source export’s', () => {
	it('shows the source figures', () => {
		const html = viewerHtml(aListing());

		expect(html).toContain('14310');
		expect(html).toContain('Triangles');
	});

	it('shows an unrecorded count as unavailable', () => {
		const html = viewerHtml(
			aListing(),
			aDescriptor({ counts: { triangles: 14310, objects: 3, materials: null } })
		);

		expect(html).toContain(UNAVAILABLE);
	});
});

describe('7.3 — an asset with no preview says so, and stays usable', () => {
	it('states the reason and still presents the annotations', () => {
		const html = viewerHtml(
			aListing(),
			aDescriptor({
				preview: null,
				absent: 'no_export_recorded',
				reason: 'no export has been validated for this asset yet'
			})
		);

		expect(html).toContain('no export has been validated');
		expect(html).toContain('finding an_1');
	});

	it('reports a preview whose bytes could not be read, and offers a retry', () => {
		// *"It SHALL NOT display a blank viewport, and SHALL NOT report the asset
		// as having no preview."* The descriptor names one; what failed is the
		// read, and the two sentences send a person to different places.
		const html = viewerHtml(aListing(), aDescriptor(), {
			unretrievable: 'the preview stored at previews/mech_scout.glb could not be retrieved'
		});

		expect(html).toContain(UNLOADABLE);
		expect(html).toContain('could not be retrieved');
		expect(html).toContain('Retry');
		expect(html).not.toContain('<canvas');
	});

	it('does not present an empty viewport as a loaded asset', () => {
		const html = viewerHtml(
			aListing(),
			aDescriptor({ preview: null, absent: 'emission_failed', reason: 'emission failed' })
		);

		expect(html).not.toContain('<canvas');
	});
});

describe('7.4 — the non-rendering presentation (D11)', () => {
	const degraded = () => viewerHtml(aListing(), aDescriptor(), { probe: () => false });

	it('states that 3D display is unavailable on this device', () => {
		expect(degraded()).toContain(NO_RENDERING);
	});

	it('states that placing a 3D anchor is unavailable rather than failing on use', () => {
		expect(degraded()).toContain(ANCHOR_UNAVAILABLE);
	});

	it('still presents the full annotation list and the triage panel', () => {
		const html = degraded();

		expect(html).toContain('finding an_1');
		expect(html).toContain('filter the annotations');
	});

	it('presents no viewport at all', () => {
		expect(degraded()).not.toContain('<canvas');
	});

	it('is not an error page: the specification and the provenance are still there', () => {
		expect(degraded()).toContain(EXPORT);
	});
});

describe('6.5 — orphans are visible, listed and countable', () => {
	it('states the count the server answered, with no renderer involved', () => {
		expect(viewerHtml(aListing())).toContain('2 orphaned on this export');
	});

	it('lists an orphan as orphaned, naming the part it expected', () => {
		const orphan = anAnnotation('an_2', { anchor_state: 'orphaned' });
		const html = viewerHtml(aListing({ annotations: [anAnnotation('an_1'), orphan] }));

		expect(html).toContain('orphaned — expected');
		expect(html).toContain(SHOULDER);
	});
});

describe('6.7 — the two surfaces agree, because they are the same ViewModel', () => {
	it('shows one reference image card for path and slot aliases with both pins', () => {
		const listing = aListing({
			view_names: ['concept/front.png', 'front'],
			annotations: [
				anAnnotation('an_old', { anchor: viewAnchor('concept/front.png', { u: 0.2, v: 0.2 })! }),
				anAnnotation('an_new', { anchor: viewAnchor('front', { u: 0.8, v: 0.8 })! })
			]
		});
		const html = render(ModelSheet, {
			props: {
				model: aModel(listing), listing,
				images: { front: { source: 'data:image/png;base64,cG5n', reason: null } }
			}
		}).body;

		expect(html.match(/data-view="front"/g)).toHaveLength(1);
		expect(html).toContain('src="data:image/png;base64,cG5n"');
		expect(html).toContain('data-annotation="an_old"');
		expect(html).toContain('data-annotation="an_new"');
	});

	it('filters out in the viewer exactly what the sheet filters out', () => {
		const listing = aListing({
			annotations: [
				anAnnotation('an_1'),
				anAnnotation('an_2', { kind: 'technical', text: 'finding an_2' })
			]
		});
		const model = aModel(listing);
		model.toggleKind('technical');

		const viewer = render(Viewer3D, {
			props: { model, listing, descriptor: aDescriptor(), probe: () => true }
		}).body;
		const sheet = render(ModelSheet, { props: { model, listing } }).body;

		expect(viewer).toContain('finding an_2');
		expect(viewer).not.toContain('finding an_1');
		expect(sheet).not.toContain('finding an_1');
	});

	it('offers promotion in the viewer under exactly the rule the sheet uses', () => {
		// The panel offers an exit only for a selected thread, in either surface —
		// which is the shared behaviour being checked rather than an artefact.
		const withoutRole = viewerHtml(aListing(), aDescriptor(), {
			mayPromote: false,
			selected: 'an_1'
		});
		const withRole = viewerHtml(aListing(), aDescriptor(), {
			mayPromote: true,
			actor: RAFA,
			selected: 'an_1'
		});

		expect(withoutRole).not.toContain('Promote');
		expect(withRole).toContain('Promote');
	});

	it('takes the same exit from the viewer as from the sheet, through one ViewModel', async () => {
		// *"WHEN it is resolved from the viewer THEN it SHALL take the same exit,
		// with the same effect on the compiled specification, as resolving it from
		// the 2D surface."* One ViewModel, one method, one request — so there is
		// no second implementation for the two to disagree through.
		const calls: string[] = [];
		const listing = aListing();
		const model = aModel(listing);
		model.attach(aGateway(calls), PROJECT, ASSET);
		model.hydrate(listing);
		model.select('an_1');

		await model.resolve('it reads correctly now');

		expect(calls).toEqual([`resolve ${PROJECT}/${ASSET}/an_1`]);
	});

	it('presents a 2D anchor in the viewer’s list without pretending it is a part', () => {
		const flat = anAnnotation('an_3', { anchor: viewAnchor('front', { u: 0.2, v: 0.2 })! });

		expect(viewerHtml(aListing({ annotations: [flat] }))).toContain('finding an_3');
	});
});

describe('8 — the transport as it is rendered', () => {
	function transportHtml(clips: readonly { name: string; duration: number }[], absence = '') {
		return render(AnimationTransport, {
			props: { clips, coverage: COVERAGE, transport: STOPPED, absence }
		}).body;
	}

	it('lists the clips with their durations and the state each satisfies', () => {
		const html = transportHtml([{ name: WALK, duration: 1.5 }]);

		expect(html).toContain(WALK);
		expect(html).toContain('0:01.50');
		expect(html).toContain('satisfies walk');
	});

	it('offers no transport when the preview carries no clips, and says why', () => {
		const html = transportHtml([], 'this preview carries no animation clips');

		expect(html).toContain('this preview carries no animation clips');
		expect(html).not.toContain('aria-label="playback"');
	});

	it('lists a declared state with no clip rather than omitting it', () => {
		const html = transportHtml([{ name: WALK, duration: 1 }]);

		expect(html).toContain('fire');
		expect(html).toContain('no clip');
	});

	it('shows a deliberately unanimated state as declared, not as a gap', () => {
		const html = transportHtml([{ name: WALK, duration: 1 }]);

		expect(html).toContain('declared unanimated');
	});

	it('labels an unclaimed clip rather than rejecting it', () => {
		const html = transportHtml([{ name: WALK, duration: 1 }]);

		expect(html).toContain('A_mech_scout_test');
		expect(html).toContain('Satisfying no declared state');
	});

	it('offers at least three speeds', () => {
		const html = transportHtml([{ name: WALK, duration: 1 }]);

		expect(html.match(/<option/g)?.length).toBeGreaterThanOrEqual(3);
	});
});
