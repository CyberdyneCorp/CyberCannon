/**
 * D4 and D5 — re-projection, and the displacement it is honest about.
 *
 * The hard requirement of this whole change is here: *"the placement SHALL be
 * confined to the named part and SHALL NOT land on any other part, even when
 * another part's surface is nearer to the hint"*. It is checkable as plain
 * arithmetic because the geometry half of resolution was deliberately kept out
 * of the renderer, and it is the one property that decides whether feedback
 * survives a retopology or quietly becomes a lie.
 */

import { describe, expect, it } from 'vitest';
import type { Anchor } from '../src/lib/api';
import {
	PartIndex,
	accelerate,
	boundsOf,
	closestOnTriangle,
	diagonal,
	distance
} from '../src/lib/viewer/geometry';
import type { PartGeometry } from '../src/lib/viewer/geometry';
import {
	DISPLACEMENT_THRESHOLD,
	displacementOf,
	resolverFor
} from '../src/lib/viewer/resolution';
import {
	DEFAULT_FOV_DEG,
	frameCamera,
	reframe,
	withinFrustum
} from '../src/lib/viewer/framing';
import { TAP_TOLERANCE_PX, deviceCoordinates, isTap } from '../src/lib/viewer/gesture';

const SHOULDER = 'SM_MechScout_Shoulder_L';
const TORSO = 'SM_MechScout_Torso';

/** A unit square in the z=0 plane, offset along x. Two triangles, four corners. */
function plateAt(x: number, name: string): PartGeometry {
	return {
		name,
		positions: [x, 0, 0, x + 1, 0, 0, x + 1, 1, 0, x, 1, 0],
		indices: [0, 1, 2, 0, 2, 3]
	};
}

const MESH = { parts: [plateAt(0, SHOULDER), plateAt(4, TORSO)], bones: null };

function anAnchor(part: string, point: readonly number[]): Anchor {
	return { part, point, durable_key: part };
}

describe('closest point on a triangle', () => {
	const a = [0, 0, 0] as const;
	const b = [1, 0, 0] as const;
	const c = [0, 1, 0] as const;

	it('projects a point above the interior straight down', () => {
		const found = closestOnTriangle([0.2, 0.2, 5], a, b, c);

		expect(found[0]).toBeCloseTo(0.2);
		expect(found[1]).toBeCloseTo(0.2);
		expect(found[2]).toBeCloseTo(0);
	});

	it('returns a vertex for a point beyond a corner', () => {
		expect(closestOnTriangle([-3, -3, 0], a, b, c)).toEqual(a);
	});

	it('returns a point on an edge for a point beyond one', () => {
		const found = closestOnTriangle([0.5, -2, 0], a, b, c);

		expect(found[1]).toBeCloseTo(0);
		expect(found[0]).toBeCloseTo(0.5);
	});
});

describe('5.1 — the query is restricted to the named part', () => {
	it('resolves onto the named part even when another part’s surface is nearer', () => {
		// The hint sits at x = 3.9 — a tenth of a unit from the torso plate and
		// nearly three units from the shoulder's. The named part still wins.
		const resolution = resolverFor(MESH)(anAnchor(SHOULDER, [3.9, 0.5, 0]));

		expect(resolution.outcome).toBe('resolved');
		expect(resolution.part).toBe(SHOULDER);
		expect(resolution.point?.[0]).toBeCloseTo(1);
	});

	it('places the pin on the named part’s surface, not at the recorded point', () => {
		const resolution = resolverFor(MESH)(anAnchor(SHOULDER, [0.3, 0.3, 7]));

		expect(resolution.point?.[2]).toBeCloseTo(0);
		expect(resolution.normal).not.toBeNull();
	});

	it('resolves an anchor whose hint is nowhere near the mesh', () => {
		// *"GIVEN an annotation whose recorded point now lies well away from the
		// mesh surface, with its named part still present, THEN it SHALL resolve
		// to that part rather than being reported as orphaned."*
		expect(resolverFor(MESH)(anAnchor(SHOULDER, [900, -900, 900])).outcome).toBe('resolved');
	});

	it('resolves an anchor carrying no hint at all', () => {
		expect(resolverFor(MESH)({ part: SHOULDER, durable_key: SHOULDER }).outcome).toBe(
			'resolved'
		);
	});
});

describe('5.2 — resolution does not depend on the camera', () => {
	it('answers the same surface position however the resolver is asked', () => {
		const anchor = anAnchor(SHOULDER, [0.3, 0.3, 7]);

		const first = resolverFor(MESH)(anchor);
		const second = resolverFor(MESH)(anchor);

		expect(second.point).toEqual(first.point);
		expect(second.normal).toEqual(first.normal);
	});

	it('answers the same position from one resolver asked twice', () => {
		const resolve = resolverFor(MESH);
		const anchor = anAnchor(TORSO, [4.5, 0.5, -3]);

		expect(resolve(anchor).point).toEqual(resolve(anchor).point);
	});
});

