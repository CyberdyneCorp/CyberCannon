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
 */

import type { LayoutLoad } from './$types';
import { probeApi } from '$api/availability';
import { apiBaseUrl } from '$lib/config';
import { verificationNotice } from '$lib/session/verification';

export const ssr = false;

export const load: LayoutLoad = async ({ fetch }) => {
	const reach = await probeApi(fetch, apiBaseUrl());
	return { verification: verificationNotice(reach) };
};
