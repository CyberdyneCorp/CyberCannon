/**
 * Task 7.2 — every screen in the closed route-state set, enumerated per route.
 *
 * Task 1.4 asserted the set is closed: nothing but the six is a route state and
 * a screen that handles the six handles everything (`route-state.test.ts`).
 * That is a claim about the *type*. It says nothing about whether the browser
 * can actually produce a `not-found`, or whether the asset page has a screen
 * for a `degraded` answer — and "I looked and they are all there" is exactly
 * the inspection D6 exists to replace.
 *
 * So this suite enumerates, per route, which members of the set that route can
 * resolve to, and it does it three ways at once:
 *
 * 1. **The table is total.** Every route declares all six members — each one
 *    either a driver that makes the route produce it, or a recorded reason it
 *    cannot occur there. A member left out fails to type; a seventh member
 *    would fail every entry at once.
 * 2. **Each driver runs the real `load`.** The kind is what the route actually
 *    returned for a real surface answer, never a state handed to a renderer. A
 *    route that lost its not-found path fails here rather than in review.
 * 3. **Each produced state is rendered by the route's own component**, and the
 *    markup has to carry that state's screen. A state a route can reach and no
 *    screen renders is the omission this task is about.
 *
 * And across the table: the union of what the routes can produce is the whole
 * set, so no member of D6's closed set is a screen nobody built.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';
import type { Component } from 'svelte';
import type { SignInConfig } from '../src/lib/session/oidc';
import type { RouteState, RouteStateKind } from '../src/lib/route-state';
import { ROUTE_STATES, isRouteState } from '../src/lib/route-state';
import { SURFACE_VERSION } from '../src/lib/api/types';

/** Any of the route components, seen only as "takes the route's `data`". */
type RouteComponent = Component<{ data: Record<string, unknown> }>;

const ORIGIN = 'https://canon.cyberdynecorp.ai';
const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const ASSET_ADDRESS = `/p/${PROJECT}/a/${ASSET}`;

/**
 * The identity service, substituted rather than set.
 *
 * Configuration in a SvelteKit build is fixed when the build is made
 * (`signed-in.test.ts` says the same thing for the same reason), and both the
 * sign-in screens need it present for one state and absent for another.
 */
const CONFIGURED = vi.hoisted<SignInConfig>(() => ({
	endpoints: {
		authorization: 'https://auth.cyberdynecorp.ai/authorize',
		token: 'https://auth.cyberdynecorp.ai/oauth/token'
	},
	clientId: 'cybercanon-web',
	redirectUri: `https://canon.cyberdynecorp.ai/signed-in`,
	audience: 'cybercanon'
}));

const identity = vi.hoisted(() => ({ configured: true }));

vi.mock('$lib/config', async (original) => ({
	...(await original<Record<string, unknown>>()),
	signInConfiguration: () => (identity.configured ? CONFIGURED : null)
}));

/** The one thing a component cannot have outside a request (`$app/state`). */
vi.mock('$app/state', () => ({ page: { url: new URL(`${ORIGIN}${ASSET_ADDRESS}`) } }));

const { load: loadRoot } = await import('../src/routes/+page');
const { load: loadBrowser } = await import('../src/routes/p/[project]/assets/+page');
const { load: loadAsset } = await import('../src/routes/p/[project]/a/[asset]/+page');
const { load: loadSignIn } = await import('../src/routes/sign-in/+page');
const { load: loadSignedIn } = await import('../src/routes/signed-in/+page');

const RootScreen = (await import('../src/routes/+page.svelte')).default;
const BrowserScreen = (await import('../src/routes/p/[project]/assets/+page.svelte')).default;
const AssetScreen = (await import('../src/routes/p/[project]/a/[asset]/+page.svelte')).default;
const SignInScreen = (await import('../src/routes/sign-in/+page.svelte')).default;
const SignedInScreen = (await import('../src/routes/signed-in/+page.svelte')).default;

const { sessionStore } = await import('../src/lib/session/session');
const { queryCache } = await import('../src/lib/api/cache');
const { mappedPerson } = await import('./support/credentials');

// --------------------------------------------------------------- the surface

