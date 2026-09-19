/**
 * The browser screen end to end over a hand-written surface: every route state
 * group 4 can produce, and the reads it took to decide which one.
 *
 * The surface below answers exactly what `http-api` answers — a page of rows, a
 * page of ranked hits, a location answer, or one of the six refusals — so what
 * is tested is this application's decisions and never a mock of them. The reads
 * are recorded because two of the decisions are *about* reading: a filtered
 * search has to establish which assets the filters admit, and an empty filtered
 * listing has to ask once more without them, or *"nothing is here"* and *"you
 * filtered everything out"* become the same screen.
 */

import { describe, expect, it } from 'vitest';
import type {
	ApiResult,
	AssetRow,
	Failure,
	ListingFilters,
	LocationAnswer,
	Page,
	SearchHit
} from '../src/lib/api';
import type { BrowserAddress } from '../src/lib/address';
import type { BrowserReads, BrowserView } from '../src/lib/browser';
import {
	DELEGATED_SEARCH,
	FILTERS_NOT_APPLIED,
	INDEX_REBUILDING,
	MEMBERSHIP_PAGE_SIZE,
	PARTIAL_FILTER_CHECK,
	REBUILDING_NOTE,
	browserScreen
} from '../src/lib/browser';
import type { Degraded, Empty, RouteState } from '../src/lib/route-state';

const PROJECT = 'atlas';
const OWNERS = [{ discipline: 'art', display: 'rafa', recorded: true, unmapped: false }];

function row(asset: string, status = 'modeling'): AssetRow {
	return { asset, name: asset.replace('_', ' '), status, owners: OWNERS };
}

function page<T>(items: readonly T[], next: string | null = null): Page<T> {
	return { items, next_token: next, page_size: 25, total: items.length };
}

function hit(asset: string, matched: string): SearchHit {
	return { asset, name: asset.replace('_', ' '), matched };
}

function ok<T>(data: T, mayBeStale = false): ApiResult<T> {
	return {
		ok: true,
		data,
		freshness: { revision: 'abc123', confirmedAt: '2026-09-19T10:00:00+00:00', mayBeStale }
	};
}

function no<T>(kind: Failure['kind'], identifier: string, message = 'no'): ApiResult<T> {
	return { ok: false, failure: { kind, identifier, message, subject: null, correlationId: null } };
}

function address(over: Partial<BrowserAddress> = {}): BrowserAddress {
	return { project: PROJECT, query: '', filters: {}, page: null, ...over };
}

interface Answers {
	assets?: (filters: ListingFilters) => ApiResult<Page<AssetRow>>;
	search?: (term: string) => ApiResult<Page<SearchHit>>;
	locations?: (asset: string) => ApiResult<LocationAnswer>;
}

interface Surface extends BrowserReads {
	readonly listings: ListingFilters[];
	readonly searches: string[];
	readonly lookups: string[];
}

function surface(answers: Answers): Surface {
	const listings: ListingFilters[] = [];
	const searches: string[] = [];
	const lookups: string[] = [];
	return {
		listings,
		searches,
		lookups,
		async assets(_project: string, filters: ListingFilters = {}) {
			listings.push(filters);
			return answers.assets?.(filters) ?? ok(page<AssetRow>([]));
		},
		async search(_project: string, term: string) {
			searches.push(term);
			return answers.search?.(term) ?? ok(page<SearchHit>([]));
		},
		async locations(_project: string, asset: string) {
			lookups.push(asset);
			return answers.locations?.(asset) ?? no<LocationAnswer>('not_found', 'asset.unknown');
		}
	};
}

function rows(state: RouteState<BrowserView>): readonly string[] {
	const data = state.kind === 'content' || state.kind === 'degraded' ? state.data : null;
	return (data?.rows ?? []).map((entry) => entry.asset);
}

