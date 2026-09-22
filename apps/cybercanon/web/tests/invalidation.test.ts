/**
 * Tasks 2.2 and 2.3 — the one cache, and the test per write path that D2 asks
 * for by name: *"a cache invalidation map that must be kept honest, and a test
 * per write path asserting what it invalidates"*.
 *
 * Each case fills the cache with every resource the application knows how to
 * name, runs one write, and asserts the exact set of keys that went — so an
 * invalidation that is too wide fails as loudly as one that is too narrow. Too
 * wide is the one a hand-written test usually misses, and it is the one that
 * turns a cache into a slow uncached client.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { QueryCache } from '../src/lib/api/cache';
import { resources, type ResourceKey } from '../src/lib/api/resources';
import { invalidatedBy, WRITE_PATHS, type WritePath } from '../src/lib/api/invalidation';
import { CanonApi } from '../src/lib/api';

const PROJECT = 'atlas';
const OTHER = 'orion';
const ASSET = 'mech_scout';
const REQUEST = 'req-1';

/** Every key the application can hold, for one project and for another. */
const POPULATION: Readonly<Record<string, ResourceKey>> = {
	'assets:unfiltered': resources.assets(PROJECT),
	'assets:filtered': resources.assets(PROJECT, { status: 'in_progress', owner: 'rafa' }),
	'asset:spec': resources.asset(PROJECT, ASSET),
	'asset:spec:lensed': resources.asset(PROJECT, ASSET, 'art'),
	'asset:other-asset': resources.asset(PROJECT, 'crate_small'),
	briefing: resources.briefing(PROJECT, ASSET),
	locations: resources.locations(PROJECT, ASSET),
	search: resources.search(PROJECT, 'scout'),
	'project-briefing': resources.projectBriefing(PROJECT),
	validation: resources.validation(PROJECT, 'exports/mech_scout.glb'),
	requests: resources.requests(PROJECT),
	request: resources.request(PROJECT, REQUEST),
	unread: resources.unread(PROJECT),
	annotations: resources.annotations(PROJECT, ASSET, 'rev-1'),
	'annotations:another-revision': resources.annotations(PROJECT, ASSET, 'rev-2'),
	'annotations:other-asset': resources.annotations(PROJECT, 'crate_small', 'rev-1'),
	preview: resources.preview(PROJECT, ASSET),
	'preview-content': resources.previewContent(PROJECT, ASSET),
	resolutions: resources.resolutions(PROJECT, ASSET),
	'resolutions:other-asset': resources.resolutions(PROJECT, 'crate_small'),
	triage: resources.triage(PROJECT),
	'triage:filtered': resources.triage(PROJECT, { kind: 'art-direction' }),
	'other-project:assets': resources.assets(OTHER),
	'other-project:requests': resources.requests(OTHER),
	'other-project:unread': resources.unread(OTHER)
};

let cache: QueryCache;

beforeEach(() => {
	cache = new QueryCache(() => 0);
	for (const key of Object.values(POPULATION)) cache.set(key, 'remembered');
});

function forgottenBy(path: WritePath, target: Record<string, string>): string[] {
	const dropped = new Set(cache.invalidate(invalidatedBy(path, { project: PROJECT, ...target })));
	return Object.entries(POPULATION)
		.filter(([, key]) => dropped.has(key))
		.map(([name]) => name)
		.sort();
}

describe('every write path declares what it invalidates', () => {
	it.each(WRITE_PATHS)('%s has an entry in the map', (path) => {
		expect(invalidatedBy(path, { project: PROJECT, asset: ASSET, request: REQUEST }).length)
			.toBeGreaterThan(0);
	});
});

describe('write-spec', () => {
	it('drops the asset, its briefing, its locations, the listing, search and validations', () => {
		expect(forgottenBy('write-spec', { asset: ASSET })).toEqual([
			'asset:spec',
			'asset:spec:lensed',
			'assets:filtered',
			'assets:unfiltered',
			'briefing',
			'locations',
			'search',
			'validation'
		]);
	});

	it('keeps another asset, the project briefing and every other project', () => {
		const dropped = forgottenBy('write-spec', { asset: ASSET });

		expect(dropped).not.toContain('asset:other-asset');
		expect(dropped).not.toContain('project-briefing');
		expect(dropped).not.toContain('other-project:assets');
	});
});

describe('raise-request', () => {
	it('drops the project requests and the unread items, and nothing else', () => {
		expect(forgottenBy('raise-request', {})).toEqual(['requests', 'unread']);
	});

	it('leaves an already-read request alone — a new one did not change it', () => {
		expect(forgottenBy('raise-request', {})).not.toContain('request');
	});

	it('leaves another project alone', () => {
		const dropped = forgottenBy('raise-request', {});

		expect(dropped).not.toContain('other-project:requests');
		expect(dropped).not.toContain('other-project:unread');
	});
});

