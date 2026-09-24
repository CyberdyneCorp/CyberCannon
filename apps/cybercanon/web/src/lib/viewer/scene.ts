/**
 * D1 — the one module that owns a `three.js` scene, reached by dynamic import.
 *
 * *"A person browsing an asset list should not download a 3D engine."* That is
 * a decision rather than an optimisation because it constrains **where this
 * module may be imported from**: nothing may name it in a static `import`, so
 * the bundler puts it in a chunk of its own and the browser route never asks
 * for that chunk. `tests/tooling/test_web_structure.py` fails the build when
 * something imports it statically, and `tests/e2e` asserts the built browser
 * bundle does not contain it.
 *
 * Everything else — the Svelte components, the shared `AnnotationViewModel` —
 * talks to a scene through :type:`Viewer3DScene` and nothing else. The decisions
 * that matter are all *outside* this module, in plain arithmetic
 * (`$lib/viewer/geometry`, `framing`, `resolution`, `clips`), so that the only
 * thing needing a GPU to check is the drawing.
 *
 * **Two boundaries this module exists to hold.**
 *
 * * **D3 — topology is discarded here.** A raycast returns an intersection
 *   carrying the object, the face index, the barycentric weights and a world
 *   point. :meth:`pick` returns the object's *name* and a point, and there is
 *   nowhere in the returned value for anything else. The face index is used and
 *   thrown away inside one function.
 * * **D10 — the pose never touches the stored hint.** The point a pick returns
 *   is the **rest-pose** local coordinate of the picked surface: the hit's
 *   barycentric weights are applied to the part's bind-pose positions, so the
 *   same physical spot annotated at rest and mid-clip produces the same anchor.
 */

import {
	AmbientLight,
	AnimationMixer,
	Box3,
	Color,
	DirectionalLight,
	Mesh,
	PerspectiveCamera,
	Raycaster,
	Scene,
	SkinnedMesh,
	Vector2,
	Vector3,
	WebGLRenderer,
	type AnimationAction,
	type AnimationClip,
	type BufferGeometry,
	type Object3D
} from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { Anchor } from '$lib/api';
import type { CameraState, Pick } from './anchor';
import type { Clip } from './clips';
import type { Bounds, PartGeometry, Vec3 } from './geometry';
import { boundsOf, union } from './geometry';
import { clipPlanes, frameCamera, reframe } from './framing';
import type { LoadedMesh, Resolution } from './resolution';
import { resolverFor } from './resolution';

/** Whatever shape the position attribute is stored in — read, never written. */
type Positions = ReturnType<BufferGeometry['getAttribute']>;

/** What one loaded preview turned out to be — names, geometry, clips and size. */
export interface LoadedPreview {
	readonly parts: readonly PartGeometry[];
	readonly bones: readonly string[];
	readonly clips: readonly Clip[];
	readonly triangles: number;
	readonly primitives: number;
	readonly normalPrimitives: number;
	readonly bounds: Bounds;
}

export function partNamesOf(preview: LoadedPreview): readonly string[] {
	return preview.parts.map((part) => part.name);
}

/**
 * Parse a preview's bytes into names, geometry and clips — with no renderer.
 *
 * Separate from :func:`mountScene` on purpose: *what a preview contains* is
 * answerable headlessly, and a suite that needed a GPU to ask would be a suite
 * that never runs in `just check`. `GLTFLoader.parse` is used rather than
 * `load`, so nothing here fetches anything.
 */
export function parsePreview(bytes: ArrayBuffer): Promise<LoadedPreview> {
	return new Promise((resolve, reject) => {
		previewLoader().parse(
			bytes,
			'',
			(gltf) => resolve(describe(gltf.scene, gltf.animations ?? [])),
			(error) => reject(error)
		);
	});
}

const draco = new DRACOLoader().setDecoderPath('/draco/');

function previewLoader(): GLTFLoader {
	return new GLTFLoader().setDRACOLoader(draco);
}

function describe(root: Object3D, animations: readonly AnimationClip[]): LoadedPreview {
	const parts: PartGeometry[] = [];
	const bones: string[] = [];
	let triangles = 0;
	let normalPrimitives = 0;
	root.updateMatrixWorld(true);
	root.traverse((node) => {
		if (node.type === 'Bone') bones.push(node.name);
		const mesh = node as Mesh;
		if (!mesh.isMesh || !mesh.geometry) return;
		const part = geometryOf(mesh);
		if (mesh.geometry.getAttribute('normal')) normalPrimitives += 1;
		triangles += Math.floor(part.indices.length / 3);
		parts.push(part);
	});
	return {
		parts,
		bones,
		clips: animations.map((clip) => ({ name: clip.name, duration: clip.duration })),
		triangles,
		primitives: parts.length,
		normalPrimitives,
		bounds: boundsOfParts(parts)
	};
}

