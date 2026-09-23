/**
 * The server half of sign-in: discovery, and the three relays under `/auth/`.
 *
 * Two defects found against the real CyberdyneAuth are what this suite is for:
 *
 * * **B2** — the browser built its endpoints from fixed paths (`/authorize`,
 *   `/oauth/token`), and CyberdyneAuth serves them at `/api/v1/auth/oauth2/…`,
 *   so "Sign in" landed on a 404. The endpoints now come from the discovery
 *   document, and every fixture here uses CyberdyneAuth's own paths so a guess
 *   cannot pass.
 * * **W2** — CyberdyneAuth answers no cross-origin request from the
 *   application's origin, so the browser's token exchange failed with *"Failed
 *   to fetch"* even once the path was right. The exchange is now relayed by this
 *   application's server, and it stays a public client's: nothing is added but
 *   the client id, and nothing is kept.
 *
 * No test here opens a socket: every `fetch` is a function this suite writes.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const environment = vi.hoisted(() => ({ values: {} as Record<string, string | undefined> }));

vi.mock('$env/dynamic/public', () => ({
	get env() {
		return environment.values;
	}
}));
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const {
	DISCOVERY_MAX_STALE_MS,
	DISCOVERY_PATH,
	DISCOVERY_TTL_MS,
	Discovery,
	DiscoveryFailed,
	discover,
	endSessionUrl,
	endpointsFrom,
	identityService,
	reachable,
	relayedForm
} = await import('../src/lib/server/identity');
const { GET: authorize } = await import('../src/routes/auth/authorize/+server');
const { POST: token } = await import('../src/routes/auth/token/+server');
const { GET: endSession, POST: endSessionPosted } = await import('../src/routes/auth/end-session/+server');

const ORIGIN = 'https://canon.backend.coolify.cyberdynecorp.ai';
const CLIENT = 'cyb_5UIdba7PWtBo1MmH';

/** A discovery document shaped like CyberdyneAuth's, for an issuer of your choosing. */
function document(issuer: string, overrides: Record<string, unknown> = {}) {
	return {
		issuer,
		authorization_endpoint: `${issuer}/api/v1/auth/oauth2/authorize`,
		token_endpoint: `${issuer}/api/v1/auth/oauth2/token`,
		end_session_endpoint: `${issuer}/api/v1/auth/oauth2/logout`,
		jwks_uri: `${issuer}/.well-known/jwks.json`,
		...overrides
	};
}

interface Call {
	readonly url: string;
	readonly init?: RequestInit;
}

/**
 * The issuer, over a fake `fetch`: its discovery document at the discovery
 * path, and `answer` from its token endpoint.
 */
function issuerAt(
	issuer: string,
	options: { answer?: unknown; status?: number; described?: unknown } = {}
): { fetch: typeof fetch; calls: Call[] } {
	const calls: Call[] = [];
	const fetcher = (async (input: string, init?: RequestInit) => {
		const url = String(input);
		calls.push({ url, init });
		if (url.endsWith(DISCOVERY_PATH)) {
			return Response.json(options.described ?? document(issuer));
		}
		return Response.json(options.answer ?? {}, { status: options.status ?? 200 });
	}) as unknown as typeof fetch;
	return { fetch: fetcher, calls };
}

const unreachable = (async () => {
	throw new TypeError('fetch failed: ECONNREFUSED');
}) as unknown as typeof fetch;

/**
 * An issuer that accepts the connection and never answers: the request only
 * ends when its abort signal fires.
 */
function hangingAt(issuer: string, options: { discovers?: boolean } = {}): typeof fetch {
	return (async (input: string, init?: RequestInit) => {
		if (options.discovers && String(input).endsWith(DISCOVERY_PATH)) return Response.json(document(issuer));
		return new Promise((_resolve, reject) => {
			const signal = init?.signal;
			if (!signal) return; // no timeout at all: hangs for ever, and the test times out
			signal.addEventListener('abort', () => reject(signal.reason));
		});
	}) as unknown as typeof fetch;
}

/** Every issuer timeout, shortened so a test of a hung issuer takes milliseconds. */
function shortTimeouts(): void {
	const original = AbortSignal.timeout.bind(AbortSignal);
	vi.spyOn(AbortSignal, 'timeout').mockImplementation(() => original(20));
}

/** Each test gets its own issuer, so the process-wide discovery cache cannot carry answers between them. */
let issuer = '';
let counter = 0;

beforeEach(() => {
	vi.restoreAllMocks();
	counter += 1;
	issuer = `https://auth-${counter}.cyberdynecorp.ai`;
	environment.values = { PUBLIC_CANON_AUTH_ISSUER: issuer, PUBLIC_CANON_AUTH_CLIENT_ID: CLIENT };
});

