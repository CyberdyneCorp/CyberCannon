/**
 * D10 — one input path, with `pointerType` deciding intent.
 *
 * *"Pen places pins and draws; mouse and trackpad place pins; touch pans and
 * zooms once a pen has been seen in the session, and places pins when it has
 * not."*
 *
 * One code path for four input devices, and the palm-rejection rule becomes a
 * **state flag** rather than a heuristic: once a stylus has been seen, a finger
 * is navigation, which is what stops a hand resting on a tablet from covering a
 * view in pins. Before one has been seen, a finger places pins, so the sheet is
 * never unusable on a tablet that has no stylus.
 *
 * Nothing here touches the DOM. The input is a plain record with the two members
 * that decide — the device kind and the position — so the whole rule is
 * exercised without a browser, and the view's only remaining job is reading a
 * real `PointerEvent` into one.
 */

import type { SurfacePoint } from './transform';

/** The `pointerType` values the Pointer Events specification defines. */
export type PointerKind = 'mouse' | 'pen' | 'touch' | string;

/** What a gesture is for. A closed set: there is no fourth intent. */
export const INTENTS = ['place', 'draw', 'navigate'] as const;
export type Intent = (typeof INTENTS)[number];

/** One gesture, as far as the rule is concerned. */
export interface Gesture {
	readonly kind: PointerKind;
	readonly point: SurfacePoint;
	/** Whether the person is composing a scribble rather than placing a pin. */
	readonly drawing?: boolean;
}

/**
 * The session's memory of which devices have been used.
 *
 * Scoped to one sheet and reset with it (D10's accepted cost): a person who
 * picks up a stylus on one asset has not thereby chosen how they will work on
 * the next one.
 */
export interface InputSession {
	readonly penSeen: boolean;
}

export const NEW_SESSION: InputSession = { penSeen: false };

/** The session after this gesture. A pen, once seen, is remembered. */
export function afterGesture(session: InputSession, gesture: Gesture): InputSession {
	return gesture.kind === 'pen' ? { penSeen: true } : session;
}

/**
 * What this gesture is for.
 *
 * A pen draws while a scribble is being composed and places a pin otherwise; a
 * mouse or a trackpad does the same, because there is no reason for a person on
 * a laptop to be denied the scribble; a finger navigates once a pen has been
 * seen, and places a pin when none has.
 */
export function intentOf(session: InputSession, gesture: Gesture): Intent {
	if (gesture.kind === 'touch') return session.penSeen ? 'navigate' : placement(gesture);
	return placement(gesture);
}

function placement(gesture: Gesture): Intent {
	return gesture.drawing ? 'draw' : 'place';
}

/** Whether this gesture should produce an anchor at all. */
export function placesAPin(session: InputSession, gesture: Gesture): boolean {
	return intentOf(session, gesture) === 'place';
}

/** The two members a real `PointerEvent` contributes. Read at the edge, once. */
export function gestureFrom(
	event: { pointerType: string; clientX: number; clientY: number },
	origin: SurfacePoint = { x: 0, y: 0 },
	drawing = false
): Gesture {
	return {
		kind: event.pointerType,
		point: { x: event.clientX - origin.x, y: event.clientY - origin.y },
		drawing
	};
}
