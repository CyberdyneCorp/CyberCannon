/**
 * Framing — where the camera has to be for something to fit, and whether it does.
 *
 * `viewer-3d` asks for two actions and one property: *"an action that frames the
 * whole asset"*, framing for a selected part alone, and — for both — that what
 * was framed is visible within the viewport. The property is the interesting
 * half, because it is the one a screenshot cannot settle and a renderer cannot
 * be asked about: :func:`withinFrustum` answers it over the eight corners of a
 * box, in plain arithmetic, so *"the whole asset SHALL be visible"* is a test
 * rather than a claim.
 *
 * Nothing here imports `three.js`. The scene module applies the camera this
 * produces; this decides where it goes.
 */

import type { CameraState } from './anchor';
import type { Bounds, Vec3 } from './geometry';
import { add, centre, cross, diagonal, dot, normalize, scale, subtract } from './geometry';

export const DEFAULT_FOV_DEG = 45;

/** A little room around what was framed, so nothing sits exactly on the edge. */
export const MARGIN = 1.15;

/** Where the camera looks from when nothing says otherwise — three-quarter view. */
export const DEFAULT_DIRECTION: Vec3 = [0.6, 0.45, 1];

function radians(degrees: number): number {
	return (degrees * Math.PI) / 180;
}

/**
 * How far back the camera must be for this box to fit, at this field of view.
 *
 * Over the box's bounding **sphere** rather than its half-extents, and that is
 * the whole of why this is right: the camera looks from an arbitrary direction,
 * so the axis-aligned extents mix into the view's own axes and a
 * half-extent-over-tangent calculation leaves a corner outside the cone exactly
 * when the view is oblique — which is the ordinary case, because the default
 * framing is a three-quarter view. A sphere has no orientation, so
 * `radius / sin(half-angle)` contains it from everywhere.
 *
 * The narrower of the two half-angles wins, so a wide asset in a narrow
 * viewport is framed by its width rather than disappearing off the sides.
 */
export function frameDistance(bounds: Bounds, fovDeg = DEFAULT_FOV_DEG, aspect = 1): number {
	const radius = diagonal(bounds) / 2;
	const vertical = radians(fovDeg) / 2;
	const horizontal = Math.atan(Math.tan(vertical) * Math.max(aspect, 0.0001));
	const narrowest = Math.min(vertical, horizontal);
	if (radius === 0 || narrowest <= 0) return MARGIN;
	return (radius / Math.sin(narrowest)) * MARGIN;
}

/**
 * A camera that frames this box from this direction.
 *
 * The target is the box's centre, which is what makes framing *restore a known
 * view*: orbiting afterwards turns around what was framed rather than around
 * wherever the model's origin happens to be.
 */
export function frameCamera(
	bounds: Bounds,
	{
		direction = DEFAULT_DIRECTION,
		fovDeg = DEFAULT_FOV_DEG,
		aspect = 1
	}: { direction?: Vec3; fovDeg?: number; aspect?: number } = {}
): CameraState {
	const target = centre(bounds);
	const away = normalize(direction);
	return {
		position: add(target, scale(away, frameDistance(bounds, fovDeg, aspect))),
		target,
		fovDeg
	};
}

/** Keep the current direction, and move only as far as the new box needs. */
export function reframe(
	bounds: Bounds,
	camera: CameraState,
	aspect = 1
): CameraState {
	const direction = subtract(camera.position, camera.target);
	const away = dot(direction, direction) > 0 ? direction : DEFAULT_DIRECTION;
	return frameCamera(bounds, { direction: away, fovDeg: camera.fovDeg, aspect });
}

/**
 * Whether every corner of the box is inside the camera's frustum.
 *
 * The check the framing actions are asserted with. A box whose corners are all
 * in front of the camera and within both half-angles is a box the viewport
 * shows — which is exactly what *"the whole asset SHALL be visible within the
 * viewport"* claims.
 */
export function withinFrustum(
	bounds: Bounds,
	camera: CameraState,
	aspect = 1,
	near = 0.01
): boolean {
	const forward = normalize(subtract(camera.target, camera.position));
	const right = sideways(forward);
	const up = cross(right, forward);
	const vertical = radians(camera.fovDeg) / 2;
	const horizontal = Math.atan(Math.tan(vertical) * Math.max(aspect, 0.0001));
	return corners(bounds).every((corner) => {
		const offset = subtract(corner, camera.position);
		const depth = dot(offset, forward);
		if (depth < near) return false;
		const across = Math.abs(dot(offset, right));
		const above = Math.abs(dot(offset, up));
		return across <= depth * Math.tan(horizontal) && above <= depth * Math.tan(vertical);
	});
}

/** A right vector for a forward direction, chosen so it is never degenerate. */
function sideways(forward: Vec3): Vec3 {
	const reference: Vec3 = Math.abs(forward[1]) > 0.99 ? [0, 0, 1] : [0, 1, 0];
	return normalize(cross(forward, reference));
}

export function corners(bounds: Bounds): readonly Vec3[] {
	const { min, max } = bounds;
	return [
		[min[0], min[1], min[2]],
		[max[0], min[1], min[2]],
		[min[0], max[1], min[2]],
		[max[0], max[1], min[2]],
		[min[0], min[1], max[2]],
		[max[0], min[1], max[2]],
		[min[0], max[1], max[2]],
		[max[0], max[1], max[2]]
	];
}

/** A sensible near/far pair for a scene this size, so nothing clips or z-fights. */
export function clipPlanes(bounds: Bounds): { near: number; far: number } {
	const span = diagonal(bounds) || 1;
	return { near: Math.max(span / 1000, 0.001), far: span * 100 };
}