/** One answer from `http-api`, in the envelope the client reads. */
function envelope(data: unknown, mayBeStale = false): Record<string, unknown> {
	return {
		version: SURFACE_VERSION,
		revision: 'abc123',
		confirmed_at: '2026-09-19T10:00:00+00:00',
		may_be_stale: mayBeStale,
		data
	};
}

function refusal(id: string, kind: string, message: string): Record<string, unknown> {
	return { error: { id, kind, message, subject: ASSET } };
}

const LISTING = (items: readonly unknown[]) =>
	envelope({ items, next_token: null, page_size: 50, total: items.length });

const ROW = { asset: ASSET, name: 'Mech Scout', status: 'approved', owners: [] };

const LOCATIONS = envelope({
	asset: ASSET,
	name: 'Mech Scout',
	status: 'approved',
	project: PROJECT,
	locations: [
		{ label: 'directory', value: `characters/${ASSET}`, recorded: true },
		{ label: 'source file', value: 'not recorded', recorded: false },
		{ label: 'latest validated export', value: 'not recorded', recorded: false },
		{ label: 'validated', value: 'not recorded', recorded: false },
		{ label: 'engine path', value: 'not recorded', recorded: false },
		{ label: 'discussion', value: 'not recorded', recorded: false },
		{ label: 'design document', value: 'not recorded', recorded: false }
	],
	owners: [],
	stale: false,
	notice: ''
});

const SPEC = envelope({
	asset: ASSET,
	source: `characters/${ASSET}/asset.yaml`,
	lens: null,
	body: '',
	full: `# ${ASSET} — Mech Scout\n\n## Engineering constraints — authored by engineering\n\n- **Triangle budget**: 12000\n`,
	notice: ''
});

const DOCUMENTS = envelope({
	project: PROJECT,
	asset: ASSET,
	path: `characters/${ASSET}/asset.yaml`,
	available: false,
	reason: 'unconfigured',
	guidance: 'Checkable statements belong in the specification; rationale in the document.',
	links: []
});

type Answer = { readonly status: number; readonly body: Record<string, unknown> };

/** A surface that answers by path, so one route's reads cannot answer another's. */
function surface(answer: (path: string) => Answer): typeof fetch {
	return (async (url: string) => {
		const answered = answer(String(url));
		return new Response(JSON.stringify(answered.body), {
			status: answered.status,
			headers: { 'Content-Type': 'application/json' }
		});
	}) as unknown as typeof fetch;
}

/** A surface nobody is allowed to call: calling it is the failure being tested. */
const unreachable: typeof fetch = (async (url: string) => {
	throw new Error(`asked the surface for ${url}`);
}) as unknown as typeof fetch;

function ok(body: Record<string, unknown>): Answer {
	return { status: 200, body };
}

function refused(status: number, body: Record<string, unknown>): Answer {
	return { status, body };
}

function assetAnswers(over: Partial<Record<'locations' | 'spec', Answer>> = {}) {
	return (path: string): Answer => {
		if (path.includes('/locations')) return over.locations ?? ok(LOCATIONS);
		if (path.includes('/validations')) return ok(envelope(null));
		if (path.includes('/documents')) return ok(DOCUMENTS);
		return over.spec ?? ok(SPEC);
	};
}

// ------------------------------------------------------------- driving a route

interface Loaded {
	readonly state: RouteState<unknown>;
	readonly [key: string]: unknown;
}

async function loaded(loading: unknown): Promise<Loaded> {
	return (await loading) as Loaded;
}

function signedIn(): void {
	sessionStore.signIn(mappedPerson({ exp: Math.floor(Date.now() / 1000) + 3600 }));
}

function browserEvent(fetcher: typeof fetch, query = ''): never {
	return {
		params: { project: PROJECT },
		url: new URL(`${ORIGIN}/p/${PROJECT}/assets${query}`),
		fetch: fetcher
	} as never;
}

function assetEvent(fetcher: typeof fetch): never {
	return {
		params: { project: PROJECT, asset: ASSET },
		url: new URL(`${ORIGIN}${ASSET_ADDRESS}`),
		fetch: fetcher
	} as never;
}

/**
 * How a route reaches one member of the closed set, or why it cannot.
 *
 * A string is a recorded reason — reviewed like any other exception — and a
 * function is a driver that runs the route's real `load` and returns what it
 * returned, so the kind under test is the kind the route produced.
 */
