/**
 * The browser screen, resolved to one member of the closed set (D6).
 *
 * The route's `load` is three lines and this is the rest of it, out here where
 * it can be run without SvelteKit: it takes the one cache-backed API and an
 * address, and returns a route state. Everything it decides is decided from
 * what the surface answered — the ranking, the filters' meaning, whether an
 * answer was complete — because `asset-browser` forbids this application from
 * having an opinion about any of the three.
 *
 * Two requests are made where one would do, and both are deliberate:
 *
 * * **a query also reads the project's listing**, for two reasons at once. A
 *   search hit carries an identifier, a name and the pass that found it and
 *   nothing else, so the status and the owners `asset-browser` asks a row to
 *   show come from the listing; and where a filter is active, the listing is
 *   what knows which assets it admits, because the search surface takes no
 *   filters. Intersecting two answers keeps the filters' definition in
 *   `asset-lookup`; re-implementing them over the fields a hit happens to carry
 *   would be the second opinion this change exists not to create. (That the
 *   search surface cannot be filtered is a gap in `http-api`, and it is
 *   recorded as one rather than worked around silently.)
 * * **an empty filtered listing asks once more without the filters**, because
 *   *"nothing is here"* and *"you filtered everything out"* are two different
 *   screens and nothing else distinguishes them. It costs one request, only
 *   when the screen is already empty.
 */

import type { BrowserAddress } from '$lib/address';
import { activeFilters } from '$lib/address';
import type {
	ApiResult,
	AssetRow,
	Failure,
	ListingFilters,
	LocationAnswer,
	Page,
	SearchHit
} from '$lib/api';
import { routeStateFor } from '$lib/api';
import { degraded, type RouteState } from '$lib/route-state';
import { screenFor } from '$lib/screen';
import {
	FILTERS_NOT_APPLIED,
	PARTIAL_FILTER_CHECK,
	noteFor,
	servesExactResults
} from './degradation';
import type { BrowserRow, BrowserView } from './results';
import { viewOfListing, viewOfNothing, viewOfOne, viewOfSearch } from './results';
import { emptinessFor, type Evidence } from './screens';
import { noteOf, semanticOf } from './semantic';

/** The surface's maximum page size — what a caller asking for everything gets. */
export const MEMBERSHIP_PAGE_SIZE = 100;

/**
 * The three reads this screen makes, as the only thing it needs from the Model.
 *
 * `CanonApi` satisfies it, which is what the route passes; naming it structurally
 * rather than by the class keeps the browser's decisions runnable against a
 * hand-written answer, and keeps this module from acquiring a second way to
 * reach the network — there is one client and one cache behind all three (D2).
 */
export interface BrowserReads {
	assets(project: string, filters?: ListingFilters): Promise<ApiResult<Page<AssetRow>>>;
	search(project: string, term: string, page?: string | null): Promise<ApiResult<Page<SearchHit>>>;
	locations(project: string, asset: string): Promise<ApiResult<LocationAnswer>>;
}

/** The browser at this address: a listing, or the ranked results of its query. */
export function browserScreen(
	api: BrowserReads,
	address: BrowserAddress
): Promise<RouteState<BrowserView>> {
	return address.query ? searched(api, address) : listed(api, address);
}

// ----------------------------------------------------------------- listing

async function listed(
	api: BrowserReads,
	address: BrowserAddress
): Promise<RouteState<BrowserView>> {
	const listing = await api.assets(address.project, { ...address.filters, page: address.page });
	if (!listing.ok) return refusal(listing.failure);
	const view = viewOfListing(listing.data);
	const evidence = await evidenceFor(api, address, view);
	return screenFor<BrowserView>(
		{ ok: true, data: view, freshness: listing.freshness },
		{ emptiness: (data) => emptinessFor(data, address, evidence) }
	);
}

/**
 * Whether the project has any asset at all — asked only when the screen is empty
 * and a filter is active, because that is the only time the answer changes a
 * word on it.
 */
async function evidenceFor(
	api: BrowserReads,
	address: BrowserAddress,
	view: BrowserView
): Promise<Evidence> {
	const filtered = activeFilters(address).length > 0;
	if (view.rows.length > 0) return { anyAssets: true };
	if (!filtered) return { anyAssets: false };
	const unfiltered = await api.assets(address.project, {});
	return { anyAssets: unfiltered.ok ? unfiltered.data.total > 0 : null };
}

