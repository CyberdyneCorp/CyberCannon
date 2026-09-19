/**
 * D7 — the 3D engine lives here, and here is reached by dynamic import only.
 *
 * *"A person browsing an asset list should not download a 3D engine."* That is
 * a decision rather than an optimisation because it constrains **where this
 * module may be imported from**: nothing may name it in a static `import`, so
 * the bundler puts it in a chunk of its own and the browser route never asks
 * for that chunk. `tests/tooling/test_web_structure.py` fails the build when
 * something imports it statically, and `tests/e2e` asserts the built browser
 * bundle does not contain it.
 *
 * The scene itself belongs to `add-viewer-3d`. What is here is the boundary and
 * the smallest thing that makes it real: a module that genuinely costs what a
 * 3D engine costs, so the split is measurable rather than asserted.
 */

import { PerspectiveCamera, Scene, WebGLRenderer } from 'three';

export interface MountedScene {
	readonly scene: Scene;
	readonly camera: PerspectiveCamera;
	dispose(): void;
}

/** Put a scene on a canvas. `add-viewer-3d` fills it; this only proves the split. */
export function mountScene(canvas: HTMLCanvasElement): MountedScene {
	const scene = new Scene();
	const camera = new PerspectiveCamera(50, canvas.clientWidth / canvas.clientHeight || 1, 0.1, 1000);
	camera.position.set(0, 0, 3);
	const renderer = new WebGLRenderer({ canvas, antialias: true });
	renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
	renderer.render(scene, camera);
	return {
		scene,
		camera,
		dispose() {
			renderer.dispose();
		}
	};
}
