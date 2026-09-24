/**
 * Tasks 3.5, 3.6, 3.7 and 3.8 — who is acting, what they are told, and what
 * leaves with them.
 *
 * Four requirements of `web-session` are executed here, and each is asserted as
 * the requirement is worded rather than as the implementation is shaped:
 *
 * * **signing out clears local state** — not "the store was reset", but *"no
 *   project or asset content SHALL remain reachable"*, which is a claim about
 *   the query cache and is asserted against it;
 * * **the identity in use is always visible** — the frame is given a label, and
 *   it is the session's person rather than a subject nobody recognises;
 * * **an unmapped person is told before they are refused** — the notice exists
 *   with no write anywhere near it, which is the whole of "before";
 * * **an identity provider outage degrades rather than blanks** — reads are
 *   untouched and the unavailability has a sentence.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { QueryCache } from '../src/lib/api/cache';
import { resources } from '../src/lib/api/resources';
import { probeApi } from '../src/lib/api/availability';
import {
	REPOSITORY_ACTIONS,
	UNMAPPED_HEADLINE,
	claimsOf,
	identityFrom,
	isMapped,
	unmappedNotice
} from '../src/lib/session/identity';
import { SESSION_KEY, SessionStore, actingIdentity } from '../src/lib/session/session';
import { memoryStorage } from '../src/lib/session/storage';
import { SESSION_LAPSED, SIGN_IN_REQUIRED, signedOutScreen } from '../src/lib/session/guard';
import {
	IDENTITY_SERVICE,
	VERIFICATION_UNAVAILABLE,
	degradationOf,
	identityProviderDown,
	verificationNotice
} from '../src/lib/session/verification';
import {
	credential,
	cyberdyneAccessToken,
	cyberdyneIdToken,
	mappedPerson,
	unmappedPerson
} from './support/credentials';

const NOW = 1_700_000_000_000;

function store(options: { forget?: () => void; now?: () => number } = {}) {
	return new SessionStore({ storage: memoryStorage(), now: () => NOW, ...options });
}

describe('the identity a credential describes', () => {
	it('is the subject, the name and the git identity the claims carry', () => {
		const identity = identityFrom(claimsOf(mappedPerson()));

		expect(identity).toEqual({
			subject: 'auth|rafa',
			display: 'Rafa',
			gitIdentity: 'rafa@cyberdyne.com',
			mapping: 'mapped'
		});
	});

	it('falls back to the subject when the credential names nobody', () => {
		expect(identityFrom(claimsOf(credential({ sub: 'auth|rafa' })))?.display).toBe('auth|rafa');
	});

	it('is nothing at all when there is no subject to act as', () => {
		expect(identityFrom(claimsOf(credential({ name: 'Rafa' })))).toBeNull();
	});

	it('survives a credential this application cannot read', () => {
		expect(claimsOf('not-a-token')).toEqual({});
		expect(claimsOf('header.@@@.signature')).toEqual({});
	});
});

describe('the acting identity, on every authenticated screen', () => {
	it('is the person the session belongs to', () => {
		const session = store();
		session.signIn(mappedPerson());

		expect(actingIdentity(session.current())).toEqual({
			signedIn: true,
			label: 'Rafa',
			subject: 'auth|rafa',
			expired: false
		});
	});

	it('is nobody before anyone has signed in', () => {
		expect(actingIdentity(store().current())).toBeNull();
	});

	it('still names the person whose session expired, so the offer can address them', () => {
		const session = store();
		session.signIn(mappedPerson());
		session.expire();

		expect(actingIdentity(session.current())).toMatchObject({
			label: 'Rafa',
			signedIn: false,
			expired: true
		});
	});
});

describe('the credential the client carries', () => {
	it('is the one the session was established with', () => {
		const session = store();
		const token = mappedPerson();
		session.signIn(token);

		expect(session.token()).toBe(token);
		expect(session.isAuthenticated()).toBe(true);
	});

	it('is withheld once the credential has lapsed by its own claim', () => {
		const session = store();
		session.signIn(mappedPerson({ exp: Math.floor(NOW / 1000) - 1 }));

		expect(session.token()).toBeNull();
		expect(session.isAuthenticated()).toBe(false);
	});

	it('survives a reload within the tab, and not a lapse', () => {
		const storage = memoryStorage();
		new SessionStore({ storage, now: () => NOW }).signIn(mappedPerson());

		const reopened = new SessionStore({ storage, now: () => NOW });

		expect(reopened.isAuthenticated()).toBe(true);
		expect(reopened.identity()?.display).toBe('Rafa');
	});

	it('comes back as expired when what was stored has since lapsed', () => {
		const storage = memoryStorage();
		storage.write(SESSION_KEY, mappedPerson({ exp: Math.floor(NOW / 1000) - 60 }));

		expect(new SessionStore({ storage, now: () => NOW }).current().kind).toBe('expired');
	});
});

describe('signing out', () => {
	it('leaves no project or asset content behind', () => {
		const cache = new QueryCache();
		cache.set(resources.assets('ironwood'), { items: ['mech_scout'] });
		cache.set(resources.asset('ironwood', 'mech_scout'), { body: 'a specification' });
		const session = store({ forget: () => cache.clear() });
		session.signIn(mappedPerson());

		session.signOut();

		expect(cache.keys()).toEqual([]);
		expect(cache.peek(resources.asset('ironwood', 'mech_scout'))).toBeUndefined();
	});

	it('leaves no credential behind either', () => {
		const storage = memoryStorage();
		const session = new SessionStore({ storage, now: () => NOW });
		session.signIn(mappedPerson());

		session.signOut();

		expect(storage.read(SESSION_KEY)).toBeNull();
		expect(session.identity()).toBeNull();
		expect(new SessionStore({ storage, now: () => NOW }).isAuthenticated()).toBe(false);
	});

	it('leaves the next person nothing to read without signing in again', () => {
		const session = store();
		session.signIn(mappedPerson());
		session.signOut();

		expect(signedOutScreen(session)).toMatchObject({ kind: 'forbidden', remedy: 'sign-in' });
	});
});

describe('the screen a person with no session is offered', () => {
	it('is an offer of sign-in rather than an error', () => {
		expect(signedOutScreen(store())).toEqual({
			kind: 'forbidden',
			message: SIGN_IN_REQUIRED,
			remedy: 'sign-in'
		});
	});

	it('says so differently when a session lapsed rather than never existed', () => {
		const session = store();
		session.signIn(mappedPerson());
		session.expire();

		expect(signedOutScreen(session)).toMatchObject({ message: SESSION_LAPSED });
	});

	it('is nothing at all for a session that is in order', () => {
		const session = store();
		session.signIn(mappedPerson());

		expect(signedOutScreen(session)).toBeNull();
	});
});

describe('a person with no mapped git identity', () => {
	it('is told before they write anything, not after they are refused', () => {
		const identity = identityFrom(claimsOf(unmappedPerson()));

		const notice = unmappedNotice(identity);

		expect(notice).toContain(UNMAPPED_HEADLINE);
		expect(notice).toContain('auth|newcomer');
		expect(notice).toContain('.canon/actors.yaml');
	});

	it('is told which actions are unavailable, by name', () => {
		const notice = unmappedNotice(identityFrom(claimsOf(unmappedPerson()))) ?? '';

		for (const action of REPOSITORY_ACTIONS) expect(notice).toContain(action);
	});

	it('is told that reading is unaffected, because it is', () => {
		expect(unmappedNotice(identityFrom(claimsOf(unmappedPerson())))).toContain(
			'Reading is unaffected'
		);
	});

	it('is nobody, when the credential carries a git identity', () => {
		const identity = identityFrom(claimsOf(mappedPerson()));

		expect(isMapped(identity)).toBe(true);
		expect(unmappedNotice(identity)).toBeNull();
	});

	it('is not warned before there is anyone to warn', () => {
		expect(unmappedNotice(null)).toBeNull();
	});
});

describe('a credential that says nothing about a git identity', () => {
	// Regression: CyberdyneAuth emits no `git_emails` claim, so every signed-in
	// person was told they had no git identity — including people mapped in
	// `.canon/actors.yaml`, who can write.
	const identity = identityFrom(claimsOf(cyberdyneAccessToken()), claimsOf(cyberdyneIdToken()));

	it('is an unknown mapping, not an unmapped one', () => {
		expect(identity?.mapping).toBe('unknown');
		expect(isMapped(identity)).toBe(false);
	});

	it('warns nobody, because nothing is known to warn about', () => {
		expect(unmappedNotice(identity)).toBeNull();
	});
});

describe('an identity provider outage', () => {
	const readiness = {
		status: 'ready',
		dependencies: [{ name: IDENTITY_SERVICE, state: 'unavailable' }],
		degraded: [IDENTITY_SERVICE]
	};

	function answering(body: unknown, status = 200): typeof fetch {
		return (async () =>
			new Response(JSON.stringify(body), {
				status,
				headers: { 'Content-Type': 'application/json' }
			})) as unknown as typeof fetch;
	}

	it('is read from the signal the API already publishes', async () => {
		const reach = await probeApi(answering(readiness), 'https://api.canon.example');

		expect(reach.reachable).toBe(true);
		expect(reach.degraded).toEqual([IDENTITY_SERVICE]);
	});

	it('is stated, rather than turned into a blank screen', () => {
		expect(verificationNotice({ degraded: [IDENTITY_SERVICE] })).toBe(VERIFICATION_UNAVAILABLE);
		expect(VERIFICATION_UNAVAILABLE).toContain('reading');
	});

	it('leaves a valid session valid, so browsing continues', () => {
		const session = store();
		session.signIn(mappedPerson());

		expect(identityProviderDown({ degraded: [IDENTITY_SERVICE] })).toBe(true);
		expect(session.isAuthenticated()).toBe(true);
		expect(signedOutScreen(session)).toBeNull();
	});

	it('says nothing when the identity service is not the thing that is down', () => {
		expect(verificationNotice({ degraded: ['search_index'] })).toBeNull();
		expect(verificationNotice(null)).toBeNull();
	});

	it('reads a readiness body defensively, because a proxy may answer instead', () => {
		expect(degradationOf(null)).toEqual({ degraded: [] });
		expect(degradationOf({ degraded: 'identity_service' })).toEqual({ degraded: [] });
		expect(degradationOf({ degraded: [1, IDENTITY_SERVICE] })).toEqual({
			degraded: [IDENTITY_SERVICE]
		});
	});
});

describe('what the store tells anyone watching', () => {
	let seen: string[];

	beforeEach(() => {
		seen = [];
	});

	it('is every state it moves through, including the one it starts in', () => {
		const session = store();
		session.subscribe((current) => seen.push(current.kind));

		session.signIn(mappedPerson());
		session.expire();
		session.signOut();

		expect(seen).toEqual(['anonymous', 'active', 'expired', 'anonymous']);
	});

	it('stops when the watcher stops', () => {
		const session = store();
		const unsubscribe = session.subscribe((current) => seen.push(current.kind));

		unsubscribe();
		session.signIn(mappedPerson());

		expect(seen).toEqual(['anonymous']);
	});
});
