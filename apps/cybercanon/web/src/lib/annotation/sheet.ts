/**
 * The 2D half — the only module in `$lib/annotation` that knows what a view is.
 *
 * D1 draws the line here on purpose. Grouping pins by the view they sit on is a
 * question about *this medium*: a 3D anchor has no view and never will, so a
 * ViewModel that answered it would be a ViewModel with a 2D-specific member in
 * it, and `add-viewer-3d` would have to fork the file it was supposed to reuse.
 *
 * So everything below takes annotations and gives back annotations, the sheet
 * calls it, and the ViewModel does not import it.
 */

import type { Annotation } from '$lib/api';
import type { ImagePoint } from './anchor';

/** The view an annotation sits on, or `null` when it is anchored some other way. */
export function viewOf(annotation: Annotation): string | null {
	return annotation.anchor.view ?? null;
}

/** Where on that view it sits. `null` for an anchor that carries no coordinate. */
export function pointOf(annotation: Annotation): ImagePoint | null {
	const { u, v } = annotation.anchor;
	return u === undefined || v === undefined ? null : { u, v };
}

/** The annotations to draw over one view, in the order they were read. */
export function pinsOn(view: string, annotations: readonly Annotation[]): readonly Annotation[] {
	return annotations.filter((annotation) => viewOf(annotation) === view && pointOf(annotation));
}

/** Preserve the recorded order when legacy path and canonical slot anchors share a card. */
export function pinsOnAny(views: readonly string[], annotations: readonly Annotation[]): readonly Annotation[] {
	const aliases = new Set(views);
	return annotations.filter((annotation) => aliases.has(viewOf(annotation) ?? '') && pointOf(annotation));
}

/**
 * Which view has to be brought into presentation for this annotation.
 *
 * *"WHEN it is selected from the thread panel THEN that view SHALL be brought
 * into presentation with its pin highlighted."* `null` means the selection
 * names nothing this sheet can show — an orphan, or an anchor of the other
 * form — and the panel says so rather than the sheet scrolling nowhere.
 */
export function focusedView(
	selected: Annotation | null,
	views: readonly string[]
): string | null {
	const named = selected ? viewOf(selected) : null;
	return named && views.includes(named) ? named : null;
}

/**
 * How overlapping pins stay individually selectable.
 *
 * *"Annotations whose pins fall close enough together to overlap SHALL each
 * remain individually selectable."* No clustering — a view with enough pins to
 * need clustering is a triage failure, and the queue is the fix — so instead,
 * pins that share a spot are **fanned**: each gets a small offset along a
 * circle, in a deterministic order, so every one of them has a target a pointer
 * can reach. The recorded coordinate is untouched; this is presentation.
 */
export const OVERLAP = 0.02;
export const FAN = 0.012;

export function fanned(
	annotations: readonly Annotation[]
): readonly { readonly annotation: Annotation; readonly at: ImagePoint }[] {
	const placed: { annotation: Annotation; at: ImagePoint }[] = [];
	for (const annotation of annotations) {
		const at = pointOf(annotation);
		if (!at) continue;
		placed.push({ annotation, at: offset(at, crowd(placed, at)) });
	}
	return placed;
}

function crowd(
	placed: readonly { readonly at: ImagePoint }[],
	at: ImagePoint
): number {
	return placed.filter((entry) => Math.hypot(entry.at.u - at.u, entry.at.v - at.v) < OVERLAP)
		.length;
}

function offset(at: ImagePoint, index: number): ImagePoint {
	if (index === 0) return at;
	const angle = (index * 2 * Math.PI) / 6;
	return {
		u: clamp(at.u + Math.cos(angle) * FAN),
		v: clamp(at.v + Math.sin(angle) * FAN)
	};
}

function clamp(value: number): number {
	return Math.min(1, Math.max(0, value));
}