/** Where a handler sent the browser, or what it threw. */
async function location(handling: Promise<unknown>): Promise<{ status?: number; location?: string }> {
	try {
		await handling;
		return {};
	} catch (thrown) {
		return thrown as { status?: number; location?: string };
	}
}

describe('reading the identity service’s discovery document', () => {
	it('takes the endpoints from the document rather than guessing paths (B2 regression)', () => {
		const endpoints = endpointsFrom(document('https://auth.example'), 'https://auth.example');

		expect(endpoints).toEqual({
			authorization: 'https://auth.example/api/v1/auth/oauth2/authorize',
			token: 'https://auth.example/api/v1/auth/oauth2/token',
			endSession: 'https://auth.example/api/v1/auth/oauth2/logout'
		});
	});

	it('refuses a document that describes another issuer', () => {
		expect(() => endpointsFrom(document('https://impostor.example'), 'https://auth.example')).toThrow(
			DiscoveryFailed
		);
	});

	it('compares the issuer exactly: a trailing slash in the document is another issuer', () => {
		expect(() => endpointsFrom(document('https://auth.example/'), 'https://auth.example')).toThrow(
			DiscoveryFailed
		);
	});

	it('refuses a document with no token endpoint', () => {
		expect(() =>
			endpointsFrom(document('https://auth.example', { token_endpoint: undefined }), 'https://auth.example')
		).toThrow(DiscoveryFailed);
	});

	it('does without an end-session endpoint, which not every issuer has', () => {
		const endpoints = endpointsFrom(
			document('https://auth.example', { end_session_endpoint: undefined }),
			'https://auth.example'
		);

		expect(endpoints.endSession).toBeNull();
	});

	it('reads the document at the issuer’s well-known address', async () => {
		const { fetch, calls } = issuerAt(issuer);

		await discover(identityService()!, fetch);

		expect(calls[0].url).toBe(`${issuer}/.well-known/openid-configuration`);
	});

	it('fails as DiscoveryFailed, and only as that, when nothing answers', async () => {
		await expect(discover(identityService()!, unreachable)).rejects.toThrow(DiscoveryFailed);
	});

	it('gives up on an issuer that never answers, as DiscoveryFailed (hung issuer regression)', async () => {
		await expect(discover(identityService()!, hangingAt(issuer), 20)).rejects.toThrow(DiscoveryFailed);
	});

	it('bounds every discovery read with a timeout', async () => {
		const { fetch, calls } = issuerAt(issuer);

		await discover(identityService()!, fetch);

		expect(calls[0].init?.signal).toBeInstanceOf(AbortSignal);
	});

	it('shares one read between callers that ask at the same time', async () => {
		const cache = new Discovery(() => 0);
		const { fetch, calls } = issuerAt(issuer);

		await Promise.all([cache.endpoints(identityService()!, fetch), cache.endpoints(identityService()!, fetch)]);

		expect(calls).toHaveLength(1);
	});

	it('keeps using the last good endpoints when reading them again fails, for up to a day', async () => {
		let now = 0;
		const cache = new Discovery(() => now);
		const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
		const first = await cache.endpoints(identityService()!, issuerAt(issuer).fetch);

		now += DISCOVERY_TTL_MS + 1;
		expect(await cache.endpoints(identityService()!, unreachable)).toEqual(first);
		expect(warn).toHaveBeenCalled();

		now = DISCOVERY_MAX_STALE_MS;
		await expect(cache.endpoints(identityService()!, unreachable)).rejects.toThrow(DiscoveryFailed);
	});

	it('remembers a document for a while, and reads it again after', async () => {
		let now = 0;
		const cache = new Discovery(() => now);
		const { fetch, calls } = issuerAt(issuer);

		await cache.endpoints(identityService()!, fetch);
		await cache.endpoints(identityService()!, fetch);
		now += DISCOVERY_TTL_MS + 1;
		await cache.endpoints(identityService()!, fetch);

		expect(calls).toHaveLength(2);
	});
});

describe('how the server names the identity service', () => {
	it('is the issuer without a trailing slash, which is how CyberdyneAuth states it', () => {
		const service = identityService({
			PUBLIC_CANON_AUTH_ISSUER: 'https://auth.backend.coolify.cyberdynecorp.ai/',
			PUBLIC_CANON_AUTH_CLIENT_ID: CLIENT
		});

		expect(service).toMatchObject({
			issuer: 'https://auth.backend.coolify.cyberdynecorp.ai',
			clientId: CLIENT,
			reachedAt: 'https://auth.backend.coolify.cyberdynecorp.ai',
			postLogoutRedirect: false
		});
	});

	it('is nothing when half of it is missing', () => {
		expect(identityService({ PUBLIC_CANON_AUTH_ISSUER: 'https://auth.example' })).toBeNull();
	});

	it('reaches the issuer at an internal address when one is configured', () => {
		const service = identityService({
			PUBLIC_CANON_AUTH_ISSUER: 'http://localhost:9000',
			PUBLIC_CANON_AUTH_CLIENT_ID: 'cybercanon-web',
			CANON_AUTH_INTERNAL_URL: 'http://issuer:9000'
		})!;

		expect(reachable(service, 'http://localhost:9000/oauth/token')).toBe('http://issuer:9000/oauth/token');
		expect(reachable(service, 'https://elsewhere.example/token')).toBe('https://elsewhere.example/token');
	});
});