describe('the listing', () => {
	it('shows the project’s assets with their state', async () => {
		const api = surface({ assets: () => ok(page([row('mech_scout', 'blocked'), row('crate')])) });

		const state = await browserScreen(api, address());

		expect(state.kind).toBe('content');
		expect(rows(state)).toEqual(['mech_scout', 'crate']);
		expect(api.searches).toEqual([]);
	});

	it('asks the surface for exactly the filters the address carries', async () => {
		const api = surface({ assets: () => ok(page([row('mech_scout')])) });

		await browserScreen(api, address({ filters: { status: 'blocked', owner: 'rafa' } }));

		expect(api.listings).toEqual([{ status: 'blocked', owner: 'rafa', page: null }]);
	});

	it('is the no-assets screen on an empty project, and asks nothing more', async () => {
		const api = surface({ assets: () => ok(page<AssetRow>([])) });

		const state = await browserScreen(api, address());

		expect(state.kind).toBe('empty');
		expect((state as Empty).reason).toBe('no-assets');
		expect(api.listings).toHaveLength(1);
	});

	it('distinguishes filters-excluded from no-assets by asking without them', async () => {
		const api = surface({
			assets: (filters) => ok(filters.status ? page<AssetRow>([]) : page([row('mech_scout')]))
		});

		const state = await browserScreen(api, address({ filters: { status: 'approved' } }));

		expect((state as Empty).reason).toBe('filters-excluded');
		expect(api.listings).toHaveLength(2);
	});

	it('is degraded, never content, when the working copy may be stale', async () => {
		const api = surface({ assets: () => ok(page([row('mech_scout')]), true) });

		const state = await browserScreen(api, address());

		expect(state.kind).toBe('degraded');
		expect(rows(state)).toEqual(['mech_scout']);
	});

	it('discloses a rebuilding index instead of showing an empty project', async () => {
		const api = surface({ assets: () => no<Page<AssetRow>>('unavailable', INDEX_REBUILDING) });

		const state = await browserScreen(api, address());

		expect(state.kind).toBe('degraded');
		expect((state as Degraded<BrowserView>).unavailable).toEqual([REBUILDING_NOTE]);
		expect((state as Degraded<BrowserView>).data).toBeNull();
	});

	it('refuses a project it may not read as a refusal, not as an empty listing', async () => {
		const api = surface({ assets: () => no<Page<AssetRow>>('forbidden', 'project.forbidden') });

		expect((await browserScreen(api, address())).kind).toBe('forbidden');
	});
});

