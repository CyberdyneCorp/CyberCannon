/**
 * Signing out of the identity service too, not only of this tab.
 *
 * Clearing this application's storage ends *its* session, and on a shared
 * studio machine that was not enough: the identity service's own session
 * survived, so the next person to press "Sign in" was signed straight back in
 * as the previous one. The browser is sent here after its local sign-out, and
 * from here to the end-session endpoint the discovery document names, with the
 * client id and the identity token as the hint.
 *
 * `post_logout_redirect_uri` is added only when `CANON_AUTH_POST_LOGOUT_REDIRECT`
 * says the identity service has this origin registered for it; CyberdyneAuth
 * refuses an unregistered one outright, which would leave the person on an
 * error instead of signed out. Without it the identity service shows its own
 * "signed out" page.
 *
 * When there is nothing to end — no identity service configured, a discovery
 * document that cannot be read, or one naming no end-session endpoint — the
 * person is taken home, already signed out locally.
 */
import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { HOME } from '$lib/session/intent';
import { discovery, endSessionUrl, identityService } from '$lib/server/identity';

export const prerender = false;

export const GET: RequestHandler = async ({ url, fetch }) => {
	const service = identityService();
	const endpoints = service ? await discovery.endpoints(service, fetch).catch(() => null) : null;
	if (!service || !endpoints?.endSession) redirect(303, HOME);
	redirect(
		303,
		endSessionUrl(service, endpoints.endSession, {
			idTokenHint: url.searchParams.get('id_token_hint'),
			origin: url.origin
		})
	);
};
