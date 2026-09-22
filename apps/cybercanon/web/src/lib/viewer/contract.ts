/**
 * D1's interface, written down where a component may import it.
 *
 * *"Everything else — Svelte components, the ViewModel — talks to it through a
 * small interface (`load(url)`, `pick(x, y) -> partName | null`,
 * `resolve(anchor) -> Resolution`, `applyCamera(camera)`, `playClip(name, t)`)."*
 *
 * The interface lives here and the implementation lives in `$lib/viewer/scene`,
 * and the separation is what makes D7 and D2 hold at once: a component names
 * *this* module statically, so it carries no `three.js`, and the engine arrives
 * as a value at run time. It is also what lets every requirement about the
 * viewer's behaviour — provenance, counts, orphans, transport, degradation — be
 * exercised against a scene that is an ordinary object.
 */

import type { Anchor } from '$lib/api';
import type { CameraState, Pick } from './anchor';
import type { Clip } from './clips';
import type { Resolution } from './resolution';

/** What a loaded preview turned out to hold, as a component needs to know it. */
export interface LoadedSummary {
	readonly clips: readonly Clip[];
	readonly triangles: number;
	readonly parts: readonly { readonly name: string }[];
}

export interface SceneLike {
	load(bytes: ArrayBuffer): Promise<LoadedSummary>;
	/** The part under the pointer and the rest-pose point on it, or nothing (D3). */
	pick(x: number, y: number): Pick | null;
	resolve(anchor: Anchor): Resolution;
	applyCamera(camera: CameraState): void;
	camera(): CameraState;
	/** Hold a clip paused at a proportion of its duration (D9). */
	playClip(name: string, t: number): void;
	frameAll(): void;
	frameSelected(): void;
	select(part: string | null): void;
	isolate(part: string | null): void;
	restore(): void;
	render(): void;
	dispose(): void;
}

/** How a scene is built. Handed to a component so the engine stays lazy (D7). */
export type SceneFactory = (
	canvas: HTMLCanvasElement,
	sourceParts: readonly string[]
) => SceneLike;
