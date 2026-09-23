/**
 * Credentials for the session suites — signed by nobody, and deliberately so.
 *
 * The application never verifies a token; the API does, against the issuer's
 * published keys (`auth-integration`). What this application does with a
 * credential is carry it and read three claims out of it, so a credential in a
 * test is a payload with a header and a signature that are never looked at. A
 * suite that reached for a real signing key here would be testing CyberdyneAuth.
 */

export interface TestClaims {
	readonly sub?: string;
	readonly name?: string;
	readonly email?: string;
	readonly git_emails?: readonly string[];
	readonly exp?: number;
	readonly [claim: string]: unknown;
}

export function credential(claims: TestClaims): string {
	return `header.${base64Url(JSON.stringify(claims))}.signature`;
}

/** A person CyberdyneAuth carries a git identity for: they can write. */
export function mappedPerson(overrides: TestClaims = {}): string {
	return credential({
		sub: 'auth|rafa',
		name: 'Rafa',
		git_emails: ['rafa@cyberdyne.com'],
		...overrides
	});
}

/** A person whose claims carry no git identity: the early warning's subject. */
export function unmappedPerson(overrides: TestClaims = {}): string {
	return credential({ sub: 'auth|newcomer', name: 'Newcomer', ...overrides });
}

function base64Url(text: string): string {
	return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** The subject CyberdyneAuth gives a person: a UUID, and nothing a person reads. */
export const CYBERDYNE_SUBJECT = '968a70af-8b4c-4f0e-9a51-3c2d1e0f7a6b';
export const CYBERDYNE_CLIENT = 'cyb_5UIdba7PWtBo1MmH';

/**
 * An access token shaped like the ones CyberdyneAuth actually issues: a
 * subject, roles prefixed with the client id, an audience of `cybercanon` —
 * and no `name`, no `email` and no `git_emails`.
 */
export function cyberdyneAccessToken(overrides: TestClaims = {}): string {
	return credential({
		iss: 'https://auth.backend.coolify.cyberdynecorp.ai',
		sub: CYBERDYNE_SUBJECT,
		type: 'access',
		aud: 'cybercanon',
		client_id: CYBERDYNE_CLIENT,
		roles: [`${CYBERDYNE_CLIENT}:art_director`, `${CYBERDYNE_CLIENT}:artist`],
		scope: 'openid profile email offline_access roles',
		exp: Math.floor(Date.now() / 1000) + 900,
		...overrides
	});
}

/** The identity token beside it: the client as its audience, and the person's email. */
export function cyberdyneIdToken(overrides: TestClaims = {}): string {
	return credential({
		iss: 'https://auth.backend.coolify.cyberdynecorp.ai',
		sub: CYBERDYNE_SUBJECT,
		aud: CYBERDYNE_CLIENT,
		email: 'leo@cyberdynecorp.ai',
		email_verified: false,
		...overrides
	});
}
