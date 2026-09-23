/**
 * The token exchange, relayed from this application's origin to the issuer.
 *
 * CyberdyneAuth answers no cross-origin request from a browser, so a browser
 * that posted its authorization code — or its refresh token — straight to the
 * token endpoint was refused before it could read the answer. The browser posts
 * the same form here instead, and it is forwarded to the token endpoint the
 * discovery document names (`$lib/server/identity`).
 *
 * It is still a public client's exchange. The proof key never leaves the
 * browser, no secret exists to add, and the answer is handed back untouched and
 * uncached; this process keeps nothing. A request from another origin is
 * refused, and only the two grants a browser uses are forwarded.
 *
 * An issuer that cannot be reached is a 502 with an OAuth-shaped body, which the
 * browser reports as an outage rather than as a refusal.
 */
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import {
	discovery,
	identityService,
	reachable,
	reason,
	relayedForm,
	type IdentityService
} from '$lib/server/identity';
import { TEMPORARILY_UNAVAILABLE } from '$lib/session/oidc';

export const prerender = false;

const NO_STORE = { 'Cache-Control': 'no-store' };

export const POST: RequestHandler = async ({ request, url, fetch }) => {
	const service = identityService();
	if (!service) return refusal(404, 'not_configured', 'Sign-in is not configured for this deployment.');
	const origin = request.headers.get('origin');
	if (origin && origin !== url.origin) return refusal(403, 'invalid_request', 'cross-origin request');
	const form = relayedForm(await received(request), service.clientId);
	if (!form) return refusal(400, 'unsupported_grant_type', 'only authorization_code and refresh_token are relayed');
	try {
		return await relay(service, form, fetch);
	} catch (failure) {
		return refusal(502, TEMPORARILY_UNAVAILABLE, reason(failure));
	}
};

async function relay(
	service: IdentityService,
	form: Record<string, string>,
	fetcher: typeof globalThis.fetch
): Promise<Response> {
	const { token } = await discovery.endpoints(service, fetcher);
	const answered = await fetcher(reachable(service, token), {
		method: 'POST',
		headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
		body: new URLSearchParams(form).toString()
	});
	const body = await answered.json().catch(() => ({
		error: 'invalid_response',
		error_description: `the issuer answered ${answered.status}`
	}));
	return json(body, { status: answered.status, headers: NO_STORE });
}

async function received(request: Request): Promise<URLSearchParams> {
	return new URLSearchParams(await request.text().catch(() => ''));
}

function refusal(status: number, code: string, description: string): Response {
	return json({ error: code, error_description: description }, { status, headers: NO_STORE });
}
