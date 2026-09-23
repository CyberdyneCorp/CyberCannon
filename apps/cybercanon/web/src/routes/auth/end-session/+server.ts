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
 * The browser **posts** the identity token here, in the body. A query string
 * would put it — a signed token carrying the person's email — into the proxy's
 * and this server's access logs and into browser history, on the way to an
 * identity service that is the only party that needs it. A plain `GET` still
 * signs out, with the client id alone, which CyberdyneAuth accepts.
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

export const POST: RequestHandler = async ({ request, url, fetch }) => {
	const form = await request.formData().catch(() => null);
	const hint = form?.get('id_token_hint');
	return endSession(url, fetch, typeof hint === 'string' && hint ? hint : null);
};

export const GET: RequestHandler = ({ url, fetch }) => endSession(url, fetch, null);

async function endSession(url: URL, fetch: typeof globalThis.fetch, idTokenHint: string | null): Promise<never> {
	const service = identityService();
	const endpoints = service ? await discovery.endpoints(service, fetch).catch(() => null) : null;
	if (!service || !endpoints?.endSession) redirect(303, HOME);
	redirect(303, endSessionUrl(service, endpoints.endSession, { idTokenHint, origin: url.origin }));
}
