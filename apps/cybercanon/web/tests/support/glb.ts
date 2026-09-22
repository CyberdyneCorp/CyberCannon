/**
 * A real GLB, written from code, so the scene module is exercised on real bytes.
 *
 * `add-test-strategy` keeps binary fixtures out of git and writes them from code
 * instead (`tools/canon_fixtures` does the same on the Python side). The reason
 * is the same here: a committed `.glb` is a fixture nobody can read in review,
 * and the one property the viewer's tests turn on — *the same part names across
 * two entirely different triangle layouts* — is only visible if the layouts are
 * written down rather than exported by somebody, once, in 2026.
 *
 * What is produced is a minimal but valid glTF-binary: named nodes over indexed
 * triangle meshes, and optionally one animation clip. Nothing external is
 * referenced, so `GLTFLoader.parse` reads it with no fetch and no DOM.
 */

const MAGIC = 0x46546c67; // 'glTF'
const JSON_CHUNK = 0x4e4f534a;
const BIN_CHUNK = 0x004e4942;
const VERSION = 2;

const FLOAT = 5126;
const UNSIGNED_INT = 5125;
const ARRAY_BUFFER = 34962;
const ELEMENT_ARRAY_BUFFER = 34963;

export interface PartSpec {
	readonly name: string;
	/** Vertex positions, three numbers per vertex. */
	readonly positions: readonly number[];
	/** Triangle corners as indices into `positions`. */
	readonly indices: readonly number[];
}

export interface ClipSpec {
	readonly name: string;
	/** Keyframe times in seconds. The clip's duration is the last of them. */
	readonly times: readonly number[];
	/** One translation per keyframe, three numbers each, applied to the first part. */
	readonly translations: readonly number[];
}

/** One triangle in the z=0 plane, offset along x — the smallest thing with a surface. */
export function triangleAt(x: number, size = 1): readonly number[] {
	return [x, 0, 0, x + size, 0, 0, x, size, 0];
}

/**
 * The same triangle, retopologised: a different layout over the same surface.
 *
 * Four triangles where there was one, with an interior vertex, so *"an entirely
 * different triangle layout"* is what the fixture actually holds rather than
 * what a comment claims.
 */
export function subdividedAt(x: number, size = 1): PartSpec['positions'] {
	const half = size / 2;
	return [
		x, 0, 0,
		x + size, 0, 0,
		x, size, 0,
		x + half, 0, 0,
		x + half, half, 0,
		x, half, 0
	];
}

export const SUBDIVIDED_INDICES: readonly number[] = [0, 3, 5, 3, 1, 4, 5, 4, 2, 3, 4, 5];

interface Accessor {
	bufferView: number;
	componentType: number;
	count: number;
	type: string;
	min?: number[];
	max?: number[];
}

/** Build a GLB holding these parts and clips. Returns the bytes, ready to parse. */
export function buildGlb(parts: readonly PartSpec[], clips: readonly ClipSpec[] = []): ArrayBuffer {
	const chunks: Uint8Array[] = [];
	const views: Record<string, unknown>[] = [];
	const accessors: Accessor[] = [];
	let offset = 0;

	function append(data: Float32Array | Uint32Array, target?: number): number {
		const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
		chunks.push(bytes);
		views.push({
			buffer: 0,
			byteOffset: offset,
			byteLength: bytes.byteLength,
			...(target ? { target } : {})
		});
		offset += bytes.byteLength;
		return views.length - 1;
	}

	const meshes = parts.map((part) => {
		const positions = Float32Array.from(part.positions);
		const positionView = append(positions, ARRAY_BUFFER);
		accessors.push({
			bufferView: positionView,
			componentType: FLOAT,
			count: positions.length / 3,
			type: 'VEC3',
			min: extreme(positions, Math.min),
			max: extreme(positions, Math.max)
		});
		const positionAccessor = accessors.length - 1;
		const indices = Uint32Array.from(part.indices);
		const indexView = append(indices, ELEMENT_ARRAY_BUFFER);
		accessors.push({
			bufferView: indexView,
			componentType: UNSIGNED_INT,
			count: indices.length,
			type: 'SCALAR'
		});
		return {
			name: part.name,
			primitives: [{ attributes: { POSITION: positionAccessor }, indices: accessors.length - 1 }]
		};
	});

	const animations = clips.map((clip) => {
		const times = Float32Array.from(clip.times);
		const timeView = append(times);
		accessors.push({
			bufferView: timeView,
			componentType: FLOAT,
			count: times.length,
			type: 'SCALAR',
			min: [Math.min(...clip.times)],
			max: [Math.max(...clip.times)]
		});
		const input = accessors.length - 1;
		const values = Float32Array.from(clip.translations);
		const valueView = append(values);
		accessors.push({
			bufferView: valueView,
			componentType: FLOAT,
			count: values.length / 3,
			type: 'VEC3'
		});
		return {
			name: clip.name,
			samplers: [{ input, output: accessors.length - 1, interpolation: 'LINEAR' }],
			channels: [{ sampler: 0, target: { node: 0, path: 'translation' } }]
		};
	});

	const document = {
		asset: { version: '2.0', generator: 'cybercanon test fixture' },
		scene: 0,
		scenes: [{ nodes: parts.map((_, index) => index) }],
		nodes: parts.map((part, index) => ({ name: part.name, mesh: index })),
		meshes,
		accessors,
		bufferViews: views,
		buffers: [{ byteLength: offset }],
		...(animations.length > 0 ? { animations } : {})
	};

	return assemble(document, concat(chunks, offset));
}

function extreme(values: Float32Array, pick: (...numbers: number[]) => number): number[] {
	const axes: number[][] = [[], [], []];
	for (let index = 0; index < values.length; index += 1) axes[index % 3].push(values[index]);
	return axes.map((axis) => pick(...axis));
}

function concat(chunks: readonly Uint8Array[], total: number): Uint8Array {
	const bytes = new Uint8Array(total);
	let at = 0;
	for (const chunk of chunks) {
		bytes.set(chunk, at);
		at += chunk.byteLength;
	}
	return bytes;
}

function padded(bytes: Uint8Array, filler: number): Uint8Array {
	const remainder = bytes.byteLength % 4;
	if (remainder === 0) return bytes;
	const grown = new Uint8Array(bytes.byteLength + (4 - remainder)).fill(filler);
	grown.set(bytes, 0);
	return grown;
}

function assemble(document: unknown, binary: Uint8Array): ArrayBuffer {
	const json = padded(new TextEncoder().encode(JSON.stringify(document)), 0x20);
	const bin = padded(binary, 0);
	const total = 12 + 8 + json.byteLength + 8 + bin.byteLength;
	const buffer = new ArrayBuffer(total);
	const view = new DataView(buffer);
	const bytes = new Uint8Array(buffer);
	view.setUint32(0, MAGIC, true);
	view.setUint32(4, VERSION, true);
	view.setUint32(8, total, true);
	view.setUint32(12, json.byteLength, true);
	view.setUint32(16, JSON_CHUNK, true);
	bytes.set(json, 20);
	const binHeader = 20 + json.byteLength;
	view.setUint32(binHeader, bin.byteLength, true);
	view.setUint32(binHeader + 4, BIN_CHUNK, true);
	bytes.set(bin, binHeader + 8);
	return buffer;
}
