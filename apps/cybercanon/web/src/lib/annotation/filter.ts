/**
 * Filtering, medium-agnostic — the same answer here as on any other surface.
 *
 * `model-sheet-2d` requires it in so many words: *"WHEN the same filter is
 * applied on the sheet and on any other surface THEN both SHALL present the
 * same set of annotations."* The rule is the domain's
 * (:mod:`cybercanon.domain.annotations`), and this is the client half of it —
 * present so that hiding a pin does not need a round trip, and written so that
 * it cannot disagree: empty means *every*, the two axes combine, and nothing
 * here sorts.
 *
 * The count of what is hidden is part of the filter rather than of the view,
 * because the sheet has to *report* it — a filter that silently removed work
 * would be the reason somebody swears an annotation vanished.
 */

import type { Annotation, AnnotationKind, AnnotationState } from '$lib/api';
import { ANNOTATION_KINDS } from '$lib/api';

export interface AnnotationFilter {
	/** The kinds wanted. Empty is every kind, which is the default presentation. */
	readonly kinds: readonly AnnotationKind[];
	/** The exit states wanted. Empty is every state. */
	readonly states: readonly AnnotationState[];
	/** Whether orphans are included in the list. They are never *placed*. */
	readonly orphans: boolean;
}

/**
 * What a sheet opened with no filter chosen presents.
 *
 * *"WHEN a model sheet is opened with no filter chosen THEN open annotations of
 * every kind SHALL be presented."*
 */
export const DEFAULT_FILTER: AnnotationFilter = {
	kinds: [],
	states: ['open'],
	orphans: true
};

/** Every annotation, whatever its kind, state or anchor. */
export const EVERY: AnnotationFilter = { kinds: [], states: [], orphans: true };

export function wants(filter: AnnotationFilter, annotation: Annotation): boolean {
	if (filter.kinds.length > 0 && !filter.kinds.includes(annotation.kind)) return false;
	if (filter.states.length > 0 && !filter.states.includes(annotation.state)) return false;
	return filter.orphans || annotation.anchor_state !== 'orphaned';
}

/** The annotations this filter wants, in the order they were given. Never sorted. */
export function applyFilter(
	filter: AnnotationFilter,
	annotations: readonly Annotation[]
): readonly Annotation[] {
	return annotations.filter((annotation) => wants(filter, annotation));
}

/** How many the current filter is keeping off the views. */
export function hiddenCount(filter: AnnotationFilter, annotations: readonly Annotation[]): number {
	return annotations.length - applyFilter(filter, annotations).length;
}

/** The same filter with one kind added or removed — what a filter bar toggles. */
export function toggleKind(filter: AnnotationFilter, kind: AnnotationKind): AnnotationFilter {
	const kinds = filter.kinds.includes(kind)
		? filter.kinds.filter((entry) => entry !== kind)
		: [...ANNOTATION_KINDS].filter((entry) => entry === kind || filter.kinds.includes(entry));
	return { ...filter, kinds };
}

/** The same filter with one exit state added or removed. */
export function toggleState(filter: AnnotationFilter, state: AnnotationState): AnnotationFilter {
	const states = filter.states.includes(state)
		? filter.states.filter((entry) => entry !== state)
		: [...filter.states, state];
	return { ...filter, states };
}

/** What the listing request carries. A member nobody narrowed is simply absent. */
export function filterQuery(filter: AnnotationFilter): {
	kinds?: readonly string[];
	states?: readonly string[];
} {
	return {
		...(filter.kinds.length > 0 ? { kinds: filter.kinds } : {}),
		...(filter.states.length > 0 ? { states: filter.states } : {})
	};
}
