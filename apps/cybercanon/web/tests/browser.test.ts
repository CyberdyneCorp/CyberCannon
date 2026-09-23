/**
 * Group 4's decisions, without a browser: what matched, what is shown, and what
 * having nothing to show means.
 *
 * Every assertion here is one of `asset-browser`'s sentences. The ordering one
 * is the load-bearing case: the specification says this application *"SHALL NOT
 * apply its own ranking, re-sorting or relevance scoring"*, and the only way to
 * test an absence is to hand it an order no comparator would produce and insist
 * it comes back unchanged.
 */

import { describe, expect, it } from 'vitest';
import type { AssetRow, Page, SearchHit } from '../src/lib/api';
import type { BrowserAddress } from '../src/lib/address';
import {
	DELEGATED_NOTE,
	DELEGATED_SEARCH,
	HOW_AN_ASSET_BEGINS,
	INDEX_REBUILDING,
	NOTHING_DELEGATED,
	REBUILDING_NOTE,
	disclosureOf,
	emptinessFor,
	isUnaccepted,
	noteFor,
	viewOfListing,
	viewOfSearch
} from '../src/lib/browser';

const OWNERS = [{ discipline: 'art', display: 'rafa', recorded: true, unmapped: false }];

function row(asset: string, status = 'modeling'): AssetRow {
	return { asset, name: asset.replace('_', ' '), status, owners: OWNERS };
}

function listing(items: readonly AssetRow[], next: string | null = null): Page<AssetRow> {
	return { items, next_token: next, page_size: 25, total: items.length };
}

function hit(asset: string, matched: string): SearchHit {
	return { asset, name: asset.replace('_', ' '), matched };
}

function hits(items: readonly SearchHit[], next: string | null = null): Page<SearchHit> {
	return { items, next_token: next, page_size: 25, total: items.length };
}

function address(over: Partial<BrowserAddress> = {}): BrowserAddress {
	return { project: 'atlas', query: '', filters: {}, page: null, ...over };
}

describe('how a result matched is disclosed', () => {
	it('says nothing when it matched the name or the identifier', () => {
		expect(disclosureOf('exact_id')).toBeNull();
		expect(disclosureOf('name_prefix')).toBeNull();
	});

	it.each([
		['alias', /alias/],
		['tag', /tag/],
		['description', /description/]
	])('discloses a %s match', (matched, expected) => {
		expect(disclosureOf(matched)?.text).toMatch(expected);
	});

	it('marks a result produced only by an unaccepted suggestion', () => {
		const disclosure = disclosureOf('suggested_alias');

		expect(disclosure?.unaccepted).toBe(true);
		expect(disclosure?.text).toMatch(/unaccepted/);
		expect(isUnaccepted('suggested_alias')).toBe(true);
		expect(isUnaccepted('alias')).toBe(false);
	});

	it('discloses a pass it has never heard of rather than staying silent', () => {
		const disclosure = disclosureOf('embedding');

		expect(disclosure).not.toBeNull();
		expect(disclosure?.text).toContain('embedding');
		expect(disclosure?.unaccepted).toBe(false);
	});
});

describe('the listing shows state without opening an asset', () => {
	it('carries the name, the identifier, the status and the owners of each row', () => {
		const view = viewOfListing(listing([row('mech_scout', 'blocked'), row('crate', 'approved')]));

		expect(view.rows.map((entry) => entry.asset)).toEqual(['mech_scout', 'crate']);
		expect(view.rows[0]).toMatchObject({
			asset: 'mech_scout',
			name: 'mech scout',
			status: 'blocked',
			owners: OWNERS
		});
		expect(view.rows[1].status).toBe('approved');
	});

	it('reports that more exist rather than implying the page is everything', () => {
		expect(viewOfListing(listing([row('a')], 'token')).more).toBe(true);
		expect(viewOfListing(listing([row('a')])).more).toBe(false);
	});
});

