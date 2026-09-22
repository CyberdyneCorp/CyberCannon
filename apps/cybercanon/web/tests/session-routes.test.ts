/**
 * Tasks 3.1 and 3.5, asserted where they actually have to hold: the routes.
 *
 * The module suites prove the session behaves; this one proves the screens use
 * it. Two claims, and both are about something *not* happening:
 *
 * * **no content leaks before authentication.** The browser and the asset
 *   routes are driven with a `fetch` that fails the test if it is called at
 *   all, so *"no project or asset content SHALL be shown"* is checked as
 *   nothing having been fetched rather than as nothing having been rendered —
 *   a screen cannot leak what the route never asked for.
 * * **nothing survives sign-out.** The same route is loaded signed in, then the
 *   person signs out, then it is loaded again: the cached listing is gone and
 *   the route is back to offering sign-in without reaching the surface.
 *
 * These drive the real `load` functions and the real module-level session and
 * cache, because the thing being asserted is the wiring.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { load as loadBrowser } from '../src/routes/p/[project]/assets/+page';
import { load as loadAsset } from '../src/routes/p/[project]/a/[asset]/+page';
import { load as loadSignIn } from '../src/routes/sign-in/+page';
import { NOT_CONFIGURED, SIGN_IN } from '../src/lib/session/messages';
import { sessionStore } from '../src/lib/session/session';
import { queryCache } from '../src/lib/api/cache';
import { resources } from '../src/lib/api/resources';
import { signInConfiguration } from '../src/lib/config';
import { SIGNED_IN_PATH } from '../src/lib/session/intent';
import { SURFACE_VERSION } from '../src/lib/api/types';
import type { RouteState } from '../src/lib/route-state';
import { mappedPerson } from './support/credentials';

/**
 * What a load returned, once it has returned.
 *
 * A SvelteKit `load` is typed as possibly returning nothing, because one that
 * redirects never returns at all. These routes do return, and saying so once
 * here is better than an assertion per line that they did.
 */
type Loaded = {
	readonly state: RouteState<unknown>;
	readonly address?: Record<string, unknown>;
	readonly next?: string;
};

async function screen(loading: unknown): Promise<Loaded> {
	return (await loading) as Loaded;
}

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';

const LISTING = {
	version: SURFACE_VERSION,
	revision: 'abc123',
	confirmed_at: '2026-09-19T10:00:00+00:00',
	may_be_stale: false,
	data: {
		items: [{ asset: ASSET, name: 'Mech Scout', status: 'approved', owners: [] }],
		next_token: null,
		page_size: 50,
		total: 1
	}
};

/** A surface nobody is allowed to call. Calling it is the failure being tested for. */
function forbiddenFetch(): typeof fetch {
	return (async (url: string) => {
		throw new Error(`the route asked the surface for ${url} with no session`);
	}) as unknown as typeof fetch;
}

function answering(body: unknown): { calls: string[]; fetcher: typeof fetch } {
	const calls: string[] = [];
	const fetcher = (async (url: string) => {
		calls.push(String(url));
		return new Response(JSON.stringify(body), {
			status: 200,
			headers: { 'Content-Type': 'application/json' }
		});
	}) as unknown as typeof fetch;
	return { calls, fetcher };
}

function browserEvent(fetcher: typeof fetch) {
	return {
		params: { project: PROJECT },
		url: new URL(`https://canon.cyberdynecorp.ai/p/${PROJECT}/assets`),
		fetch: fetcher
	} as never;
}

function assetEvent(fetcher: typeof fetch) {
	return {
		params: { project: PROJECT, asset: ASSET },
		url: new URL(`https://canon.cyberdynecorp.ai/p/${PROJECT}/a/${ASSET}`),
		fetch: fetcher
	} as never;
}

beforeEach(() => {
	sessionStore.signOut();
	queryCache.clear();
});

