/**
 * Where the surface is, and who signs people in. Configuration is
 * environment-only (openspec/project.md).
 *
 * `PUBLIC_CANON_API_URL` is read at build time by SvelteKit's `$env` module; the
 * default is the same origin, which is what a deployment serving both behind
 * one host wants and what the e2e compose stack provides.
 *
 * The identity service is configured the same way and by the same names the API
 * uses, `PUBLIC_`-prefixed because a browser build has to carry them: a public
 * client's issuer, client id and audience are not secrets, and there is no
 * variable here for a client secret because `auth-integration` forbids a
 * browser build from having one.
 *
 * **The identity service's addresses are not configured here.** They are read
 * from its discovery document (`<issuer>/.well-known/openid-configuration`), and
 * that happens on this application's own server (`src/routes/auth/`), because
 * CyberdyneAuth answers no cross-origin request from a browser — neither the
 * discovery document nor the token endpoint. So the browser is handed three
 * addresses on its own origin: one that redirects to the discovered
 * authorization endpoint, one that relays the token exchange, and one that
 * redirects to the discovered end-session endpoint. Fixed paths are how
 * sign-in used to reach a 404 in production.
 *
 * **Absent configuration is a state, not a crash.** A deployment with no issuer
 * configured still serves every screen; sign-in states that it is unavailable,
 * which is what keeps a misconfigured environment debuggable instead of blank.
 */
import { env } from '$env/dynamic/public';
import type { SignInConfig } from '$lib/session/oidc';
import { SIGNED_IN_PATH } from '$lib/session/intent';

export function apiBaseUrl(): string {
	return env.PUBLIC_CANON_API_URL ?? '';
}

/** This application's own relays to the identity service (`src/routes/auth/`). */
export const AUTHORIZE_ROUTE = '/auth/authorize';
export const TOKEN_ROUTE = '/auth/token';
export const END_SESSION_ROUTE = '/auth/end-session';

/** The shape configuration arrives in: names to values, and nothing else. */
export type Environment = Record<string, string | undefined>;

/**
 * How this application signs a person in, or `null` when nobody configured it.
 *
 * The redirect address is derived from the origin the person is actually on
 * rather than configured, so a preview deployment cannot send people back to
 * production by inheriting its value.
 *
 * `values` defaults to the process environment and is a parameter so the
 * mapping can be read against a deployment that is not this one — which is how
 * it is tested, and the same shape `adapters/wiring/configuration.py` uses for
 * the same reason.
 */
export function signInConfiguration(origin: string, values: Environment = env): SignInConfig | null {
	const issuer = trimmed(values.PUBLIC_CANON_AUTH_ISSUER);
	const clientId = trimmed(values.PUBLIC_CANON_AUTH_CLIENT_ID);
	if (!issuer || !clientId) return null;
	const base = origin.replace(/\/+$/, '');
	return {
		endpoints: {
			authorization: `${base}${AUTHORIZE_ROUTE}`,
			token: `${base}${TOKEN_ROUTE}`,
			endSession: `${base}${END_SESSION_ROUTE}`
		},
		clientId,
		redirectUri: `${base}${SIGNED_IN_PATH}`,
		audience: trimmed(values.PUBLIC_CANON_AUTH_AUDIENCE) ?? undefined
	};
}

function trimmed(value: string | undefined): string | null {
	return value && value.trim() ? value.trim() : null;
}
