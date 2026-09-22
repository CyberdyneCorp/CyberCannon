/**
 * What the viewer *says*: provenance, counts, absences and clip coverage.
 *
 * All of it is derived from the descriptor and from what the browser managed to
 * load, and none of it decides anything about the canon. The module exists
 * because every one of these sentences is a requirement — *"a count that was
 * never recorded SHALL be shown as unavailable"*, *"the viewer SHALL state that
 * the preview is not derived from the latest validated export"*, *"it SHALL NOT
 * report the asset as having no animation"* — and a sentence assembled inside a
 * component is a sentence no test can read without a DOM.
 *
 * The rule that shapes the counts: **the asset's figures are the source
 * export's**, and the preview's own are labelled as the preview's. *"Nobody
 * should argue about a budget using a number the budget was never measured
 * against."*
 */

import type { AnchorResolutions, ClipCoverage, CoveredState, PreviewDescriptor } from '$lib/api';
import type { Clip } from './clips';

export const UNAVAILABLE = 'unavailable';

/** The three counts, in the order every surface names them. */
export const COUNT_LABELS = {
	triangles: 'Triangles',
	objects: 'Objects',
	materials: 'Materials'
} as const;

export const PREVIEW_COUNT_LABEL = 'Triangles (preview)';
/** What the preview's own figure is called, so it can never read as the asset's. */

export const SUPERSEDED =
	'this preview was made from an export that a newer validated export has since ' +
	'superseded, so what is on screen is not the latest validated export';

export const UNLOADABLE =
	'the preview could not be loaded. Nothing about the asset is missing — its ' +
	'specification and its annotations are below — and the load can be retried';

export const NO_RENDERING =
	'3D display is unavailable on this device, so this asset is shown without its ' +
	'preview. Its imagery, its specification and its annotations — orphans ' +
	'included — are all here and can still be triaged';

export const ANCHOR_UNAVAILABLE =
	'placing a new 3D anchor needs the preview on screen, so it is unavailable here';

export const CONTEXT_LOST =
	'the rendering context was lost and is being restored; the camera and the ' +
	'paused clip position are kept';

export const NO_CLIPS_IN_PREVIEW = 'this preview carries no animation clips';

export const CLIPS_UNAVAILABLE =
	'clips are unavailable for this preview: the export it came from is recorded ' +
	'as carrying animation that this preview does not';

export const NO_CAMERA_RECORDED =
	'no camera was recorded with this annotation, so its part has been framed instead';

export const CLIP_HINT_UNAVAILABLE =
	'the clip this annotation was recorded against is not in this preview, so it ' +
	'is shown on its part in the rest pose';

export const POINT_AT_A_PART = 'a 3D anchor is placed by pointing at a part of the mesh';

export interface Figure {
	readonly label: string;
	readonly value: string;
	/** Whether the figure was recorded. An unrecorded one is stated, never inferred. */
	readonly recorded: boolean;
}

/**
 * The asset's counts — the source export's — and the preview's, labelled apart.
 *
 * `previewTriangles` is what the browser counted in the mesh it loaded, and it
 * is *added* rather than substituted: an unavailable source count stays
 * unavailable, which is the difference between *"we do not know"* and *"4200"*.
 */
export function figuresOf(
	descriptor: PreviewDescriptor,
	previewTriangles: number | null = null
): readonly Figure[] {
	const counts = descriptor.counts;
	const recorded: Figure[] = [
		figure(COUNT_LABELS.triangles, counts.triangles),
		figure(COUNT_LABELS.objects, counts.objects),
		figure(COUNT_LABELS.materials, counts.materials)
	];
	if (previewTriangles === null) return recorded;
	return [...recorded, figure(PREVIEW_COUNT_LABEL, previewTriangles)];
}

function figure(label: string, value: number | null): Figure {
	return value === null
		? { label, value: UNAVAILABLE, recorded: false }
		: { label, value: String(value), recorded: true };
}

