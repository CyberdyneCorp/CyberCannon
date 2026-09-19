/**
 * Whether the API is reachable, as a route state rather than as an exception.
 *
 * `deployment-operations` requires the application to *"render a state
 * describing the API as unavailable"* while the API is down — and D10 accepts
 * the consequence in one line: *"no top-level load function may throw when the
 * API is down"*. A `fetch` that cannot connect rejects, so exactly one place
 * has to turn that rejection into one of the six route states (D6), and this is
 * it.
 *
 * It probes the API's own open readiness endpoint. That endpoint is
 * unauthenticated and names no project by specification, so probing it leaks
 * nothing and needs no session — and it is the same signal the deployment
 * platform gates on, so the application and the platform cannot disagree about
 * whether the API is up.
 */

import { degraded, content, type RouteState } from '$lib/route-state';
import { degradationOf } from '$lib/session/verification';

export const READINESS_PATH = '/readyz';

export const API = 'The CyberCanon API';

export const UNAVAILABLE_MESSAGE =
	'The API is not answering, so nothing from the canon can be shown right now. ' +
	'This page is up; what it reads from is not.';

export type Fetch = typeof globalThis.fetch;

export interface Reachability {
	readonly reachable: boolean;
	/** What was observed, for a screen that wants to state it. */
	readonly detail: string;
	/**
	 * The dependencies the API reports as degraded, as it named them.
	 *
	 * The readiness answer carries them already (`deployment-operations`), and
	 * one of them — the identity service — is what `web-session` requires the
	 * application to disclose while reads carry on regardless. Reading it here
	 * costs one parse of a body that was fetched anyway; asking a second
	 * endpoint for it would be a second probe that could disagree with the first.
	 */
	readonly degraded?: readonly string[];
}

/** One probe. It resolves whatever happens, and never throws. */
export async function probeApi(fetcher: Fetch, baseUrl: string): Promise<Reachability> {
	const url = `${baseUrl.replace(/\/+$/, '')}${READINESS_PATH}`;
	try {
		const response = await fetcher(url);
		const reported = degradationOf(await body(response));
		return { reachable: response.ok, detail: `${response.status}`, degraded: reported.degraded };
	} catch (failure) {
		return {
			reachable: false,
			detail: failure instanceof Error ? failure.message : 'unreachable',
			degraded: []
		};
	}
}

/** The body, or nothing. A readiness answer that is not JSON is still an answer. */
async function body(response: Response): Promise<unknown> {
	try {
		return await response.json();
	} catch {
		return null;
	}
}

/** The probe as a route state: content when it answered, degraded when it did not. */
export function availabilityState(reach: Reachability): RouteState<Reachability> {
	if (reach.reachable) return content(reach);
	return degraded<Reachability>(null, [API], UNAVAILABLE_MESSAGE);
}

/** What a top-level load returns: a state, never a rejection. */
export async function apiAvailability(
	fetcher: Fetch,
	baseUrl: string
): Promise<RouteState<Reachability>> {
	return availabilityState(await probeApi(fetcher, baseUrl));
}
