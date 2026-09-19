import type { PageLoad } from './$types';
import { CanonApi } from '$lib/api';
import { readBrowserAddress } from '$lib/address';
import { browserScreen, type BrowserView } from '$lib/browser';
import { apiBaseUrl } from '$lib/config';
import { signedOutScreen } from '$lib/session/guard';
import { sessionStore } from '$lib/session/session';

/**
 * The browser, resolved to one member of the closed set (D6).
 *
 * The filters and the query come from the address and nowhere else (D3), so
 * opening this address again — or someone else opening it — produces the same
 * screen without anything having been synchronised.
 *
 * Nothing is asked of the surface on behalf of a person with no session
 * (`web-session`): the address is kept, the sign-in screen is offered, and no
 * project content is fetched to be leaked.
 *
 * Everything the screen *is* — the listing, the ranked results, which of the
 * three empty screens applies, what was unavailable — is decided by
 * `$lib/browser`, out of reach of SvelteKit and therefore testable without it.
 */
export const load: PageLoad = async ({ params, url, fetch }) => {
	const address = readBrowserAddress(params.project, url);
	const signedOut = signedOutScreen<BrowserView>();
	if (signedOut) return { address, state: signedOut };
	const api = new CanonApi({ baseUrl: apiBaseUrl(), fetch, token: () => sessionStore.token() });
	return { address, state: await browserScreen(api, address) };
};
