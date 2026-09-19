/**
 * Task 4.8 — a search that could not be served completely says so.
 *
 * `asset-browser`: *"the browser SHALL serve what it can and state what was
 * unavailable. It SHALL NOT present a partial result as complete."* Two causes
 * are named — the index being rebuilt and a delegated search being unreachable
 * — and they are disclosed differently because what survives them differs:
 *
 * * **the index is rebuilding.** The surface answers a listing or a search with
 *   `unavailable` while a project's index is being rebuilt, because either
 *   would be *"incomplete"* — its own words — but *"specifications are still
 *   served from the working copy"*. So what is derivable without the index is
 *   an exact identifier, looked up as a location answer, and that is what the
 *   caller falls back to.
 * * **the delegated semantic search is unreachable.** The local exact results
 *   are unaffected by definition: `semantic-search-delegation` requires that
 *   *"local results SHALL be produced for every query regardless of whether
 *   delegation occurs or succeeds"*. Nothing delegates yet — that capability is
 *   `add-cyberarche-integration` — so the identifier below is the seam the
 *   disclosure will arrive through, and until it does, an unavailability this
 *   module does not recognise is disclosed in the surface's own words rather
 *   than swallowed.
 *
 * Nothing here decides *whether* something was unavailable. That is the API's
 * answer; this only says it in a sentence a person can act on.
 */

import type { Failure } from '$lib/api';

/** `cybercanon.application.use_cases.deployment_status.INDEX_REBUILDING`. */
export const INDEX_REBUILDING = 'index.rebuilding';

/** What a delegated retrieval failure will be identified as (`semantic-search-delegation`). */
export const DELEGATED_SEARCH = 'search.delegated';

export const REBUILDING_NOTE =
	'the index for this project is being rebuilt, so these results may be ' +
	'incomplete; what is shown was derived without it';

export const DELEGATED_NOTE =
	'the delegated semantic search is unavailable, so only exact results are shown';

/**
 * More assets match the filters than one page of the listing could carry.
 *
 * A ranked result can then be neither admitted nor excluded, and the honest
 * answer is to say so — the alternative is dropping a match the filters may
 * well have allowed and calling the remainder complete.
 */
export const PARTIAL_FILTER_CHECK =
	'more assets match these filters than fit one page, so some ranked results ' +
	'could not be checked against them and may be missing';

/** The filters were asked for and could not be established, so they were not applied. */
export const FILTERS_NOT_APPLIED =
	'the active filters could not be applied to these results, so every match is ' +
	'shown and some of them may be ones you filtered out';

/** What was unavailable, named, in the words the person needs. */
export function noteFor(failure: Failure): string {
	if (failure.identifier === INDEX_REBUILDING) return REBUILDING_NOTE;
	if (failure.identifier === DELEGATED_SEARCH) return DELEGATED_NOTE;
	return failure.message;
}

/** Whether this failure is one where the exact, index-free answer is still worth asking for. */
export function servesExactResults(failure: Failure): boolean {
	return failure.kind === 'unavailable';
}
