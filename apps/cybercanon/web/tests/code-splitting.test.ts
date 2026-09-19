/**
 * Task 1.5 — route-level code splitting (D7), verified against a real build.
 *
 * *"A person browsing an asset list should not download a 3D engine."* That is
 * a claim about a bundle, so it is checked against a bundle: the application is
 * built, and the client manifest is walked to find, for every route, the
 * closure of chunks the browser fetches when that route is entered.
 *
 * Two assertions, and the second is the one that matters:
 *
 * * the viewer's scene module is a **dynamic** import of exactly one route, so
 *   the bundler gives it a chunk of its own;
 * * **no route's static closure contains it** — the browser route included, by
 *   name, because that is the screen the decision was taken for.
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { beforeAll, describe, expect, it } from 'vitest';

const ROOT = new URL('..', import.meta.url).pathname;
const MANIFEST = `${ROOT}.svelte-kit/output/client/.vite/manifest.json`;
const NODES = `${ROOT}.svelte-kit/generated/client-optimized/nodes`;
const SCENE = 'src/lib/viewer/scene.ts';
const BROWSER_ROUTE = 'src/routes/p/[project]/assets/+page.svelte';
const VIEWER_ROUTE = 'src/routes/p/[project]/a/[asset]/+page.svelte';

interface Entry {
	file: string;
	imports?: string[];
	dynamicImports?: string[];
}

type Manifest = Record<string, Entry>;

let manifest: Manifest;

beforeAll(() => {
	execFileSync('node', ['node_modules/vite/bin/vite.js', 'build', '--logLevel', 'error'], {
		cwd: ROOT,
		stdio: 'inherit'
	});
	manifest = JSON.parse(readFileSync(MANIFEST, 'utf8')) as Manifest;
}, 180_000);

/** Which generated node module belongs to a route's own source file. */
function nodeOf(route: string): string {
	for (let index = 0; index < 32; index += 1) {
		const path = `${NODES}/${index}.js`;
		let source: string;
		try {
			source = readFileSync(path, 'utf8');
		} catch {
			continue;
		}
		if (source.includes(route)) return `.svelte-kit/generated/client-optimized/nodes/${index}.js`;
	}
	throw new Error(`no generated node imports ${route}`);
}

/** Every chunk the browser fetches to enter this entry — statically, not lazily. */
function staticClosure(entry: string, seen = new Set<string>()): Set<string> {
	if (seen.has(entry)) return seen;
	seen.add(entry);
	for (const imported of manifest[entry]?.imports ?? []) staticClosure(imported, seen);
	return seen;
}

function chunkFiles(entries: Iterable<string>): string[] {
	return [...entries].map((entry) => manifest[entry].file);
}

function containsThree(file: string): boolean {
	return readFileSync(`${ROOT}.svelte-kit/output/client/${file}`, 'utf8').includes('WebGLRenderer');
}

describe('the viewer scene is its own chunk, reached lazily', () => {
	it('is a dynamic import of the viewer route and of nothing else', () => {
		const importers = Object.entries(manifest)
			.filter(([, entry]) => (entry.dynamicImports ?? []).includes(SCENE))
			.map(([name]) => name);

		expect(importers).toEqual([nodeOf(VIEWER_ROUTE)]);
	});

	it('is statically imported by nothing at all', () => {
		const importers = Object.entries(manifest)
			.filter(([, entry]) => (entry.imports ?? []).includes(SCENE))
			.map(([name]) => name);

		expect(importers).toEqual([]);
	});
});

describe('no route downloads the 3D engine to render itself', () => {
	it('keeps it out of the browser route', () => {
		const files = chunkFiles(staticClosure(nodeOf(BROWSER_ROUTE)));

		expect(files.filter(containsThree)).toEqual([]);
	});

	it('keeps it out of the viewer route, until the surface is opened', () => {
		const files = chunkFiles(staticClosure(nodeOf(VIEWER_ROUTE)));

		expect(files.filter(containsThree)).toEqual([]);
	});

	it('really is in the build, so the assertions above are not vacuous', () => {
		const everything = Object.values(manifest).map((entry) => entry.file);

		expect(everything.filter(containsThree).length).toBe(1);
	});
});