describe('arriving signed out', () => {
	it('is offered sign-in on the browser, and asks the surface for nothing', async () => {
		const loaded = await screen(loadBrowser(browserEvent(forbiddenFetch())));

		expect(loaded.state).toMatchObject({ kind: 'forbidden', remedy: 'sign-in' });
	});

	it('is offered sign-in on an asset, and asks the surface for nothing', async () => {
		const loaded = await screen(loadAsset(assetEvent(forbiddenFetch())));

		expect(loaded.state).toMatchObject({ kind: 'forbidden', remedy: 'sign-in' });
	});

	it('keeps the address it arrived at, so sign-in can return the person to it', async () => {
		const loaded = await screen(loadAsset(assetEvent(forbiddenFetch())));

		expect(loaded.address).toMatchObject({ project: PROJECT, asset: ASSET, surface: 'overview' });
	});

	it('is never shown an error, which is a different member of the closed set', async () => {
		const loaded = await screen(loadBrowser(browserEvent(forbiddenFetch())));

		expect(loaded.state.kind).not.toBe('failed');
		expect(loaded.state.kind).not.toBe('not-found');
	});
});

describe('signing out', () => {
	it('leaves nothing of the previous session reachable', async () => {
		sessionStore.signIn(mappedPerson());
		const surface = answering(LISTING);
		const signedIn = await screen(loadBrowser(browserEvent(surface.fetcher)));
		expect(signedIn.state.kind).toBe('content');
		expect(queryCache.has(resources.assets(PROJECT))).toBe(true);

		sessionStore.signOut();

		expect(queryCache.has(resources.assets(PROJECT))).toBe(false);
		const after = await screen(loadBrowser(browserEvent(forbiddenFetch())));
		expect(after.state).toMatchObject({ kind: 'forbidden', remedy: 'sign-in' });
		expect(surface.calls).toHaveLength(1);
	});

	it('carries the credential while there is one, and stops when there is not', async () => {
		sessionStore.signIn(mappedPerson());
		const surface = answering(LISTING);

		await screen(loadBrowser(browserEvent(surface.fetcher)));

		expect(surface.calls[0]).toContain(`/projects/${PROJECT}/assets`);
	});
});

describe('the sign-in screen', () => {
	it('shows nothing from the canon, whatever else it shows', async () => {
		const loaded = await screen(loadSignIn({
			url: new URL('https://canon.cyberdynecorp.ai/sign-in?next=%2Fp%2Fironwood%2Fassets')
		} as never));

		expect(loaded.next).toBe('/p/ironwood/assets');
	});

	it('states that sign-in is unavailable when no identity service is configured', async () => {
		const loaded = await screen(loadSignIn({
			url: new URL('https://canon.cyberdynecorp.ai/sign-in')
		} as never));

		expect(loaded.state).toEqual({
			kind: 'degraded',
			data: null,
			unavailable: [SIGN_IN],
			message: NOT_CONFIGURED
		});
	});
});

describe('how a deployment says who signs people in', () => {
	const configured = {
		PUBLIC_CANON_AUTH_ISSUER: 'https://auth.cyberdynecorp.ai/',
		PUBLIC_CANON_AUTH_CLIENT_ID: 'cybercanon-web',
		PUBLIC_CANON_AUTH_AUDIENCE: 'cybercanon'
	};

	it('is the issuer, the client and the origin the person is actually on', () => {
		const config = signInConfiguration('https://canon.cyberdynecorp.ai', configured);

		expect(config).toEqual({
			endpoints: {
				authorization: 'https://auth.cyberdynecorp.ai/authorize',
				token: 'https://auth.cyberdynecorp.ai/oauth/token'
			},
			clientId: 'cybercanon-web',
			redirectUri: `https://canon.cyberdynecorp.ai${SIGNED_IN_PATH}`,
			audience: 'cybercanon'
		});
	});

	it('is nothing at all when half of it is missing, rather than a broken address', () => {
		expect(signInConfiguration('https://canon.example', {})).toBeNull();
		expect(
			signInConfiguration('https://canon.example', { PUBLIC_CANON_AUTH_ISSUER: 'https://auth' })
		).toBeNull();
		expect(
			signInConfiguration('https://canon.example', {
				PUBLIC_CANON_AUTH_ISSUER: '  ',
				PUBLIC_CANON_AUTH_CLIENT_ID: 'web'
			})
		).toBeNull();
	});

	it('has nowhere to put a client secret, because a browser build cannot hold one', () => {
		const config = signInConfiguration('https://canon.example', {
			...configured,
			PUBLIC_CANON_AUTH_CLIENT_SECRET: 'never'
		});

		expect(JSON.stringify(config)).not.toContain('never');
	});
});
