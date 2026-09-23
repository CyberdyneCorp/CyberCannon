/**
 * Keeping a session alive without asking the person anything.
 *
 * CyberdyneAuth issues access tokens that last fifteen minutes. Without
 * renewal every session lapsed on that clock, every read after it showed
 * *"Your session has expired"*, and every write was held for a pop-up
 * re-authentication. The issuer also hands back a refresh token (the
 * `offline_access` scope), and this module spends it shortly before the access
 * token lapses.
 *
 * Three triggers, one renewal: a timer set for each new access token,
 * {@link SessionRenewal.ensureFresh} before the frame reads anything — which is
 * what catches a tab that was asleep when its timer should have fired — and
 * {@link SessionRenewal.renewNow} when the API refuses an access token the
 * clock still thought was good. All go through one in-flight renewal, because
 * the issuer rotates refresh tokens and two concurrent renewals would spend the
 * same one twice, and the second would be refused.
 *
 * **Other tabs.** A duplicated tab starts with a copy of this one's session
 * storage, so two tabs can hold the same rotating refresh token. Renewals are
 * therefore serialised across the origin's tabs ({@link RenewalChannel}: a Web
 * Lock), and a tab that renews announces the new credential; a tab still
 * holding the refresh token that was just spent adopts it instead of spending a
 * token the issuer has already rotated. The announcement and the lock are
 * separate browser mechanisms, so a tab can in principle take the lock before
 * the announcement reaches it; it then spends a rotated token, is refused, and
 * falls back to the in-place prompt — the same outcome as with no coordination.
 *
 * What a failure does is D5's business, not this module's. A refused refresh
 * token revokes the session to `expired`, which is exactly the state the
 * in-place re-authentication prompt answers. An unreachable issuer changes
 * nothing but is tried again after {@link RENEWAL_RETRY_MS}, so an outage that
 * ends does not leave the session to lapse with nothing retrying.
 */

import type { Credential, RenewalOutcome } from './oidc';
import type { Session, SessionStore } from './session';

/** Renew this long before the access token lapses. */
export const RENEWAL_LEAD_MS = 60_000;

/** Try again this long after a renewal the issuer did not answer. */
export const RENEWAL_RETRY_MS = 30_000;

/** The one call a renewal makes: a refresh token in, an outcome out. */
export type Refresher = (refreshToken: string) => Promise<RenewalOutcome>;

export type Cancel = () => void;

/** How the tabs of one origin keep from spending one refresh token twice. */
export interface RenewalChannel {
	/** Run `task` while no other tab of this origin is renewing. */
	exclusive(task: () => Promise<void>): Promise<void>;
	/** Tell the other tabs that `spent` was rotated into `credential`. */
	announce(spent: string, credential: Credential): void;
	/** Hear what another tab announced. */
	listen(heard: (spent: string, credential: Credential) => void): Cancel;
}

export interface RenewalOptions {
	readonly now?: () => number;
	readonly leadMs?: number;
	readonly retryMs?: number;
	readonly schedule?: (run: () => void, delayMs: number) => Cancel;
	readonly channel?: RenewalChannel;
}

/** `setTimeout`'s ceiling; a longer delay fires at once. */
const LONGEST_DELAY_MS = 2_147_483_647;

const CHANNEL_NAME = 'cybercanon.renewal';

export class SessionRenewal {
	readonly #store: SessionStore;
	readonly #now: () => number;
	readonly #leadMs: number;
	readonly #retryMs: number;
	readonly #schedule: (run: () => void, delayMs: number) => Cancel;
	readonly #channel: RenewalChannel;
	#refresh: Refresher | null = null;
	#inFlight: Promise<void> | null = null;
	#watching: Cancel[] = [];
	#timer: Cancel | null = null;

	constructor(store: SessionStore, options: RenewalOptions = {}) {
		this.#store = store;
		this.#now = options.now ?? (() => Date.now());
		this.#leadMs = options.leadMs ?? RENEWAL_LEAD_MS;
		this.#retryMs = options.retryMs ?? RENEWAL_RETRY_MS;
		this.#schedule = options.schedule ?? timeout;
		this.#channel = options.channel ?? browserChannel();
	}