describe('the form the token relay forwards', () => {
	it('sets this deployment’s client id, whatever was posted', () => {
		const form = relayedForm(
			new URLSearchParams({ grant_type: 'authorization_code', code: 'c', client_id: 'someone-else' }),
			CLIENT
		);

		expect(form).toEqual({ grant_type: 'authorization_code', code: 'c', client_id: CLIENT });
	});

	it('forwards nothing it was not built to forward', () => {
		const form = relayedForm(
			new URLSearchParams({ grant_type: 'refresh_token', refresh_token: 'rt', client_secret: 'x', scope: 'admin' }),
			CLIENT
		);

		expect(form).toEqual({ grant_type: 'refresh_token', refresh_token: 'rt', client_id: CLIENT });
	});

	it('relays no grant a browser does not use', () => {
		expect(relayedForm(new URLSearchParams({ grant_type: 'password' }), CLIENT)).toBeNull();
		expect(relayedForm(new URLSearchParams({ grant_type: 'client_credentials' }), CLIENT)).toBeNull();
	});
});

describe('GET /auth/authorize', () => {
	const query = 'response_type=code&client_id=cyb_5UIdba7PWtBo1MmH&state=the-state&code_challenge=x';

	it('sends the browser to the discovered authorization endpoint, query untouched', async () => {
		const url = new URL(`${ORIGIN}/auth/authorize?${query}`);

		const sent = await location(authorize({ url, fetch: issuerAt(issuer).fetch } as never) as Promise<unknown>);

		expect(sent).toMatchObject({ status: 302, location: `${issuer}/api/v1/auth/oauth2/authorize?${query}` });
	});

	it('returns the person to /signed-in with an outage, not a crash, when discovery fails', async () => {
		const url = new URL(`${ORIGIN}/auth/authorize?${query}&redirect_uri=https://evil.example/`);

		const sent = await location(authorize({ url, fetch: unreachable } as never) as Promise<unknown>);
		const back = new URL(sent.location ?? '', ORIGIN);

		expect(back.origin + back.pathname).toBe(`${ORIGIN}/signed-in`);
		expect(back.searchParams.get('error')).toBe('temporarily_unavailable');
		expect(back.searchParams.get('state')).toBe('the-state');
	});

	it('reports an outage within seconds when the issuer hangs, rather than hanging with it', async () => {
		shortTimeouts();
		const url = new URL(`${ORIGIN}/auth/authorize?${query}`);

		const sent = await location(authorize({ url, fetch: hangingAt(issuer) } as never) as Promise<unknown>);

		expect(new URL(sent.location ?? '', ORIGIN).searchParams.get('error')).toBe('temporarily_unavailable');
	});

	it('refuses to redirect anywhere when no identity service is configured', async () => {
		environment.values = {};

		const sent = await location(
			authorize({ url: new URL(`${ORIGIN}/auth/authorize`), fetch: unreachable } as never) as Promise<unknown>
		);

		expect(sent).toMatchObject({ status: 404 });
	});
});

