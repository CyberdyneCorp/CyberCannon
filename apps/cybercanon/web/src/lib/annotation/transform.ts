/**
 * D3 — the pixel maths, in the one place it is allowed to exist.
 *
 * *"A normalized coordinate is a fact about the image; a pixel is a fact about a
 * display that existed for one afternoon. Putting the conversion in the view is
 * what makes 'independent of zoom and display size' a structural property rather
 * than a bug someone fixes twice."*
 *
 * So everything about a bounding rectangle, a device pixel ratio, a zoom
 * transform or a rendition scale is here, and nothing about it is anywhere else.
 * The ViewModel imports none of it — a test imports the ViewModel with no DOM to
 * keep that honest — and this module imports no DOM type either, which is what
 * lets the round trip be exercised without a browser.
 *
 * The one property that matters is asserted rather than described:
 * :func:`toImage` and :func:`toPresentation` are inverses within float
 * tolerance at every zoom, pan, display size, device pixel ratio and rendition
 * scale. `tests/annotation-transform.test.ts` round-trips a coordinate through
 * all five.
 */

import type { ImagePoint } from './anchor';

/**
 * How a view is currently being presented.
 *
 * Five numbers, and every one of them is a fact about *this afternoon*:
 *
 * * `left`/`top` — where the image's top-left corner sits in the surface's own
 *   coordinates, letterboxing already accounted for;
 * * `width`/`height` — how large the image is drawn, after zoom;
 * * `ratio` — the device pixel ratio, when the caller is working in device
 *   pixels rather than CSS pixels. It cancels out of the round trip entirely,
 *   which is the point: a coordinate recorded on a retina display and read on a
 *   projector is the same coordinate.
 */
export interface Presentation {
	readonly left: number;
	readonly top: number;
	readonly width: number;
	readonly height: number;
	readonly ratio?: number;
}

/** A position in the surface's own coordinates — a pixel, and nothing durable. */
export interface SurfacePoint {
	readonly x: number;
	readonly y: number;
}

/**
 * How a view is laid out inside the box it was given.
 *
 * The image keeps its aspect ratio and is centred, so there is letterboxing on
 * one axis whenever the box and the image disagree about shape — and a gesture
 * in the letterboxing is *outside the image*, which the sheet refuses rather
 * than clamps.
 */
export function fitted(
	box: { readonly width: number; readonly height: number },
	image: { readonly width: number; readonly height: number },
	zoom = 1,
	pan: SurfacePoint = { x: 0, y: 0 }
): Presentation {
	const scale = Math.min(box.width / image.width, box.height / image.height) * zoom;
	const width = image.width * scale;
	const height = image.height * scale;
	return {
		left: (box.width - width) / 2 + pan.x,
		top: (box.height - height) / 2 + pan.y,
		width,
		height
	};
}

/**
 * A position on the display as a coordinate in the image's own space.
 *
 * `null` when the position is outside the image — in the letterboxing, on the
 * sheet background, or beyond the edge during a drag. Never clamped: the caller
 * has to be told that no pin was placed, and a clamp would hide that.
 */
export function toImage(point: SurfacePoint, presentation: Presentation): ImagePoint | null {
	const ratio = presentation.ratio ?? 1;
	if (presentation.width <= 0 || presentation.height <= 0) return null;
	const u = (point.x * ratio - presentation.left) / presentation.width;
	const v = (point.y * ratio - presentation.top) / presentation.height;
	if (![u, v].every((value) => Number.isFinite(value) && value >= 0 && value <= 1)) return null;
	return { u, v };
}

/** The same coordinate back on the display, wherever the display now is. */
export function toPresentation(point: ImagePoint, presentation: Presentation): SurfacePoint {
	const ratio = presentation.ratio ?? 1;
	return {
		x: (presentation.left + point.u * presentation.width) / ratio,
		y: (presentation.top + point.v * presentation.height) / ratio
	};
}

/** Where a pin sits as a percentage of the image, for a CSS position. */
export function asPercentages(point: ImagePoint): { readonly left: string; readonly top: string } {
	return { left: `${point.u * 100}%`, top: `${point.v * 100}%` };
}

/** A stroke as an SVG polyline over a unit box, so it scales with the image for free. */
export function strokePath(stroke: readonly (readonly [number, number])[]): string {
	return stroke.map(([u, v]) => `${u * 100},${v * 100}`).join(' ');
}
