/**
 * The identity service, as this application's server reaches it.
 *
 * Two facts about CyberdyneAuth decide this module. Its endpoints live where its
 * discovery document says (`/api/v1/auth/oauth2/…`), not at the conventional
 * paths a client might guess — guessing is how sign-in reached a 404 in
 * production. And it sends no `Access-Control-Allow-Origin` for this
 * application's origin, so a browser can read neither the discovery document
 * nor a token response. Both are therefore done here, on the server:
 *
 * * the discovery document is read from `<issuer>/.well-known/openid-configuration`,
 *   its `issuer` checked against the configured one, and the result cached;
 * * the token exchange is relayed: the browser posts its form to this
 *   application's origin and the form is forwarded to the discovered token
 *   endpoint. It stays a **public** client's exchange — the proof key is the
 *   browser's, no secret is added, and nothing is kept. The relay forwards the
 *   two grants a browser uses and the fields they need, and sets the client id
 *   itself, so it is not a general-purpose proxy to the issuer.
 *
 * `CANON_AUTH_INTERNAL_URL` is for a server that reaches the issuer at another
 * address than the browser does — the end-to-end stack, where the browser sees
 * `localhost:9000` and this process sees `issuer:9000`. It is the web
 * application's counterpart of the API's `CANON_AUTH_KEY_SET_URL`, and it
 * defaults to the issuer.
 */

import { env as publicEnv } from '$env/dynamic/public';
import { env as privateEnv } from '$env/dynamic/private';

export const DISCOVERY_PATH = '/.well-known/openid-configuration';

/** How long a discovery document is trusted before it is read again. */
export const DISCOVERY_TTL_MS = 10 * 60 * 1000;

const RELAYED_GRANTS: ReadonlySet<string> = new Set(['authorization_code', 'refresh_token']);
const RELAYED_FIELDS = ['grant_type', 'code', 'redirect_uri', 'code_verifier', 'refresh_token'];

export type Environment = Record<string, string | undefined>;

export interface IdentityService {
	/** The issuer identifier, exactly as the discovery document and `iss` state it. */
	readonly issuer: string;
	readonly clientId: string;
	/** Where this process reaches the issuer. The issuer, unless configured otherwise. */
	readonly reachedAt: string;
	/** Whether the identity service has this application's origin registered for post-logout. */
	readonly postLogoutRedirect: boolean;
}

export interface IssuerEndpoints {
	readonly authorization: string;
	readonly token: string;
	readonly endSession: string | null;
}

/** The discovery document could not be read, or does not describe the configured issuer. */
export class DiscoveryFailed extends Error {}

/** The identity service this deployment names, or `null` when it names none. */
export function identityService(values: Environment = environment()): IdentityService | null {
	const issuer = withoutSlash(values.PUBLIC_CANON_AUTH_ISSUER);
	const clientId = values.PUBLIC_CANON_AUTH_CLIENT_ID?.trim();
	if (!issuer || !clientId) return null;
	return {
		issuer,
		clientId,
		reachedAt: withoutSlash(values.CANON_AUTH_INTERNAL_URL) || issuer,
		postLogoutRedirect: /^(1|true|yes)$/i.test(values.CANON_AUTH_POST_LOGOUT_REDIRECT?.trim() ?? '')
	};
}

/**
 * The endpoints a discovery document names, refused unless it names this issuer.
 *
 * The issuer check is OpenID Connect Discovery §4.3: a document that describes
 * some other issuer is not a description of this one, whatever address served it.
 */
export function endpointsFrom(document: unknown, issuer: string): IssuerEndpoints {
	const described = (document ?? {}) as Record<string, unknown>;
	const named = typeof described.issuer === 'string' ? withoutSlash(described.issuer) : '';
	if (named !== issuer) {
		throw new DiscoveryFailed(`the discovery document names issuer "${named}", not "${issuer}"`);
	}
	const authorization = address(described.authorization_endpoint);
	const token = address(described.token_endpoint);
	if (!authorization || !token) {
		throw new DiscoveryFailed('the discovery document names no authorization or token endpoint');
	}
	return { authorization, token, endSession: address(described.end_session_endpoint) };
}

/** Read and check the discovery document. Throws {@link DiscoveryFailed}, and nothing else. */
export async function discover(
	service: IdentityService,
	fetcher: typeof globalThis.fetch
): Promise<IssuerEndpoints> {
	const response = await fetcher(`${service.reachedAt}${DISCOVERY_PATH}`, {
		headers: { Accept: 'application/json' }
	}).catch((failure: unknown) => {
		throw new DiscoveryFailed(`the identity service could not be reached (${reason(failure)})`);
	});
	if (!response.ok) {
		throw new DiscoveryFailed(`the identity service's discovery document answered ${response.status}`);
	}
	return endpointsFrom(await response.json().catch(() => null), service.issuer);
}

/** Discovery, remembered for a while. Only a document that checked out is remembered. */
export class Discovery {
	#held: { issuer: string; endpoints: IssuerEndpoints; until: number } | null = null;
	readonly #now: () => number;

	constructor(now: () => number = () => Date.now()) {
		this.#now = now;
	}

	async endpoints(service: IdentityService, fetcher: typeof globalThis.fetch): Promise<IssuerEndpoints> {
		const held = this.#held;
		if (held && held.issuer === service.issuer && held.until > this.#now()) return held.endpoints;
		const endpoints = await discover(service, fetcher);
		this.#held = { issuer: service.issuer, endpoints, until: this.#now() + DISCOVERY_TTL_MS };
		return endpoints;
	}
}

/** The one cache, for the process. */
export const discovery = new Discovery();

/**
 * The form the relay forwards, or `null` for a grant it does not relay.
 *
 * Only the fields the two browser grants use are copied, and the client id is
 * this deployment's rather than whatever was posted.
 */
export function relayedForm(received: URLSearchParams, clientId: string): Record<string, string> | null {
	const grant = received.get('grant_type');
	if (!grant || !RELAYED_GRANTS.has(grant)) return null;
	const form: Record<string, string> = {};
	for (const name of RELAYED_FIELDS) {
		const value = received.get(name);
		if (value) form[name] = value;
	}
	form.client_id = clientId;
	return form;
}

/** Where this process sends a request for an address the issuer published. */
export function reachable(service: IdentityService, url: string): string {
	if (service.reachedAt === service.issuer || !url.startsWith(service.issuer)) return url;
	return `${service.reachedAt}${url.slice(service.issuer.length)}`;
}

/** The end-session address, with the hints the identity service asks for. */
export function endSessionUrl(
	service: IdentityService,
	endpoint: string,
	options: { idTokenHint: string | null; origin: string }
): string {
	const query = new URLSearchParams({ client_id: service.clientId });
	if (options.idTokenHint) query.set('id_token_hint', options.idTokenHint);
	if (service.postLogoutRedirect) query.set('post_logout_redirect_uri', `${options.origin}/`);
	return `${endpoint}${endpoint.includes('?') ? '&' : '?'}${query}`;
}

export function reason(failure: unknown): string {
	return failure instanceof Error ? failure.message : 'unknown failure';
}

function environment(): Environment {
	return { ...publicEnv, ...privateEnv };
}

function address(value: unknown): string | null {
	return typeof value === 'string' && /^https?:\/\//.test(value) ? value : null;
}

function withoutSlash(value: string | undefined): string {
	return (value ?? '').trim().replace(/\/+$/, '');
}