type Reachable = () => Promise<Loaded>;
type Entry = Reachable | string;

interface RouteUnderTest {
	/** The address, for a failure message a person can act on. */
	readonly address: string;
	readonly component: RouteComponent;
	/** Every member of the set, each reachable or explicitly not. */
	readonly states: Readonly<Record<RouteStateKind, Entry>>;
	/** What the rendered screen must carry when this route has content. */
	readonly contentMarker: string;
	/** Anything the component needs besides the state. */
	readonly props?: Record<string, unknown>;
}

const NO_EMPTINESS =
	'nothing about this route can be empty: it shows one answer, and an absent ' +
	'part of it is stated in place rather than replacing the screen';

const ROUTES: readonly RouteUnderTest[] = [
	{
		address: '/',
		component: RootScreen as unknown as RouteComponent,
		contentMarker: `data-project="${PROJECT}"`,
		props: { projects: [PROJECT] },
		states: {
			content: async () => {
				signedIn();
				return loaded(loadRoot({ fetch: surface(() => ok({})) } as never));
			},
			degraded: () => loaded(loadRoot({ fetch: unreachable } as never)),
			empty: NO_EMPTINESS,
			forbidden:
				'the root address reads nothing on anybody’s behalf, so the surface ' +
				'has nothing to refuse; being signed out is content here, not a refusal',
			'not-found': 'there is one root address and it always exists',
			failed:
				'the probe resolves whatever happens (D10), so an unreachable API is ' +
				'degraded rather than failed'
		}
	},
	{
		address: '/p/[project]/assets',
		component: BrowserScreen as unknown as RouteComponent,
		contentMarker: ASSET,
		states: {
			content: async () => {
				signedIn();
				return loaded(loadBrowser(browserEvent(surface(() => ok(LISTING([ROW]))))));
			},
			empty: async () => {
				signedIn();
				return loaded(loadBrowser(browserEvent(surface(() => ok(LISTING([]))))));
			},
			degraded: async () => {
				signedIn();
				return loaded(
					loadBrowser(
						browserEvent(surface(() => ok({ ...LISTING([ROW]), may_be_stale: true })))
					)
				);
			},
			forbidden: async () => {
				sessionStore.signOut();
				return loaded(loadBrowser(browserEvent(unreachable)));
			},
			'not-found': async () => {
				signedIn();
				return loaded(
					loadBrowser(
						browserEvent(
							surface(() =>
								refused(404, refusal('project.unknown', 'not_found', 'no such project'))
							)
						)
					)
				);
			},
			failed: async () => {
				signedIn();
				return loaded(
					loadBrowser(
						browserEvent(
							surface(() => refused(409, refusal('write.conflict', 'conflict', 'it moved')))
						)
					)
				);
			}
		}
	},
	{
		address: '/p/[project]/a/[asset]',
		component: AssetScreen as unknown as RouteComponent,
		contentMarker: 'Mech Scout',
		states: {
			content: async () => {
				signedIn();
				return loaded(loadAsset(assetEvent(surface(assetAnswers()))));
			},
			degraded: async () => {
				signedIn();
				return loaded(
					loadAsset(
						assetEvent(
							surface(
								assetAnswers({
									locations: refused(
										503,
										refusal('index.rebuilding', 'unavailable', 'the index is being rebuilt')
									)
								})
							)
						)
					)
				);
			},
			forbidden: async () => {
				sessionStore.signOut();
				return loaded(loadAsset(assetEvent(unreachable)));
			},
			'not-found': async () => {
				signedIn();
				return loaded(
					loadAsset(
						assetEvent(
							surface(
								assetAnswers({
									locations: refused(404, refusal('asset.unknown', 'not_found', 'no such asset'))
								})
							)
						)
					)
				);
			},
			failed: async () => {
				signedIn();
				return loaded(
					loadAsset(
						assetEvent(
							surface(
								assetAnswers({
									locations: refused(409, refusal('spec.conflict', 'conflict', 'it moved'))
								})
							)
						)
					)
				);
			},
			empty: NO_EMPTINESS
		}
	},
	{
		address: '/sign-in',
		component: SignInScreen as unknown as RouteComponent,
		contentMarker: 'Sign in with CyberdyneAuth',
		states: {
			content: async () => {
				identity.configured = true;
				return loaded(loadSignIn({ url: new URL(`${ORIGIN}/sign-in`) } as never));
			},
			degraded: async () => {
				identity.configured = false;
				return loaded(loadSignIn({ url: new URL(`${ORIGIN}/sign-in`) } as never));
			},
			empty: NO_EMPTINESS,
			forbidden: 'this screen is what a refusal offers; it cannot refuse in turn',
			'not-found': 'there is one sign-in address and it always exists',
			failed:
				'it reads nothing from the canon, so there is nothing here that can ' +
				'fail — an unconfigured deployment is degraded, not broken'
		}
	},
	{
		address: '/signed-in',
		component: SignedInScreen as unknown as RouteComponent,
		contentMarker: 'This window can be closed',
		states: {
			content: async () => {
				identity.configured = true;
				const closed: string[] = [];
				(globalThis as { window?: unknown }).window = {
					opener: { postMessage: () => undefined },
					close: () => closed.push('closed')
				};
				try {
					return await loaded(
						loadSignedIn({
							url: new URL(`${ORIGIN}/signed-in?code=the-code&state=s`),
							fetch: unreachable
						} as never)
					);
				} finally {
					delete (globalThis as { window?: unknown }).window;
				}
			},
			failed: async () => {
				identity.configured = true;
				return loaded(
					loadSignedIn({
						url: new URL(`${ORIGIN}/signed-in?error=access_denied`),
						fetch: unreachable
					} as never)
				);
			},
			degraded: async () => {
				identity.configured = false;
				return loaded(
					loadSignedIn({ url: new URL(`${ORIGIN}/signed-in`), fetch: unreachable } as never)
				);
			},
			empty: NO_EMPTINESS,
			forbidden: 'nobody is refused here: this address is the answer to a sign-in',
			'not-found': 'there is one return address and it always exists'
		}
	}
];

