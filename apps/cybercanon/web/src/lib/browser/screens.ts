/**
 * Tasks 4.6 and 4.7 — having nothing to show is three different screens.
 *
 * `asset-browser` is explicit that an empty result *"is a screen, not an
 * absence"*, and it names three of them:
 *
 * * **nothing matched** — state the query, and offer to clear any active filter;
 * * **the filters excluded the matches** — a *distinct* screen, because
 *   "nothing is called that" and "something is called that and you told me not
 *   to show it" lead a person to two different next actions;
 * * **this project has no assets yet** — which has to say how one comes to
 *   exist, or the person is left looking for a button that does not exist.
 *
 * Which of the three it is cannot be decided from an empty answer alone, and
 * guessing is how the middle one silently becomes the first. So the caller
 * brings the evidence: how many ranked results the filters removed, and whether
 * the project has any assets at all when nothing was searched for. Both come
 * from the surface; neither is inferred here.
 */

import type { BrowserAddress } from '$lib/address';
import { activeFilters } from '$lib/address';
import type { Empty } from '$lib/route-state';
import { empty } from '$lib/route-state';
import type { BrowserView } from './results';

/**
 * How an asset comes to exist, named on the screen that has none.
 *
 * `asset-spec` puts the specification in the game repository beside the asset,
 * and `canon validate` is what admits it — so this is where an artist or a
 * programmer is actually sent, rather than to a button this application does
 * not have. Creating an asset from the web is `add-model-sheet-2d`'s G3 and is
 * deliberately not claimed here.
 */
export const HOW_AN_ASSET_BEGINS =
	'this project has no assets yet. An asset comes to exist when an asset.yaml ' +
	'is committed beside it in the game repository — `canon validate` checks it, ' +
	'and this browser lists it from the next index build onwards.';

export interface Evidence {
	/** Whether the project has any asset at all, ignoring the filters. `null` when unchecked. */
	readonly anyAssets: boolean | null;
}

/** The empty screen this view means, or `null` when it has something to show. */
export function emptinessFor(
	view: BrowserView,
	address: BrowserAddress,
	evidence: Evidence = { anyAssets: null }
): Empty | null {
	if (view.rows.length > 0) return null;
	const filtered = activeFilters(address).length > 0;
	return view.searched ? searchedNothing(view, filtered) : listedNothing(address, filtered, evidence);
}

function searchedNothing(view: BrowserView, filtered: boolean): Empty {
	if (filtered && view.excluded > 0) {
		return empty(
			'filters-excluded',
			view.query,
			`${view.excluded} asset(s) matched ${quoted(view.query)}, and the active ` +
				'filters excluded every one of them'
		);
	}
	return empty('no-results', view.query, `nothing matched ${quoted(view.query)}`);
}

function listedNothing(address: BrowserAddress, filtered: boolean, evidence: Evidence): Empty {
	if (filtered && evidence.anyAssets !== false) {
		return empty(
			'filters-excluded',
			address.project,
			'this project has assets, and the active filters excluded every one of them'
		);
	}
	return empty('no-assets', address.project, HOW_AN_ASSET_BEGINS);
}

function quoted(query: string): string {
	return query ? `“${query}”` : 'an empty query';
}
