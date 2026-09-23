/**
 * The frame's own data, and the one configuration decision this shell makes.
 *
 * **`ssr = false` is a session decision, not a performance one.** The credential
 * this application acts under is obtained in the browser by an authorization
 * code exchange bound to a proof key generated there (`auth-integration`), and
 * it never reaches the node process that serves the pages. A server render
 * would therefore have to produce every authenticated screen with no
 * credential — signed out, every time — and SvelteKit does not re-run a
 * universal load during hydration, so a signed-in person would be left looking
 * at the sign-out screen their own server render produced. Worse, holding the
 * session in a module singleton on a shared server process is one request
 * reading another person's session.
 *
 * So the application renders in the browser, where the session is. The one
 * server route that remains is `/readyz`, which answers a constant and is
 * unaffected (`deployment-operations`, D10).
 *
 * The load itself asks the API's open readiness endpoint what it can see, for
 * the one thing `web-session` requires the frame to disclose: an identity
 * provider outage, during which reads carry on and re-verification does not.
 * It never throws — the probe resolves whatever happens — so an API that is
 * entirely down produces a frame, not a 500.
 *
 * Before anything is read, a session whose access token is about to lapse is
 * renewed with its refresh token (`$lib/session/renewal`), and the renewal is
 * set to keep doing so while the tab is open. A renewal that fails leaves the
 * session as it was or `expired`, both of which the screens already handle.
 */

import type { LayoutLoad } from './$types';
import { probeApi } from '$api/availability';
import { CanonApi } from '$lib/api';
import { apiBaseUrl, signInConfiguration } from '$lib/config';
import { entitledProjects } from '$lib/projects';
import { SESSION_DEPENDENCY } from '$lib/session/dependency';
import { fetchTransport, refreshSession } from '$lib/session/oidc';
import type { Refresher } from '$lib/session/renewal';
import { sessionRenewal } from '$lib/session';
import { sessionStore } from '$lib/session/session';
import { verificationNotice } from '$lib/session/verification';

export const ssr = false;

export const load: LayoutLoad = async ({ fetch, depends }) => {
	depends(SESSION_DEPENDENCY);
	// The page's own origin, rather than `url`: reading `url` would re-run this
	// load, and its API probe, on every navigation.
	await keepSessionFresh(globalThis.location?.origin);
	const reach = await probeApi(fetch, apiBaseUrl());
	return {
		verification: verificationNotice(reach),
		projects: await switchableProjects(fetch)
	};
};

/** Renew now if due, and keep renewing while the tab is open. */
async function keepSessionFresh(origin: string | undefined): Promise<void> {
	const configuration = origin ? signInConfiguration(origin) : null;
	if (!configuration) return;
	const transport = fetchTransport(globalThis.fetch);
	const refresh: Refresher = (token) => refreshSession(configuration, token, transport);
	sessionRenewal.watch(refresh);
	await sessionRenewal.ensureFresh(refresh);
}

/**
 * The projects the switcher offers, and nothing while nobody is signed in.
 *
 * `web-session` allows an unauthenticated person *"no project or asset
 * content"*, and a list of project names is exactly that — so the frame does
 * not ask. A person who is signed in gets the projects the surface says they
 * may read, and an unreachable surface gets none: the switcher then offers only
 * where they already are, which is the degradation `deployment-operations`
 * asks for rather than a frame that fails to render.
 */
async function switchableProjects(fetch: typeof globalThis.fetch): Promise<readonly string[]> {
	if (!sessionStore.isAuthenticated()) return [];
	const api = new CanonApi({ baseUrl: apiBaseUrl(), fetch, token: () => sessionStore.token() });
	// A surface that never answered makes `fetch` throw rather than resolve.
	const status = await api.status().catch(() => null);
	return status ? entitledProjects(status) : [];
}
