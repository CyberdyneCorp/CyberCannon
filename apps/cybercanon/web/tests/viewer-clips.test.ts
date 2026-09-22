/**
 * Group 8 — the transport, and the presentation of what it is playing.
 *
 * Every claim `animation-playback` makes about playback is a claim about a
 * *state*, so every one of them is a call here: pausing holds the position,
 * scrubbing is deterministic, speed scales time and never the clip, and looping
 * wraps rather than stopping. None of it needs a mixer, which is why the
 * transport is a value rather than something inside `three.js`.
 */

import { describe, expect, it } from 'vitest';
import type { Clip } from '../src/lib/viewer/clips';
import {
	NORMAL_SPEED,
	SPEEDS,
	STOPPED,
	advanced,
	clipNamed,
	clipUnavailable,
	durationOf,
	pause,
	play,
	readout,
	restore,
	scrubTo,
	secondsAt,
	select,
	setLoop,
	setSpeed,
	toggle,
	within
} from '../src/lib/viewer/clips';
import {
	CLIPS_UNAVAILABLE,
	NO_CLIPS_IN_PREVIEW,
	clipAbsence,
	clipRows,
	stateRows,
	transportAvailable
} from '../src/lib/viewer/presentation';
import type { ClipCoverage, PreviewDescriptor } from '../src/lib/api';

const WALK = 'A_mech_scout_walk';
const FIRE = 'A_mech_scout_fire';
const TEST = 'A_mech_scout_test';

const CLIPS: readonly Clip[] = [
	{ name: WALK, duration: 2 },
	{ name: FIRE, duration: 0.5 }
];

const COVERAGE: ClipCoverage = {
	states: [
		{ state: 'walk', clip: WALK, coverage: 'satisfied' },
		{ state: 'fire', clip: FIRE, coverage: 'no clip' },
		{ state: 'destroyed', clip: null, coverage: 'declared unanimated' }
	],
	unclaimed: [TEST]
};

function aDescriptor(over: Partial<PreviewDescriptor> = {}): PreviewDescriptor {
	return {
		project: 'ironwood',
		asset: 'mech_scout',
		path: 'characters/mech_scout/asset.yaml',
		revision: 'rev-1',
		preview: {
			key: 'previews/mech_scout.glb',
			source_export: 'exports/mech_scout.glb',
			size_bytes: 24,
			content_type: 'model/gltf-binary'
		},
		source_export: 'exports/mech_scout.glb',
		latest_validated_export: 'exports/mech_scout.glb',
		derived_from_latest: true,
		counts: { triangles: 14310, objects: 3, materials: 2 },
		parts: ['SM_MechScout_Shoulder_L'],
		clips: [WALK],
		coverage: COVERAGE,
		absent: null,
		reason: null,
		...over
	};
}

