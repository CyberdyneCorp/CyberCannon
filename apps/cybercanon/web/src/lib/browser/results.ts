/**
 * Tasks 4.1, 4.2 and 4.4 — what the browser screen is, as data.
 *
 * Three rules shape everything here, and all three are `asset-browser`'s:
 *
 * * **the listing shows state without opening an asset** — name, identifier,
 *   status and owners, which is exactly what the surface's listing carries;
 * * **search results appear in the order `asset-lookup` specifies**, and this
 *   application *"SHALL NOT apply its own ranking, re-sorting or relevance
 *   scoring"*. So the hits arrive in order and are only ever *filtered* —
 *   :func:`rowsForSearch` never calls `sort`, and the test suite asserts the
 *   order it produces is the order it was given, reversed input included;
 * * **a partial result is never presented as complete.** Filtering a ranked
 *   result needs to know which assets the filters admit, and the only thing
 *   that knows is the surface's own filtered listing. One page of that listing
 *   may not cover every hit, so when it does not, this module says so rather
 *   than quietly dropping a result it could not check.
 *
 * A search hit carries an identifier, a name and the pass that found it; status
 * and owners come from the listing row for the same asset when there is one.
 * Nothing is invented for a hit with no row: the fields are absent, and the
 * screen states their absence rather than showing a default somebody would read
 * as recorded.
 */

import type { AssetRow, Owner, Page, SearchHit } from '$lib/api';
import type { Disclosure } from './disclosure';
import { disclosureOf } from './disclosure';

/** One line of the browser, whether it came from a listing or from a search. */
export interface BrowserRow {
	readonly asset: string;
	readonly name: string;
	/** The status the listing recorded, or `null` when this row came from a hit alone. */
	readonly status: string | null;
	readonly owners: readonly Owner[] | null;
	/** How it matched, when that was something other than its name or identifier. */
	readonly disclosure: Disclosure | null;
}

/** Everything the browser screen renders, and everything it has to disclose. */
export interface BrowserView {
	readonly rows: readonly BrowserRow[];
	/** What the surface said matched in total, before any filter was applied here. */
	readonly total: number;
	readonly searched: boolean;
	readonly query: string;
	/** How many ranked results the active filters removed — the empty screen's evidence. */
	readonly excluded: number;
	/** Whether more results exist beyond this page, as the surface reported it. */
	readonly more: boolean;
}

export function rowOf(row: AssetRow): BrowserRow {
	return {
		asset: row.asset,
		name: row.name,
		status: row.status,
		owners: row.owners,
		disclosure: null
	};
}

/** The listing screen: the project's assets under the filters that were asked for. */
export function viewOfListing(listing: Page<AssetRow>): BrowserView {
	return {
		rows: listing.items.map(rowOf),
		total: listing.total,
		searched: false,
		query: '',
		excluded: 0,
		more: listing.next_token !== null
	};
}

/**
 * One ranked result joined to what the listing knows about the same asset.
 *
 * The join is by the identifier the specification declares, which is the same
 * key both answers are addressed by — never a name and never a row position.
 */
function rowOfHit(hit: SearchHit, known: ReadonlyMap<string, AssetRow>): BrowserRow {
	const row = known.get(hit.asset);
	return {
		asset: hit.asset,
		name: hit.name,
		status: row?.status ?? null,
		owners: row?.owners ?? null,
		disclosure: disclosureOf(hit.matched)
	};
}

export interface SearchInput {
	readonly hits: Page<SearchHit>;
	/** The filtered listing, which is what says whether a hit is admitted. */
	readonly admitted: Page<AssetRow> | null;
	/** Whether any filter is active; with none, nothing is excluded. */
	readonly filtered: boolean;
	readonly query: string;
}

/**
 * The search screen: the cascade's order, narrowed by the filters and by nothing
 * else.
 *
 * With no filter active every hit is shown, because there is nothing to exclude
 * it. With one active a hit is shown only if the surface's filtered listing
 * contains it — the filters' meaning stays where `asset-lookup` defines it
 * rather than being re-implemented against fields this application happens to
 * have.
 */
export function viewOfSearch(input: SearchInput): BrowserView {
	const known = byAsset(input.admitted);
	const shown = input.filtered
		? input.hits.items.filter((hit) => known.has(hit.asset))
		: input.hits.items;
	return {
		rows: shown.map((hit) => rowOfHit(hit, known)),
		total: input.hits.total,
		searched: true,
		query: input.query,
		excluded: input.hits.items.length - shown.length,
		more: input.hits.next_token !== null
	};
}

/** A single row that was derivable without the index — the degraded search's answer. */
export function viewOfOne(row: BrowserRow, query: string): BrowserView {
	return { rows: [row], total: 1, searched: true, query, excluded: 0, more: false };
}

/** Nothing at all, with the query the person asked, for a screen that must still speak. */
export function viewOfNothing(query: string): BrowserView {
	return { rows: [], total: 0, searched: Boolean(query), query, excluded: 0, more: false };
}

function byAsset(listing: Page<AssetRow> | null): ReadonlyMap<string, AssetRow> {
	return new Map((listing?.items ?? []).map((row) => [row.asset, row]));
}
