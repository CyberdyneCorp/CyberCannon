/**
 * D4 — the nearest point on a named part's surface, and nothing about a camera.
 *
 * *"Resolution builds (lazily, per part, on first use) a bounding-volume
 * hierarchy over that part's triangles and returns the closest point on its
 * surface to the hint. Other parts are not candidates, at any distance."*
 *
 * Everything here is plain numbers over plain arrays. That is deliberate and it
 * is what makes D4 checkable: a nearest-point query is either right or wrong
 * about a triangle, and asserting it through a renderer would be asserting it
 * through the one component a test cannot see. `three.js` is not imported, so
 * this module is free to be reached by a static import while
 * `$lib/viewer/scene` is not (D7).
 *
 * **Why nearest-point rather than a ray along the stored normal.** The ray is
 * what most people reach for and it fails exactly when it matters: after a
 * retopology the surface may have moved off that ray entirely, and the ray then
 * either misses or hits something behind. A nearest-point query always answers,
 * and restricting it to the named part means the answer is never the wrong
 * part.
 */

export type Vec3 = readonly [number, number, number];

/** One part's triangles in its **own** local space (D4, D10). Never world space. */
export interface PartGeometry {
	readonly name: string;
	/** Vertex positions, three numbers per vertex, in the part's local space. */
	readonly positions: ArrayLike<number>;
	/** Triangle corners as indices into `positions`. Non-indexed geometry lists 0..n. */
	readonly indices: ArrayLike<number>;
}

export interface Bounds {
	readonly min: Vec3;
	readonly max: Vec3;
}

/** Where a hint landed, and how far it had to travel to get there. */
export interface Projection {
	readonly point: Vec3;
	readonly normal: Vec3;
	readonly distance: number;
}

export const ORIGIN: Vec3 = [0, 0, 0];
export const UP: Vec3 = [0, 1, 0];