describe('POST /auth/token (W2 regression)', () => {
	function posted(form: Record<string, string>, headers: Record<string, string> = { origin: ORIGIN }) {
		return new Request(`${ORIGIN}/auth/token`, {
			method: 'POST',
			headers: { 'content-type': 'application/x-www-form-urlencoded', ...headers },
			body: new URLSearchParams(form).toString()
		});
	}

	const exchange = { grant_type: 'authorization_code', code: 'c', code_verifier: 'v', redirect_uri: `${ORIGIN}/signed-in` };

	it('forwards the exchange to the discovered token endpoint and hands the answer back', async () => {
		const answer = { access_token: 'at', id_token: 'it', refresh_token: 'rt', token_type: 'Bearer' };
		const { fetch, calls } = issuerAt(issuer, { answer });

		const response = await token({ request: posted(exchange), url: new URL(`${ORIGIN}/auth/token`), fetch } as never);

		expect(response.status).toBe(200);
		expect(await response.json()).toEqual(answer);
		expect(response.headers.get('cache-control')).toBe('no-store');
		const forwarded = calls.find((call) => call.url === `${issuer}/api/v1/auth/oauth2/token`);
		expect(Object.fromEntries(new URLSearchParams(String(forwarded?.init?.body)))).toEqual({
			...exchange,
			client_id: CLIENT
		});
	});

	it('passes the issuer’s refusal through, status and all', async () => {
		const refusal = { error: 'invalid_grant', error_description: 'authorization code already used' };
		const { fetch } = issuerAt(issuer, { answer: refusal, status: 400 });

		const response = await token({ request: posted(exchange), url: new URL(`${ORIGIN}/auth/token`), fetch } as never);

		expect(response.status).toBe(400);
		expect(await response.json()).toEqual(refusal);
	});

	it('answers 502 temporarily_unavailable when the issuer cannot be reached', async () => {
		const response = await token({
			request: posted(exchange),
			url: new URL(`${ORIGIN}/auth/token`),
			fetch: unreachable
		} as never);

		expect(response.status).toBe(502);
		expect(await response.json()).toMatchObject({ error: 'temporarily_unavailable' });
	});

	it('answers 502 temporarily_unavailable when the token endpoint hangs (hung issuer regression)', async () => {
		shortTimeouts();

		const response = await token({
			request: posted(exchange),
			url: new URL(`${ORIGIN}/auth/token`),
			fetch: hangingAt(issuer, { discovers: true })
		} as never);

		expect(response.status).toBe(502);
		expect(await response.json()).toMatchObject({ error: 'temporarily_unavailable' });
	});

	it('refuses a request from another origin', async () => {
		const { fetch, calls } = issuerAt(issuer);

		const response = await token({
			request: posted(exchange, { origin: 'https://evil.example' }),
			url: new URL(`${ORIGIN}/auth/token`),
			fetch
		} as never);

		expect(response.status).toBe(403);
		expect(calls).toEqual([]);
	});

	it('refuses a grant it does not relay', async () => {
		const { fetch, calls } = issuerAt(issuer);

		const response = await token({
			request: posted({ grant_type: 'password', username: 'u', password: 'p' }),
			url: new URL(`${ORIGIN}/auth/token`),
			fetch
		} as never);

		expect(response.status).toBe(400);
		expect(calls).toEqual([]);
	});
});

describe('/auth/end-session', () => {
	function signOutPosted(fields: Record<string, string>) {
		return new Request(`${ORIGIN}/auth/end-session`, {
			method: 'POST',
			headers: { 'content-type': 'application/x-www-form-urlencoded', origin: ORIGIN },
			body: new URLSearchParams(fields).toString()
		});
	}

	it('sends the browser to the discovered end-session endpoint with the client and the posted hint', async () => {
		const url = new URL(`${ORIGIN}/auth/end-session`);
		const request = signOutPosted({ id_token_hint: 'the-id-token' });

		const sent = await location(
			endSessionPosted({ request, url, fetch: issuerAt(issuer).fetch } as never) as Promise<unknown>
		);
		const target = new URL(sent.location ?? '');

		expect(target.origin + target.pathname).toBe(`${issuer}/api/v1/auth/oauth2/logout`);
		expect(target.searchParams.get('client_id')).toBe(CLIENT);
		expect(target.searchParams.get('id_token_hint')).toBe('the-id-token');
		// CyberdyneAuth refuses an unregistered post-logout address outright.
		expect(target.searchParams.has('post_logout_redirect_uri')).toBe(false);
	});

	it('takes no identity token from the address, which access logs keep (regression)', async () => {
		const url = new URL(`${ORIGIN}/auth/end-session?id_token_hint=the-id-token`);

		const sent = await location(endSession({ url, fetch: issuerAt(issuer).fetch } as never) as Promise<unknown>);
		const target = new URL(sent.location ?? '');

		expect(target.searchParams.get('client_id')).toBe(CLIENT);
		expect(target.searchParams.has('id_token_hint')).toBe(false);
	});

	it('asks to come back only when the deployment says the address is registered', () => {
		const service = { ...identityService()!, postLogoutRedirect: true };

		const target = new URL(endSessionUrl(service, `${issuer}/logout`, { idTokenHint: null, origin: ORIGIN }));

		expect(target.searchParams.get('post_logout_redirect_uri')).toBe(`${ORIGIN}/`);
	});

	it('goes home when there is no end-session endpoint to go to', async () => {
		const described = document(issuer, { end_session_endpoint: undefined });
		const url = new URL(`${ORIGIN}/auth/end-session`);

		const sent = await location(endSession({ url, fetch: issuerAt(issuer, { described }).fetch } as never) as Promise<unknown>);

		expect(sent).toMatchObject({ status: 303, location: '/' });
	});

	it('goes home when the identity service cannot be reached', async () => {
		const sent = await location(
			endSession({ url: new URL(`${ORIGIN}/auth/end-session`), fetch: unreachable } as never) as Promise<unknown>
		);

		expect(sent).toMatchObject({ status: 303, location: '/' });
	});
});
