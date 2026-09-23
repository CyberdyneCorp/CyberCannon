/**
 * The session, as three states and nothing else.
 *
 * `web-session` distinguishes two things that a boolean would flatten into one:
 * a person who has not signed in, and a person whose session expired *while
 * they were in the middle of something*. The first is offered sign-in; the
 * second is offered re-authentication **in place**, with their work still on
 * screen, because *"losing someone's writing once is enough for them to stop
 * using the tool"* (D5).
 *
 * So `expired` keeps the identity. It is the state that lets the prompt say
 * *"your session as Rafa has expired"* rather than dropping the person on a
 * sign-in screen that has forgotten who they were.
 *
 * The store keeps the whole credential the issuer answered with, not only the
 * access token: the refresh token renews the session without a redirect
 * (`renewal.ts`) and the identity token names the person and is the hint
 * sign-out hands the identity service. Only the access token is ever presented
 * to the API. All three live in the tab's session storage, which a closed tab
 * ends, and sign-out removes them.
 *
 * This is a plain class with listeners, not a rune module: D1 reserves
 * `*.svelte.ts` for the one `AnnotationViewModel`, and a component subscribes
 * to this from `$state` in three lines. It is also what makes the whole session
 * testable with no DOM, which is how the scenarios below are executed.
 */

import { queryCache } from '../api/cache';
import type { Identity } from './identity';
import { claimsOf, expiryOf, identityFrom } from './identity';
import type { Credential } from './oidc';
import { browserStorage, type SessionStorage } from './storage';

export const SESSION_KEY = 'cybercanon.session';

export type Session =
	| { readonly kind: 'anonymous' }
	| {
			readonly kind: 'active';
			readonly identity: Identity;
			readonly token: string;
			/** Epoch milliseconds, or `null` when the credential declares no expiry. */
			readonly expiresAt: number | null;
	  }
	| { readonly kind: 'expired'; readonly identity: Identity };

export const ANONYMOUS: Session = { kind: 'anonymous' };

export type Listener = (session: Session) => void;

/** What the frame prints on every authenticated screen (`web-session`). */
export interface ActingIdentity {
	readonly signedIn: boolean;
	readonly label: string;
	readonly subject: string;
	readonly expired: boolean;
}

export interface SessionOptions {
	readonly storage?: SessionStorage;
	/** Called on sign-out: the query cache, which must not survive it (D2). */
	readonly forget?: () => void;
	readonly now?: () => number;
}

export class SessionStore {
	#session: Session = ANONYMOUS;
	#credential: Credential | null = null;
	readonly #listeners = new Set<Listener>();
	readonly #storage: SessionStorage;
	readonly #forget: () => void;
	readonly #now: () => number;

	constructor(options: SessionOptions = {}) {
		this.#storage = options.storage ?? browserStorage();
		this.#forget = options.forget ?? (() => {});
		this.#now = options.now ?? (() => Date.now());
		this.#session = this.#restored();
	}

	current(): Session {
		return this.#session;
	}

	identity(): Identity | null {
		return this.#session.kind === 'anonymous' ? null : this.#session.identity;
	}

	/** The credential the API client carries, or `null` — read at call time. */
	token(): string | null {
		return this.#session.kind === 'active' && !this.#lapsed() ? this.#session.token : null;
	}

	isAuthenticated(): boolean {
		return this.token() !== null;
	}

