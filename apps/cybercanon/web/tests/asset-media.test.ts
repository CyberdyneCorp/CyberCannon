import { describe, expect, it } from 'vitest';
import { canonicalView, imageType, sheetViews } from '../src/lib/asset/media';

describe('concept views on the sheet', () => {
	it('combines a declared file path with the discovered slot without losing either anchor name', () => {
		expect(sheetViews(['concept/front.png', 'front', 'concept/side.jpg', 'side'])).toEqual([
			{ slot: 'front', aliases: ['concept/front.png', 'front'] },
			{ slot: 'side', aliases: ['concept/side.jpg', 'side'] }
		]);
		expect(canonicalView('front.png')).toBe('front');
	});

	it('keeps names that are not image paths distinct', () => {
		expect(sheetViews(['front', 'notes/front', 'front'])).toEqual([
			{ slot: 'front', aliases: ['front', 'front'] },
			{ slot: 'notes/front', aliases: ['notes/front'] }
		]);
	});

	it('labels supported repository image formats for data URLs', () => {
		expect(imageType('characters/mech_scout/concept/front.png')).toBe('image/png');
		expect(imageType('characters/mech_scout/concept/side.jpg')).toBe('image/jpeg');
		expect(imageType('characters/mech_scout/concept/back.webp')).toBe('image/webp');
		expect(imageType('characters/mech_scout/concept/back.unknown')).toBeNull();
	});
});
