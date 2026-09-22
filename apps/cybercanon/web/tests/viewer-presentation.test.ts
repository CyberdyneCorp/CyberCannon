/**
 * Group 7 — provenance, counts, absences and degradation, as data.
 *
 * The rule the counts turn on: *"nobody should argue about a budget using a
 * number the budget was never measured against"*. The asset's figures are the
 * **source export's**, the preview's own figure is labelled as the preview's,
 * and a figure that was never recorded is *unavailable* rather than quietly
 * replaced by the one that happens to be on hand.
 */

import { describe, expect, it } from 'vitest';
import type { AnchorResolutions, PreviewDescriptor } from '../src/lib/api';
import {
	NO_RENDERING,
	PREVIEW_COUNT_LABEL,
	SUPERSEDED,
	UNAVAILABLE,
	absenceOf,
	figuresOf,
	orphanCount,
	partialAmong,
	provenanceOf
} from '../src/lib/viewer/presentation';
import {
	KEPT_NOTHING,
	canPlaceAnchor,
	contextLost,
	contextRestored,
	isDegraded,
	loaded,
	newSession,
	restorationFailed,
	retrying,
	unloadable
} from '../src/lib/viewer/capability';
import { STOPPED } from '../src/lib/viewer/clips';

const EXPORT = 'characters/mech_scout/exports/mech_scout.glb';
const NEWER = 'characters/mech_scout/exports/mech_scout_v2.glb';

function aDescriptor(over: Partial<PreviewDescriptor> = {}): PreviewDescriptor {
	return {
		project: 'ironwood',
		asset: 'mech_scout',
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
		parts: [],
		clips: [],
		coverage: { states: [], unclaimed: [] },
		absent: null,
		reason: null,
		...over
	};
}

const CAN_RENDER = () => true;
const CANNOT_RENDER = () => false;

describe('7.1 — which export and which revision are on screen', () => {
	it('states the export the preview came from and the revision in view', () => {
		const provenance = provenanceOf(aDescriptor());

		expect(provenance.export).toBe(EXPORT);
		expect(provenance.revision).toBe('rev-7');
		expect(provenance.notice).toBeNull();
	});

	it('says so when the preview is not derived from the latest validated export', () => {
		const provenance = provenanceOf(
			aDescriptor({ latest_validated_export: NEWER, derived_from_latest: false })
		);

		expect(provenance.derivedFromLatest).toBe(false);
		expect(provenance.notice).toBe(SUPERSEDED);
	});

	it('does not flag an asset that has no preview at all as superseded', () => {
		const provenance = provenanceOf(
			aDescriptor({ preview: null, derived_from_latest: false, absent: 'emission_failed' })
		);

		expect(provenance.notice).toBeNull();
	});
});

describe('7.2 — the counts are the source export’s', () => {
	it('shows the source’s figures as the asset’s', () => {
		const figures = figuresOf(aDescriptor());

		expect(figures.map((figure) => [figure.label, figure.value])).toEqual([
			['Triangles', '14310'],
			['Objects', '3'],
			['Materials', '2']
		]);
	});

	it('labels the preview’s own count as the preview’s', () => {
		const figures = figuresOf(aDescriptor(), 4200);

		const preview = figures.find((figure) => figure.label === PREVIEW_COUNT_LABEL);
		expect(preview?.value).toBe('4200');
		expect(figures.find((figure) => figure.label === 'Triangles')?.value).toBe('14310');
	});

	it('never substitutes the preview’s count for an unrecorded source count', () => {
		const figures = figuresOf(
			aDescriptor({ counts: { triangles: null, objects: 3, materials: null } }),
			4200
		);

		expect(figures.find((figure) => figure.label === 'Triangles')?.value).toBe(UNAVAILABLE);
		expect(figures.find((figure) => figure.label === 'Materials')?.recorded).toBe(false);
		expect(figures.find((figure) => figure.label === PREVIEW_COUNT_LABEL)?.value).toBe('4200');
	});

	it('shows an unrecorded material count as unavailable rather than zero', () => {
		const figures = figuresOf(
			aDescriptor({ counts: { triangles: 1, objects: 1, materials: null } })
		);

		expect(figures.find((figure) => figure.label === 'Materials')?.value).toBe(UNAVAILABLE);
	});
});