// ------------------------------------------------------------------ search

async function searched(
	api: BrowserReads,
	address: BrowserAddress
): Promise<RouteState<BrowserView>> {
	const hits = await api.search(address.project, address.query, address.page);
	if (!hits.ok) return withoutTheIndex(api, address, hits.failure);
	const wanted = activeFilters(address).length > 0;
	const admitted = await api.assets(address.project, membership(address));
	const listing = admitted.ok ? admitted.data : null;
	const semantic = semanticOf(hits);
	const view = viewOfSearch({
		hits: hits.data,
		admitted: listing,
		filtered: wanted && listing !== null,
		query: address.query,
		semantic
	});
	const answer = { ok: true as const, data: view, freshness: hits.freshness };
	// A delegated half that could not answer is a disclosure, not a failure:
	// `asset-browser` asks for the exact results to still be shown *and* for
	// the screen to say the semantic ones are unavailable. Both, in the
	// surface's own sentence.
	const unavailableSemantic = semantic.available ? [] : [noteOf(semantic)];
	const notes = [...filterNotes(wanted, admitted, listing), ...unavailableSemantic];
	const nothing = emptinessFor(view, address, { anyAssets: null });
	// An empty screen that had something to disclose says both. The empty screens
	// are a closed set and carry no disclosure of their own, so a screen that
	// showed only *"nothing matched"* would be presenting an answer it could not
	// complete as a complete answer — which is the one thing `asset-browser`
	// rules out.
	if (nothing !== null && notes.length > 0) {
		return screenFor<BrowserView>(answer, { unavailable: [nothing.message, ...notes] });
	}
	return screenFor<BrowserView>(answer, { emptiness: () => nothing, unavailable: notes });
}

function membership(address: BrowserAddress) {
	return { ...address.filters, page: null, size: MEMBERSHIP_PAGE_SIZE };
}

/** What could not be established about the filters, said rather than hidden. */
function filterNotes(
	wanted: boolean,
	admitted: ApiResult<Page<AssetRow>>,
	listing: Page<AssetRow> | null
): readonly string[] {
	if (!wanted) return [];
	if (listing === null) {
		const why = admitted.ok ? '' : ` (${noteFor(admitted.failure)})`;
		return [`${FILTERS_NOT_APPLIED}${why}`];
	}
	return listing.next_token === null ? [] : [PARTIAL_FILTER_CHECK];
}

/**
 * What is still answerable when the search itself is unavailable.
 *
 * An exact identifier is: the location answer is served from the working copy
 * for an entry the index already holds, which is what `deployment-operations`
 * means by *"specifications are still served from the working copy"* during a
 * rebuild. Anything else yields no rows — and the screen says what was
 * unavailable either way, because a partial result presented as complete is the
 * one outcome `asset-browser` rules out.
 */
async function withoutTheIndex(
	api: BrowserReads,
	address: BrowserAddress,
	failure: Failure
): Promise<RouteState<BrowserView>> {
	if (!servesExactResults(failure)) return refusal(failure);
	const exact = await api.locations(address.project, address.query);
	const view = exact.ok
		? viewOfOne(rowOfLocation(exact.data), address.query)
		: viewOfNothing(address.query);
	const note = noteFor(failure);
	return degraded(view, [note], note);
}

function rowOfLocation(answer: LocationAnswer): BrowserRow {
	return {
		asset: answer.asset,
		name: answer.name,
		status: answer.status,
		owners: answer.owners,
		disclosure: null
	};
}

// ----------------------------------------------------------------- refusals

/**
 * One failure as the screen it produces.
 *
 * Unavailability is degraded rather than failed — `http-api`'s own vocabulary
 * calls it a precondition unmet *for now* — and it is disclosed in the words
 * :func:`noteFor` gives it, so *"the index is being rebuilt"* reaches the
 * person as a sentence rather than as an identifier.
 */
function refusal(failure: Failure): RouteState<BrowserView> {
	if (failure.kind === 'unavailable') {
		const note = noteFor(failure);
		return degraded<BrowserView>(null, [note], note);
	}
	return routeStateFor<BrowserView>(failure);
}