describe('search results keep the order the ranking produced', () => {
	const ranked = hits([
		hit('zulu', 'exact_id'),
		hit('alpha', 'alias'),
		hit('mike', 'description')
	]);

	it('renders them in the given order, which no comparator would produce', () => {
		const view = viewOfSearch({ hits: ranked, admitted: null, filtered: false, query: 'scout' });

		expect(view.rows.map((entry) => entry.asset)).toEqual(['zulu', 'alpha', 'mike']);
	});

	it('joins the status and the owners the listing knows for the same asset', () => {
		const view = viewOfSearch({
			hits: ranked,
			admitted: listing([row('alpha', 'approved')]),
			filtered: false,
			query: 'scout'
		});

		expect(view.rows[1]).toMatchObject({ asset: 'alpha', status: 'approved', owners: OWNERS });
		expect(view.rows[0].status).toBeNull();
	});

	it('discloses the pass that found each one', () => {
		const view = viewOfSearch({ hits: ranked, admitted: null, filtered: false, query: 'scout' });

		expect(view.rows[0].disclosure).toBeNull();
		expect(view.rows[1].disclosure?.matched).toBe('alias');
		expect(view.rows[2].disclosure?.matched).toBe('description');
	});

	it('removes what the filters exclude and counts it, keeping the rest in order', () => {
		const view = viewOfSearch({
			hits: ranked,
			admitted: listing([row('mike'), row('zulu')]),
			filtered: true,
			query: 'scout'
		});

		expect(view.rows.map((entry) => entry.asset)).toEqual(['zulu', 'mike']);
		expect(view.excluded).toBe(1);
	});
});

describe('an empty result is three different screens', () => {
	const nothing = { rows: [], total: 0, more: false, semantic: NOTHING_DELEGATED };

	it('states the query when nothing matched it', () => {
		const state = emptinessFor(
			{ ...nothing, searched: true, query: 'scavenger', excluded: 0 },
			address({ query: 'scavenger' })
		);

		expect(state?.reason).toBe('no-results');
		expect(state?.subject).toBe('scavenger');
		expect(state?.message).toContain('scavenger');
	});

	it('says the filters excluded the matches when they did', () => {
		const state = emptinessFor(
			{ ...nothing, searched: true, query: 'scout', excluded: 3 },
			address({ query: 'scout', filters: { status: 'approved' } })
		);

		expect(state?.reason).toBe('filters-excluded');
		expect(state?.message).toContain('3');
		expect(state?.message).toMatch(/filters excluded/);
	});

	it('separates a project with no assets from one whose filters excluded them', () => {
		const filtered = emptinessFor(
			{ ...nothing, searched: false, query: '', excluded: 0 },
			address({ filters: { owner: 'rafa' } }),
			{ anyAssets: true }
		);
		const bare = emptinessFor(
			{ ...nothing, searched: false, query: '', excluded: 0 },
			address(),
			{ anyAssets: false }
		);

		expect(filtered?.reason).toBe('filters-excluded');
		expect(bare?.reason).toBe('no-assets');
		expect(bare?.message).toBe(HOW_AN_ASSET_BEGINS);
		expect(bare?.message).toMatch(/asset\.yaml/);
	});

	it('is not an empty screen at all when there is something to show', () => {
		const view = viewOfListing(listing([row('mech_scout')]));

		expect(emptinessFor(view, address())).toBeNull();
	});
});

describe('what was unavailable is said in words a person can act on', () => {
	function failure(identifier: string, message = 'the surface said so') {
		return { kind: 'unavailable' as const, identifier, message, subject: null, correlationId: null };
	}

	it('names a rebuilding index and warns the results may be incomplete', () => {
		expect(noteFor(failure(INDEX_REBUILDING))).toBe(REBUILDING_NOTE);
		expect(REBUILDING_NOTE).toMatch(/incomplete/);
	});

	it('names an unreachable delegated search and says exact results remain', () => {
		expect(noteFor(failure(DELEGATED_SEARCH))).toBe(DELEGATED_NOTE);
		expect(DELEGATED_NOTE).toMatch(/exact/);
	});

	it('repeats the surface for an unavailability it has never heard of', () => {
		expect(noteFor(failure('something.new', 'the widget is down'))).toBe('the widget is down');
	});
});
