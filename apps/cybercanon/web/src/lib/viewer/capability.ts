/**
 * D11 — degradation is a different presentation, not a disabled viewer.
 *
 * *"With no rendering context, the route renders the still presentation:
 * concept views, specification, the full annotation list including orphan and
 * partial states, with triage available. The 3D anchor placement action is
 * present and stated as unavailable."* The annotation data is the valuable
 * part and none of it needs a GPU; an error page would make an entire asset
 * unreachable because of a driver.
 *
 * Two questions live here, and both are answered without a renderer so that
 * both are testable:
 *
 * * **can this device render at all** — asked through an injected probe, so a
 *   suite can simulate a locked-down laptop without one;
 * * **what happens when a live context is lost** — one restoration attempt,
 *   carrying the camera and the paused clip position across it, and the
 *   degraded presentation if that attempt fails. A second attempt is not
 *   offered: a context that will not come back once will not come back twice,
 *   and a retry loop against a reset GPU is a page that never settles.
 */

import type { CameraState } from './anchor';
import type { Transport } from './clips';
import { STOPPED } from './clips';
import type { ViewerState } from './presentation';

/** How the application asks whether this device can present a preview at all. */
export type RenderingProbe = () => boolean;

/**
 * The ordinary probe: is there a rendering context to be had here.
 *
 * Guarded rather than trusted, because the honest answers on a locked-down
 * machine include *throwing*: a browser with hardware acceleration disabled can
 * raise from `getContext` rather than return `null`, and an exception escaping
 * this function would become the error page D11 exists to prevent.
 */
export function browserCanRender(): boolean {
	try {
		if (typeof document === 'undefined') return false;
		const canvas = document.createElement('canvas');
		return Boolean(
			canvas.getContext('webgl2') ?? canvas.getContext('webgl')
		);
	} catch {
		return false;
	}
}

/** What the viewer keeps across a context loss, and restores on the way back. */
export interface Kept {
	readonly camera: CameraState | null;
	readonly transport: Transport;
}

export const KEPT_NOTHING: Kept = { camera: null, transport: STOPPED };

export interface Session {
	readonly state: ViewerState;
	/** How many restorations have been attempted. At most one is ever made. */
	readonly attempts: number;
	readonly kept: Kept;
}

export function newSession(probe: RenderingProbe): Session {
	return {
		state: probe() ? 'loading' : 'degraded',
		attempts: 0,
		kept: KEPT_NOTHING
	};
}

/**
 * Every transition is idempotent, and that is load-bearing rather than tidy.
 *
 * A viewer mounts its scene from an effect that also records what the load
 * produced, so a transition that returned a *new* session for a state it was
 * already in would invalidate the effect that had just set it — and the scene
 * would tear down and remount on every frame, for ever. Returning the same
 * value when nothing changed is what stops that being possible.
 */
function moved(session: Session, state: ViewerState): Session {
	if (session.state === 'degraded' || session.state === state) return session;
	return { ...session, state };
}

export function loaded(session: Session): Session {
	return moved(session, 'ready');
}

export function unloadable(session: Session): Session {
	return moved(session, 'unloadable');
}

/** Retry a load that failed — the affordance `viewer-3d` requires beside the report. */
export function retrying(session: Session): Session {
	return moved(session, 'loading');
}

/**
 * The context went away. Attempt a restoration once, and keep what has to survive.
 *
 * The camera and the paused clip position are carried because they are what the
 * reviewer was looking at: a restoration that came back to the default view
 * would be a restoration in name only.
 */
export function contextLost(session: Session, kept: Kept): Session {
	if (session.attempts >= 1) return { ...session, state: 'degraded', kept };
	return { ...session, state: 'loading', attempts: session.attempts + 1, kept };
}

/** The restoration worked: back to the kept camera and the kept clip position. */
export function contextRestored(session: Session): Session {
	return { ...session, state: 'ready' };
}

/** The restoration did not work. One attempt was the budget, so this is D11. */
export function restorationFailed(session: Session): Session {
	return { ...session, state: 'degraded' };
}

/** Whether a new 3D anchor can be placed at all — stated, never failing on use. */
export function canPlaceAnchor(session: Session): boolean {
	return session.state === 'ready';
}

/** Whether the still presentation is what this session shows (D11). */
export function isDegraded(session: Session): boolean {
	return session.state === 'degraded';
}
