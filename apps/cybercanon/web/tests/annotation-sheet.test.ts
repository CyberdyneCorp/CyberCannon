/**
 * Tasks 5.2 to 5.7 — the coordinate transform, the input path, and the pins.
 *
 * These are the parts of the sheet that must not be got wrong, and they are all
 * here because they are all pure: a coordinate, a gesture and a fan of
 * overlapping pins are decided without a browser, which is what makes the
 * round trip assertable rather than describable.
 *
 * The one that earns the most is the round trip (5.2): a coordinate goes
 * through zoom, pan, a window resize, a device pixel ratio and a rendition
 * scale, and comes back the same within float tolerance. That is D3's claim —
 * *"independent of zoom and display size is a structural property rather than a
 * bug someone fixes twice"* — and it is checked over all five at once rather
 * than one at a time, because it is the combination that breaks.
 */

import { describe, expect, it } from 'vitest';
import {
	DEFAULT_FILTER,
	EVERY,
	applyFilter,
	asPercentages,
	fitted,
	hiddenCount,
	partAnchor,
	strokePath,
	toImage,
	toPresentation,
	viewAnchor
} from '../src/lib/annotation';
import { NEW_SESSION, afterGesture, gestureFrom, intentOf } from '../src/lib/annotation';
import { fanned, focusedView, pinsOn, pinsOnAny, pointOf, viewOf } from '../src/lib/annotation/sheet';
import type { Annotation } from '../src/lib/api';

const VIEW = 'front';
const TOLERANCE = 1e-9;

function anAnnotation(id: string, anchor: Annotation['anchor'], over: Partial<Annotation> = {}) {
	return {
		id,
		kind: 'art-direction',
		author: 'auth|rafa',
		via: null,
		attribution: 'auth|rafa',
		text: id,
		state: 'open',
		anchor,
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
	} as Annotation;
}

// --------------------------------------------------------------------------
// 5.2 — the round trip, across everything that can change under a coordinate
// --------------------------------------------------------------------------

/** Five presentations of one image, differing in every way a display can. */
const PRESENTATIONS = [
	{ name: 'fit to a wide box', box: { width: 1200, height: 500 }, zoom: 1, ratio: 1 },
	{ name: 'fit to a tall box', box: { width: 400, height: 900 }, zoom: 1, ratio: 1 },
	{ name: 'zoomed in', box: { width: 800, height: 600 }, zoom: 3.5, ratio: 1 },
	{ name: 'zoomed out', box: { width: 800, height: 600 }, zoom: 0.4, ratio: 1 },
	{ name: 'a retina display', box: { width: 800, height: 600 }, zoom: 1.7, ratio: 2 }
];

/** Three renditions of the same image. The scale must cancel out entirely. */
const RENDITIONS = [
	{ width: 4096, height: 3072 },
	{ width: 1024, height: 768 },
	{ width: 320, height: 240 }
];

const COORDINATES = [
	{ u: 0, v: 0 },
	{ u: 1, v: 1 },
	{ u: 0.25, v: 0.4 },
	{ u: 0.5, v: 0.5 },
	{ u: 0.9134, v: 0.0271 }
];

describe('a normalized coordinate survives every presentation of it (5.2)', () => {
	for (const presentation of PRESENTATIONS) {
		for (const image of RENDITIONS) {
			for (const point of COORDINATES) {
				it(`round-trips ${point.u},${point.v} at ${image.width}px, ${presentation.name}`, () => {
					const pan = { x: 37, y: -19 };
					const placed = {
						...fitted(presentation.box, image, presentation.zoom, pan),
						ratio: presentation.ratio
					};

					const onScreen = toPresentation(point, placed);
					const back = toImage(onScreen, placed);

					expect(back).not.toBeNull();
					expect(Math.abs((back?.u ?? -1) - point.u)).toBeLessThan(TOLERANCE);
					expect(Math.abs((back?.v ?? -1) - point.v)).toBeLessThan(TOLERANCE);
				});
			}
		}
	}

	it('puts a pin over the same feature after a zoom and a window resize', () => {
		const image = { width: 1024, height: 768 };
		const before = fitted({ width: 800, height: 600 }, image, 1);
		const after = fitted({ width: 1440, height: 400 }, image, 2.5, { x: 12, y: 8 });
		const feature = { u: 0.62, v: 0.18 };

		const moved = toImage(toPresentation(feature, after), after);

		expect(toImage(toPresentation(feature, before), before)?.u).toBeCloseTo(feature.u, 9);
		expect(moved?.u).toBeCloseTo(feature.u, 9);
		expect(moved?.v).toBeCloseTo(feature.v, 9);
	});

	it('states a position as a percentage of the image, so CSS scales it for free', () => {
		expect(asPercentages({ u: 0.25, v: 0.4 })).toEqual({ left: '25%', top: '40%' });
	});

	it('draws a stroke over a unit box, which is why it scales with the view (5.7)', () => {
		expect(
			strokePath([
				[0.1, 0.2],
				[0.3, 0.4]
			])
		).toBe('10,20 30,40');
	});
});

