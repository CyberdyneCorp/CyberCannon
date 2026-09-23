/**
 * REGRESSION — the neo-brutal restyle must not move a single pin.
 *
 * `SheetView` places a pin at `left: u * 100%`, which a browser resolves
 * against its containing block's **padding** box, and reads a gesture through
 * `getBoundingClientRect()`, which is a **border** box. Those are the same box
 * only while the element carries no border and no padding — so a heavy black
 * edge added to the element that is both measured and positioned in would
 * shift the coordinate origin by exactly that edge's width and move every
 * existing pin on every view at once, silently, with no test failing.
 *
 * This suite is the two halves of that invariant:
 *
 * * **the coordinate survives the markup.** A pin renders the normalized
 *   coordinate verbatim, so nothing between the anchor and the style
 *   attribute scales, clamps or offsets it;
 * * **the two boxes still coincide.** The element bound to `image` — the one
 *   `imagePoint` measures and the one pins are absolutely positioned in —
 *   declares no border, no padding and no inset, and the element that carries
 *   this design's edge and offset is a different element outside it.
 *
 * The second half is read out of the component's own source because there is
 * no DOM here: these tests run under `environment: 'node'`, which is what lets
 * the whole suite stay in `just check`. A stylesheet assertion is a weaker
 * instrument than a layout one, and it is the one that catches the mistake
 * this file exists for — the mistake is a declaration, not a computation.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import SheetView from '../src/lib/components/SheetView.svelte';
import { createAnnotationViewModel, viewAnchor } from '../src/lib/annotation';
import type { Annotation } from '../src/lib/api';

const SOURCE = readFileSync(
	fileURLToPath(new URL('../src/lib/components/SheetView.svelte', import.meta.url)),
	'utf8'
);

const AT = { u: 0.25, v: 0.4 };

function anAnnotation(over: Partial<Annotation> = {}): Annotation {
	return {
		id: 'an_1',
		kind: 'art-direction',
		author: 'auth|rafa',
		via: null,
		attribution: 'auth|rafa',
		text: 'the pauldron reads as a backpack at 15 m',
		state: 'open',
		anchor: viewAnchor('front', AT)!,
		anchor_state: 'carried',
		authored_against: null,
		created_at: null,
		edited_at: null,
		moved_by: null,
		moved_at: null,
		closed_by: null,
		closed_at: null,
		closing_text: null,
		replies: [],
		strokes: [],
		exits: ['promote', 'resolve'],
		...over
	};
}

function viewHtml(): string {
	return render(SheetView, {
		props: {
			view: 'front',
			source: 'https://mirror.invalid/front.png',
			annotations: [anAnnotation()],
			model: createAnnotationViewModel()
		}
	}).body;
}

/** One CSS rule out of the component's `<style>` block, by its selector. */
function rule(selector: string): string {
	const at = SOURCE.indexOf(`\n\t${selector} {`);
	expect(at, `no \`${selector}\` rule in SheetView.svelte`).toBeGreaterThan(-1);
	return SOURCE.slice(at, SOURCE.indexOf('\n\t}', at));
}

describe('a pin lands on the coordinate the gesture produced', () => {
	it('renders the normalized coordinate verbatim, unscaled and unoffset', () => {
		expect(viewHtml()).toContain(`style="left: ${AT.u * 100}%; top: ${AT.v * 100}%"`);
	});

	/**
	 * The gesture is measured from the element bound to `image`, and a pin is
	 * positioned inside that same element. Two different elements would mean
	 * two different origins and no test could tell, because each one would look
	 * right on its own.
	 */
	it('measures the gesture in the element the pins are positioned in', () => {
		expect(SOURCE).toContain('class="image"');
		expect(SOURCE).toMatch(/class="image"\s*\n\s*bind:this=\{image\}/);
		// The pins, the strokes and the draft pin are all inside that element:
		// it closes after the last of them.
		const opened = SOURCE.indexOf('class="image"');
		const closed = SOURCE.indexOf('</div>', SOURCE.indexOf('data-annotation="draft"'));
		expect(SOURCE.indexOf('class="pin"')).toBeGreaterThan(opened);
		expect(SOURCE.indexOf('class="pin"')).toBeLessThan(closed);
	});

	it('gives that element no border, no padding and no inset offset', () => {
		const image = rule('.image');

		expect(image).not.toMatch(/\bborder\b/);
		expect(image).not.toMatch(/\bpadding\b/);
		// `inset: 0` is the whole of its box arithmetic — any other value would
		// move the origin away from the frame's content box.
		expect(image).toMatch(/inset:\s*0;/);
	});

	/**
	 * Where the design's edge actually lives. The frame is outside the measured
	 * element, so its 3px rule and its hard offset cost the pins nothing.
	 */
	it('carries this design’s edge and offset on the frame outside it', () => {
		const frame = rule('.frame');

		expect(frame).toMatch(/border:\s*var\(--border-thick\)/);
		expect(frame).toMatch(/box-shadow:\s*var\(--shadow-lg\)/);
		expect(SOURCE.indexOf('class="frame"')).toBeLessThan(SOURCE.indexOf('class="image"'));
	});

	/**
	 * The hover travel every other control in this interface has would slide a
	 * pin off its own anchor, so a pin does not have it. It lifts by its shadow
	 * instead.
	 */
	it('never translates a pin on hover or press', () => {
		expect(rule('.pin:hover:not(:disabled)')).toMatch(/transform:\s*none;/);
		expect(rule('.pin:active:not(:disabled)')).toMatch(/transform:\s*none;/);
	});
});
