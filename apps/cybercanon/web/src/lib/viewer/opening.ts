/**
 * What opening an annotation means, decided here so it can be checked here.
 *
 * *"Restoring the saved camera when an annotation is opened is a requirement,
 * not a nicety: it is most of what makes 3D feedback legible."* Three things
 * follow from that, and all three are decisions rather than drawing — which is
 * why they are a function over an annotation and a clip list rather than a
 * branch inside a component:
 *
 * * **the camera** — restored verbatim when one was recorded, and when one was
 *   not, the anchor's part is framed and the viewer *says* no camera was
 *   recorded rather than silently showing the default view;
 * * **the clip and the position** (D9) — selected and held paused where the
 *   author left them, and when the preview no longer carries that clip, the
 *   annotation opens against the rest pose and says the clip is unavailable;
 * * **nothing is written.** There is no annotation in the return value and no
 *   parameter that could carry one back, so *"restoring a camera SHALL NOT
 *   modify the annotation"* is a shape rather than a promise.
 */

import type { Anchor, Annotation } from '$lib/api';
import type { CameraState } from './anchor';
import { cameraFrom, playbackOf } from './anchor';
import type { Clip, Transport } from './clips';
import { STOPPED, clipUnavailable, restore } from './clips';
import { CLIP_HINT_UNAVAILABLE, NO_CAMERA_RECORDED } from './presentation';

/** Everything opening one annotation asks the scene to do, as a value. */
export interface Opening {
	/** The camera to apply, or `null` when the part should be framed instead. */
	readonly camera: CameraState | null;
	/** The part to frame when no camera was recorded, or an empty string. */
	readonly frame: string;
	readonly transport: Transport;
	/** What the viewer has to say about what it could not restore. */
	readonly notices: readonly string[];
}

export const NOTHING_OPEN: Opening = {
	camera: null,
	frame: '',
	transport: STOPPED,
	notices: []
};

/**
 * How to present this annotation, given what the loaded preview turned out to have.
 *
 * Total: every annotation produces an opening, including one anchored to a
 * concept view, which frames nothing and restores nothing because there is
 * nothing here for it to name.
 */
export function openingFor(annotation: Annotation, clips: readonly Clip[]): Opening {
	const anchor: Anchor = annotation.anchor;
	const camera = cameraFrom(anchor.camera);
	const hint = playbackOf(anchor);
	const notices = [
		...(camera === null ? [NO_CAMERA_RECORDED] : []),
		...(clipUnavailable(clips, anchor) ? [CLIP_HINT_UNAVAILABLE] : [])
	];
	return {
		camera,
		frame: camera === null ? (anchor.part ?? '') : '',
		transport: restore(clips, hint),
		notices
	};
}

/**
 * The anchor a manual re-anchoring produces: a part a person chose, and a camera.
 *
 * No hint point, deliberately. A person re-anchoring an orphan is saying *this
 * thread belongs on that part*, not *and exactly here on it* — and inventing a
 * position they did not point at would be the silently relocated pin arriving
 * through the one door the design left open. The next resolution places it on
 * the part's surface, and the viewer frames the part.
 */
export function reanchorTo(part: string, camera: CameraState | null): Anchor | null {
	if (!part) return null;
	return {
		part,
		durable_key: part,
		...(camera
			? {
					camera: {
						position: [...camera.position],
						target: [...camera.target],
						fov_deg: camera.fovDeg
					}
				}
			: {})
	};
}