	subscribe(listener: Listener): () => void {
		this.#listeners.add(listener);
		listener(this.#session);
		return () => void this.#listeners.delete(listener);
	}

	/** The refresh token the session can be renewed with, or `null`. */
	refreshToken(): string | null {
		return this.#credential?.refreshToken ?? null;
	}

	/** The identity token sign-out hands back as a hint, or `null`. */
	idToken(): string | null {
		return this.#credential?.idToken ?? null;
	}

	/**
	 * Whether the session should be renewed now: it can be, and its access token
	 * lapses within `leadMs` — or already has.
	 */
	renewalDue(leadMs: number): boolean {
		if (!this.refreshToken()) return false;
		const session = this.#session;
		if (session.kind === 'expired') return true;
		if (session.kind !== 'active' || session.expiresAt === null) return false;
		return session.expiresAt - this.#now() <= leadMs;
	}

	/** A credential accepted: the session this application acts under. */
	signIn(accepted: Credential | string): Session {
		const credential = credentialOf(accepted);
		const claims = claimsOf(credential.accessToken);
		const identity = identityFrom(claims, claimsOf(credential.idToken ?? ''));
		if (!identity) return this.#moveTo(ANONYMOUS);
		this.#store(credential);
		const token = credential.accessToken;
		return this.#moveTo({ kind: 'active', identity, token, expiresAt: expiryOf(claims) });
	}

	/**
	 * A renewed credential. The issuer rotates refresh tokens, so the new one
	 * replaces the old; a token the answer left out is kept rather than lost.
	 */
	renew(renewed: Credential): Session {
		return this.signIn({
			accessToken: renewed.accessToken,
			refreshToken: renewed.refreshToken ?? this.refreshToken(),
			idToken: renewed.idToken ?? this.idToken()
		});
	}

	/**
	 * The access token is no longer accepted — keep who, and what can renew it.
	 *
	 * Called when the surface answers `unauthenticated`, which is the only
	 * authority on the question: a clock skew between a browser and an issuer is
	 * not a reason to throw a person out of a session the API still honours.
	 *
	 * The refresh token survives it. An access token can lapse before its renewal
	 * fires — a laptop that slept, a throttled background tab — and that is a
	 * renewal to make, not a person to interrupt; `renewal.ts` spends it, and
	 * only a refusal of it ({@link revoke}) leaves nothing to renew with.
	 */
	expire(): Session {
		if (!this.refreshToken()) this.#forgetCredential();
		return this.#moveTo(this.#expiredOrAnonymous());
	}

	/** The refresh token was refused: expire, with nothing left to renew with. */
	revoke(): Session {
		this.#forgetCredential();
		return this.#moveTo(this.#expiredOrAnonymous());
	}

	/**
	 * Signing out: the credential, and everything it was used to read.
	 *
	 * `forget` is the query cache. Clearing the token without clearing the cache
	 * would leave the previous person's assets on screen for the next one, which
	 * is the scenario in so many words.
	 */
	signOut(): Session {
		this.#forgetCredential();
		this.#forget();
		return this.#moveTo(ANONYMOUS);
	}

	/**
	 * The session a reload finds. A lapsed one is `expired` but keeps its
	 * credential, so a refresh token can still renew it without a prompt.
	 */
	#restored(): Session {
		const credential = parsedCredential(this.#storage.read(SESSION_KEY));
		if (!credential) return ANONYMOUS;
		const claims = claimsOf(credential.accessToken);
		const identity = identityFrom(claims, claimsOf(credential.idToken ?? ''));
		if (!identity) return ANONYMOUS;
		this.#credential = credential;
		const expiresAt = expiryOf(claims);
		if (expiresAt !== null && expiresAt <= this.#now()) return { kind: 'expired', identity };
		return { kind: 'active', identity, token: credential.accessToken, expiresAt };
	}

	#lapsed(): boolean {
		const session = this.#session;
		if (session.kind !== 'active' || session.expiresAt === null) return false;
		return session.expiresAt <= this.#now();
	}

	#expiredOrAnonymous(): Session {
		const identity = this.identity();
		return identity ? { kind: 'expired', identity } : ANONYMOUS;
	}

	#forgetCredential(): void {
		this.#credential = null;
		this.#storage.remove(SESSION_KEY);
	}

	#store(credential: Credential): void {
		this.#credential = credential;
		this.#storage.write(SESSION_KEY, JSON.stringify(credential));
	}

	#moveTo(session: Session): Session {
		this.#session = session;
		for (const listener of this.#listeners) listener(session);
		return session;
	}
}

/** A bare access token is a credential with nothing to renew it and no identity token. */
function credentialOf(accepted: Credential | string): Credential {
	if (typeof accepted !== 'string') return accepted;
	return { accessToken: accepted, refreshToken: null, idToken: null };
}

/**
 * What storage held. A value that is not a stored credential is read as a bare
 * access token, which is what an earlier build of this application kept there.
 */
function parsedCredential(held: string | null): Credential | null {
	if (!held) return null;
	try {
		const parsed = JSON.parse(held) as Partial<Credential>;
		if (typeof parsed.accessToken !== 'string') return null;
		return {
			accessToken: parsed.accessToken,
			refreshToken: parsed.refreshToken ?? null,
			idToken: parsed.idToken ?? null
		};
	} catch {
		return credentialOf(held);
	}
}

/** What the frame shows. Derived once so two screens cannot print it differently. */
export function actingIdentity(session: Session): ActingIdentity | null {
	if (session.kind === 'anonymous') return null;
	return {
		signedIn: session.kind === 'active',
		label: session.identity.display,
		subject: session.identity.subject,
		expired: session.kind === 'expired'
	};
}

/**
 * The one session. A second instance is a second answer to "who is acting".
 *
 * It is wired to the one query cache here rather than at each call site, so
 * *"signing out clears cached project and asset content"* cannot be true on the
 * screens that remembered to do it and false on the ones that did not.
 */
export const sessionStore = new SessionStore({ forget: () => queryCache.clear() });
