/**
 * Coming back from the identity service.
 *
 * The same address serves both ways in, because they differ only in how the
 * authorization code travels:
 *
 * * a **full-page** sign-in redeems the code here, adopts the credential and
 *   sends the person to the address they originally asked for — *"not to a
 *   default landing screen"* (`web-session`);
 * * an **in-place** re-authentication (D5) lands here inside a second window
 *   that this application opened. That window redeems nothing: it hands the
 *   code back to the tab that generated the proof key — the tab still holding
 *   somebody's unsaved paragraph — and closes.
 *
 * Nothing here throws. A refused or unreachable exchange resolves to a member
 * of the closed set (D6) with the reason on it, because a person who has just
 * been bounced through an identity service and back is owed a sentence rather
 * than a stack trace.
 */
import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { signInConfiguration } from '$lib/config';
import { completeSignIn, fetchTransport } from '$lib/session/oidc';
import { relaySignIn, type RelayTarget } from '$lib/session/reauthentication';
import { sessionStore } from '$lib/session/session';
import { browserStorage } from '$lib/session/storage';
import { content, degraded, failed } from '$lib/route-state';
import { NOT_CONFIGURED, SIGN_IN } from '../sign-in/+page';

export const REFUSED = 'sign-in.refused';

export interface Completion {
	/** True when this window's only job was to hand the answer back (D5). */
	readonly relayed: boolean;
}

export const load: PageLoad = async ({ url, fetch }) => {
	const configuration = signInConfiguration(url.origin);
	if (!configuration) {
		return { state: degraded<Completion>(null, [SIGN_IN], NOT_CONFIGURED) };
	}
	const opener = relayTarget();
	if (opener) {
		relaySignIn(url, opener, url.origin);
		closeRelay();
		return { state: content<Completion>({ relayed: true }) };
	}
	const outcome = await completeSignIn(configuration, url, {
		storage: browserStorage(),
		transport: fetchTransport(fetch)
	});
	if (outcome.kind === 'signed-in') {
		sessionStore.signIn(outcome.token);
		redirect(303, outcome.next);
	}
	if (outcome.kind === 'refused') {
		return { state: failed(REFUSED, outcome.message) };
	}
	return { state: degraded<Completion>(null, [SIGN_IN], outcome.message) };
};

/** The window that opened this one, when this is the second window of a D5 flow. */
function relayTarget(): RelayTarget | null {
	const opener = globalThis.window?.opener as RelayTarget | undefined;
	return opener && opener !== globalThis.window ? opener : null;
}

function closeRelay(): void {
	globalThis.window?.close();
}
