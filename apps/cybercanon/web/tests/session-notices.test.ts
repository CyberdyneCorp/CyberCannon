/**
 * Task 3.7 — the warning an unmapped person is owed *before* they write.
 *
 * `web-session` is explicit about the timing: the application SHALL state that
 * a person has no mapped git identity and SHALL indicate which actions are
 * unavailable *"before they attempt one — rather than only reporting a refusal
 * after they have written something"*. The refusal itself is real and lives in
 * the domain (`add-web-backend` D8); this is the part that has to arrive in
 * time to matter.
 *
 * "Before they attempt one" is asserted structurally, because it is a claim
 * about *where* the notice is rather than about what it says: it is rendered
 * from the frame, from the session alone, with no write having been started and
 * nothing about a write in its inputs. A notice that needed a write to have
 * been attempted could not be rendered by this test at all.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import SessionNotices from '../src/lib/components/SessionNotices.svelte';
import { REPOSITORY_ACTIONS, UNMAPPED_HEADLINE } from '../src/lib/session/identity';
import { sessionStore } from '../src/lib/session/session';
import { cyberdyneAccessToken, mappedPerson, unmappedPerson } from './support/credentials';

function notices(verification: string | null = null): string {
	return render(SessionNotices, { props: { verification } }).body;
}

afterEach(() => {
	sessionStore.signOut();
});

describe('a person with no mapped git identity is warned early', () => {
	it('states it as soon as they are signed in, with no write attempted', () => {
		sessionStore.signIn(unmappedPerson());

		const body = notices();

		expect(body).toContain('data-notice="unmapped"');
		expect(body).toContain(UNMAPPED_HEADLINE);
	});

	it('names the actions that are unavailable as a result', () => {
		sessionStore.signIn(unmappedPerson());

		const body = notices();

		for (const action of REPOSITORY_ACTIONS) {
			expect(body).toContain(action);
		}
	});

	it('says what would fix it, since a warning with no remedy is a dead end', () => {
		sessionStore.signIn(unmappedPerson());

		expect(notices()).toContain('.canon/actors.yaml');
	});

	it('says reading is unaffected, because it is', () => {
		sessionStore.signIn(unmappedPerson());

		expect(notices()).toContain('Reading is unaffected');
	});

	it('warns nobody whose credential carries a git identity', () => {
		sessionStore.signIn(mappedPerson());

		expect(notices()).not.toContain('data-notice="unmapped"');
	});

	it('warns nobody who is not signed in', () => {
		expect(notices()).not.toContain('data-notice="unmapped"');
	});

	it('warns nobody whose credential does not state a git identity either way', () => {
		sessionStore.signIn(cyberdyneAccessToken());

		expect(notices()).not.toContain('data-notice="unmapped"');
	});
});

describe('an identity provider outage is stated beside it', () => {
	it('renders both notices at once when both apply', () => {
		sessionStore.signIn(unmappedPerson());

		const body = notices('re-verification is unavailable while the identity service is down');

		expect(body).toContain('data-notice="unmapped"');
		expect(body).toContain('data-notice="verification"');
	});
});