/** Which export and which revision are on screen — the provenance line (7.1). */
export interface Provenance {
	readonly export: string;
	readonly revision: string;
	readonly derivedFromLatest: boolean;
	/** The sentence to show when it is not, or `null` when it is. */
	readonly notice: string | null;
}

export function provenanceOf(descriptor: PreviewDescriptor): Provenance {
	const stated = descriptor.source_export ?? descriptor.latest_validated_export ?? '';
	return {
		export: stated,
		revision: descriptor.revision,
		derivedFromLatest: descriptor.derived_from_latest,
		notice: descriptor.preview && !descriptor.derived_from_latest ? SUPERSEDED : null
	};
}

/**
 * Why there is nothing to render, in the words the use case chose.
 *
 * The reason travels from the server rather than being reconstructed here, so
 * the asset page, the viewer and an agent reading the same descriptor all give
 * the same account of the same asset.
 */
export function absenceOf(descriptor: PreviewDescriptor): string | null {
	return descriptor.preview ? null : (descriptor.reason ?? 'no preview is available');
}

/** What the viewer can be doing. A closed set, so a screen cannot invent a state. */
export const VIEWER_STATES = ['loading', 'ready', 'unloadable', 'absent', 'degraded'] as const;
export type ViewerState = (typeof VIEWER_STATES)[number];

/** One clip as the transport lists it, with the state it satisfies (D8). */
export interface ClipRow {
	readonly name: string;
	readonly duration: number;
	/** The declared state this clip satisfies, or an empty string for none. */
	readonly state: string;
}

/**
 * The clips this preview carries, each labelled with the state it satisfies.
 *
 * The mapping is the specification's, consumed verbatim (D8): a clip whose name
 * matches a declared state's required clip exactly satisfies it, and one that
 * does not is listed and labelled as satisfying no declared state. No case
 * folding, no similarity — a clip named one character off shows as a state with
 * no clip beside an unclaimed clip, which is the report a modeller can act on.
 */
export function clipRows(coverage: ClipCoverage, clips: readonly Clip[]): readonly ClipRow[] {
	const byClip = new Map(
		coverage.states
			.filter((entry) => entry.coverage === 'satisfied' && entry.clip)
			.map((entry) => [entry.clip as string, entry.state])
	);
	return clips.map((clip) => ({
		name: clip.name,
		duration: clip.duration,
		state: byClip.get(clip.name) ?? ''
	}));
}

/** Every declared state, in declaration order, gap included (`animation-playback`). */
export function stateRows(coverage: ClipCoverage): readonly CoveredState[] {
	return coverage.states;
}

/**
 * What to say about an absence of clips — and the two absences are different.
 *
 * *"When an asset's export is recorded as carrying animation clips but the
 * preview displayed carries none, the viewer SHALL state that clips are
 * unavailable for this preview. It SHALL NOT state that the asset has no
 * animation."*
 */
export function clipAbsence(
	descriptor: PreviewDescriptor,
	loaded: readonly Clip[]
): string | null {
	if (loaded.length > 0) return null;
	return descriptor.clips.length > 0 ? CLIPS_UNAVAILABLE : NO_CLIPS_IN_PREVIEW;
}

/** Whether a transport may be offered at all — one that cannot act is not offered. */
export function transportAvailable(loaded: readonly Clip[]): boolean {
	return loaded.length > 0;
}

/**
 * How many annotations are orphaned on this export, from the read that has no GPU.
 *
 * The viewer shows the *server's* count rather than its own, because D6 puts
 * that answer where the asset page and the agent surface can also read it — and
 * two counts of the same thing is exactly the drift D6 exists to prevent. The
 * viewer's own resolution against the loaded mesh adds the *placement*, not the
 * count.
 */
export function orphanCount(resolutions: AnchorResolutions | null): number {
	return resolutions?.orphaned ?? 0;
}

export function partialAmong(resolutions: AnchorResolutions | null): readonly string[] {
	return (resolutions?.resolutions ?? [])
		.filter((row) => row.outcome === 'partial')
		.map((row) => row.id);
}