/**
 * One mesh's rest-pose geometry, in its own local space (D4, D10).
 *
 * The position attribute of a glTF mesh is its bind pose, which is exactly the
 * space `Anchor3D` records a hint in — so nothing is transformed here, and that
 * absence is the requirement rather than an omission.
 */
function geometryOf(mesh: Mesh): PartGeometry {
	const geometry = mesh.geometry as BufferGeometry;
	const positions = geometry.getAttribute('position');
	const indexed = geometry.getIndex();
	const count = positions ? positions.count : 0;
	return {
		name: mesh.name,
		positions: positions ? (positions.array as ArrayLike<number>) : [],
		indices: indexed
			? (indexed.array as ArrayLike<number>)
			: Array.from({ length: count }, (_, index) => index)
	};
}

function boundsOfParts(parts: readonly PartGeometry[]): Bounds {
	if (parts.length === 0) return boundsOf([]);
	return parts.map((part) => boundsOf(part.positions)).reduce(union);
}

/**
 * The interface everything outside this module uses (D1).
 *
 * Five verbs the design names — `load`, `pick`, `resolve`, `applyCamera`,
 * `playClip` — plus the view state D12 keeps out of the specification:
 * selection, isolation and framing.
 */
export interface Viewer3DScene {
	load(bytes: ArrayBuffer): Promise<LoadedPreview>;
	pick(x: number, y: number): Pick | null;
	resolve(anchor: Anchor): Resolution;
	applyCamera(camera: CameraState): void;
	camera(): CameraState;
	playClip(name: string, t: number): void;
	frameAll(): void;
	frameSelected(): void;
	zoomIn(): void;
	zoomOut(): void;
	select(part: string | null): void;
	selected(): string | null;
	isolate(part: string | null): void;
	restore(): void;
	isolated(): string | null;
	loaded(): LoadedPreview | null;
	render(): void;
	dispose(): void;
}

const BACKGROUND = 0x14161a;

/**
 * Put a viewer on a canvas.
 *
 * The scene holds one loaded preview at a time. `sourceParts` is what the
 * *export* recorded, so a part the preview dropped is reported as a preview
 * limitation rather than as removed from the asset (`anchor-resolution`).
 */
export function mountScene(
	canvas: HTMLCanvasElement,
	sourceParts: readonly string[] = []
): Viewer3DScene {
	const scene = new Scene();
	scene.background = new Color(BACKGROUND);
	scene.add(new AmbientLight(0xffffff, 1.6));
	const key = new DirectionalLight(0xffffff, 1.4);
	key.position.set(3, 5, 4);
	scene.add(key);

	const camera = new PerspectiveCamera(45, aspectOf(canvas), 0.01, 1000);
	camera.position.set(2, 1.5, 3);
	const renderer = new WebGLRenderer({ canvas, antialias: true });
	renderer.setSize(canvas.clientWidth || 1, canvas.clientHeight || 1, false);

	// Orbit, pan and zoom, against the library's controls rather than inherited
	// from a higher-level widget — D1 accepts that cost in so many words. Damping
	// is off deliberately: a camera that keeps moving after the pointer stops is
	// a camera an annotation cannot be recorded against reproducibly, and
	// `Anchor3D` records the camera.
	const controls = new OrbitControls(camera, canvas);
	controls.enableDamping = false;
	controls.enableRotate = true;
	controls.enablePan = true;
	controls.enableZoom = true;
	const draw = () => {
		renderer.setSize(canvas.clientWidth || 1, canvas.clientHeight || 1, false);
		camera.aspect = aspectOf(canvas);
		camera.updateProjectionMatrix();
		renderer.render(scene, camera);
	};
	controls.addEventListener('change', draw);
	const resize = new ResizeObserver(draw);
	resize.observe(canvas);

	const state: SceneState = {
		root: null,
		preview: null,
		resolve: null,
		selected: null,
		isolated: null,
		mixer: null,
		action: null,
		clips: [],
		target: controls.target
	};
	const raycaster = new Raycaster();

	return {
		async load(bytes) {
			const loaded = await parsePreview(bytes);
			const gltf = await new Promise<Object3D>((done, fail) => {
				previewLoader().parse(
					bytes,
					'',
					(parsed) => {
						state.clips = parsed.animations ?? [];
						done(parsed.scene);
					},
					fail
				);
			});
			if (state.root) scene.remove(state.root);
			state.root = gltf;
			state.preview = loaded;
			state.resolve = resolverFor(meshOf(loaded), sourceParts);
			state.mixer = new AnimationMixer(gltf);
			scene.add(gltf);
			applyCamera(camera, state, frameCamera(loaded.bounds, { aspect: aspectOf(canvas) }));
			const planes = clipPlanes(loaded.bounds);
			camera.near = planes.near;
			camera.far = planes.far;
			camera.updateProjectionMatrix();
			return loaded;
		},

		pick(x, y) {
			if (state.root === null) return null;
			raycaster.setFromCamera(new Vector2(x, y), camera);
			const hits = raycaster.intersectObject(state.root, true);
			const hit = firstVisible(hits);
			return hit ? narrowedHit(hit) : null;
		},

		resolve(anchor) {
			if (state.resolve === null) {
				return resolverFor({ parts: [], bones: null }, sourceParts)(anchor);
			}
			return state.resolve(anchor);
		},

		applyCamera(wanted) {
			applyCamera(camera, state, wanted);
		},

		camera() {
			return currentCamera(camera, state);
		},

		playClip(name, t) {
			hold(state, name, t);
		},

		frameAll() {
			if (state.preview === null) return;
			applyCamera(
				camera,
				state,
				reframe(state.preview.bounds, currentCamera(camera, state), aspectOf(canvas))
			);
		},

		frameSelected() {
			const part = state.selected;
			const found = state.preview?.parts.find((entry) => entry.name === part);
			if (!found) return;
			applyCamera(
				camera,
				state,
				reframe(boundsOf(found.positions), currentCamera(camera, state), aspectOf(canvas))
			);
		},

		zoomIn() {
			zoom(camera, controls.target, controls, 0.8);
		},

		zoomOut() {
			zoom(camera, controls.target, controls, 1.25);
		},

		select(part) {
			state.selected = part;
		},

		selected() {
			return state.selected;
		},

		isolate(part) {
			state.isolated = part;
			showOnly(state.root, part);
		},

		restore() {
			state.isolated = null;
			showOnly(state.root, null);
		},

		isolated() {
			return state.isolated;
		},

		loaded() {
			return state.preview;
		},

		render() {
			controls.update();
			draw();
		},

		dispose() {
			state.mixer?.stopAllAction();
			resize.disconnect();
			controls.removeEventListener('change', draw);
			controls.dispose();
			renderer.dispose();
		}
	};
}