// --------------------------------------------------------------------------
// 5.3 — placement outside the image is refused, never clamped
// --------------------------------------------------------------------------

describe('a gesture outside the image places nothing (5.3)', () => {
	const image = { width: 1024, height: 768 };
	const placed = fitted({ width: 1200, height: 500 }, image, 1);

	it.each([
		['in the letterboxing to the left', { x: 2, y: 250 }],
		['in the letterboxing to the right', { x: 1198, y: 250 }],
		['above the image', { x: 600, y: -40 }],
		['below the image', { x: 600, y: 640 }]
	])('refuses a gesture %s', (_where, point) => {
		expect(toImage(point, placed)).toBeNull();
	});

	it('never clamps a refused coordinate to an edge', () => {
		const outside = toImage({ x: -500, y: -500 }, placed);

		expect(outside).toBeNull();
		expect(outside).not.toEqual({ u: 0, v: 0 });
	});

	it('refuses to build an anchor from a coordinate outside the image', () => {
		expect(viewAnchor(VIEW, { u: 1.2, v: 0.5 })).toBeNull();
		expect(viewAnchor(VIEW, { u: Number.NaN, v: 0.5 })).toBeNull();
		expect(viewAnchor('', { u: 0.5, v: 0.5 })).toBeNull();
	});

	it('accepts the edges of the image, because a limit rejecting its own value is none', () => {
		expect(viewAnchor(VIEW, { u: 0, v: 0 })).not.toBeNull();
		expect(viewAnchor(VIEW, { u: 1, v: 1 })).not.toBeNull();
	});
});

// --------------------------------------------------------------------------
// 5.4 — one input path, with `pointerType` deciding intent
// --------------------------------------------------------------------------

describe('pen, mouse, trackpad and finger go through one path (5.4)', () => {
	const image = { width: 1024, height: 768 };
	const placed = fitted({ width: 1024, height: 768 }, image, 1);

	it('produces the same anchor for a pen and a mouse at the same position', () => {
		const at = { clientX: 300, clientY: 200 };
		const pen = gestureFrom({ pointerType: 'pen', ...at });
		const mouse = gestureFrom({ pointerType: 'mouse', ...at });

		const fromPen = toImage(pen.point, placed);
		const fromMouse = toImage(mouse.point, placed);

		expect(fromPen).toEqual(fromMouse);
		expect(viewAnchor(VIEW, fromPen!)).toEqual(viewAnchor(VIEW, fromMouse!));
	});

	it('places a pin with a finger while no stylus has been seen', () => {
		expect(intentOf(NEW_SESSION, { kind: 'touch', point: { x: 1, y: 1 } })).toBe('place');
	});

	it('pans with a finger once a stylus has been used', () => {
		const session = afterGesture(NEW_SESSION, { kind: 'pen', point: { x: 1, y: 1 } });

		expect(session.penSeen).toBe(true);
		expect(intentOf(session, { kind: 'touch', point: { x: 1, y: 1 } })).toBe('navigate');
	});

	it('keeps drawing with a pen while a scribble is being composed', () => {
		const session = afterGesture(NEW_SESSION, { kind: 'pen', point: { x: 1, y: 1 } });

		expect(intentOf(session, { kind: 'pen', point: { x: 1, y: 1 }, drawing: true })).toBe('draw');
	});

	it('lets a mouse draw too, because a laptop is not a lesser tool', () => {
		expect(intentOf(NEW_SESSION, { kind: 'mouse', point: { x: 1, y: 1 }, drawing: true })).toBe(
			'draw'
		);
	});
});

