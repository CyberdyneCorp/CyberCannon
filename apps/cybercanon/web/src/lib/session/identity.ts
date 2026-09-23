/**
 * Who the session belongs to, and whether the repository knows them.
 *
 * `web-session` asks for two different things from one value. The first is
 * presentation — *"the application SHALL show which person the current session
 * belongs to, so that attribution of anything they write is never a
 * surprise"*. The second is a warning that has to arrive **before** a refusal:
 * a person with no mapped git identity cannot write to the repository, and
 * `add-web-backend`'s D8 accepts that cost only because *"the refusal names the
 * missing mapping"* — which is no comfort at all if the person learns it after
 * typing two paragraphs.
 *
 * **The claims are decoded, never trusted.** Authorization happens in the
 * domain, behind a credential the API verifies against the issuer's published
 * keys (`auth-integration`). Nothing here decides anything; it reads three
 * fields out of a token so a frame can print a name, and a frame printing the
 * wrong name is a cosmetic bug rather than an authorization one.
 *
 * **Where `gitIdentity` comes from, and what it cannot yet know.**
 * `openspec/project.md` says the mapping is carried *"by claims when
 * CyberdyneAuth can; otherwise `.canon/actors.yaml` maps `sub` → git emails"*.
 * This application can read the first and has no way to read the second: no
 * endpoint on the `http-api` surface states whether the acting person is mapped
 * in a project's working copy. CyberdyneAuth emits no `git_emails` claim at
 * all, so for a real credential the answer is **not known here** — and an
 * unknown mapping is not an unmapped one. The warning below is raised only when
 * the credential itself says the person has no git identity (the claim present
 * and empty); an absent claim warns nobody, and the domain's refusal still
 * names the missing mapping if there is one. Asking instead of reading a claim
 * needs an `http-api` endpoint, and `add-web-app-shell`'s proposal says what to
 * do with that: *"if a screen needs something the API does not expose, that is
 * a gap in those capabilities, not work for this change"*.
 */

/** The claims this application reads. Everything else in the token is ignored. */
export interface Claims {
	readonly sub?: unknown;
	readonly name?: unknown;
	readonly email?: unknown;
	readonly git_emails?: unknown;
	readonly exp?: unknown;
}

export interface Identity {
	/** The `sub` claim — stable, and what the API attributes a write to. */
	readonly subject: string;
	/** What a person recognises themselves by: a name, else an email, else the subject. */
	readonly display: string;
	/** The git author a write would be committed as, or `null` when there is none. */
	readonly gitIdentity: string | null;
	/**
	 * Whether the credential states a git identity at all: `unknown` when it
	 * carries no `git_emails` claim, which is every CyberdyneAuth credential.
	 */
	readonly mapping: GitMapping;
}

/** What the credential says about the person's git identity. */
export type GitMapping = 'mapped' | 'unmapped' | 'unknown';

/**
 * What an unmapped person cannot do, named rather than implied.
 *
 * Every one of these writes a file into the game repository, and G4 in
 * `openspec/project.md` requires *"a mapped git identity"* for each. Listing
 * them is the requirement: *"SHALL indicate which actions are unavailable as a
 * result"*.
 */
export const REPOSITORY_ACTIONS: readonly string[] = [
	'raising an asset request',
	'accepting or declining a request',
	'writing or replying to an annotation',
	'resolving an issue or promoting it to a rule',
	'changing an asset’s status'
];

export const UNMAPPED_HEADLINE = 'Your credential carries no git identity';

/**
 * The warning, in the words a person can act on.
 *
 * It names the actions, the reason and the fix, because a warning that states
 * only the first is a dead end — and the fix really is one line in a file
 * somebody on the project can add.
 */
export function unmappedNotice(identity: Identity | null): string | null {
	if (identity?.mapping !== 'unmapped') return null;
	return (
		`${UNMAPPED_HEADLINE}, so CyberCanon has nobody to commit as on your behalf. ` +
		`Until one is recorded for ${identity.subject} in .canon/actors.yaml, these ` +
		`are unavailable: ${REPOSITORY_ACTIONS.join(', ')}. Reading is unaffected.`
	);
}

export function isMapped(identity: Identity | null): boolean {
	return identity?.mapping === 'mapped';
}

/**
 * The identity a set of claims describes. A claimless token has no identity.
 *
 * `claims` are the access token's, whose `sub` is what the API attributes a
 * write to. `profile` is the identity token's: CyberdyneAuth puts the person's
 * email there and nothing but the subject in the access token, so a session
 * read from the access token alone would print a UUID as the person.
 */
export function identityFrom(claims: Claims, profile: Claims = {}): Identity | null {
	const subject = text(claims.sub);
	if (!subject) return null;
	const gitIdentity = firstEmail(claims.git_emails) ?? firstEmail(profile.git_emails);
	return {
		subject,
		display: displayName(profile) ?? displayName(claims) ?? subject,
		gitIdentity,
		mapping: gitMapping(gitIdentity, claims, profile)
	};
}

/** `unmapped` only when a credential carries the claim and it names nobody. */
function gitMapping(gitIdentity: string | null, claims: Claims, profile: Claims): GitMapping {
	if (gitIdentity) return 'mapped';
	const stated = claims.git_emails !== undefined || profile.git_emails !== undefined;
	return stated ? 'unmapped' : 'unknown';
}

function displayName(claims: Claims): string | null {
	return text(claims.name) ?? text(claims.email);
}

/**
 * The payload of a JWT, read without verifying it.
 *
 * The application never validates a credential — it holds one and presents it.
 * A token it cannot read produces no identity, which renders as a session
 * belonging to nobody rather than as a crash in the frame.
 */
export function claimsOf(token: string): Claims {
	const payload = token.split('.')[1];
	if (!payload) return {};
	try {
		return JSON.parse(decodeBase64Url(payload)) as Claims;
	} catch {
		return {};
	}
}

/** When this credential stops being accepted, in epoch milliseconds. */
export function expiryOf(claims: Claims): number | null {
	return typeof claims.exp === 'number' ? claims.exp * 1000 : null;
}

function decodeBase64Url(segment: string): string {
	const padded = segment.replace(/-/g, '+').replace(/_/g, '/');
	const binary = atob(padded.padEnd(Math.ceil(padded.length / 4) * 4, '='));
	const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
	return new TextDecoder().decode(bytes);
}

function firstEmail(value: unknown): string | null {
	if (Array.isArray(value)) return text(value[0]);
	return text(value);
}

function text(value: unknown): string | null {
	return typeof value === 'string' && value.trim() ? value.trim() : null;
}
