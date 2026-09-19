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
 * This is a plain class with listeners, not a rune module: D1 reserves
 * `*.svelte.ts` for the one `AnnotationViewModel`, and a component subscribes
 * to this from `$state` in three lines. It is also what makes the whole session
 * testable with no DOM, which is how the scenarios below are executed.
 */

import { queryCache } from '../api/cache';
import type { Identity } from './identity';
import { claimsOf, expiryOf, identityFrom } from './identity';
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

	/** A credential accepted: the session this application acts under. */
	signIn(token: string): Session {
		const claims = claimsOf(token);
		const identity = identityFrom(claims);
		if (!identity) return this.#moveTo(ANONYMOUS);
		this.#store(token);
		return this.#moveTo({ kind: 'active', identity, token, expiresAt: expiryOf(claims) });
	}

	/**
	 * The credential is no longer accepted — keep who, drop what.
	 *
	 * Called when the surface answers `unauthenticated`, which is the only
	 * authority on the question: a clock skew between a browser and an issuer is
	 * not a reason to throw a person out of a session the API still honours.
	 */
	expire(): Session {
		const identity = this.identity();
		this.#storage.remove(SESSION_KEY);
		return this.#moveTo(identity ? { kind: 'expired', identity } : ANONYMOUS);
	}

	/**
	 * Signing out: the credential, and everything it was used to read.
	 *
	 * `forget` is the query cache. Clearing the token without clearing the cache
	 * would leave the previous person's assets on screen for the next one, which
	 * is the scenario in so many words.
	 */
	signOut(): Session {
		this.#storage.remove(SESSION_KEY);
		this.#forget();
		return this.#moveTo(ANONYMOUS);
	}

	#restored(): Session {
		const token = this.#storage.read(SESSION_KEY);
		if (!token) return ANONYMOUS;
		const claims = claimsOf(token);
		const identity = identityFrom(claims);
		if (!identity) return ANONYMOUS;
		const expiresAt = expiryOf(claims);
		if (expiresAt !== null && expiresAt <= this.#now()) return { kind: 'expired', identity };
		return { kind: 'active', identity, token, expiresAt };
	}

	#lapsed(): boolean {
		const session = this.#session;
		if (session.kind !== 'active' || session.expiresAt === null) return false;
		return session.expiresAt <= this.#now();
	}

	#store(token: string): void {
		this.#storage.write(SESSION_KEY, token);
	}

	#moveTo(session: Session): Session {
		this.#session = session;
		for (const listener of this.#listeners) listener(session);
		return session;
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
