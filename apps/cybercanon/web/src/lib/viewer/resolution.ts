/**
 * A stored anchor against a loaded mesh: the name decides, the geometry follows.
 *
 * This module is the browser half of D6. The Python domain answers *is this
 * anchor's part present in this export* with no renderer, and this answers
 * *where on that part does the pin go* with one — and the two agree on the
 * three outcomes by using the same words, because a viewer that called
 * something orphaned that the asset page called carried would be two opinions
 * about the same annotation.
 *
 * Three rules, each of them a requirement rather than a preference:
 *
 * * **the named part is the identity.** The hint never participates in deciding
 *   whether an anchor resolves, so an anchor whose recorded point now lies well
 *   away from the surface still resolves (`anchor-resolution`);
 * * **the placement is confined to the named part.** Another part's surface is
 *   not a candidate, at any distance;
 * * **displacement is measured and shown, never absorbed** (D5). Above a
 *   configured proportion of the part's bounding size the annotation is
 *   *possibly displaced* and says how far. Orphaning on a large displacement
 *   was rejected: it throws away a still-valid part reference because geometry
 *   changed, which is the brittleness the dual anchor exists to avoid.
 */

import type { Anchor } from '$lib/api';
import type { PartGeometry, Vec3 } from './geometry';
import { PartIndex, accelerate, distance } from './geometry';

/** The three outcomes, spelled exactly as `cybercanon.domain.anchor_resolution` spells them. */
export type Outcome = 'resolved' | 'partial' | 'orphaned';

export const NO_SUCH_PART = 'the mesh part it was anchored to is no longer in the export';
export const NO_SUCH_BONE =
	'the bone it named is not in this export, so it is placed on its part alone';
export const NOT_IN_PREVIEW =
	'this part is in the validated export but not in its preview, so it cannot be shown here';
export const NO_GEOMETRY = 'this part carries no geometry in the preview, so it cannot be placed';

/**
 * D5's threshold: how far a re-projection may move a pin before it is flagged.
 *
 * A proportion of the part's bounding-box diagonal, so it means the same thing
 * on a rivet and on a hull. It is configuration rather than a specified value —
 * `add-viewer-3d`'s open question calls for one calibration pass against a real
 * retopologised asset — and it lives here so that tuning it touches no
 * specification.
 */
export const DISPLACEMENT_THRESHOLD = 0.08;

export interface Displacement {
	readonly distance: number;
	readonly proportion: number;
	readonly possiblyDisplaced: boolean;
}

/** One anchor's standing against one loaded mesh, name first and geometry second. */
export interface Resolution {
	readonly outcome: Outcome;
	readonly part: string;
	readonly bone: string;
	readonly reason: string;
	/** Where the pin goes, in the part's local space, or `null` when it goes nowhere. */
	readonly point: Vec3 | null;
	readonly normal: Vec3 | null;
	readonly displacement: Displacement | null;
	/**
	 * Whether the part is absent from the *preview* while the export still has it.
	 *
	 * `anchor-resolution` requires this to be *"reported as a preview limitation,
	 * distinct from the part having been removed from the asset"* — so it is a
	 * member of its own rather than a shade of `orphaned`.
	 */
	readonly missingFromPreview: boolean;
}

/** What a loaded preview offers a resolution: named parts, and the bones it has. */
export interface LoadedMesh {
	readonly parts: readonly PartGeometry[];
	/** The skeleton's bone names, or `null` when this load did not look for them. */
	readonly bones: readonly string[] | null;
}

/** The part of an anchor that is its durable key, or an empty string for a 2D one. */
export function partOf(anchor: Anchor): string {
	return anchor.part ?? '';
}

export function isPartAnchor(anchor: Anchor): boolean {
	return Boolean(anchor.part);
}

export function hintOf(anchor: Anchor): Vec3 | null {
	const point = anchor.point;
	if (!point || point.length < 3) return null;
	return [point[0], point[1], point[2]];
}