// --------------------------------------------------------------------------
// 5.5 — overlapping pins, and the view a selection brings into presentation
// --------------------------------------------------------------------------

describe('pins stay reachable however they fall (5.5)', () => {
	const crowded = [
		anAnnotation('an_1', viewAnchor(VIEW, { u: 0.5, v: 0.5 })!),
		anAnnotation('an_2', viewAnchor(VIEW, { u: 0.502, v: 0.501 })!),
		anAnnotation('an_3', viewAnchor(VIEW, { u: 0.501, v: 0.5 })!)
	];

	it('gives two annotations within a pin width of each other distinct positions', () => {
		const placed = fanned(crowded);
		const positions = placed.map((entry) => `${entry.at.u}:${entry.at.v}`);

		expect(new Set(positions).size).toBe(3);
	});

	it('leaves the recorded coordinate untouched — fanning is presentation', () => {
		fanned(crowded);

		expect(pointOf(crowded[1])).toEqual({ u: 0.502, v: 0.501 });
	});

	it('keeps every crowded annotation individually addressable', () => {
		expect(fanned(crowded).map((entry) => entry.annotation.id)).toEqual([
			'an_1',
			'an_2',
			'an_3'
		]);
	});

	it('draws only the pins that belong to the view being presented', () => {
		const mixed = [
			anAnnotation('an_1', viewAnchor('front', { u: 0.2, v: 0.2 })!),
			anAnnotation('an_2', viewAnchor('side', { u: 0.2, v: 0.2 })!),
			anAnnotation('an_3', partAnchor('SM_Shoulder')!)
		];

		expect(pinsOn('front', mixed).map((entry) => entry.id)).toEqual(['an_1']);
		expect(viewOf(mixed[2])).toBeNull();
	});

	it('keeps pins from both a declared path and its slot in recorded order', () => {
		const mixed = [
			anAnnotation('an_old', viewAnchor('concept/front.png', { u: 0.2, v: 0.2 })!),
			anAnnotation('an_other', viewAnchor('side', { u: 0.2, v: 0.2 })!),
			anAnnotation('an_new', viewAnchor('front', { u: 0.8, v: 0.8 })!)
		];
		expect(pinsOnAny(['concept/front.png', 'front'], mixed).map((entry) => entry.id)).toEqual([
			'an_old', 'an_new'
		]);
	});

	it('brings the view a selected annotation lives on into presentation', () => {
		const selected = anAnnotation('an_1', viewAnchor('back', { u: 0.2, v: 0.2 })!);

		expect(focusedView(selected, ['front', 'side', 'back'])).toBe('back');
		expect(focusedView(selected, ['front', 'side'])).toBeNull();
		expect(focusedView(null, ['front'])).toBeNull();
	});
});

// --------------------------------------------------------------------------
// 5.6 — the filter bar, and the count it reports
// --------------------------------------------------------------------------

describe('filtering hides pins and changes nothing durable (5.6)', () => {
	const listed = [
		anAnnotation('an_1', viewAnchor(VIEW, { u: 0.1, v: 0.1 })!, { kind: 'art-direction' }),
		anAnnotation('an_2', viewAnchor(VIEW, { u: 0.2, v: 0.2 })!, { kind: 'technical' }),
		anAnnotation('an_3', viewAnchor(VIEW, { u: 0.3, v: 0.3 })!, { state: 'resolved' })
	];

	it('shows open annotations of every kind with no filter chosen', () => {
		expect(applyFilter(DEFAULT_FILTER, listed).map((entry) => entry.id)).toEqual([
			'an_1',
			'an_2'
		]);
	});

	it('reports how many the current filter is hiding', () => {
		expect(hiddenCount(DEFAULT_FILTER, listed)).toBe(1);
		expect(hiddenCount(EVERY, listed)).toBe(0);
	});

	it('combines the kind and the state filters', () => {
		const wanted = { kinds: ['technical'] as const, states: ['open'] as const, orphans: true };

		expect(applyFilter(wanted, listed).map((entry) => entry.id)).toEqual(['an_2']);
	});

	it('never mutates the annotations it filters', () => {
		const before = JSON.stringify(listed);

		applyFilter({ kinds: ['design'], states: [], orphans: false }, listed);

		expect(JSON.stringify(listed)).toBe(before);
	});
});