function zoom(camera: PerspectiveCamera, target: Vector3, controls: OrbitControls, factor: number): void {
	camera.position.sub(target).multiplyScalar(factor).add(target);
	controls.update();
}

interface SceneState {
	root: Object3D | null;
	preview: LoadedPreview | null;
	resolve: ((anchor: Anchor) => Resolution) | null;
	selected: string | null;
	isolated: string | null;
	mixer: AnimationMixer | null;
	action: AnimationAction | null;
	clips: readonly AnimationClip[];
	target: Vector3;
}

function aspectOf(canvas: HTMLCanvasElement): number {
	const width = canvas.clientWidth || canvas.width || 1;
	const height = canvas.clientHeight || canvas.height || 1;
	return width / height;
}

function meshOf(preview: LoadedPreview): LoadedMesh {
	return { parts: preview.parts, bones: preview.bones };
}

/**
 * Put the camera exactly where a caller asked, controls included.
 *
 * `state.target` *is* the controls' target — the same `Vector3` — so a restored
 * camera is a camera the next orbit turns around, rather than one the controls
 * snap away from on the first drag.
 */
function applyCamera(camera: PerspectiveCamera, state: SceneState, wanted: CameraState): void {
	camera.position.set(...wanted.position);
	state.target.set(...wanted.target);
	camera.lookAt(state.target);
	camera.fov = wanted.fovDeg;
	camera.updateProjectionMatrix();
}

function currentCamera(camera: PerspectiveCamera, state: SceneState): CameraState {
	return {
		position: [camera.position.x, camera.position.y, camera.position.z],
		target: [state.target.x, state.target.y, state.target.z],
		fovDeg: camera.fov
	};
}

/**
 * Hold a clip at a position, paused — the only way this module plays anything.
 *
 * Deterministic by construction: the mixer is set to an absolute time derived
 * from the proportion, never advanced by a delta, so *"scrubbed to a given
 * position twice from different starting points"* is two identical poses.
 */
function hold(state: SceneState, name: string, t: number): void {
	const clip = state.clips.find((entry) => entry.name === name);
	if (state.mixer === null || !clip) return;
	if (state.action?.getClip() !== clip) {
		state.mixer.stopAllAction();
		state.action = state.mixer.clipAction(clip);
		state.action.play();
	}
	state.action.paused = true;
	state.action.time = Math.min(Math.max(t, 0), 1) * clip.duration;
	state.mixer.setTime(state.action.time);
}

/**
 * The first hit a person can actually see, or nothing at all.
 *
 * *"A placement on a hidden or isolated-away part SHALL NOT be recorded."* An
 * isolated-away part is still in the scene and a ray still passes through it,
 * so the filter is what makes that requirement true — and it is exported so it
 * can be checked without a renderer, since visibility is a property of a graph
 * rather than of a drawing.
 */