describe.each(['assign-request', 'transition-request'] as const)('%s', (path) => {
	it('drops the requests, the one request and the unread items', () => {
		expect(forgottenBy(path, { request: REQUEST })).toEqual(['request', 'requests', 'unread']);
	});

	it('leaves the asset listing and specifications alone', () => {
		const dropped = forgottenBy(path, { request: REQUEST });

		expect(dropped).not.toContain('assets:unfiltered');
		expect(dropped).not.toContain('asset:spec');
	});
});

describe('annotate', () => {
	it('drops the asset’s threads at every revision, its briefing and the queue', () => {
		expect(forgottenBy('annotate', { asset: ASSET })).toEqual([
			'annotations',
			'annotations:another-revision',
			'briefing',
			'resolutions',
			'triage',
			'triage:filtered'
		]);
	});

	it('drops the anchor resolutions, because a moved anchor resolves differently', () => {
		expect(forgottenBy('annotate', { asset: ASSET })).toContain('resolutions');
	});

	it('keeps the preview and its bytes — an annotation changes no export', () => {
		const dropped = forgottenBy('annotate', { asset: ASSET });

		expect(dropped).not.toContain('preview');
		expect(dropped).not.toContain('preview-content');
		expect(dropped).not.toContain('resolutions:other-asset');
	});

	it('keeps the specification, the listing and the search — no declared field moved', () => {
		const dropped = forgottenBy('annotate', { asset: ASSET });

		expect(dropped).not.toContain('asset:spec');
		expect(dropped).not.toContain('assets:unfiltered');
		expect(dropped).not.toContain('search');
	});

	it('keeps another asset’s threads', () => {
		expect(forgottenBy('annotate', { asset: ASSET })).not.toContain('annotations:other-asset');
	});
});

describe('promote-annotation', () => {
	it('drops everything a thread write drops and everything a specification write does', () => {
		expect(forgottenBy('promote-annotation', { asset: ASSET })).toEqual([
			'annotations',
			'annotations:another-revision',
			'asset:spec',
			'asset:spec:lensed',
			'assets:filtered',
			'assets:unfiltered',
			'briefing',
			'locations',
			'resolutions',
			'search',
			'triage',
			'triage:filtered',
			'validation'
		]);
	});

	it('is wider than a thread write, because a promotion writes a durable rule', () => {
		const promoted = forgottenBy('promote-annotation', { asset: ASSET });

		expect(promoted).toContain('validation');
		expect(forgottenBy('annotate', { asset: ASSET })).not.toContain('validation');
	});

	it('still leaves another project and the project briefing alone', () => {
		const dropped = forgottenBy('promote-annotation', { asset: ASSET });

		expect(dropped).not.toContain('project-briefing');
		expect(dropped).not.toContain('other-project:assets');
	});
});

describe('dismiss-notification', () => {
	it('drops the unread items and nothing else — the request did not change', () => {
		expect(forgottenBy('dismiss-notification', { request: REQUEST })).toEqual(['unread']);
	});
});

describe('the cache is the only place server state lives', () => {
	it('serves a second read from the cache rather than the surface', async () => {
		let calls = 0;
		const load = async () => {
			calls += 1;
			return 'answer';
		};

		expect(await cache.read(resources.projectBriefing('new'), load)).toBe('answer');
		expect(await cache.read(resources.projectBriefing('new'), load)).toBe('answer');
		expect(calls).toBe(1);
	});

	it('asks once when two screens ask at the same time', async () => {
		let calls = 0;
		const load = () => {
			calls += 1;
			return Promise.resolve('answer');
		};
		const key = resources.projectBriefing('new');

		await Promise.all([cache.read(key, load), cache.read(key, load)]);

		expect(calls).toBe(1);
	});

	it('forgets everything on sign-out', () => {
		cache.clear();

		expect(cache.keys()).toEqual([]);
	});
});

describe('a write through the API reports what it invalidated', () => {
	it('drops the requests scope after raising one', async () => {
		const api = new CanonApi({ baseUrl: 'https://canon.example', fetch: notCalled, cache });

		const { invalidated } = await api.write('raise-request', { project: PROJECT }, async () => ({
			ok: true as const,
			data: null,
			freshness: null
		}));

		expect([...invalidated]).toContain(resources.requests(PROJECT));
	});
});

const notCalled: typeof fetch = () => {
	throw new Error('the write was performed by the caller, not by the client');
};
