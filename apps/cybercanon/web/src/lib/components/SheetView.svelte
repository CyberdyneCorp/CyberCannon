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
	 *
	 * **THE FRAME AND THE POINTER SURFACE ARE TWO ELEMENTS, AND THAT IS THE
	 * COORDINATE ORIGIN RATHER THAN A WRAPPER.** `imagePoint` reads
	 * `getBoundingClientRect()`, which is a BORDER box; a pin at `u` is placed
	 * at `left: u * 100%`, which a browser resolves against its containing
	 * block's PADDING box. The two boxes are the same box only while the
	 * element carries no border and no padding — so every edge this design
	 * draws (a 3px rule, a hard offset shadow) is on `.frame`, and `.image`,
	 * which is both the element measured and the element pins are positioned
	 * in, is a bare `inset: 0` surface inside it. Put a border back on
	 * `.image` and every existing pin moves by exactly that border's width,
	 * silently, on every view at once.
	 */
	import type { Annotation } from '$lib/api';
	import { viewAnchor } from '$lib/annotation';
	import type { ImagePoint } from '$lib/annotation';
	import { strokePath } from '$lib/annotation';
	import { fanned } from '$lib/annotation/sheet';
	import type { AnnotationViewModel } from '$lib/annotation';

	interface Props {
		/** Short slot label used for display and image lookup. */
		view: string;
		/** Exact view identity from the asset specification, accepted by the API. */
		anchorView?: string;
		/** Current reference image read from the asset's repository history. */
		source?: string | null;
		reason?: string | null;
		annotations: readonly Annotation[];
		model: AnnotationViewModel;
		/** Whether this view is the one a selected annotation lives on. */
		focused?: boolean;
	}

	let { view, anchorView = view, source = null, reason = null, annotations, model, focused = false }: Props = $props();

	let image: HTMLElement | null = $state(null);
	let imageRatio: number | null = $state(null);
	let failedSource = $state<string | null>(null);
	const imageFailed = $derived(Boolean(source && failedSource === source));

	const pins = $derived(fanned(annotations));
	const composing = $derived(model.isComposing && model.draft.anchor?.view === anchorView);

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
		const anchor = viewAnchor(anchorView, at);
		if (anchor) model.compose(anchor);
	}
</script>

<figure class="view" class:focused data-view={view}>
	<figcaption>{view}</figcaption>
	<div class="frame" style:aspect-ratio={imageRatio ?? 4 / 3}>
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
			{#if source && !imageFailed}
				<img
					src={source}
					alt={`the ${view} view`}
					onload={(event) => {
						const image = event.currentTarget as HTMLImageElement;
						imageRatio = image.naturalWidth / image.naturalHeight;
					}}
					onerror={() => (failedSource = source)}
				/>
			{:else}
				<p class="absent">
					{imageFailed ? 'The reference image could not be displayed.' : reason ?? 'Loading reference image…'}
				</p>
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
					aria-label={`${pin.annotation.kind} annotation, ${pin.annotation.state}: ${pin.annotation.text}`}
					onpointerdown={(event) => event.stopPropagation()}
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
	</div>
	<p class="view-help">Click to place · Drag to draw after placing · Select a pin to open</p>
</figure>

<style>
	.view {
		margin: 0;
		display: grid;
		gap: var(--space-1);
	}

	figcaption {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		color: var(--color-neutral-700);
	}

	.view-help {
		margin: 0;
		font-size: var(--text-fine);
		color: var(--color-neutral-700);
	}

	/*
	 * THE FRAME CARRIES EVERY EDGE THIS DESIGN DRAWS, AND `.image` CARRIES
	 * NONE — see the component's comment for why. The short version: the
	 * pointer gesture is measured from `.image`'s border box and a pin is
	 * placed against `.image`'s padding box, and those are the same box only
	 * while `.image` has no border and no padding. The 3px rule, the hard
	 * offset and the white ground are the design's, and they are all here.
	 */
	.frame {
		position: relative;
		aspect-ratio: 4 / 3;
		overflow: hidden;
		background: var(--color-surface);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
	}

	/* Nothing may be added here that has a border, a padding or an inset. */
	.image {
		position: absolute;
		inset: 0;
		touch-action: none;
	}

	/*
	 * The view a selected annotation lives on. An outline rather than a
	 * border, deliberately: an outline is drawn outside the box and takes no
	 * space, so marking a view cannot move a single pin on it.
	 */
	.focused .frame {
		outline: var(--border-heavy) solid var(--color-accent);
		outline-offset: var(--focus-ring-offset);
	}

	img {
		width: 100%;
		height: 100%;
		object-fit: contain;
		display: block;
	}

	/* A view with no readable image still takes gestures and still shows its
	   pins — so the sentence sits on the surface rather than replacing it. */
	.absent {
		margin: 0;
		padding: var(--space-4);
		font-size: var(--text-small);
		color: var(--color-neutral-700);
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
		stroke: var(--color-accent-2);
		stroke-width: 0.6;
		stroke-linecap: round;
		stroke-linejoin: round;
		vector-effect: non-scaling-stroke;
	}

	/* The stroke being composed, not yet saved. Dashed, and in the interface
	   accent rather than the ink a saved mark is drawn in. */
	polyline.draft {
		stroke: var(--color-accent);
		stroke-dasharray: 2 2;
	}

	/*
	 * A pin. Centred on its coordinate by a negative margin of exactly half
	 * its size, which is the other half of the anchor arithmetic: the
	 * element's top-left is placed at the coordinate and then pulled back by
	 * half, so the dot's CENTRE is where the gesture landed.
	 *
	 * The design's fills: ink for an ordinary pin on the page's ground, the
	 * accent for the one the panel is about. The travel every other control
	 * in this interface has on hover is switched off here — a marker that
	 * slides a pixel off its anchor when a mouse passes over it is a marker
	 * that lies about where the anchor is — so the lift is the shadow alone.
	 */
	.pin {
		position: absolute;
		width: var(--space-6);
		height: var(--space-6);
		margin: calc(-1 * var(--space-3)) 0 0 calc(-1 * var(--space-3));
		border-radius: 50%;
		border: var(--border-thick) solid var(--color-divider);
		box-shadow: var(--shadow-md);
		background: var(--color-text);
		color: var(--color-bg);
		cursor: pointer;
		padding: 0;
		display: grid;
		place-items: center;
	}

	.pin:hover:not(:disabled) {
		transform: none;
		box-shadow: var(--shadow-raised);
	}

	.pin:active:not(:disabled) {
		transform: none;
		box-shadow: var(--shadow-pressed);
	}

	/* The selected pin carries a letter, so its fill is a text background and
	   has to measure like one. `--color-accent` against `--color-bg` is 4.19:1
	   — under AA for the 13px label — so the fill takes the next step down the
	   ramp, `--color-accent-600`, at 5.49:1. It is the same accent, a step
	   deeper; the pin still reads as the blue one. */
	.pin.selected {
		background: var(--color-accent-600);
		color: var(--color-bg);
	}

	/* The pin being placed. Dashed and unfilled, so it reads as a position
	   somebody is choosing rather than as a thread that exists. */
	.pin.draft {
		border-style: dashed;
		border-color: var(--color-accent);
		background: var(--color-accent-100);
		box-shadow: none;
	}

	.label {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-small);
		line-height: 1;
	}
</style>
