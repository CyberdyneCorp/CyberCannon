/**
 * D1 and D3 — what a view produces, and the only thing it produces.
 *
 * *"The views' only job is to turn input into an `Anchor` (`Sheet2D` →
 * `Anchor2D{view,u,v}`, `Viewer3D` → `Anchor3D{part,point,normal,camera}`);
 * threads, filtering, triage, status are written once"* (`openspec/project.md`).
 *
 * So the ViewModel never learns which view produced an anchor, and the way that
 * stays true is that there is nothing here for it to branch on: an anchor is one
 * shape with optional members and a `durableKey` that answers *what is this
 * attached to* for both forms. `Sheet2D` builds one with :func:`viewAnchor`;
 * `Viewer3D` will build one with :func:`partAnchor` and add no case anywhere
 * else.
 *
 * Nothing in this module knows what a pixel is. The conversion between a
 * position on a display and a normalized coordinate is
 * :mod:`$lib/annotation/transform`'s, because a normalized coordinate is a fact
 * about the image and a pixel is a fact about a display that existed for one
 * afternoon.
 */

import type { Anchor, Camera } from '$lib/api';

/** A point in an image, normalized to its own space. Never a pixel. */
export interface ImagePoint {
	readonly u: number;
	readonly v: number;
}

/** Whether a normalized coordinate is one: inside the image, and a number. */
export function isInsideImage(point: ImagePoint): boolean {
	return [point.u, point.v].every((value) => Number.isFinite(value) && value >= 0 && value <= 1);
}

/**
 * The anchor a 2D view produces.
 *
 * Refuses a coordinate outside the image rather than clamping it, which is
 * `model-sheet-2d` in so many words: *"SHALL NOT create an annotation, and SHALL
 * NOT be clamped to the image edge"*. A clamp would put a pin on the edge of a
 * feature nobody pointed at, which is worse than no pin at all.
 */
export function viewAnchor(view: string, point: ImagePoint): Anchor | null {
	if (!view || !isInsideImage(point)) return null;
	return { view, u: point.u, v: point.v, durable_key: view };
}

/**
 * The anchor a 3D view produces. Built here so the ViewModel stays unaware.
 *
 * Every member but `part` is a *hint*: the point and the normal say roughly
 * where on the part, the camera says what the author was looking at, and the
 * clip and position say what the model was doing. None of them participates in
 * deciding whether the anchor resolves, and there is no member that could hold
 * a triangle index or a frame number — the topology and frame prohibitions are
 * enforced by the shape having nowhere to put one (D3, D9).
 */
export function partAnchor(part: string, hints: PartHints = {}): Anchor | null {
	if (!part) return null;
	if (hints.t !== undefined && !(hints.t >= 0 && hints.t <= 1)) return null;
	return { part, ...definedOnly(hints), durable_key: part };
}

/** What a 3D view may record beside the part. All optional, none an identity. */
export interface PartHints {
	readonly point?: readonly number[];
	readonly normal?: readonly number[];
	readonly bone?: string;
	readonly camera?: Camera;
	readonly clip?: string;
	/** Where in the clip, as a proportion of its duration. Never a frame (D9). */
	readonly t?: number;
}

function definedOnly(hints: PartHints): Record<string, unknown> {
	return Object.fromEntries(
		Object.entries(hints).filter(([, value]) => value !== undefined && value !== null)
	);
}

/**
 * The anchor as the write surface states it.
 *
 * `durable_key` is derived by the server from whichever form it is, so it is not
 * sent: a client that sent one would be proposing an identity for something it
 * did not author.
 */
export function anchorPayload(anchor: Anchor): Record<string, unknown> {
	const { durable_key: _derived, ...members } = anchor;
	return Object.fromEntries(
		Object.entries(members).filter(([, value]) => value !== undefined && value !== null)
	);
}