describe('7.3 — an asset with no preview says why', () => {
	it('carries the reason the use case determined', () => {
		const descriptor = aDescriptor({
			preview: null,
			absent: 'no_export_recorded',
			reason: 'no export has been validated for this asset yet'
		});

		expect(absenceOf(descriptor)).toContain('no export has been validated');
	});

	it('says nothing about an absence when there is a preview', () => {
		expect(absenceOf(aDescriptor())).toBeNull();
	});

	it('never leaves the absence blank, even for a reason nobody stated', () => {
		expect(absenceOf(aDescriptor({ preview: null, reason: null }))).toBeTruthy();
	});
});

describe('7.4 and 7.5 — degradation, and one restoration attempt', () => {
	it('starts degraded on a device that cannot render', () => {
		const session = newSession(CANNOT_RENDER);

		expect(isDegraded(session)).toBe(true);
		expect(canPlaceAnchor(session)).toBe(false);
	});

	it('states the degradation rather than failing on use', () => {
		expect(NO_RENDERING).toContain('annotations');
	});

	it('stays degraded whatever happens afterwards', () => {
		const session = newSession(CANNOT_RENDER);

		expect(loaded(session).state).toBe('degraded');
		expect(unloadable(session).state).toBe('degraded');
		expect(retrying(session).state).toBe('degraded');
	});

	it('answers the same session for a state it is already in', () => {
		// Load-bearing rather than tidy: the viewer mounts its scene from an
		// effect that also records what the load produced, so a transition that
		// returned a new session for an unchanged state would invalidate the
		// effect that had just set it — and the scene would remount for ever.
		const ready = loaded(newSession(CAN_RENDER));

		expect(loaded(ready)).toBe(ready);
		expect(retrying(unloadable(ready))).not.toBe(ready);
		const failed = unloadable(ready);
		expect(unloadable(failed)).toBe(failed);
	});

	it('becomes ready when the preview loads', () => {
		const session = loaded(newSession(CAN_RENDER));

		expect(session.state).toBe('ready');
		expect(canPlaceAnchor(session)).toBe(true);
	});

	it('reports an unloadable preview and offers a retry', () => {
		const failed = unloadable(loaded(newSession(CAN_RENDER)));

		expect(failed.state).toBe('unloadable');
		expect(retrying(failed).state).toBe('loading');
	});

	it('attempts one restoration, keeping the camera and the paused position', () => {
		const kept = {
			camera: { position: [1, 2, 3] as const, target: [0, 0, 0] as const, fovDeg: 45 },
			transport: { ...STOPPED, clip: 'A_walk', position: 0.5 }
		};

		const lost = contextLost(loaded(newSession(CAN_RENDER)), kept);

		expect(lost.state).toBe('loading');
		expect(lost.attempts).toBe(1);
		expect(lost.kept).toEqual(kept);
		expect(contextRestored(lost).state).toBe('ready');
	});

	it('falls back to the still presentation when the restoration fails', () => {
		const lost = contextLost(loaded(newSession(CAN_RENDER)), KEPT_NOTHING);

		expect(restorationFailed(lost).state).toBe('degraded');
	});

	it('does not attempt a second restoration', () => {
		const once = contextLost(loaded(newSession(CAN_RENDER)), KEPT_NOTHING);

		expect(contextLost(once, KEPT_NOTHING).state).toBe('degraded');
	});
});

describe('6.5 — the orphan count is the one the server answered', () => {
	const resolutions: AnchorResolutions = {
		project: 'ironwood',
		asset: 'mech_scout',
		export: EXPORT,
		revision: 'rev-7',
		orphaned: 3,
		resolutions: [
			{ id: 'an_1', outcome: 'orphaned', part: 'SM_Gone', bone: null, reason: 'absent' },
			{ id: 'an_2', outcome: 'partial', part: 'SM_Arm', bone: 'bone_forearm_l', reason: 'no bone' }
		]
	};

	it('reports the count the read produced, with no renderer involved', () => {
		expect(orphanCount(resolutions)).toBe(3);
	});

	it('reports none when nothing has been read', () => {
		expect(orphanCount(null)).toBe(0);
	});

	it('names the partially resolved annotations', () => {
		expect(partialAmong(resolutions)).toEqual(['an_2']);
	});
});