describe('8.3 — the transport', () => {
	it('selects a clip paused at its start', () => {
		const transport = select(STOPPED, WALK);

		expect(transport).toEqual({ ...STOPPED, clip: WALK, position: 0, playing: false });
	});

	it('plays, and pausing holds the position it was at', () => {
		const playing = advanced(play(select(STOPPED, WALK)), CLIPS[0], 1);

		const paused = pause(playing);

		expect(paused.playing).toBe(false);
		expect(paused.position).toBeCloseTo(0.5);
	});

	it('resumes from where it was paused', () => {
		const paused = pause(advanced(play(select(STOPPED, WALK)), CLIPS[0], 1));

		expect(play(paused).position).toBeCloseTo(0.5);
	});

	it('scrubs to the same pose from different starting points', () => {
		const first = scrubTo(select(STOPPED, WALK), 0.75);
		const second = scrubTo(scrubTo(select(STOPPED, WALK), 0.1), 0.75);

		expect(second.position).toBe(first.position);
	});

	it('clamps a scrub outside the clip rather than leaving it', () => {
		expect(scrubTo(select(STOPPED, WALK), 4).position).toBe(1);
		expect(scrubTo(select(STOPPED, WALK), -4).position).toBe(0);
		expect(within(Number.NaN)).toBe(0);
	});

	it('offers at least three speeds, including a normal one', () => {
		expect(SPEEDS.length).toBeGreaterThanOrEqual(3);
		expect(SPEEDS).toContain(NORMAL_SPEED);
	});

	it('plays faster at a higher speed without altering the clip’s duration', () => {
		const clip = CLIPS[0];
		const base = advanced(play(select(STOPPED, WALK)), clip, 1);
		const quick = advanced(setSpeed(play(select(STOPPED, WALK)), 2), clip, 1);

		expect(quick.position).toBeCloseTo(base.position * 2);
		expect(durationOf(clip)).toBe(2);
	});

	it('ignores a speed nobody offered', () => {
		expect(setSpeed(STOPPED, 7).speed).toBe(NORMAL_SPEED);
	});

	it('loops by wrapping, and stops at the end when it does not', () => {
		const clip = CLIPS[1];
		const looping = advanced(setLoop(play(select(STOPPED, FIRE)), true), clip, 0.75);
		const once = advanced(play(select(STOPPED, FIRE)), clip, 0.75);

		expect(looping.position).toBeCloseTo(0.5);
		expect(looping.playing).toBe(true);
		expect(once.position).toBe(1);
		expect(once.playing).toBe(false);
	});

	it('displays the current position while playing and while paused', () => {
		const transport = scrubTo(select(STOPPED, WALK), 0.25);

		expect(secondsAt(transport, CLIPS[0])).toBeCloseTo(0.5);
		expect(secondsAt(play(transport), CLIPS[0])).toBeCloseTo(0.5);
		expect(readout(0.5)).toBe('0:00.50');
	});

	it('toggles between playing and paused', () => {
		const selected = select(STOPPED, WALK);

		expect(toggle(selected).playing).toBe(true);
		expect(toggle(toggle(selected)).playing).toBe(false);
	});

	it('will not play when no clip is selected', () => {
		expect(play(STOPPED).playing).toBe(false);
	});

	it('does not advance a transport that is paused', () => {
		const paused = scrubTo(select(STOPPED, WALK), 0.3);

		expect(advanced(paused, CLIPS[0], 5).position).toBeCloseTo(0.3);
	});
});

describe('8.6 — replaying an annotation restores its clip and position', () => {
	it('holds the recorded clip paused at the recorded position', () => {
		const restored = restore(CLIPS, { clip: WALK, t: 0.75 });

		expect(restored.clip).toBe(WALK);
		expect(restored.position).toBe(0.75);
		expect(restored.playing).toBe(false);
	});

	it('leaves the transport stopped when the clip is not in this preview', () => {
		expect(restore(CLIPS, { clip: 'A_gone', t: 0.5 })).toEqual(STOPPED);
	});

	it('says the recorded clip is unavailable rather than staying silent', () => {
		expect(clipUnavailable(CLIPS, { clip: 'A_gone' })).toBe(true);
		expect(clipUnavailable(CLIPS, { clip: WALK })).toBe(false);
		expect(clipUnavailable(CLIPS, null)).toBe(false);
	});

	it('leaves an annotation with no hint at the rest pose', () => {
		expect(restore(CLIPS, null)).toEqual(STOPPED);
	});
});

describe('8.1, 8.2 and 8.4 — what the listing says', () => {
	it('lists each clip with the declared state it satisfies', () => {
		const rows = clipRows(COVERAGE, CLIPS);

		expect(rows).toEqual([
			{ name: WALK, duration: 2, state: 'walk' },
			{ name: FIRE, duration: 0.5, state: '' }
		]);
	});

	it('lists every declared state, the gap included', () => {
		expect(stateRows(COVERAGE).map((state) => state.state)).toEqual([
			'walk',
			'fire',
			'destroyed'
		]);
	});

	it('does not present a deliberately unanimated state as a gap', () => {
		const unanimated = stateRows(COVERAGE).find((state) => state.state === 'destroyed');

		expect(unanimated?.coverage).toBe('declared unanimated');
	});

	it('says a preview carries no clips when the asset has no animation', () => {
		expect(clipAbsence(aDescriptor({ clips: [] }), [])).toBe(NO_CLIPS_IN_PREVIEW);
	});

	it('says clips are unavailable when the export had them and the preview lost them', () => {
		const absence = clipAbsence(aDescriptor({ clips: [WALK] }), []);

		expect(absence).toBe(CLIPS_UNAVAILABLE);
		expect(absence).not.toContain('no animation');
	});

	it('offers no transport when there is nothing it could act on', () => {
		expect(transportAvailable([])).toBe(false);
		expect(transportAvailable(CLIPS)).toBe(true);
	});

	it('finds a clip by name, and answers nothing for one it does not have', () => {
		expect(clipNamed(CLIPS, WALK)).toEqual(CLIPS[0]);
		expect(clipNamed(CLIPS, 'A_gone')).toBeNull();
	});
});
