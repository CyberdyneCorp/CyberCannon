/**
 * Tasks 9.1 and 9.2 — the two acceptance runs this change is measured by.
 *
 * Both are written as the tasks state them, over real GLB bytes and the real
 * modules, because both are claims about a *sequence* rather than about a
 * function: annotate, re-export, resolve; annotate a pose, come back later,
 * open it.
 *
 * * **9.1 — retopology.** Four parts annotated, the asset re-exported with an
 *   entirely different triangle layout and one part renamed. Three resolve, one
 *   is orphaned naming the part it expected, and **none moved to another
 *   part** — which is the single property the whole dual-anchor design exists
 *   to produce.
 * * **9.2 — animation.** An annotation placed on a paused frame of a walk
 *   cycle, then opened in a session that has loaded the preview afresh, with
 *   the clip, the position and the camera all restored. *"Restoring the saved
 *   camera when an annotation is opened is a requirement, not a nicety: it is
 *   most of what makes 3D feedback legible."*
 */

import { describe, expect, it } from 'vitest';
import { SUBDIVIDED_INDICES, buildGlb, subdividedAt, triangleAt } from './support/glb';
import type { PartSpec } from './support/glb';
import { anchorFor, cameraFrom, playbackOf } from '../src/lib/viewer/anchor';
import type { CameraState } from '../src/lib/viewer/anchor';
import { restore } from '../src/lib/viewer/clips';
import { resolverFor } from '../src/lib/viewer/resolution';
import type { Anchor } from '../src/lib/api';

const SHOULDER = 'SM_MechScout_Shoulder_L';
const TORSO = 'SM_MechScout_Torso';
const ARM = 'SM_MechScout_Arm_L';
const HEAD = 'SM_MechScout_Head';
const PAULDRON = 'SM_MechScout_Pauldron_L';

const WALK = 'A_mech_scout_walk';

const FLAT = [0, 1, 2];
const CAMERA: CameraState = { position: [3, 2, 4], target: [0, 1, 0], fovDeg: 45 };

const ANNOTATED = [SHOULDER, TORSO, ARM, HEAD];

function part(name: string, at: number): PartSpec {
	return { name, positions: triangleAt(at), indices: FLAT };
}

/** The same part, retopologised: four triangles where there was one. */
function retopologisedPart(name: string, at: number): PartSpec {
	return { name, positions: subdividedAt(at), indices: SUBDIVIDED_INDICES };
}

async function parse(bytes: ArrayBuffer) {
	const { parsePreview } = await import('../src/lib/viewer/scene');
	return parsePreview(bytes);
}

describe('9.1 — the retopology acceptance', () => {
	/** The asset as it was annotated: four named parts, one triangle each. */
	const before = buildGlb(ANNOTATED.map((name, index) => part(name, index * 4)));

	/**
	 * The re-export: an entirely different triangle layout, and the shoulder
	 * renamed to a pauldron — the rename that has to orphan rather than relocate.
	 */
	const after = buildGlb([
		retopologisedPart(PAULDRON, 0),
		retopologisedPart(TORSO, 4),
		retopologisedPart(ARM, 8),
		retopologisedPart(HEAD, 12)
	]);

	/** Four anchors, each placed by pointing at a part and recording the camera. */
	function annotations(): readonly Anchor[] {
		return ANNOTATED.map((name, index) =>
			anchorFor(
				{ part: name, point: [index * 4 + 0.2, 0.2, 0], normal: [0, 0, 1] },
				CAMERA
			)
		).filter((anchor): anchor is Anchor => anchor !== null);
	}

	it('placed four anchors, one per part', () => {
		expect(annotations().map((anchor) => anchor.durable_key)).toEqual(ANNOTATED);
	});

	it('resolves three of them against the retopologised export', async () => {
		const resolve = resolverFor(await parse(after));

		const resolved = annotations()
			.map(resolve)
			.filter((resolution) => resolution.outcome === 'resolved');

		expect(resolved.map((resolution) => resolution.part)).toEqual([TORSO, ARM, HEAD]);
	});

	it('orphans the fourth, naming the part it expected', async () => {
		const resolve = resolverFor(await parse(after));

		const orphans = annotations()
			.map(resolve)
			.filter((resolution) => resolution.outcome === 'orphaned');

		expect(orphans).toHaveLength(1);
		expect(orphans[0].part).toBe(SHOULDER);
	});

	it('moves none of them to another part', async () => {
		const resolve = resolverFor(await parse(after));

		for (const anchor of annotations()) {
			const resolution = resolve(anchor);
			expect(resolution.part).toBe(anchor.durable_key);
			if (resolution.outcome === 'orphaned') expect(resolution.point).toBeNull();
		}
	});

	it('placed every pin on its own part before the re-export, too', async () => {
		const resolve = resolverFor(await parse(before));

		for (const anchor of annotations()) {
			const resolution = resolve(anchor);
			expect(resolution.outcome).toBe('resolved');
			expect(resolution.part).toBe(anchor.durable_key);
		}
	});

	it('keeps every surviving pin on the surface of its own part', async () => {
		const resolve = resolverFor(await parse(after));

		for (const anchor of annotations().filter((entry) => entry.part !== SHOULDER)) {
			const resolution = resolve(anchor);
			const at = ANNOTATED.indexOf(resolution.part) * 4;
			expect(resolution.point?.[0]).toBeGreaterThanOrEqual(at);
			expect(resolution.point?.[0]).toBeLessThanOrEqual(at + 1);
		}
	});
});

describe('9.2 — the animation acceptance', () => {
	const asset = buildGlb(
		[part(SHOULDER, 0), part(TORSO, 4)],
		[{ name: WALK, times: [0, 2], translations: [0, 0, 0, 0, 1, 0] }]
	);

	/** An annotation placed on a paused frame, three quarters through the walk. */
	const placed = anchorFor(
		{ part: SHOULDER, point: [0.2, 0.2, 0], normal: [0, 0, 1] },
		CAMERA,
		{ clip: WALK, t: 0.75 }
	) as Anchor;

	it('records the clip, the position and the camera at authoring time', () => {
		expect(playbackOf(placed)).toEqual({ clip: WALK, t: 0.75 });
		expect(cameraFrom(placed.camera)).toEqual(CAMERA);
	});

	it('restores the clip and the position in a session that reloaded the asset', async () => {
		// A new session: the preview is parsed again, and the transport starts
		// stopped. Nothing is carried over but the annotation itself.
		const preview = await parse(asset);

		const transport = restore(preview.clips, playbackOf(placed));

		expect(transport.clip).toBe(WALK);
		expect(transport.position).toBe(0.75);
		expect(transport.playing).toBe(false);
	});

	it('restores the camera the author was looking through', () => {
		expect(cameraFrom(placed.camera)).toEqual(CAMERA);
	});

	it('still resolves the annotation to its part in the new session', async () => {
		const resolution = resolverFor(await parse(asset))(placed);

		expect(resolution.outcome).toBe('resolved');
		expect(resolution.part).toBe(SHOULDER);
	});

	it('opens against the rest pose, and says so, when the clip is gone', async () => {
		const withoutClips = await parse(buildGlb([part(SHOULDER, 0)]));

		const transport = restore(withoutClips.clips, playbackOf(placed));

		expect(transport.clip).toBe('');
		expect(resolverFor(withoutClips)(placed).outcome).toBe('resolved');
	});
});
