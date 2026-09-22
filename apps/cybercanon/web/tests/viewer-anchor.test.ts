/**
 * D3, D9 and D10 — what a pick becomes, and everything it deliberately is not.
 *
 * Three prohibitions are checked here rather than described, and each is
 * structural in the type as well: a pick carries no face index, an anchor
 * carries no frame number, and the point an anchor records is the **rest pose**
 * of the surface picked, whatever the model was doing at the time.
 *
 * The rest-pose narrowing runs against real `three.js` objects with no renderer
 * anywhere — a `Mesh`, a `Raycaster` and a `Vector3` all work in node, and only
 * the drawing needs a GPU.
 */

import { describe, expect, it } from 'vitest';
import {
	Bone,
	BufferAttribute,
	BufferGeometry,
	Matrix4,
	Mesh,
	Raycaster,
	Skeleton,
	SkinnedMesh,
	Uint16BufferAttribute,
	Vector3
} from 'three';
import { anchorFor, carriesTopology, cameraFrom, cameraPayload, playbackOf } from '../src/lib/viewer/anchor';
import type { CameraState, Pick } from '../src/lib/viewer/anchor';
import type { Anchor } from '../src/lib/api';

const SHOULDER = 'SM_MechScout_Shoulder_L';
const WALK = 'A_mech_scout_walk';

const CAMERA: CameraState = { position: [3, 2, 4], target: [0, 1, 0], fovDeg: 45 };

const HIT: Pick = { part: SHOULDER, point: [0.2, 0.3, 0], normal: [0, 0, 1] };