function drivers(route: RouteUnderTest): readonly RouteStateKind[] {
	return ROUTE_STATES.filter((kind) => typeof route.states[kind] === 'function');
}

function body(route: RouteUnderTest, data: Loaded): string {
	return render(route.component, {
		props: { data: { ...route.props, ...data } }
	}).body;
}

beforeEach(() => {
	sessionStore.signOut();
	queryCache.clear();
	identity.configured = true;
});

// --------------------------------------------------------------------------
// The table is total, and it is the whole set
// --------------------------------------------------------------------------

describe('every route accounts for every member of the closed set', () => {
	it.each(ROUTES.map((route) => [route.address, route] as const))(
		'%s names all six',
		(_address, route) => {
			expect(Object.keys(route.states).sort()).toEqual([...ROUTE_STATES].sort());
		}
	);

	it.each(ROUTES.map((route) => [route.address, route] as const))(
		'%s records why each unreachable member cannot occur',
		(_address, route) => {
			for (const kind of ROUTE_STATES) {
				const entry = route.states[kind];
				if (typeof entry === 'function') continue;
				expect(entry.length, `${route.address} gives no reason for ${kind}`).toBeGreaterThan(20);
			}
		}
	);

	it('implements a screen for every member somewhere in the application', () => {
		const reachable = new Set(ROUTES.flatMap((route) => drivers(route)));

		expect([...reachable].sort()).toEqual([...ROUTE_STATES].sort());
	});
});

// --------------------------------------------------------------------------
// Each declared state is what the route really produces, and it renders
// --------------------------------------------------------------------------

const CASES = ROUTES.flatMap((route) =>
	drivers(route).map((kind) => [`${route.address} → ${kind}`, route, kind] as const)
);

describe('each route resolves to the state it declares, and renders it', () => {
	it.each(CASES)('%s', async (_name, route, kind) => {
		const data = await (route.states[kind] as Reachable)();

		expect(isRouteState(data.state)).toBe(true);
		expect(data.state.kind).toBe(kind);
	});

	it.each(CASES)('%s has a screen', async (_name, route, kind) => {
		const data = await (route.states[kind] as Reachable)();
		const markup = body(route, data);

		if (kind === 'content') {
			expect(markup).toContain(route.contentMarker);
			return;
		}
		expect(markup).toContain(`data-state="${kind}"`);
		expect(markup).toMatch(/<h2>[^<]+<\/h2>/);
	});
});