export function firstVisible<T extends { object: Object3D }>(hits: readonly T[]): T | undefined {
	return hits.find((entry) => visible(entry.object));
}

function visible(object: Object3D): boolean {
	let node: Object3D | null = object;
	while (node) {
		if (!node.visible) return false;
		node = node.parent;
	}
	return true;
}

function showOnly(root: Object3D | null, part: string | null): void {
	root?.traverse((node) => {
		const mesh = node as Mesh;
		if (mesh.isMesh) mesh.visible = part === null || mesh.name === part;
	});
}

/**
 * D3 and D10, in one function: the hit narrowed to a name and a rest-pose point.
 *
 * The face index and the barycentric weights exist for the few lines that need
 * them and reach nothing else. The returned object has three members, and
 * `tests/viewer-anchor.test.ts` asserts that set — a shape that could carry a
 * triangle index is the shape somebody persists.
 *
 * **The weights come from the *posed* triangle and are applied to the *bind*
 * one.** That is D10's inversion and it is the whole of it: a raycast against a
 * skinned mesh hits the triangle as the current frame deforms it, so weights
 * taken against the bind-pose corners would be weights of a different triangle
 * and the recorded point would drift with the pose. Taking them where the ray
 * landed and spending them where the anchor is stored is what makes *"the same
 * surface location annotated at rest and mid-clip"* one anchor.
 *
 * Exported so the narrowing can be checked without a renderer: a `Mesh`, a
 * `SkinnedMesh`, a `Raycaster` and a `Vector3` all work with no canvas, and
 * only the drawing needs a GPU.
 */
export function narrowedHit(hit: {
	object: Object3D;
	point: Vector3;
	face?: { a: number; b: number; c: number } | null;
}): Pick | null {
	const mesh = hit.object as Mesh;
	if (!mesh.isMesh || !hit.face) return null;
	const positions = (mesh.geometry as BufferGeometry).getAttribute('position');
	if (!positions) return null;
	const indices = [hit.face.a, hit.face.b, hit.face.c];
	const rest = indices.map((index) => new Vector3().fromBufferAttribute(positions, index));
	const posed = indices.map((index) => posedCorner(mesh, positions, index));
	const local = mesh.worldToLocal(hit.point.clone());
	const weights = barycentric(local, posed[0], posed[1], posed[2]);
	const point = rest[0]
		.clone()
		.multiplyScalar(weights[0])
		.addScaledVector(rest[1], weights[1])
		.addScaledVector(rest[2], weights[2]);
	const normal = new Vector3()
		.subVectors(rest[1], rest[0])
		.cross(new Vector3().subVectors(rest[2], rest[0]))
		.normalize();
	return {
		part: mesh.name,
		point: [point.x, point.y, point.z] as Vec3,
		normal: [normal.x, normal.y, normal.z] as Vec3
	};
}

/**
 * One vertex where this frame puts it, in the mesh's local space.
 *
 * For an unskinned mesh that is the bind position unchanged, which is why the
 * ordinary case costs nothing; for a skinned one it is the bone transform
 * `three.js` itself applies when it raycasts, so the two agree by using the
 * same function.
 */
function posedCorner(mesh: Mesh, positions: Positions, index: number): Vector3 {
	const vertex = new Vector3().fromBufferAttribute(positions, index);
	const skinned = mesh as SkinnedMesh;
	return skinned.isSkinnedMesh ? skinned.applyBoneTransform(index, vertex) : vertex;
}

/** The weights of a point within a triangle. Used, then discarded, right here. */
function barycentric(
	point: Vector3,
	a: Vector3,
	b: Vector3,
	c: Vector3
): [number, number, number] {
	const v0 = new Vector3().subVectors(b, a);
	const v1 = new Vector3().subVectors(c, a);
	const v2 = new Vector3().subVectors(point, a);
	const d00 = v0.dot(v0);
	const d01 = v0.dot(v1);
	const d11 = v1.dot(v1);
	const d20 = v2.dot(v0);
	const d21 = v2.dot(v1);
	const denominator = d00 * d11 - d01 * d01;
	if (denominator === 0) return [1, 0, 0];
	const v = (d11 * d20 - d01 * d21) / denominator;
	const w = (d00 * d21 - d01 * d20) / denominator;
	return [1 - v - w, v, w];
}

/** The bounding box of a loaded scene, for a caller that has an `Object3D`. */
export function boundsOfObject(object: Object3D): Bounds {
	const box = new Box3().setFromObject(object);
	return {
		min: [box.min.x, box.min.y, box.min.z],
		max: [box.max.x, box.max.y, box.max.z]
	};
}
