/**
 * D3 and D10 — turning a pick into an anchor, and discarding topology on the way.
 *
 * A raycast returns an intersection carrying the object, the face index, the
 * barycentric weights and a world point. What crosses this boundary is **the
 * object's name and the point in that object's local space**, and nothing else.
 * `Anchor3D` has no field capable of holding a face index, so the discard is
 * structural rather than disciplined: *"a face index that exists anywhere in
 * the pipeline eventually gets persisted 'just as a fallback'"*.
 *
 * D10 is the other half. The point recorded while a clip is paused is the
 * **rest-pose** local coordinate of the picked surface, obtained by inverting
 * the transform the part was posed by at pick time. Without that, the same
 * physical spot annotated during a walk cycle and at rest produces two
 * different anchors, and every resolution against a differently-posed load
 * drifts. What the model was *doing* is recorded separately, as the playback
 * hint (D9).
 */

import type { Anchor, Camera } from '$lib/api';
import { partAnchor } from '$lib/annotation';
import type { Vec3 } from './geometry';

/**
 * What the scene module returns from a pick, and the whole of what it returns.
 *
 * There is no `faceIndex`, no `barycentric` and no `object`: a test asserts the
 * key set, and the type is what makes that assertion cheap to keep true.
 */
export interface Pick {
	readonly part: string;
	/** The hit point in the picked part's own rest-pose space (D3, D10). */
	readonly point: Vec3;
	/** The surface normal there, in the same space. */
	readonly normal: Vec3;
}

/** Where the viewer is looking — restored verbatim when an annotation is opened. */
export interface CameraState {
	readonly position: Vec3;
	readonly target: Vec3;
	readonly fovDeg: number;
}

/** What the transport was doing when the anchor was placed (D9). */
export interface Playback {
	readonly clip: string;
	/** A proportion of the clip's duration. Never a frame index. */
	readonly t: number;
}

export function cameraPayload(camera: CameraState): Camera {
	return {
		position: [...camera.position],
		target: [...camera.target],
		fov_deg: camera.fovDeg
	};
}

export function cameraFrom(camera: Camera | undefined): CameraState | null {
	if (!camera || camera.position.length < 3 || camera.target.length < 3) return null;
	return {
		position: [camera.position[0], camera.position[1], camera.position[2]],
		target: [camera.target[0], camera.target[1], camera.target[2]],
		fovDeg: camera.fov_deg
	};
}

/**
 * The anchor a placement produces, or `null` when the placement landed on nothing.
 *
 * *"A placement that does not land on any part SHALL NOT create an anchor, and
 * SHALL say so."* The saying is the component's; the not-creating is here, and
 * it is a `null` rather than an anchor with an empty part so that there is no
 * shape in which the refused case can reach the ViewModel.
 */
export function anchorFor(
	pick: Pick | null,
	camera: CameraState | null,
	playback: Playback | null = null
): Anchor | null {
	if (pick === null || !pick.part) return null;
	return partAnchor(pick.part, {
		point: [...pick.point],
		normal: [...pick.normal],
		...(camera ? { camera: cameraPayload(camera) } : {}),
		...(playback ? { clip: playback.clip, t: playback.t } : {})
	});
}

/** The playback hint an anchor carries, or `null` when it carries none (D9). */
export function playbackOf(anchor: Anchor): Playback | null {
	if (!anchor.clip || anchor.t === undefined) return null;
	return { clip: anchor.clip, t: anchor.t };
}

/** Whether a pick carries anything it should not. The D3 assertion, as a function. */
export function carriesTopology(pick: object): boolean {
	const forbidden = ['faceindex', 'face', 'barycentric', 'bary', 'uv', 'index', 'triangle'];
	return Object.keys(pick).some((name) =>
		forbidden.some((token) => name.toLowerCase().includes(token))
	);
}