	/** Renew now if the session is due; otherwise do nothing. Never throws. */
	ensureFresh(refresh: Refresher): Promise<void> {
		if (this.#inFlight) return this.#inFlight;
		if (!this.#store.renewalDue(this.#leadMs)) return Promise.resolve();
		return this.#run(refresh);
	}

	/**
	 * The API refused the access token: renew whatever the clock says, with the
	 * refresher {@link watch} was given. Resolves to whether the session holds an
	 * accepted access token afterwards. Never throws.
	 */
	async renewNow(): Promise<boolean> {
		const refresh = this.#refresh;
		if (!refresh) return false;
		await (this.#inFlight ?? this.#run(refresh));
		return this.#store.isAuthenticated();
	}

	/** Renew each access token shortly before it lapses. Idempotent. */
	watch(refresh: Refresher): void {
		this.#refresh = refresh;
		if (this.#watching.length) return;
		this.#watching = [
			this.#store.subscribe((session) => this.#plan(session, refresh)),
			this.#channel.listen((spent, credential) => this.#adopt(spent, credential))
		];
	}

	/** Stop watching, and forget any renewal that was planned. */
	stop(): void {
		for (const cancel of this.#watching) cancel();
		this.#watching = [];
		this.#refresh = null;
		this.#cancelTimer();
	}

	#run(refresh: Refresher): Promise<void> {
		const refreshToken = this.#store.refreshToken();
		if (!refreshToken) return Promise.resolve();
		this.#inFlight = this.#channel
			.exclusive(() => this.#renew(refresh, refreshToken))
			.catch(() => {})
			.finally(() => {
				this.#inFlight = null;
			});
		return this.#inFlight;
	}

	async #renew(refresh: Refresher, refreshToken: string): Promise<void> {
		// Another tab rotated it while this one waited, and this one adopted the result.
		if (this.#store.refreshToken() !== refreshToken) return;
		const outcome = await refresh(refreshToken).catch(() => null);
		if (outcome?.kind === 'renewed') {
			this.#store.renew(outcome.credential);
			this.#channel.announce(refreshToken, outcome.credential);
		} else if (outcome?.kind === 'refused') {
			this.#store.revoke();
		} else {
			this.#retryLater(refresh);
		}
	}

	#adopt(spent: string, credential: Credential): void {
		if (this.#store.refreshToken() === spent) this.#store.renew(credential);
	}

	#plan(session: Session, refresh: Refresher): void {
		this.#cancelTimer();
		if (!this.#store.refreshToken()) return;
		const delay = this.#delayFor(session);
		if (delay !== null) this.#timer = this.#schedule(() => void this.ensureFresh(refresh), delay);
	}

	/** When to renew: before an active token lapses, or soon for one the API already refused. */
	#delayFor(session: Session): number | null {
		if (session.kind === 'expired') return this.#retryMs;
		if (session.kind !== 'active' || session.expiresAt === null) return null;
		return Math.max(0, session.expiresAt - this.#leadMs - this.#now());
	}

	#retryLater(refresh: Refresher): void {
		this.#cancelTimer();
		if (!this.#store.refreshToken()) return;
		this.#timer = this.#schedule(() => void this.ensureFresh(refresh), this.#retryMs);
	}

	#cancelTimer(): void {
		this.#timer?.();
		this.#timer = null;
	}
}

function timeout(run: () => void, delayMs: number): Cancel {
	const handle = setTimeout(run, Math.min(delayMs, LONGEST_DELAY_MS));
	return () => clearTimeout(handle);
}

/**
 * The origin's tabs, through a Web Lock and a `BroadcastChannel`. Outside a
 * browser, or in one without them, it is this tab alone.
 */
export function browserChannel(): RenewalChannel {
	const inBrowser = typeof window !== 'undefined';
	const locks = inBrowser ? globalThis.navigator?.locks : undefined;
	const broadcast =
		inBrowser && typeof BroadcastChannel === 'function' ? new BroadcastChannel(CHANNEL_NAME) : null;
	return {
		exclusive: async (task) => {
			if (locks) await locks.request(CHANNEL_NAME, task);
			else await task();
		},
		announce: (spent, credential) => broadcast?.postMessage({ spent, credential }),
		listen(heard) {
			if (!broadcast) return () => {};
			const onMessage = (event: MessageEvent) => {
				const { spent, credential } = (event.data ?? {}) as { spent?: unknown; credential?: Credential };
				if (typeof spent === 'string' && typeof credential?.accessToken === 'string') heard(spent, credential);
			};
			broadcast.addEventListener('message', onMessage);
			return () => broadcast.removeEventListener('message', onMessage);
		}
	};
}
