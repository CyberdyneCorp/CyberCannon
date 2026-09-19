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
	readonly git_emails?: readonly string[];
	readonly exp?: number;
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
