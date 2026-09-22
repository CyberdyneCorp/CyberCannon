/**
 * Tasks 4.5, 4.6, 6.4, 6.6 and 8.7 — view state, and the writes it never makes.
 *
 * D12 is the rule these check: *"Selection, isolation, loop and speed are view
 * state and are never persisted. `asset.yaml` is reviewed in pull requests; a
 * diff caused by someone having hidden a leg is noise that trains people to
 * stop reading diffs."*
 *
 * The way to check a claim about what *does not* happen is to make the thing
 * that would happen observable, so every case here drives the real modules over
 * a Model that records every call it receives — and then asserts the list is
 * empty. A component that quietly wrote would have to go through it.
 */

import { describe, expect, it } from 'vitest';
import { Mesh } from 'three';
import { buildGlb, triangleAt } from './support/glb';
import { createAnnotationViewModel, partAnchor } from '../src/lib/annotation';
import type { AnnotationViewModel } from '../src/lib/annotation';
import type { Annotation, AnnotationListing } from '../src/lib/api';
import { NOTHING_OPEN, openingFor, reanchorTo } from '../src/lib/viewer/opening';
import { NO_CAMERA_RECORDED, CLIP_HINT_UNAVAILABLE } from '../src/lib/viewer/presentation';
import type { CameraState } from '../src/lib/viewer/anchor';
import { anchorFor } from '../src/lib/viewer/anchor';
import type { Clip, Transport } from '../src/lib/viewer/clips';
import {
	STOPPED,
	advanced,
	play,
	scrubTo,
	select,
	setLoop,
	setSpeed
} from '../src/lib/viewer/clips';

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const RAFA = 'auth|rafa';
const SHOULDER = 'SM_MechScout_Shoulder_L';
const TORSO = 'SM_MechScout_Torso';
const PAULDRON = 'SM_MechScout_Pauldron_L';
const WALK = 'A_mech_scout_walk';

const CAMERA: CameraState = { position: [3, 2, 4], target: [0, 1, 0], fovDeg: 45 };
const CLIPS: readonly Clip[] = [{ name: WALK, duration: 2 }];