export function subtract(a: Vec3, b: Vec3): Vec3 {
	return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

export function add(a: Vec3, b: Vec3): Vec3 {
	return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

export function scale(a: Vec3, factor: number): Vec3 {
	return [a[0] * factor, a[1] * factor, a[2] * factor];
}

export function dot(a: Vec3, b: Vec3): number {
	return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

export function cross(a: Vec3, b: Vec3): Vec3 {
	return [
		a[1] * b[2] - a[2] * b[1],
		a[2] * b[0] - a[0] * b[2],
		a[0] * b[1] - a[1] * b[0]
	];
}

export function length(a: Vec3): number {
	return Math.sqrt(dot(a, a));
}

export function distance(a: Vec3, b: Vec3): number {
	return length(subtract(a, b));
}

/** A unit vector, or `UP` when there is no direction to normalize. */
export function normalize(a: Vec3): Vec3 {
	const size = length(a);
	return size > 0 ? scale(a, 1 / size) : UP;
}

export function centre(bounds: Bounds): Vec3 {
	return scale(add(bounds.min, bounds.max), 0.5);
}

/** The bounding box's diagonal — what a displacement is measured against (D5). */
export function diagonal(bounds: Bounds): number {
	return distance(bounds.min, bounds.max);
}

/** The axis-aligned box these positions occupy. An empty part is a point at the origin. */
export function boundsOf(positions: ArrayLike<number>): Bounds {
	if (positions.length < 3) return { min: ORIGIN, max: ORIGIN };
	const min: [number, number, number] = [Infinity, Infinity, Infinity];
	const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
	for (let index = 0; index + 2 < positions.length; index += 3) {
		for (let axis = 0; axis < 3; axis += 1) {
			const value = positions[index + axis];
			if (value < min[axis]) min[axis] = value;
			if (value > max[axis]) max[axis] = value;
		}
	}
	return { min, max };
}

/** The smallest box containing both. Used to build a hierarchy, never to test one. */
export function union(first: Bounds, second: Bounds): Bounds {
	return {
		min: [
			Math.min(first.min[0], second.min[0]),
			Math.min(first.min[1], second.min[1]),
			Math.min(first.min[2], second.min[2])
		],
		max: [
			Math.max(first.max[0], second.max[0]),
			Math.max(first.max[1], second.max[1]),
			Math.max(first.max[2], second.max[2])
		]
	};
}

/** How far a point is from a box — zero inside it. The hierarchy's only test. */
export function distanceToBounds(point: Vec3, bounds: Bounds): number {
	let total = 0;
	for (let axis = 0; axis < 3; axis += 1) {
		const value = point[axis];
		const outside = Math.max(bounds.min[axis] - value, 0) + Math.max(value - bounds.max[axis], 0);
		total += outside * outside;
	}
	return Math.sqrt(total);
}

/**
 * The closest point on one triangle to `point` — the whole geometric decision.
 *
 * Ericson's region test, written out rather than reached for: the interior
 * case, the three vertices and the three edges. A version that only projected
 * onto the plane would place a pin off the end of a limb whenever the hint sat
 * beyond it, which is exactly the retopology case.
 */
export function closestOnTriangle(point: Vec3, a: Vec3, b: Vec3, c: Vec3): Vec3 {
	const ab = subtract(b, a);
	const ac = subtract(c, a);
	const ap = subtract(point, a);
	const d1 = dot(ab, ap);
	const d2 = dot(ac, ap);
	if (d1 <= 0 && d2 <= 0) return a;

	const bp = subtract(point, b);
	const d3 = dot(ab, bp);
	const d4 = dot(ac, bp);
	if (d3 >= 0 && d4 <= d3) return b;

	const vc = d1 * d4 - d3 * d2;
	if (vc <= 0 && d1 >= 0 && d3 <= 0) return add(a, scale(ab, d1 / (d1 - d3)));

	const cp = subtract(point, c);
	const d5 = dot(ab, cp);
	const d6 = dot(ac, cp);
	if (d6 >= 0 && d5 <= d6) return c;

	const vb = d5 * d2 - d1 * d6;
	if (vb <= 0 && d2 >= 0 && d6 <= 0) return add(a, scale(ac, d2 / (d2 - d6)));

	const va = d3 * d6 - d5 * d4;
	if (va <= 0 && d4 - d3 >= 0 && d5 - d6 >= 0) {
		return add(b, scale(subtract(c, b), (d4 - d3) / (d4 - d3 + (d5 - d6))));
	}
	const denominator = 1 / (va + vb + vc);
	return add(a, add(scale(ab, vb * denominator), scale(ac, vc * denominator)));
}

/** The triangle's own normal, which is what the resolved anchor displays. */
export function triangleNormal(a: Vec3, b: Vec3, c: Vec3): Vec3 {
	return normalize(cross(subtract(b, a), subtract(c, a)));
}

/** One triangle a search has settled on so far, and how far away it was. */
interface Found {
	readonly triangle: number;
	readonly point: Vec3;
	readonly distance: number;
}

interface Node {
	readonly bounds: Bounds;
	readonly triangles: readonly number[];
	readonly left: Node | null;
	readonly right: Node | null;
}

const LEAF_SIZE = 8;
/** How many triangles a leaf holds before a split stops paying for itself. */

/**
 * One part's triangles, in a hierarchy built once and kept (D4).
 *
 * Built lazily by :func:`accelerate` on the first resolution against a part,
 * because a mesh with two hundred parts and four annotations must not pay for a
 * hundred and ninety-six hierarchies nobody queries.
 */
export class PartIndex {
	readonly name: string;
	readonly bounds: Bounds;
	readonly #positions: ArrayLike<number>;
	readonly #indices: ArrayLike<number>;
	readonly #root: Node | null;

	constructor(part: PartGeometry) {
		this.name = part.name;
		this.#positions = part.positions;
		this.#indices = part.indices;
		this.bounds = boundsOf(part.positions);
		this.#root = this.#build(this.#allTriangles());
	}

	/** The part's bounding-box diagonal — the scale a displacement is relative to. */
	get diagonal(): number {
		return diagonal(this.bounds);
	}

	get triangleCount(): number {
		return Math.floor(this.#indices.length / 3);
	}

	/**
	 * The point on this part's surface nearest the hint, with its normal.
	 *
	 * `null` only when the part carries no triangles at all — a part that exists
	 * as a node and holds no geometry, which the preview pipeline can produce
	 * and which must not be reported as a missing part.
	 */
	nearestTo(hint: Vec3): Projection | null {
		const best = this.#search(hint);
		if (best === null) return null;
		const [a, b, c] = this.#corners(best.triangle);
		return { point: best.point, normal: triangleNormal(a, b, c), distance: best.distance };
	}

	/** Descend the hierarchy, skipping every box already further than the best hit. */
	#search(hint: Vec3): Found | null {
		let best: Found | null = null;
		const pending: (Node | null)[] = [this.#root];
		while (pending.length > 0) {
			const node = pending.pop() ?? null;
			if (node === null) continue;
			if (best !== null && distanceToBounds(hint, node.bounds) >= best.distance) continue;
			if (node.left !== null || node.right !== null) {
				pending.push(node.left, node.right);
				continue;
			}
			best = this.#closestInLeaf(hint, node, best);
		}
		return best;
	}

	#closestInLeaf(hint: Vec3, node: Node, best: Found | null): Found | null {
		let closest = best;
		for (const triangle of node.triangles) {
			const [a, b, c] = this.#corners(triangle);
			const found = closestOnTriangle(hint, a, b, c);
			const span = distance(hint, found);
			if (closest === null || span < closest.distance) {
				closest = { triangle, point: found, distance: span };
			}
		}
		return closest;
	}

	#allTriangles(): number[] {
		return Array.from({ length: this.triangleCount }, (_, index) => index);
	}

	#corners(triangle: number): [Vec3, Vec3, Vec3] {
		const base = triangle * 3;
		return [
			this.#vertex(this.#indices[base]),
			this.#vertex(this.#indices[base + 1]),
			this.#vertex(this.#indices[base + 2])
		];
	}

	#vertex(index: number): Vec3 {
		const base = index * 3;
		return [this.#positions[base], this.#positions[base + 1], this.#positions[base + 2]];
	}

	#boundsOfTriangle(triangle: number): Bounds {
		const [a, b, c] = this.#corners(triangle);
		return boundsOf([...a, ...b, ...c]);
	}

	/** Median split along the widest axis — the ordinary hierarchy, built once. */
	#build(triangles: readonly number[]): Node | null {
		if (triangles.length === 0) return null;
		const bounds = triangles
			.map((triangle) => this.#boundsOfTriangle(triangle))
			.reduce(union);
		if (triangles.length <= LEAF_SIZE) {
			return { bounds, triangles, left: null, right: null };
		}
		const axis = widestAxis(bounds);
		const ordered = [...triangles].sort(
			(first, second) =>
				centre(this.#boundsOfTriangle(first))[axis] -
				centre(this.#boundsOfTriangle(second))[axis]
		);
		const middle = Math.floor(ordered.length / 2);
		return {
			bounds,
			triangles: [],
			left: this.#build(ordered.slice(0, middle)),
			right: this.#build(ordered.slice(middle))
		};
	}
}

function widestAxis(bounds: Bounds): 0 | 1 | 2 {
	const spans = [
		bounds.max[0] - bounds.min[0],
		bounds.max[1] - bounds.min[1],
		bounds.max[2] - bounds.min[2]
	];
	const widest = Math.max(...spans);
	return spans.indexOf(widest) as 0 | 1 | 2;
}

/**
 * The hierarchy for a part, built on first use and kept for the session (D4).
 *
 * A plain map rather than a class, because what is being cached is a pure
 * function of the geometry and there is nothing to invalidate: a different
 * export is a different load and a different registry.
 */
export function accelerate(): (part: PartGeometry) => PartIndex {
	const built = new Map<string, PartIndex>();
	return (part) => {
		const existing = built.get(part.name);
		if (existing) return existing;
		const index = new PartIndex(part);
		built.set(part.name, index);
		return index;
	};
}
