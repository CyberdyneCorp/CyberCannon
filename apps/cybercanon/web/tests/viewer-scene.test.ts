/**
 * Group 4 and 5 — the scene module over real bytes, with no GPU anywhere.
 *
 * `parsePreview` is deliberately separable from `mountScene`: *what a preview
 * contains* is answerable headlessly, and a suite that needed a renderer to ask
 * would be a suite `just check` never runs. What is checked here is the half
 * that the rest of the change trusts — the part names, the clips, the
 * rest-pose geometry — against a GLB written from code by
 * `tests/support/glb.ts`.
 *
 * The module is reached by a dynamic import for the same reason nothing in
 * `src/` names it statically (D7): the rule is that the engine is one chunk, and
 * a test that made it two would be a test that broke the thing it checks.
 */

import { describe, expect, it } from 'vitest';
import {
	SUBDIVIDED_INDICES,
	buildGlb,
	subdividedAt,
	triangleAt
} from './support/glb';
import { PartIndex } from '../src/lib/viewer/geometry';
import { resolverFor } from '../src/lib/viewer/resolution';
import type { Anchor } from '../src/lib/api';

const SHOULDER = 'SM_MechScout_Shoulder_L';
const TORSO = 'SM_MechScout_Torso';
const WALK = 'A_mech_scout_walk';

const FLAT = [0, 1, 2];

/** The ordinary export: two named parts, one triangle each, one walk cycle. */
function anExport(): ArrayBuffer {
	return buildGlb(
		[
			{ name: SHOULDER, positions: triangleAt(0), indices: FLAT },
			{ name: TORSO, positions: triangleAt(5), indices: FLAT }
		],
		[{ name: WALK, times: [0, 1], translations: [0, 0, 0, 0, 1, 0] }]
	);
}

/** The same asset, retopologised: same names, four triangles where there was one. */
function retopologised(): ArrayBuffer {
	return buildGlb([
		{ name: SHOULDER, positions: subdividedAt(0), indices: SUBDIVIDED_INDICES },
		{ name: TORSO, positions: subdividedAt(5), indices: SUBDIVIDED_INDICES }
	]);
}

async function parse(bytes: ArrayBuffer) {
	const { parsePreview } = await import('../src/lib/viewer/scene');
	return parsePreview(bytes);
}

function anAnchor(part: string, point: readonly number[]): Anchor {
	return { part, point, durable_key: part };
}

describe('4.2 — a loaded preview reports what it holds', () => {
	it('reports its part names', async () => {
		const preview = await parse(anExport());

		expect(preview.parts.map((part) => part.name)).toEqual([SHOULDER, TORSO]);
	});

	it('reports its clips with their durations', async () => {
		const preview = await parse(anExport());

		expect(preview.clips).toEqual([{ name: WALK, duration: 1 }]);
	});

	it('reports the preview’s own triangle count, which is not the source’s', async () => {
		const preview = await parse(anExport());

		expect(preview.triangles).toBe(2);
		expect(preview.primitives).toBe(2);
		expect(preview.normalPrimitives).toBe(0);
	});

	it('reports which preview primitives carry vertex normals', async () => {
		const preview = await parse(buildGlb([
			{ name: SHOULDER, positions: triangleAt(0), normals: [0, 0, 1, 0, 0, 1, 0, 0, 1], indices: FLAT },
			{ name: TORSO, positions: triangleAt(5), indices: FLAT }
		]));

		expect(preview.primitives).toBe(2);
		expect(preview.normalPrimitives).toBe(1);
	});

	it('says a preview carries no clips rather than inventing one', async () => {
		const preview = await parse(retopologised());

		expect(preview.clips).toEqual([]);
	});

	it('reports geometry in each part’s own space, unposed (D4, D10)', async () => {
		const preview = await parse(anExport());
		const shoulder = preview.parts.find((part) => part.name === SHOULDER);

		expect(Array.from(shoulder?.positions ?? [])).toEqual(triangleAt(0));
	});
});

describe('5.5 — retopology survival, end to end over two fixture exports', () => {
	it('resolves every anchor to its part across an entirely different layout', async () => {
		const before = await parse(anExport());
		const after = await parse(retopologised());
		const anchors = [anAnchor(SHOULDER, [0.2, 0.2, 0]), anAnchor(TORSO, [5.2, 0.2, 0])];

		const first = resolverFor(before);
		const second = resolverFor(after);

		for (const anchor of anchors) {
			expect(first(anchor).outcome).toBe('resolved');
			expect(second(anchor).outcome).toBe('resolved');
			expect(second(anchor).part).toBe(anchor.part);
		}
	});

	it('orphans the one part that was renamed, naming what it expected', async () => {
		const renamed = await parse(
			buildGlb([{ name: 'SM_MechScout_Pauldron_L', positions: triangleAt(0), indices: FLAT }])
		);

		const resolution = resolverFor(renamed)(anAnchor(SHOULDER, [0.2, 0.2, 0]));

		expect(resolution.outcome).toBe('orphaned');
		expect(resolution.part).toBe(SHOULDER);
	});

	it('never moves an anchor to a different part, however plausible', async () => {
		const renamed = await parse(
			buildGlb([{ name: 'SM_MechScout_Pauldron_L', positions: triangleAt(0), indices: FLAT }])
		);

		const resolution = resolverFor(renamed)(anAnchor(SHOULDER, [0.2, 0.2, 0]));

		expect(resolution.point).toBeNull();
		expect(resolution.part).not.toBe('SM_MechScout_Pauldron_L');
	});
});

describe('5.6 — preview and source resolve to the same part', () => {
	it('resolves to the same named part against either mesh', async () => {
		const source = await parse(anExport());
		const preview = await parse(retopologised());
		const anchor = anAnchor(TORSO, [5.1, 0.1, 0]);

		expect(resolverFor(source)(anchor).part).toBe(resolverFor(preview)(anchor).part);
	});

	it('reports a part the preview dropped as a preview limitation, not a removal', async () => {
		const preview = await parse(
			buildGlb([{ name: TORSO, positions: triangleAt(5), indices: FLAT }])
		);

		// The source export is recorded as carrying both parts.
		const resolve = resolverFor(preview, [SHOULDER, TORSO]);
		const resolution = resolve(anAnchor(SHOULDER, [0.2, 0.2, 0]));

		expect(resolution.missingFromPreview).toBe(true);
		expect(resolution.reason).toContain('preview');
		expect(resolution.reason).not.toContain('no longer in the export');
	});
});

describe('the hierarchy is over the triangles the fixture actually holds', () => {
	it('finds the nearest point on a subdivided surface', async () => {
		const preview = await parse(retopologised());
		const shoulder = preview.parts.find((part) => part.name === SHOULDER);

		const index = new PartIndex(shoulder!);

		expect(index.triangleCount).toBe(4);
		expect(index.nearestTo([0.25, 0.25, 3])?.point[2]).toBeCloseTo(0);
	});
});