describe('5.4 — displacement is measured and flagged, never absorbed', () => {
	const span = diagonal(boundsOf(plateAt(0, SHOULDER).positions));

	it('flags a placement that moved far relative to the part’s size', () => {
		const measured = displacementOf([0.5, 0.5, 0], [0.5, 0.5, span], span);

		expect(measured.possiblyDisplaced).toBe(true);
		expect(measured.distance).toBeCloseTo(span);
	});

	it('does not flag a placement that barely moved', () => {
		const measured = displacementOf([0.5, 0.5, 0], [0.5, 0.5, span * 0.01], span);

		expect(measured.possiblyDisplaced).toBe(false);
		expect(measured.proportion).toBeLessThan(DISPLACEMENT_THRESHOLD);
	});

	it('states the distance on a resolution that moved', () => {
		const resolution = resolverFor(MESH)(anAnchor(SHOULDER, [0.5, 0.5, 9]));

		expect(resolution.displacement?.possiblyDisplaced).toBe(true);
		expect(resolution.displacement?.distance).toBeCloseTo(9);
	});

	it('still resolves and stays visible when it is flagged', () => {
		const resolution = resolverFor(MESH)(anAnchor(SHOULDER, [0.5, 0.5, 9]));

		expect(resolution.outcome).toBe('resolved');
		expect(resolution.point).not.toBeNull();
	});
});

describe('the hierarchy is built once per part, on first use (D4)', () => {
	it('returns the same index for the same part', () => {
		const index = accelerate();
		const part = plateAt(0, SHOULDER);

		expect(index(part)).toBe(index(part));
	});

	it('builds one only for the parts that are asked about', () => {
		const built: string[] = [];
		const index = accelerate();
		for (const part of [plateAt(0, SHOULDER)]) {
			index(part);
			built.push(part.name);
		}

		expect(built).toEqual([SHOULDER]);
	});

	it('answers nothing for a part that carries no triangles', () => {
		const empty = new PartIndex({ name: 'SM_Empty', positions: [], indices: [] });

		expect(empty.nearestTo([0, 0, 0])).toBeNull();
	});

	it('finds the same nearest point a brute-force scan would', () => {
		const part = plateAt(0, SHOULDER);
		const index = new PartIndex(part);
		const hint = [0.7, 0.2, 4] as const;

		const found = index.nearestTo(hint);
		const brute = Math.min(
			distance(hint, closestOnTriangle(hint, [0, 0, 0], [1, 0, 0], [1, 1, 0])),
			distance(hint, closestOnTriangle(hint, [0, 0, 0], [1, 1, 0], [0, 1, 0]))
		);

		expect(found?.distance).toBeCloseTo(brute);
	});
});

describe('4.3 — framing leaves what was framed inside the frustum', () => {
	const whole = boundsOf([
		...(plateAt(0, SHOULDER).positions as number[]),
		...(plateAt(4, TORSO).positions as number[])
	]);
	const part = boundsOf(plateAt(4, TORSO).positions);

	it('frames the whole asset', () => {
		const camera = frameCamera(whole, { fovDeg: DEFAULT_FOV_DEG, aspect: 16 / 9 });

		expect(withinFrustum(whole, camera, 16 / 9)).toBe(true);
	});

	it('frames the selected part alone, with the rest still in the scene', () => {
		const camera = frameCamera(part, { aspect: 16 / 9 });

		expect(withinFrustum(part, camera, 16 / 9)).toBe(true);
	});

	it('frames from an arbitrary view without changing the direction it was at', () => {
		const arbitrary = { position: [9, -4, 2] as const, target: [0, 0, 0] as const, fovDeg: 60 };

		const framed = reframe(whole, arbitrary, 1);

		expect(withinFrustum(whole, framed, 1)).toBe(true);
		expect(framed.fovDeg).toBe(60);
	});

	it('is not vacuous: a camera too close does not contain the box', () => {
		const tooClose = { position: [0.5, 0.5, 0.2] as const, target: [0.5, 0.5, 0] as const, fovDeg: 45 };

		expect(withinFrustum(whole, tooClose, 1)).toBe(false);
	});

	it('frames a wide asset in a narrow viewport by its width', () => {
		const wide = boundsOf([-10, 0, 0, 10, 1, 0]);

		expect(withinFrustum(wide, frameCamera(wide, { aspect: 0.5 }), 0.5)).toBe(true);
	});
});

describe('4.3 — orbit, pan and zoom share the surface a placement uses', () => {
	const box = { left: 0, top: 0, width: 200, height: 100 };

	it('reads a gesture that stayed put as a placement', () => {
		expect(isTap({ x: 50, y: 50 }, { x: 52, y: 51 })).toBe(true);
	});

	it('reads a gesture that moved as navigation, and places nothing', () => {
		expect(isTap({ x: 50, y: 50 }, { x: 90, y: 20 })).toBe(false);
	});

	it('reads a release with no press as navigation', () => {
		expect(isTap(null, { x: 50, y: 50 })).toBe(false);
	});

	it('is a threshold in pixels of the display, not in scene units', () => {
		expect(TAP_TOLERANCE_PX).toBeGreaterThan(0);
		expect(isTap({ x: 0, y: 0 }, { x: TAP_TOLERANCE_PX, y: 0 })).toBe(true);
		expect(isTap({ x: 0, y: 0 }, { x: TAP_TOLERANCE_PX + 1, y: 0 })).toBe(false);
	});

	it('maps a pointer to normalized device coordinates, with y flipped', () => {
		const centre = deviceCoordinates({ x: 100, y: 50 }, box);
		expect(centre.x).toBe(0);
		expect(centre.y).toBeCloseTo(0);
		expect(deviceCoordinates({ x: 200, y: 0 }, box)).toEqual({ x: 1, y: 1 });
		expect(deviceCoordinates({ x: 0, y: 100 }, box)).toEqual({ x: -1, y: -1 });
	});

	it('answers the centre for a surface with no size rather than dividing by zero', () => {
		expect(deviceCoordinates({ x: 5, y: 5 }, { left: 0, top: 0, width: 0, height: 0 })).toEqual({
			x: 0,
			y: 0
		});
	});
});
