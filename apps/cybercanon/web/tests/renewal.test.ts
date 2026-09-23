/**
 * The session against the credential CyberdyneAuth actually issues.
 *
 * Three regressions, all found by signing in to the real identity service:
 *
 * * the access token carries a UUID as its subject and no name or email, so a
 *   session read from it alone printed *"Signed in as 968a70af-…"*; the
 *   person's email is in the identity token, which the session now keeps;
 * * the access token lasts fifteen minutes and the refresh token beside it was
 *   thrown away, so every session lapsed on that clock; it is now kept and
 *   spent shortly before the access token lapses, and the issuer's rotation is
 *   honoured;
 * * sign-out left the refresh and identity tokens nowhere, which this suite
 *   keeps true now that they are held at all.
 */

import { describe, expect, it } from 'vitest';
import { SESSION_KEY, SessionStore, actingIdentity } from '../src/lib/session/session';
import { memoryStorage, type SessionStorage } from '../src/lib/session/storage';
import { RENEWAL_LEAD_MS, SessionRenewal, type Refresher } from '../src/lib/session/renewal';
import type { Credential, RenewalOutcome } from '../src/lib/session/oidc';
import {
	CYBERDYNE_SUBJECT,
	cyberdyneAccessToken,
	cyberdyneIdToken,
	mappedPerson
} from './support/credentials';

const NOW = 1_700_000_000_000;
const IN_FIFTEEN_MINUTES = Math.floor(NOW / 1000) + 900;

function signedIn(storage: SessionStorage = memoryStorage(), now = () => NOW) {
	const store = new SessionStore({ storage, now });
	store.signIn({
		accessToken: cyberdyneAccessToken({ exp: IN_FIFTEEN_MINUTES }),
		idToken: cyberdyneIdToken(),
		refreshToken: 'rt-1'
	});
	return store;
}

function renewed(overrides: Partial<Credential> = {}): Credential {
	return {
		accessToken: cyberdyneAccessToken({ exp: IN_FIFTEEN_MINUTES + 900, jti: 'second' }),
		refreshToken: 'rt-2',
		idToken: cyberdyneIdToken(),
		...overrides
	};
}

/** A refresher that answers with `outcome` and records what it was asked. */
function refresher(outcome: RenewalOutcome): { refresh: Refresher; asked: string[] } {
	const asked: string[] = [];
	return {
		asked,
		refresh: async (token) => {
			asked.push(token);
			return outcome;
		}
	};
}

describe('who a CyberdyneAuth session belongs to', () => {
	it('is named by the identity token’s email, not the access token’s UUID (regression)', () => {
		const acting = actingIdentity(signedIn().current());

		expect(acting?.label).toBe('leo@cyberdynecorp.ai');
		expect(acting?.subject).toBe(CYBERDYNE_SUBJECT);
	});

	it('prefers a name over an email when the identity token has one', () => {
		const store = new SessionStore({ storage: memoryStorage(), now: () => NOW });
		store.signIn({
			accessToken: cyberdyneAccessToken({ exp: IN_FIFTEEN_MINUTES }),
			idToken: cyberdyneIdToken({ name: 'Leo Araujo' }),
			refreshToken: null
		});

		expect(store.identity()?.display).toBe('Leo Araujo');
	});

	it('presents the access token to the API, never the identity token', () => {
		expect(signedIn().token()).toBe(cyberdyneAccessToken({ exp: IN_FIFTEEN_MINUTES }));
	});
});

describe('what the tab keeps between two page loads', () => {
	it('keeps the whole credential, so a reload can still renew and sign out', () => {
		const storage = memoryStorage();
		signedIn(storage);

		const reopened = new SessionStore({ storage, now: () => NOW });

		expect(reopened.isAuthenticated()).toBe(true);
		expect(reopened.refreshToken()).toBe('rt-1');
		expect(reopened.idToken()).toBe(cyberdyneIdToken());
		expect(reopened.identity()?.display).toBe('leo@cyberdynecorp.ai');
	});

	it('keeps a lapsed session’s refresh token, so it can be renewed without a prompt', () => {
		const storage = memoryStorage();
		signedIn(storage);

		const later = new SessionStore({ storage, now: () => NOW + 16 * 60 * 1000 });

		expect(later.current().kind).toBe('expired');
		expect(later.renewalDue(RENEWAL_LEAD_MS)).toBe(true);
	});

	it('still reads a bare access token an earlier build stored', () => {
		const storage = memoryStorage();
		storage.write(SESSION_KEY, mappedPerson({ exp: IN_FIFTEEN_MINUTES }));

		const reopened = new SessionStore({ storage, now: () => NOW });

		expect(reopened.identity()?.display).toBe('Rafa');
		expect(reopened.refreshToken()).toBeNull();
	});

	it('keeps none of it after sign-out', () => {
		const storage = memoryStorage();
		const store = signedIn(storage);

		store.signOut();

		expect(storage.read(SESSION_KEY)).toBeNull();
		expect(store.refreshToken()).toBeNull();
		expect(store.idToken()).toBeNull();
	});
});