describe('search', () => {
	const ranked = page([hit('zulu', 'exact_id'), hit('alpha', 'description')]);

	it('shows the results in the order the ranking returned them', async () => {
		const api = surface({
			search: () => ok(ranked),
			assets: () => ok(page([row('alpha'), row('zulu')]))
		});

		const state = await browserScreen(api, address({ query: 'scout' }));

		expect(rows(state)).toEqual(['zulu', 'alpha']);
	});

	it('reads the listing at the surface’s maximum so a row can carry its state', async () => {
		const api = surface({ search: () => ok(ranked), assets: () => ok(page([row('zulu')])) });

		await browserScreen(api, address({ query: 'scout' }));

		expect(api.listings).toEqual([{ page: null, size: MEMBERSHIP_PAGE_SIZE }]);
	});

	it('states that nothing matched, naming the query', async () => {
		const api = surface({ search: () => ok(page<SearchHit>([])) });

		const state = await browserScreen(api, address({ query: 'scavenger' }));

		expect((state as Empty).reason).toBe('no-results');
		expect((state as Empty).message).toContain('scavenger');
	});

	it('says the filters excluded the matches when they are what emptied the screen', async () => {
		const api = surface({ search: () => ok(ranked), assets: () => ok(page<AssetRow>([])) });

		const state = await browserScreen(
			api,
			address({ query: 'scout', filters: { status: 'approved' } })
		);

		expect((state as Empty).reason).toBe('filters-excluded');
		expect((state as Empty).message).toContain('2');
	});

	it('never presents a filter check it could not complete as complete', async () => {
		const api = surface({
			search: () => ok(ranked),
			assets: () => ok(page([row('zulu'), row('alpha')], 'more'))
		});

		const state = await browserScreen(
			api,
			address({ query: 'scout', filters: { tag: 'mech' } })
		);

		expect(state.kind).toBe('degraded');
		expect((state as Degraded<BrowserView>).unavailable).toContain(PARTIAL_FILTER_CHECK);
		expect(rows(state)).toEqual(['zulu', 'alpha']);
	});

	it('never lets an empty screen swallow what it could not establish', async () => {
		const api = surface({
			search: () => ok(ranked),
			assets: () => ok(page([row('other')], 'more'))
		});

		const state = await browserScreen(
			api,
			address({ query: 'scout', filters: { tag: 'mech' } })
		);

		expect(state.kind).toBe('degraded');
		expect((state as Degraded<BrowserView>).unavailable).toContain(PARTIAL_FILTER_CHECK);
		expect((state as Degraded<BrowserView>).message).toMatch(/filters excluded/);
		expect(rows(state)).toEqual([]);
	});

	it('shows every match unfiltered, and says so, when the filters cannot be established', async () => {
		const api = surface({
			search: () => ok(ranked),
			assets: () => no<Page<AssetRow>>('unavailable', INDEX_REBUILDING)
		});

		const state = await browserScreen(
			api,
			address({ query: 'scout', filters: { tag: 'mech' } })
		);

		expect(state.kind).toBe('degraded');
		expect((state as Degraded<BrowserView>).unavailable[0]).toContain(FILTERS_NOT_APPLIED);
		expect(rows(state)).toEqual(['zulu', 'alpha']);
	});
});

describe('a search that cannot be served completely', () => {
	const answer: LocationAnswer = {
		asset: 'mech_scout',
		name: 'Mech Scout',
		status: 'modeling',
		project: PROJECT,
		locations: [],
		owners: OWNERS,
		stale: false,
		notice: ''
	};

	it('serves what is derivable without the index and states it may be incomplete', async () => {
		const api = surface({
			search: () => no<Page<SearchHit>>('unavailable', INDEX_REBUILDING),
			locations: () => ok(answer)
		});

		const state = await browserScreen(api, address({ query: 'mech_scout' }));

		expect(state.kind).toBe('degraded');
		expect(rows(state)).toEqual(['mech_scout']);
		expect((state as Degraded<BrowserView>).unavailable).toEqual([REBUILDING_NOTE]);
		expect(api.lookups).toEqual(['mech_scout']);
	});

	it('still shows the exact result when the delegated search is unreachable', async () => {
		const api = surface({
			search: () => no<Page<SearchHit>>('unavailable', DELEGATED_SEARCH),
			locations: () => ok(answer)
		});

		const state = await browserScreen(api, address({ query: 'mech_scout' }));

		expect(rows(state)).toEqual(['mech_scout']);
		expect((state as Degraded<BrowserView>).unavailable[0]).toMatch(/semantic search/);
	});

	it('discloses the unavailability even when nothing at all was derivable', async () => {
		const api = surface({ search: () => no<Page<SearchHit>>('unavailable', INDEX_REBUILDING) });

		const state = await browserScreen(api, address({ query: 'why does it look scavenged' }));

		expect(state.kind).toBe('degraded');
		expect(rows(state)).toEqual([]);
		expect((state as Degraded<BrowserView>).unavailable).toEqual([REBUILDING_NOTE]);
	});

	it('does not look for an exact answer when the refusal was not an unavailability', async () => {
		const api = surface({ search: () => no<Page<SearchHit>>('forbidden', 'project.forbidden') });

		const state = await browserScreen(api, address({ query: 'mech_scout' }));

		expect(state.kind).toBe('forbidden');
		expect(api.lookups).toEqual([]);
	});
});
