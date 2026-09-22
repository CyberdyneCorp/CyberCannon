<script lang="ts">
	/**
	 * One concept view, with its pins and the scribble being composed over it.
	 *
	 * This component is the *view* in the MVVM sense, and its only product is an
	 * `Anchor` (D1). Everything it contributes is here and nothing else:
	 *
	 * * it reads a `PointerEvent` into a :type:`Gesture` and asks the ViewModel
	 *   what that gesture is for (D10) — one code path for a mouse, a trackpad,
	 *   a finger and a stylus, with the palm-rejection rule as a session flag;
	 * * it converts a position on this display into a coordinate in the image's
	 *   own space, through `$lib/annotation/transform` and nowhere else (D3);
	 * * it refuses a gesture outside the image rather than clamping it, which is
	 *   `model-sheet-2d` in so many words.
	 *
	 * Pins are positioned as percentages of the image and strokes are drawn in
	 * an SVG over a `0 0 100 100` box, so both scale with zoom for free: there
	 * is no code that recomputes a position when the view is resized, because a
	 * normalized coordinate does not have one.
	 */
	import type { Annotation } from '$lib/api';
	import { viewAnchor } from '$lib/annotation';
	import type { ImagePoint } from '$lib/annotation';
	import { strokePath } from '$lib/annotation';
	import { fanned } from '$lib/annotation/sheet';
	import type { AnnotationViewModel } from '$lib/annotation';

	interface Props {
		/** The name an anchor keys on. Never a file name, never a position. */
		view: string;
		/** Where the image is served from, when the deployment mirrors one. */
		source?: string | null;
		annotations: readonly Annotation[];
		model: AnnotationViewModel;
		/** Whether this view is the one a selected annotation lives on. */
		focused?: boolean;
	}

	let { view, source = null, annotations, model, focused = false }: Props = $props();

	let image: HTMLElement | null = $state(null);

	const pins = $derived(fanned(annotations));
	const composing = $derived(model.isComposing && model.draft.anchor?.view === view);

	/** Where this gesture landed in the image's own space, or nothing at all. */
	function imagePoint(event: PointerEvent): ImagePoint | null {
		if (!image) return null;
		const box = image.getBoundingClientRect();
		if (box.width <= 0 || box.height <= 0) return null;
		const u = (event.clientX - box.left) / box.width;
		const v = (event.clientY - box.top) / box.height;
		return u < 0 || u > 1 || v < 0 || v > 1 ? null : { u, v };
	}

	function down(event: PointerEvent): void {
		const at = imagePoint(event);
		const intent = model.gesture({
			kind: event.pointerType,
			point: { x: event.clientX, y: event.clientY },
			drawing: model.isComposing
		});
		if (at === null || intent === 'navigate') return;
		if (intent === 'draw') {
			model.beginStroke(at);
			return;
		}
		place(at);
	}

	function move(event: PointerEvent): void {
		if (model.draft.drawing.length === 0) return;
		const at = imagePoint(event);
		if (at) model.extendStroke(at);
	}

	function up(): void {
		if (model.draft.drawing.length > 0) model.endStroke();
	}

	function place(at: ImagePoint): void {
		const anchor = viewAnchor(view, at);
		if (anchor) model.compose(anchor);
	}
</script>

<figure class="view" class:focused data-view={view}>
	<figcaption>{view}</figcaption>
	<div
		class="image"
		bind:this={image}
		role="application"
		aria-label={`the ${view} view of this asset`}
		onpointerdown={down}
		onpointermove={move}
		onpointerup={up}
		onpointercancel={up}
	>
		{#if source}
			<img src={source} alt={`the ${view} view`} />
		{:else}
			<p class="absent">no image is mirrored for this view yet</p>
		{/if}

		<svg class="marks" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
			{#each annotations as annotation (annotation.id)}
				{#each annotation.strokes as stroke, index (index)}
					<polyline points={strokePath(stroke)} />
				{/each}
			{/each}
			{#if composing}
				{#each model.draft.strokes as stroke, index (index)}
					<polyline class="draft" points={strokePath(stroke)} />
				{/each}
				{#if model.draft.drawing.length > 1}
					<polyline class="draft" points={strokePath(model.draft.drawing)} />
				{/if}
			{/if}
		</svg>

		{#each pins as pin (pin.annotation.id)}
			<button
				class="pin"
				class:selected={model.selectedId === pin.annotation.id}
				data-kind={pin.annotation.kind}
				data-annotation={pin.annotation.id}
				style={`left: ${pin.at.u * 100}%; top: ${pin.at.v * 100}%`}
				title={pin.annotation.text}
				onclick={(event) => {
					event.stopPropagation();
					model.select(pin.annotation.id);
				}}
			>
				<span class="label">{pin.annotation.kind.charAt(0).toUpperCase()}</span>
			</button>
		{/each}

		{#if composing && model.draft.anchor?.u !== undefined}
			<span
				class="pin draft"
				data-annotation="draft"
				style={`left: ${(model.draft.anchor.u ?? 0) * 100}%; top: ${(model.draft.anchor.v ?? 0) * 100}%`}
			></span>
		{/if}
	</div>
</figure>

<style>
	.view {
		margin: 0;
		display: grid;
		gap: 0.25rem;
	}

	figcaption {
		font-weight: 600;
	}

	.image {
		position: relative;
		border: 1px solid currentColor;
		border-radius: 0.25rem;
		aspect-ratio: 4 / 3;
		overflow: hidden;
		touch-action: none;
	}

	.focused .image {
		outline: 2px solid currentColor;
	}

	img {
		width: 100%;
		height: 100%;
		object-fit: contain;
		display: block;
	}

	.absent {
		margin: 0;
		padding: 1rem;
		opacity: 0.7;
	}

	.marks {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
	}

	polyline {
		fill: none;
		stroke: currentColor;
		stroke-width: 0.6;
		vector-effect: non-scaling-stroke;
	}

	polyline.draft {
		stroke-dasharray: 2 2;
	}

	.pin {
		position: absolute;
		width: 1.5rem;
		height: 1.5rem;
		margin: -0.75rem 0 0 -0.75rem;
		border-radius: 50%;
		border: 1px solid currentColor;
		background: Canvas;
		cursor: pointer;
		padding: 0;
	}

	.pin.selected {
		outline: 2px solid currentColor;
	}

	.pin.draft {
		border-style: dashed;
	}

	.label {
		font-size: 0.7rem;
	}
</style>
