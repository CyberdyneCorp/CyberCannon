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
 * Two triggers, one renewal: a timer set for each new access token, and
 * {@link SessionRenewal.ensureFresh} before the frame reads anything — which is
 * what catches a tab that was asleep when its timer should have fired. Both go
 * through one in-flight renewal, because the issuer rotates refresh tokens and
 * two concurrent renewals would spend the same one twice, and the second would
 * be refused.
 *
 * What a failure does is D5's business, not this module's. A refused refresh
 * token moves the session to `expired`, which is exactly the state the in-place
 * re-authentication prompt answers; an unreachable issuer changes nothing,
 * because the access token the session holds is still the API's to judge.
 */

import type { RenewalOutcome } from './oidc';
import type { Session, SessionStore } from './session';

/** Renew this long before the access token lapses. */
export const RENEWAL_LEAD_MS = 60_000;

/** The one call a renewal makes: a refresh token in, an outcome out. */
export type Refresher = (refreshToken: string) => Promise<RenewalOutcome>;

export type Cancel = () => void;

export interface RenewalOptions {
	readonly now?: () => number;
	readonly leadMs?: number;
	readonly schedule?: (run: () => void, delayMs: number) => Cancel;
}

/** `setTimeout`'s ceiling; a longer delay fires at once. */
const LONGEST_DELAY_MS = 2_147_483_647;

export class SessionRenewal {
	readonly #store: SessionStore;
	readonly #now: () => number;
	readonly #leadMs: number;
	readonly #schedule: (run: () => void, delayMs: number) => Cancel;
	#inFlight: Promise<void> | null = null;
	#watching: Cancel | null = null;
	#timer: Cancel | null = null;

	constructor(store: SessionStore, options: RenewalOptions = {}) {
		this.#store = store;
		this.#now = options.now ?? (() => Date.now());
		this.#leadMs = options.leadMs ?? RENEWAL_LEAD_MS;
		this.#schedule = options.schedule ?? timeout;
	}

	/** Renew now if the session is due; otherwise do nothing. Never throws. */
	ensureFresh(refresh: Refresher): Promise<void> {
		if (this.#inFlight) return this.#inFlight;
		const refreshToken = this.#store.refreshToken();
		if (!refreshToken || !this.#store.renewalDue(this.#leadMs)) return Promise.resolve();
		this.#inFlight = this.#renew(refresh, refreshToken).finally(() => {
			this.#inFlight = null;
		});
		return this.#inFlight;
	}

	/** Renew each access token shortly before it lapses. Idempotent. */
	watch(refresh: Refresher): void {
		if (this.#watching) return;
		this.#watching = this.#store.subscribe((session) => this.#plan(session, refresh));
	}

	/** Stop watching, and forget any renewal that was planned. */
	stop(): void {
		this.#watching?.();
		this.#watching = null;
		this.#cancelTimer();
	}

	async #renew(refresh: Refresher, refreshToken: string): Promise<void> {
		const outcome = await refresh(refreshToken).catch(() => null);
		if (outcome?.kind === 'renewed') this.#store.renew(outcome.credential);
		else if (outcome?.kind === 'refused') this.#store.expire();
	}

	#plan(session: Session, refresh: Refresher): void {
		this.#cancelTimer();
		if (session.kind !== 'active' || session.expiresAt === null) return;
		if (!this.#store.refreshToken()) return;
		const delay = Math.max(0, session.expiresAt - this.#leadMs - this.#now());
		this.#timer = this.#schedule(() => void this.ensureFresh(refresh), delay);
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