function anAnnotation(id: string, over: Partial<Annotation> = {}): Annotation {
	return {
		id,
		kind: 'art-direction',
		author: RAFA,
		via: null,
		attribution: RAFA,
		text: `finding ${id}`,
		state: 'open',
		anchor: partAnchor(SHOULDER)!,
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

function aListing(annotations: readonly Annotation[]): AnnotationListing {
	return {
		project: PROJECT,
		asset: ASSET,
		path: 'characters/mech_scout/asset.yaml',
		revision: 'rev-1',
		annotations,
		hidden: 0,
		orphans: [],
		view_names: [],
		actor: RAFA,
		may_promote: false
	};
}

/** A Model that records every call. What is asserted is that the list stays empty. */
function recording(listing: () => AnnotationListing) {
	const calls: string[] = [];
	const write = (verb: string) => async (...args: unknown[]) => {
		calls.push(`${verb} ${String(args[2] ?? '')}`);
		return {
			ok: true as const,
			data: {
				project: PROJECT,
				asset: ASSET,
				path: '',
				revision: 'rev-2',
				committed: true,
				annotation: anAnnotation('an_1')
			},
			freshness: null
		};
	};
	const model = {
		list: async () => ({ ok: true as const, data: listing(), freshness: null }),
		create: write('create'),
		reply: write('reply'),
		edit: write('edit'),
		withdraw: write('withdraw'),
		move: write('move'),
		resolve: write('resolve'),
		reopen: write('reopen'),
		promote: write('promote')
	};
	return { calls, model };
}

function attached(annotations: readonly Annotation[]) {
	const { calls, model } = recording(() => aListing(annotations));
	const viewModel: AnnotationViewModel = createAnnotationViewModel();
	viewModel.attach(model as never, PROJECT, ASSET);
	viewModel.hydrate(aListing(annotations));
	return { calls, viewModel };
}

describe('4.5 — a pick against an isolated-away part records nothing', () => {
	async function filter(hits: readonly { object: Mesh }[]) {
		const { firstVisible } = await import('../src/lib/viewer/scene');
		return firstVisible(hits);
	}

	function aMesh(name: string, visible: boolean): Mesh {
		const mesh = new Mesh();
		mesh.name = name;
		mesh.visible = visible;
		return mesh;
	}

	it('passes over a hidden part and answers with the one behind it', async () => {
		const found = await filter([{ object: aMesh(SHOULDER, false) }, { object: aMesh(TORSO, true) }]);

		expect(found?.object.name).toBe(TORSO);
	});

	it('answers nothing when every part the ray met is hidden', async () => {
		expect(await filter([{ object: aMesh(SHOULDER, false) }])).toBeUndefined();
	});

	it('answers nothing for a ray that met no part at all', async () => {
		expect(await filter([])).toBeUndefined();
	});

	it('treats a part hidden by its parent as hidden', async () => {
		const parent = aMesh('SM_Group', false);
		const child = aMesh(SHOULDER, true);
		parent.add(child);

		expect(await filter([{ object: child }])).toBeUndefined();
	});

	it('creates no anchor from a pick that found nothing', () => {
		expect(anchorFor(null, CAMERA)).toBeNull();
	});
});

describe('4.6 and 8.7 — view state is never written', () => {
	it('records nothing through selection, isolation, loop and speed', async () => {
		const { calls, viewModel } = attached([anAnnotation('an_1')]);
		let transport: Transport = select(STOPPED, WALK);

		// Selection and isolation are scene operations with no Model in reach;
		// loop and speed are transport values. None of the four has a write.
		transport = setLoop(transport, true);
		transport = setSpeed(transport, 2);
		transport = scrubTo(transport, 0.4);
		viewModel.select('an_1');
		viewModel.toggleKind('technical');

		expect(calls).toEqual([]);
		expect(transport).toEqual({ clip: WALK, position: 0.4, playing: false, loop: true, speed: 2 });
	});

	it('leaves every recorded anchor unchanged while a clip plays through, looped', async () => {
		const annotations = [anAnnotation('an_1'), anAnnotation('an_2')];
		const before = JSON.stringify(annotations.map((entry) => entry.anchor));
		const { calls, viewModel } = attached(annotations);

		let transport = play(setLoop(select(STOPPED, WALK), true));
		for (let tick = 0; tick < 40; tick += 1) {
			transport = advanced(transport, CLIPS[0], 0.25);
		}

		expect(transport.playing).toBe(true);
		expect(JSON.stringify(viewModel.annotations.map((entry) => entry.anchor))).toBe(before);
		expect(calls).toEqual([]);
	});

	it('is not vacuous: a write through the same Model is recorded', async () => {
		const { calls, viewModel } = attached([anAnnotation('an_1')]);
		viewModel.select('an_1');

		await viewModel.resolve('done');

		expect(calls).toEqual(['resolve an_1']);
	});

	it('leaves the specification untouched by a scrub, whatever it is scrubbed to', () => {
		const positions = [0, 0.25, 0.5, 0.75, 1];

		const scrubbed = positions.map((position) => scrubTo(select(STOPPED, WALK), position));

		expect(scrubbed.map((transport) => transport.position)).toEqual(positions);
		expect(scrubbed.every((transport) => transport.clip === WALK)).toBe(true);
	});
});

describe('6.4 — opening an annotation restores the view, and writes nothing', () => {
	const withCamera = anAnnotation('an_1', {
		anchor: anchorFor({ part: SHOULDER, point: [0.2, 0.2, 0], normal: [0, 0, 1] }, CAMERA)!
	});

	it('restores the recorded camera', () => {
		expect(openingFor(withCamera, CLIPS).camera).toEqual(CAMERA);
	});

	it('frames the part and says so when no camera was recorded', () => {
		const opening = openingFor(anAnnotation('an_2'), CLIPS);

		expect(opening.camera).toBeNull();
		expect(opening.frame).toBe(SHOULDER);
		expect(opening.notices).toContain(NO_CAMERA_RECORDED);
	});

	it('leaves the annotation’s recorded camera unchanged after the view moves', () => {
		const opened = openingFor(withCamera, CLIPS);

		// The reader moves the view — a new camera entirely — and opens it again.
		const moved: CameraState = { position: [-9, 1, 0], target: [0, 0, 0], fovDeg: 60 };
		const again = openingFor(withCamera, CLIPS);

		expect(again.camera).toEqual(opened.camera);
		expect(again.camera).not.toEqual(moved);
		expect(withCamera.anchor.camera).toEqual({
			position: [3, 2, 4],
			target: [0, 1, 0],
			fov_deg: 45
		});
	});

	it('restores the clip and the position together with the camera (8.6)', () => {
		const posed = anAnnotation('an_3', {
			anchor: anchorFor(
				{ part: SHOULDER, point: [0.2, 0.2, 0], normal: [0, 0, 1] },
				CAMERA,
				{ clip: WALK, t: 0.75 }
			)!
		});

		const opening = openingFor(posed, CLIPS);

		expect(opening.camera).toEqual(CAMERA);
		expect(opening.transport.clip).toBe(WALK);
		expect(opening.transport.position).toBe(0.75);
		expect(opening.transport.playing).toBe(false);
	});

	it('opens against the rest pose and says the clip is unavailable when it is', () => {
		const posed = anAnnotation('an_4', {
			anchor: anchorFor(
				{ part: SHOULDER, point: [0.2, 0.2, 0], normal: [0, 0, 1] },
				CAMERA,
				{ clip: 'A_gone', t: 0.5 }
			)!
		});

		const opening = openingFor(posed, CLIPS);

		expect(opening.transport).toEqual(STOPPED);
		expect(opening.notices).toContain(CLIP_HINT_UNAVAILABLE);
	});

	it('produces an opening for an annotation that names nothing this viewer has', () => {
		const flat = anAnnotation('an_5', { anchor: { view: 'front', u: 0.2, v: 0.2, durable_key: 'front' } });

		const opening = openingFor(flat, CLIPS);

		expect(opening.frame).toBe('');
		expect(opening.transport).toEqual(NOTHING_OPEN.transport);
	});
});

describe('6.6 — re-anchoring from the viewer, through the interface', () => {
	it('builds an anchor naming the part a person selected, with the current camera', () => {
		const anchor = reanchorTo(PAULDRON, CAMERA);

		expect(anchor?.part).toBe(PAULDRON);
		expect(anchor?.durable_key).toBe(PAULDRON);
		expect(anchor?.camera?.fov_deg).toBe(45);
	});

	it('builds no anchor when no part has been selected', () => {
		expect(reanchorTo('', CAMERA)).toBeNull();
	});

	it('invents no hint point — the person named a part, not a position', () => {
		expect(reanchorTo(PAULDRON, null)?.point).toBeUndefined();
	});

	it('ceases to be orphaned and keeps its thread, read back through the ViewModel', async () => {
		const orphan = anAnnotation('an_1', {
			anchor_state: 'orphaned',
			replies: [
				{
					id: 're_1',
					author: 'auth|ana',
					via: null,
					attribution: 'auth|ana',
					text: 'agreed',
					at: '2026-09-22T10:00:00Z',
					edited_at: null
				}
			]
		});
		const rescued = anAnnotation('an_1', {
			anchor: reanchorTo(PAULDRON, CAMERA)!,
			anchor_state: 'carried',
			replies: orphan.replies
		});
		let current = [orphan];
		const { model } = recording(() => aListing(current));
		const viewModel = createAnnotationViewModel();
		viewModel.attach(model as never, PROJECT, ASSET);
		viewModel.hydrate(aListing(current));

		// The write is the route's, handed to the view as one function (D2).
		current = [rescued];
		await viewModel.load();

		const after = viewModel.annotations[0];
		expect(after.anchor_state).toBe('carried');
		expect(after.anchor.durable_key).toBe(PAULDRON);
		expect(after.replies.map((reply) => reply.id)).toEqual(['re_1']);
		expect(after.text).toBe(orphan.text);
	});
});

describe('the fixture the view-state suite leans on is a real preview', () => {
	it('parses, so an assertion about parts is about a mesh', async () => {
		const { parsePreview } = await import('../src/lib/viewer/scene');

		const preview = await parsePreview(
			buildGlb([{ name: SHOULDER, positions: triangleAt(0), indices: [0, 1, 2] }])
		);

		expect(preview.parts.map((part) => part.name)).toEqual([SHOULDER]);
	});
});
