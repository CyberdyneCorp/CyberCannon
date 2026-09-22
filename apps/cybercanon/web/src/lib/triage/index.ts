/**
 * The art director's pass, as a screen.
 *
 * `annotation-triage` asks for one thing and it is the reason the whole change
 * exists: *"a queue of all open annotations across its assets, filterable by
 * kind, by asset and by discipline owner"*, ordered so that *"feedback repeating
 * across a project rises to the top as a promotion candidate"*.
 *
 * **Nothing here orders anything.** The ordering is the domain's — the
 * same-kind counts, then the reply count, then the age — and a client that
 * re-sorted would be a second opinion about which feedback matters, which is
 * exactly the judgement the pass exists to make. This module reads the address,
 * asks for the queue, and decides which of the closed route states it is.
 *
 * The filters live in the address (D3), so an art director can send somebody a
 * link to *the technical annotations on the mech* and have it open that.
 */

import type { ApiResult, TriageQueue } from '$lib/api';
import type { RouteState } from '$lib/route-state';
import { empty } from '$lib/route-state';
import { screenFor } from '$lib/screen';

/** The three filters the pass uses, as the address carries them. */
export interface TriageAddress {
	readonly project: string;
	readonly kind: string;
	readonly asset: string;
	readonly owner: string;
}

export const TRIAGE_FILTERS = ['kind', 'asset', 'owner'] as const;

/** What the screen needs from the Model, and nothing more. */
export interface TriageReads {
	triage(
		project: string,
		filters: { kind?: string; asset?: string; owner?: string }
	): Promise<ApiResult<TriageQueue>>;
}

export function triageAddress(project: string, url: URL): TriageAddress {
	const read = (name: string) => url.searchParams.get(name)?.trim() ?? '';
	return { project, kind: read('kind'), asset: read('asset'), owner: read('owner') };
}

/** The address a set of filters produces — what a link to this pass looks like. */
export function triageLink(address: TriageAddress): string {
	const parameters = new URLSearchParams();
	for (const name of TRIAGE_FILTERS) {
		const value = address[name];
		if (value) parameters.set(name, value);
	}
	const search = parameters.toString();
	return `/p/${encodeURIComponent(address.project)}/triage${search ? `?${search}` : ''}`;
}

export const NOTHING_OPEN = 'no annotation is open in this project';
export const NOTHING_MATCHED = 'no open annotation matches these filters';

/**
 * The queue as one member of the closed route-state set (D6).
 *
 * Two empty screens rather than one, for the reason `asset-browser` gives about
 * its own: *nothing is here* and *you filtered everything out* are different
 * facts, and a single screen makes the second one look like the first.
 */
export async function triageScreen(
	api: TriageReads,
	address: TriageAddress
): Promise<RouteState<TriageQueue>> {
	const answer = await api.triage(address.project, filtersOf(address));
	return screenFor<TriageQueue>(answer, {
		emptiness: (queue) => emptiness(queue, address),
		unavailable: unreadable(answer)
	});
}

function filtersOf(address: TriageAddress): { kind?: string; asset?: string; owner?: string } {
	return {
		...(address.kind ? { kind: address.kind } : {}),
		...(address.asset ? { asset: address.asset } : {}),
		...(address.owner ? { owner: address.owner } : {})
	};
}

function emptiness(queue: TriageQueue, address: TriageAddress) {
	if (queue.entries.length > 0) return null;
	const filtered = TRIAGE_FILTERS.some((name) => address[name]);
	return filtered
		? empty('filters-excluded', address.kind || address.asset || address.owner, NOTHING_MATCHED)
		: empty('no-results', address.project, NOTHING_OPEN);
}

/**
 * The specifications the queue could not read, disclosed rather than skipped.
 *
 * A queue that quietly omitted an asset would tell an art director the project
 * is clean when one of its files is broken — which is the one thing a pass over
 * open work must not do.
 */
function unreadable(answer: ApiResult<TriageQueue>): readonly string[] {
	if (!answer.ok || answer.data.unreadable.length === 0) return [];
	return answer.data.unreadable.map(
		(path) => `${path} could not be read, so its annotations are not in this queue`
	);
}
