/**
 * The first redirect of a sign-in, to wherever the identity service says.
 *
 * The browser built the whole authorization request — the state, the proof-key
 * challenge, the return address — and sends it here because it cannot read the
 * discovery document itself (`$lib/server/identity`). This handler adds nothing
 * and removes nothing: it looks the authorization endpoint up and sends the
 * same query there.
 *
 * When the discovery document cannot be read, the person is returned to
 * `/signed-in` with `temporarily_unavailable` (RFC 6749 §4.1.2.1) and the state
 * they sent, which that screen reports as an outage rather than a crash. The
 * return is always to this application's own `/signed-in`, never to a
 * `redirect_uri` taken from the query, so this address cannot be used to
 * redirect anybody elsewhere.
 */
import { error, redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { SIGNED_IN_PATH } from '$lib/session/intent';
import { TEMPORARILY_UNAVAILABLE } from '$lib/session/oidc';
import { discovery, identityService, reason } from '$lib/server/identity';

export const prerender = false;

export const GET: RequestHandler = async ({ url, fetch }) => {
	const service = identityService();
	if (!service) error(404, 'Sign-in is not configured for this deployment.');
	redirect(302, await destination(url, () => discovery.endpoints(service, fetch)));
};

async function destination(
	url: URL,
	endpoints: () => Promise<{ authorization: string }>
): Promise<string> {
	try {
		const { authorization } = await endpoints();
		return `${authorization}${authorization.includes('?') ? '&' : '?'}${url.searchParams}`;
	} catch (failure) {
		return unavailable(url, reason(failure));
	}
}

function unavailable(url: URL, description: string): string {
	const query = new URLSearchParams({
		error: TEMPORARILY_UNAVAILABLE,
		error_description: `the identity service's configuration could not be read: ${description}`
	});
	const state = url.searchParams.get('state');
	if (state) query.set('state', state);
	return `${SIGNED_IN_PATH}?${query}`;
}
