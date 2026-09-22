import type { PageLoad } from './$types';
import { CanonApi } from '$lib/api';
import { apiBaseUrl } from '$lib/config';
import { signedOutScreen } from '$lib/session/guard';
import { sessionStore } from '$lib/session/session';
import type { TriageQueue } from '$lib/api';
import { triageAddress, triageScreen } from '$lib/triage';

/**
 * The art director's periodic pass over a project's open feedback.
 *
 * The filters are the address (D3), so a link to *the technical annotations on
 * the mech* opens that and nothing has to be synchronised. Nothing is asked of
 * the surface on behalf of a person with no session (`web-session`).
 *
 * The queue itself is derivable from the repository alone (D11) — an index
 * accelerates it and never answers it — so this screen is as available as the
 * working copy is, and the rows it shows are the same rows `canon` would.
 */
export const load: PageLoad = async ({ params, url, fetch }) => {
	const address = triageAddress(params.project, url);
	const signedOut = signedOutScreen<TriageQueue>();
	if (signedOut) return { address, state: signedOut };
	const api = new CanonApi({ baseUrl: apiBaseUrl(), fetch, token: () => sessionStore.token() });
	return { address, state: await triageScreen(api, address) };
};