describe('renewing before the access token lapses', () => {
	it('does nothing while the access token has long to run', async () => {
		const store = signedIn();
		const { refresh, asked } = refresher({ kind: 'renewed', credential: renewed() });

		await new SessionRenewal(store, { now: () => NOW }).ensureFresh(refresh);

		expect(asked).toEqual([]);
	});

	it('spends the refresh token and replaces the whole credential (rotation)', async () => {
		const nearlyLapsed = NOW + 14.5 * 60 * 1000;
		const store = signedIn(memoryStorage(), () => nearlyLapsed);
		const next = renewed();
		const { refresh, asked } = refresher({ kind: 'renewed', credential: next });

		await new SessionRenewal(store, { now: () => nearlyLapsed }).ensureFresh(refresh);

		expect(asked).toEqual(['rt-1']);
		expect(store.token()).toBe(next.accessToken);
		expect(store.refreshToken()).toBe('rt-2');
	});

	it('renews a session a reload found lapsed', async () => {
		const storage = memoryStorage();
		signedIn(storage);
		const later = () => NOW + 16 * 60 * 1000;
		const store = new SessionStore({ storage, now: later });
		const fresh = cyberdyneAccessToken({ exp: Math.floor(later() / 1000) + 900 });
		const { refresh } = refresher({ kind: 'renewed', credential: renewed({ accessToken: fresh }) });

		await new SessionRenewal(store, { now: later }).ensureFresh(refresh);

		expect(store.current().kind).toBe('active');
		expect(store.isAuthenticated()).toBe(true);
	});

	it('keeps the refresh token it had when the answer carries none', async () => {
		const store = signedIn(memoryStorage(), () => NOW + 14.5 * 60 * 1000);

		store.renew(renewed({ refreshToken: null, idToken: null }));

		expect(store.refreshToken()).toBe('rt-1');
		expect(store.idToken()).toBe(cyberdyneIdToken());
	});

	it('spends one refresh token once, however many callers ask at the same time', async () => {
		const nearlyLapsed = () => NOW + 14.5 * 60 * 1000;
		const store = signedIn(memoryStorage(), nearlyLapsed);
		const { refresh, asked } = refresher({ kind: 'renewed', credential: renewed() });
		const renewal = new SessionRenewal(store, { now: nearlyLapsed });

		await Promise.all([renewal.ensureFresh(refresh), renewal.ensureFresh(refresh)]);

		expect(asked).toEqual(['rt-1']);
	});

	it('falls back to the in-place re-authentication when the refresh token is refused', async () => {
		const nearlyLapsed = () => NOW + 14.5 * 60 * 1000;
		const store = signedIn(memoryStorage(), nearlyLapsed);
		const { refresh } = refresher({ kind: 'refused', message: 'refresh token already used or unknown' });

		await new SessionRenewal(store, { now: nearlyLapsed }).ensureFresh(refresh);

		expect(store.current().kind).toBe('expired');
		expect(store.identity()?.display).toBe('leo@cyberdynecorp.ai');
		expect(store.refreshToken()).toBeNull();
	});

	it('changes nothing when the identity service cannot be reached', async () => {
		const nearlyLapsed = () => NOW + 14.5 * 60 * 1000;
		const store = signedIn(memoryStorage(), nearlyLapsed);
		const before = store.token();
		const { refresh } = refresher({ kind: 'unavailable', message: 'down' });

		await new SessionRenewal(store, { now: nearlyLapsed }).ensureFresh(refresh);

		expect(store.token()).toBe(before);
		expect(store.refreshToken()).toBe('rt-1');
	});

	it('plans each renewal for shortly before its access token lapses', () => {
		const store = signedIn();
		const planned: number[] = [];
		const renewal = new SessionRenewal(store, {
			now: () => NOW,
			schedule: (_run, delay) => {
				planned.push(delay);
				return () => {};
			}
		});

		renewal.watch(refresher({ kind: 'renewed', credential: renewed() }).refresh);

		expect(planned).toEqual([900_000 - RENEWAL_LEAD_MS]);
	});

	it('plans nothing for a session it cannot renew', () => {
		const store = new SessionStore({ storage: memoryStorage(), now: () => NOW });
		store.signIn(mappedPerson({ exp: IN_FIFTEEN_MINUTES }));
		const planned: number[] = [];

		new SessionRenewal(store, {
			now: () => NOW,
			schedule: (_run, delay) => {
				planned.push(delay);
				return () => {};
			}
		}).watch(refresher({ kind: 'unavailable', message: '' }).refresh);

		expect(planned).toEqual([]);
	});
});
