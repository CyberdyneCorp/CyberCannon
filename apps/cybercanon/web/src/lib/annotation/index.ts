/**
 * The annotation module — the one place MVVM lives (D2).
 *
 * `tests/tooling/test_web_structure.py` names this directory: a `*.svelte.ts`
 * anywhere else fails the build, because MVVM earns its keep under exactly one
 * condition — one state machine, more than one view — and annotation is the
 * only place in CyberCanon where that holds.
 *
 * What is here, and why each piece is separate from the ViewModel:
 *
 * * `anchor` — what a view produces, and the only thing it produces;
 * * `transform` — the pixel maths, which the ViewModel may not touch (D3);
 * * `pointer` — the one input path, with `pointerType` deciding intent (D10);
 * * `filter` — filtering, medium-agnostic, so the sheet and the viewer agree;
 * * `model` — what the ViewModel is allowed to know about the network;
 * * `annotation-view-model.svelte.ts` — the ViewModel itself.
 */

export * from './anchor';
export * from './filter';
export * from './model';
export * from './pointer';
export * from './transform';
export {
	AnnotationViewModel,
	EMPTY_DRAFT,
	annotationViewModel,
	createAnnotationViewModel
} from './annotation-view-model.svelte';
export type { Draft, WriteState } from './annotation-view-model.svelte';
