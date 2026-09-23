/**
 * D5 — expiry mid-edit is handled by holding the request, not by redirecting.
 *
 * This is the module `add-web-app-shell` exists for, in the change's own words:
 * *"the conventional redirect-to-login loses the annotation the person just
 * spent two minutes writing — and losing someone's writing once is enough for
 * them to stop using the tool"*.
 *
 * So a write is a **value**, not a call. It carries its payload and the
 * idempotency key it will be sent under, and it can be sent more than once:
 *
 * 1. the write is submitted and the surface answers `unauthenticated`;
 *    if the session can be renewed silently (a refresh token), it is, and the
 *    write is sent once more under the same key — no prompt at all;
 * 2. otherwise the session moves to `expired` — keeping *who*, so the prompt can name
 *    them — and the write is **held**, payload intact;
 * 3. re-authentication is offered *in place*: no navigation, no unmount, the
 *    input still on screen;
 * 4. on success the held write is replayed **under its original key**, and the
 *    person never retypes anything;
 * 5. on decline it is released still unsent, and the payload is handed back so
 *    the screen keeps showing it.
 *
 * **The key is generated once per draft and never regenerated.** That is what
 * makes step 4 safe rather than merely convenient: `http-api` specifies that a
 * replayed key returns the original outcome and that *"a retried write creates
 * one commit"*, so if the first attempt actually landed before the credential
 * was refused, the replay is answered rather than duplicated. A fresh key per
 * attempt would turn every expiry into a possible double annotation.
 *
 * D5's accepted risk is stated where it bites: a key whose record was lost to
 * an index rebuild may come back as a conflict. The person still has their
 * text — `failed` is a screen with the draft beside it, not a lost paragraph.
 */

import type { ApiResult } from '../api/types';
import type { SessionStore } from './session';

/** One write, in a form that can be sent twice and lose nothing in between. */
export interface HeldWrite<T> {
	/** The idempotency key `http-api` requires. Generated once, reused on replay. */
	readonly key: string;
	/** What is waiting, in the words the prompt shows: "your annotation on mech_scout". */
	readonly describe: string;
	/** Exactly what the person typed. Never touched by this module. */
	readonly payload: unknown;
	/** Sends it. The key is passed in so a replay cannot quietly use a new one. */
	readonly send: (key: string) => Promise<ApiResult<T>>;
}

/** It reached the surface. `result` may still be a refusal — that is an answer. */
export interface Completed<T> {
	readonly kind: 'completed';
	readonly result: ApiResult<T>;
}

/** The session had expired. Nothing was lost and nothing was sent again. */
export interface Held<T> {
	readonly kind: 'held';
	readonly write: HeldWrite<T>;
	readonly message: string;
}

/** Re-authentication was declined. The payload comes back; it was not sent. */
export interface Kept<T> {
	readonly kind: 'kept';
	readonly write: HeldWrite<T>;
	readonly message: string;
}

export type Submission<T> = Completed<T> | Held<T> | Kept<T>;

export const EXPIRED_MESSAGE =
	'Your session expired before this could be saved. Nothing has been lost — ' +
	'sign in again and it will be submitted exactly as you wrote it.';

export const KEPT_MESSAGE =
	'Not submitted. Your text is still here; submit it again whenever you are ready.';

export type HeldListener = (held: HeldWrite<unknown> | null) => void;

/**
 * The gate every write goes through.
 *
 * It holds at most one write, which is the shape of the problem rather than a
 * simplification: the person is looking at one screen, typing one thing, and a
 * queue of held writes would be a queue of prompts nobody can reason about.
 */
/** Renews the session without asking anyone; resolves to whether it worked. */
export type SilentRenewal = () => Promise<boolean>;

export class WriteGate {
	#held: HeldWrite<unknown> | null = null;
	readonly #listeners = new Set<HeldListener>();
	readonly #session: SessionStore;
	readonly #renew: SilentRenewal;

	constructor(session: SessionStore, renew: SilentRenewal = async () => false) {
		this.#session = session;
		this.#renew = renew;
	}

	/** The write waiting for a credential, or `null` when nothing is waiting. */
	held(): HeldWrite<unknown> | null {
		return this.#held;
	}

	subscribe(listener: HeldListener): () => void {
		this.#listeners.add(listener);
		listener(this.#held);
		return () => void this.#listeners.delete(listener);
	}

	/**
	 * Send it, or hold it.
	 *
	 * The decision is the surface's: only an `unauthenticated` outcome holds.
	 * A refusal for any other reason is an answer the screen has to show —
	 * holding a `forbidden` would offer re-authentication to a person whose
	 * credential is perfectly valid and whose role simply does not allow it.
	 *
	 * An `unauthenticated` answer is first met with a silent renewal: an access
	 * token that lapsed while its renewal timer slept is not a reason to
	 * interrupt anybody. The write is re-sent once, under its key, so a first
	 * attempt that did land is answered rather than duplicated.
	 */
	async submit<T>(write: HeldWrite<T>): Promise<Submission<T>> {
		let result = await write.send(write.key);
		if (unauthenticated(result) && (await this.#renew().catch(() => false))) {
			result = await write.send(write.key);
		}
		if (unauthenticated(result)) {
			this.#session.expire();
			this.#hold(write as HeldWrite<unknown>);
			return { kind: 'held', write, message: EXPIRED_MESSAGE };
		}
		this.#hold(null);
		return { kind: 'completed', result };
	}

	/**
	 * A credential was obtained in place: replay what was held, under its key.
	 *
	 * `null` when nothing was held, which is the ordinary case for a sign-in
	 * that had nothing to do with an expiry.
	 */
	async replay(): Promise<Submission<unknown> | null> {
		const write = this.#held;
		if (!write) return null;
		this.#hold(null);
		return this.submit(write);
	}

	/**
	 * Re-authentication was declined.
	 *
	 * The scenario is exact about both halves: *"the input SHALL remain on
	 * screen and recoverable"* and *"it SHALL NOT be submitted"*. So the write
	 * is handed back with its payload and the gate sends nothing — the screen
	 * keeps the draft it never stopped holding, and the person can submit again
	 * later under the same key.
	 */
	decline(): Kept<unknown> | null {
		const write = this.#held;
		if (!write) return null;
		this.#hold(null);
		return { kind: 'kept', write, message: KEPT_MESSAGE };
	}

	/** Sign-out drops it: a held write belongs to the session that authored it. */
	discard(): void {
		this.#hold(null);
	}

	#hold(write: HeldWrite<unknown> | null): void {
		this.#held = write;
		for (const listener of this.#listeners) listener(write);
	}
}

function unauthenticated(result: ApiResult<unknown>): boolean {
	return !result.ok && result.failure.kind === 'unauthenticated';
}

/**
 * A write with a fresh key.
 *
 * Called once, when the person starts the draft — not when they press submit,
 * and never again on a retry. `crypto.randomUUID` is available in every browser
 * this application supports and in the test runner; the fallback exists so a
 * context without it degrades to a still-unique key rather than to no key at
 * all, which would be a write with no replay protection.
 */
export function heldWrite<T>(write: Omit<HeldWrite<T>, 'key'> & { key?: string }): HeldWrite<T> {
	return { ...write, key: write.key ?? newIdempotencyKey() };
}

export function newIdempotencyKey(): string {
	const source = globalThis.crypto;
	if (source?.randomUUID) return source.randomUUID();
	return `key-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