/**
 * A resolver over one loaded mesh, with each part's hierarchy built on first use.
 *
 * A closure rather than a class because what it holds is a cache of pure
 * derivations: the same anchor against the same mesh answers the same thing
 * however many times it is asked, and from whatever direction the camera
 * happens to be pointing.
 */
export function resolverFor(
	mesh: LoadedMesh,
	sourceParts: readonly string[] = [],
	threshold = DISPLACEMENT_THRESHOLD
): (anchor: Anchor) => Resolution {
	const index = accelerate();
	const byName = new Map(mesh.parts.map((part) => [part.name, part]));
	const inSource = new Set(sourceParts);
	return (anchor) => {
		const part = partOf(anchor);
		const bone = anchor.bone ?? '';
		const geometry = byName.get(part);
		if (!geometry) return absent(part, bone, inSource.has(part));
		const narrowed = narrowing(mesh.bones, bone);
		return placed(anchor, index(geometry), part, bone, narrowed, threshold);
	};
}

/**
 * A part that is not in the loaded mesh: an orphan, or a preview limitation.
 *
 * Never a relocation. There is no branch here that looks at another part, and
 * no parameter that could carry a candidate — which is how *"nothing
 * re-anchors on its own"* stays true rather than stays remembered.
 */
function absent(part: string, bone: string, inSource: boolean): Resolution {
	return {
		outcome: 'orphaned',
		part,
		bone,
		reason: inSource ? NOT_IN_PREVIEW : NO_SUCH_PART,
		point: null,
		normal: null,
		displacement: null,
		missingFromPreview: inSource
	};
}

/** Whether a recorded bone is missing from a load that knows its bone set. */
function narrowing(bones: readonly string[] | null, bone: string): boolean {
	if (!bone || bones === null) return false;
	return !bones.includes(bone);
}

function placed(
	anchor: Anchor,
	part: PartIndex,
	name: string,
	bone: string,
	narrowed: boolean,
	threshold: number
): Resolution {
	const outcome: Outcome = narrowed ? 'partial' : 'resolved';
	const reason = narrowed ? NO_SUCH_BONE : '';
	const hint = hintOf(anchor);
	const projection = hint === null ? null : part.nearestTo(hint);
	if (projection === null) {
		return {
			outcome,
			part: name,
			bone,
			reason: reason || (hint === null ? '' : NO_GEOMETRY),
			point: hint,
			normal: null,
			displacement: null,
			missingFromPreview: false
		};
	}
	return {
		outcome,
		part: name,
		bone,
		reason,
		point: projection.point,
		normal: projection.normal,
		displacement: displacementOf(hint as Vec3, projection.point, part.diagonal, threshold),
		missingFromPreview: false
	};
}

/**
 * How far the re-projection moved the hint, relative to the part's own size (D5).
 *
 * Normalized by the bounding-box diagonal so that the threshold means the same
 * thing whatever the part is, and stated in absolute units too because *"two
 * centimetres"* is what a modeller acts on.
 */
export function displacementOf(
	hint: Vec3,
	placedAt: Vec3,
	span: number,
	threshold = DISPLACEMENT_THRESHOLD
): Displacement {
	const moved = distance(hint, placedAt);
	const proportion = span > 0 ? moved / span : 0;
	return { distance: moved, proportion, possiblyDisplaced: proportion > threshold };
}

/** Every anchor that could not be placed, for a panel that has to list them. */
export function orphansAmong<T extends { readonly anchor: Anchor }>(
	entries: readonly T[],
	resolve: (anchor: Anchor) => Resolution
): readonly { readonly entry: T; readonly resolution: Resolution }[] {
	return entries
		.filter((entry) => isPartAnchor(entry.anchor))
		.map((entry) => ({ entry, resolution: resolve(entry.anchor) }))
		.filter((found) => found.resolution.outcome === 'orphaned');
}