/** One triangle in the z=0 plane, as a mesh a raycaster can actually hit. */
function aPlate(name: string): Mesh {
	const geometry = new BufferGeometry();
	geometry.setAttribute(
		'position',
		new BufferAttribute(Float32Array.from([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3)
	);
	geometry.setIndex([0, 1, 2]);
	geometry.computeVertexNormals();
	const mesh = new Mesh(geometry);
	mesh.name = name;
	return mesh;
}

async function narrow(mesh: Mesh, from: Vector3) {
	const { narrowedHit } = await import('../src/lib/viewer/scene');
	mesh.updateMatrixWorld(true);
	const raycaster = new Raycaster(from, new Vector3(0, 0, -1).normalize());
	const [hit] = raycaster.intersectObject(mesh, true);
	expect(hit, 'the fixture ray must actually hit the plate').toBeTruthy();
	return narrowedHit(hit);
}

describe('4.4 — a pick is narrowed to a name and a point', () => {
	it('returns the picked part’s name and nothing about topology', async () => {
		const found = await narrow(aPlate(SHOULDER), new Vector3(0.2, 0.2, 5));

		expect(found?.part).toBe(SHOULDER);
		expect(Object.keys(found ?? {}).sort()).toEqual(['normal', 'part', 'point']);
	});

	it('carries no face index and no barycentric weights', async () => {
		const found = await narrow(aPlate(SHOULDER), new Vector3(0.2, 0.2, 5));

		expect(carriesTopology(found ?? {})).toBe(false);
	});

	it('is not vacuous: a value with a face index is recognised as one', () => {
		expect(carriesTopology({ part: SHOULDER, faceIndex: 17 })).toBe(true);
	});

	it('creates no anchor for a placement that landed on nothing', () => {
		expect(anchorFor(null, CAMERA)).toBeNull();
	});

	it('creates no anchor for a hit that names no part', () => {
		expect(anchorFor({ ...HIT, part: '' }, CAMERA)).toBeNull();
	});
});

describe('5.3 — the recorded point is the rest pose, whatever the pose was', () => {
	it('records the same point for a part posed away from its rest position', async () => {
		const atRest = aPlate(SHOULDER);
		const posed = aPlate(SHOULDER);
		posed.position.set(0, 4, 0);

		const first = await narrow(atRest, new Vector3(0.2, 0.2, 5));
		const second = await narrow(posed, new Vector3(0.2, 4.2, 5));

		expect(second?.point[0]).toBeCloseTo(first?.point[0] ?? NaN);
		expect(second?.point[1]).toBeCloseTo(first?.point[1] ?? NaN);
		expect(second?.point[2]).toBeCloseTo(first?.point[2] ?? NaN);
	});

	it('records the same normal for both', async () => {
		const atRest = aPlate(SHOULDER);
		const posed = aPlate(SHOULDER);
		posed.position.set(0, 4, 0);

		const first = await narrow(atRest, new Vector3(0.2, 0.2, 5));
		const second = await narrow(posed, new Vector3(0.2, 4.2, 5));

		expect(second?.normal).toEqual(first?.normal);
	});

	it('records the point in the part’s own space, not the world’s', async () => {
		const posed = aPlate(SHOULDER);
		posed.position.set(10, 0, 0);

		const found = await narrow(posed, new Vector3(10.2, 0.2, 5));

		expect(found?.point[0]).toBeCloseTo(0.2);
	});
});

describe('the anchor a placement produces', () => {
	it('records the part, the hints and the camera', () => {
		const anchor = anchorFor(HIT, CAMERA) as Anchor;

		expect(anchor.part).toBe(SHOULDER);
		expect(anchor.durable_key).toBe(SHOULDER);
		expect(anchor.point).toEqual([0.2, 0.3, 0]);
		expect(anchor.camera).toEqual({ position: [3, 2, 4], target: [0, 1, 0], fov_deg: 45 });
	});

	it('records the clip and a position as a proportion, never a frame (D9)', () => {
		const anchor = anchorFor(HIT, CAMERA, { clip: WALK, t: 0.5 }) as Anchor;

		expect(anchor.clip).toBe(WALK);
		expect(anchor.t).toBe(0.5);
		expect(Object.keys(anchor)).not.toContain('frame');
	});

	it('refuses a position that is not a proportion', () => {
		expect(anchorFor(HIT, CAMERA, { clip: WALK, t: 24 })).toBeNull();
	});

	it('records no playback hint when no clip is selected', () => {
		const anchor = anchorFor(HIT, CAMERA) as Anchor;

		expect(anchor.clip).toBeUndefined();
		expect(playbackOf(anchor)).toBeNull();
	});

	it('reads back the playback hint it recorded', () => {
		const anchor = anchorFor(HIT, CAMERA, { clip: WALK, t: 0.75 }) as Anchor;

		expect(playbackOf(anchor)).toEqual({ clip: WALK, t: 0.75 });
	});

	it('records no camera when the viewer could not state one', () => {
		const anchor = anchorFor(HIT, null) as Anchor;

		expect(anchor.camera).toBeUndefined();
	});
});

describe('the camera round trip', () => {
	it('survives being written and read back', () => {
		expect(cameraFrom(cameraPayload(CAMERA))).toEqual(CAMERA);
	});

	it('answers nothing for an annotation that recorded none', () => {
		expect(cameraFrom(undefined)).toBeNull();
	});

	it('answers nothing for a half-written camera rather than guessing', () => {
		expect(cameraFrom({ position: [1, 2, 3], target: [], fov_deg: 45 })).toBeNull();
	});
});


describe('D10 — the inversion that makes a skinned pose leave the hint alone', () => {
	/**
	 * The same plate, skinned to one bone, so a pose is a real deformation
	 * rather than a node translation. `three.js` raycasts a `SkinnedMesh`
	 * against the posed vertices, so this is the case the bind-pose weights
	 * would have got wrong.
	 */
	function aSkinnedPlate(name: string): SkinnedMesh {
		const geometry = new BufferGeometry();
		geometry.setAttribute(
			'position',
			new BufferAttribute(Float32Array.from([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3)
		);
		geometry.setIndex([0, 1, 2]);
		geometry.setAttribute('skinIndex', new Uint16BufferAttribute([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 4));
		geometry.setAttribute(
			'skinWeight',
			new BufferAttribute(Float32Array.from([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]), 4)
		);
		const bone = new Bone();
		const mesh = new SkinnedMesh(geometry, undefined);
		mesh.name = name;
		mesh.add(bone);
		mesh.bind(new Skeleton([bone], [new Matrix4()]));
		return mesh;
	}

	async function narrowSkinned(mesh: SkinnedMesh, from: Vector3) {
		const { narrowedHit } = await import('../src/lib/viewer/scene');
		mesh.updateMatrixWorld(true);
		const raycaster = new Raycaster(from, new Vector3(0, 0, -1).normalize());
		const [hit] = raycaster.intersectObject(mesh, true);
		expect(hit, 'the fixture ray must hit the skinned plate').toBeTruthy();
		return narrowedHit(hit);
	}

	it('records the rest-pose point for a plate its bone has displaced', async () => {
		const atRest = aSkinnedPlate(SHOULDER);
		const posed = aSkinnedPlate(SHOULDER);
		// The bone moves the whole plate two units along y — the deformation the
		// ray sees and the bind pose does not.
		posed.skeleton.bones[0].position.set(0, 2, 0);
		posed.skeleton.bones[0].updateMatrixWorld(true);
		posed.skeleton.update();

		const rest = await narrowSkinned(atRest, new Vector3(0.2, 0.2, 5));
		const moved = await narrowSkinned(posed, new Vector3(0.2, 2.2, 5));

		expect(moved?.point[0]).toBeCloseTo(rest?.point[0] ?? NaN, 4);
		expect(moved?.point[1]).toBeCloseTo(rest?.point[1] ?? NaN, 4);
		expect(moved?.point[2]).toBeCloseTo(rest?.point[2] ?? NaN, 4);
	});

	it('records the bind-pose normal, not the posed one', async () => {
		const posed = aSkinnedPlate(SHOULDER);
		posed.skeleton.bones[0].position.set(0, 2, 0);
		posed.skeleton.bones[0].updateMatrixWorld(true);
		posed.skeleton.update();

		const found = await narrowSkinned(posed, new Vector3(0.2, 2.2, 5));

		expect(found?.normal).toEqual([0, 0, 1]);
	});
});
