/**
 * Task 3.2, end to end through the route that actually does it.
 *
 * `intent.test.ts` proves the address survives the round trip and
 * `oidc.test.ts` proves the exchange carries the proof; what is left — and what
 * the scenario is actually about — is that the route puts the two together:
 * *"a deep link to an asset arrives there after authenticating"*.
 *
 * The identity service this deployment uses is configuration, and configuration
 * in a SvelteKit build is fixed when the build is made. So it is substituted
 * here rather than set: what is being asserted is the route's behaviour given a
 * configured issuer, and `session-routes.test.ts` asserts the other case — an
 * unconfigured deployment, which still serves every screen.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SignInConfig } from '../src/lib/session/oidc';
import type { RouteState } from '../src/lib/route-state';

const ORIGIN = 'https://canon.cyberdynecorp.ai';
const ASSET = '/p/ironwood/a/mech_scout';

const CONFIG = vi.hoisted<SignInConfig>(() => ({
	endpoints: {
		authorization: 'https://auth.cyberdynecorp.ai/authorize',
		token: 'https://auth.cyberdynecorp.ai/oauth/token'
	},
	clientId: 'cybercanon-web',
	redirectUri: 'https://canon.cyberdynecorp.ai/signed-in',
	audience: 'cybercanon'
}));

vi.mock('$lib/config', async (original) => ({
	...(await original<Record<string, unknown>>()),
	signInConfiguration: () => CONFIG
}));

const { load } = await import('../src/routes/signed-in/+page');
const { load: loadSignIn } = await import('../src/routes/sign-in/+page');
const { beginSignIn } = await import('../src/lib/session/oidc');
const { browserStorage } = await import('../src/lib/session/storage');
const { sessionStore } = await import('../src/lib/session/session');
const { REFUSED } = await import('../src/routes/signed-in/+page');
const { mappedPerson } = await import('./support/credentials');

/**
 * What a load returned, or where it sent the person.
 *
 * A `load` that redirects never returns, which is why SvelteKit types one as
 * possibly returning nothing; these two helpers say which of the two happened
 * once, rather than an assertion per line.
 */
async function screen(loading: unknown): Promise<{ state: RouteState<unknown> }> {
	return (await loading) as { state: RouteState<unknown> };
}

async function redirected(
	loading: unknown
): Promise<{ status?: number; location?: string } | null> {
	try {
		await loading;
		return null;
	} catch (thrown) {
		return thrown as { status?: number; location?: string };
	}
}

/** The issuer, as far as a token endpoint goes: one form in, one body out. */
function issuing(body: unknown, status = 200): typeof fetch {
	return (async () =>
		new Response(JSON.stringify(body), {
			status,
			headers: { 'Content-Type': 'application/json' }
		})) as unknown as typeof fetch;
}

async function returning(next: string): Promise<URL> {
	const request = await beginSignIn(CONFIG, { storage: browserStorage(), next });
	const url = new URL(CONFIG.redirectUri);
	url.searchParams.set('code', 'the-code');
	url.searchParams.set('state', request.state);
	return url;
}

beforeEach(() => {
	sessionStore.signOut();
});

afterEach(() => {
	delete (globalThis as { window?: unknown }).window;
});

describe('a deep link through sign-in', () => {
	it('arrives at the asset the person asked for', async () => {
		const url = await returning(ASSET);

		const redirect = await redirected(
			load({ url, fetch: issuing({ access_token: mappedPerson() }) } as never)
		);

		expect(redirect).toMatchObject({ status: 303, location: ASSET });
	});

	it('adopts the credential, so the next screen is read as that person', async () => {
		const url = await returning(ASSET);

		await redirected(load({ url, fetch: issuing({ access_token: mappedPerson() }) } as never));

		expect(sessionStore.isAuthenticated()).toBe(true);
		expect(sessionStore.identity()?.display).toBe('Rafa');
	});

	it('goes to the root when the sign-in was not chasing an address', async () => {
		const url = await returning('/');

		const redirect = await redirected(
			load({ url, fetch: issuing({ access_token: mappedPerson() }) } as never)
		);

		expect(redirect).toMatchObject({ location: '/' });
	});
});

describe('a sign-in that did not work', () => {
	it('says what the issuer said, and signs nobody in', async () => {
		const url = await returning(ASSET);

		const loaded = await screen(
			load({ url, fetch: issuing({ error_description: 'that code was already used' }, 400) } as never)
		);

		expect(loaded.state).toMatchObject({ kind: 'failed', identifier: REFUSED });
		expect(sessionStore.isAuthenticated()).toBe(false);
	});

	it('degrades rather than failing when the issuer cannot be reached', async () => {
		const url = await returning(ASSET);
		const unreachable = (async () => {
			throw new TypeError('fetch failed: ECONNREFUSED');
		}) as unknown as typeof fetch;

		const loaded = await screen(load({ url, fetch: unreachable } as never));

		expect(loaded.state.kind).toBe('degraded');
	});
});

describe('the second window of an in-place re-authentication', () => {
	it('hands the code back to the tab that opened it and signs nobody in itself', async () => {
		const posted: unknown[] = [];
		let closed = false;
		const url = await returning(ASSET);
		(globalThis as { window?: unknown }).window = {
			opener: { postMessage: (message: unknown) => posted.push(message) },
			close: () => {
				closed = true;
			}
		};

		const loaded = await screen(
			load({ url, fetch: issuing({ access_token: mappedPerson() }) } as never)
		);

		expect(loaded.state).toMatchObject({ kind: 'content', data: { relayed: true } });
		expect(posted).toHaveLength(1);
		expect(closed).toBe(true);
		expect(sessionStore.isAuthenticated()).toBe(false);
	});
});

describe('the sign-in screen of a configured deployment', () => {
	it('offers a sign-in that knows where the person was going', async () => {
		const loaded = await screen(
			loadSignIn({ url: new URL(`${ORIGIN}/sign-in?next=${encodeURIComponent(ASSET)}`) } as never)
		);

		expect(loaded.state).toMatchObject({
			kind: 'content',
			data: { next: ASSET, configuration: CONFIG }
		});
	});
});
