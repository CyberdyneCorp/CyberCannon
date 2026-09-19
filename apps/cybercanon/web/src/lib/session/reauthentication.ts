/**
 * D5's *"in place"*, taken literally: the page is never unloaded.
 *
 * The whole point of holding a write is that the person's text is still in the
 * component that holds it. A full-page redirect to the identity service would
 * unload that component, and the only way back would be to serialise the draft
 * somewhere — which is the same as admitting the redirect lost it and then
 * rebuilding it. So re-authentication happens in a second window opened from
 * the person's own click, and this tab keeps running the whole time.
 *
 * The second window lands on `/signed-in` exactly as the ordinary flow does. It
 * posts the authorization code and state back and closes; **the code is
 * redeemed here**, in the tab that generated the proof key, so the exchange
 * never depends on whether a browser copied session storage into the popup.
 *
 * Three ways it ends, and none of them loses anything: a credential arrives and
 * the held write is replayed, the window is closed and the write stays held, or
 * nothing happens for long enough that waiting stops being honest. The person
 * can always decline instead, which keeps their text and sends nothing.
 */

import type { SignInConfig, SignInOutcome, Transport } from './oidc';
import { beginSignIn, completeSignIn } from './oidc';
import type { SessionStorage } from './storage';

export const CREDENTIAL_MESSAGE = 'cybercanon.sign-in';

export const WINDOW_BLOCKED =
	'The sign-in window could not be opened. Allow pop-ups for this site, or ' +
	'sign in again in another tab — your text stays here either way.';

export const WINDOW_CLOSED =
	'The sign-in window was closed before a credential arrived. Your text is ' +
	'still here; try again whenever you are ready.';

export const TIMED_OUT =
	'Sign-in did not complete in time. Your text is still here; try again ' +
	'whenever you are ready.';

/** What the second window sends back. Never a credential — a code and its state. */
export interface SignInMessage {
	readonly type: typeof CREDENTIAL_MESSAGE;
	readonly code?: string;
	readonly state?: string;
	readonly error?: string;
	readonly error_description?: string;
}

export interface OpenedWindow {
	readonly closed: boolean;
	close(): void;
}

export interface Opener {
	open(url: string): OpenedWindow | null;
}

export interface MessageSource {
	addEventListener(type: 'message', listener: (event: MessageEvent) => void): void;
	removeEventListener(type: 'message', listener: (event: MessageEvent) => void): void;
}

export interface ReauthenticateOptions {
	readonly opener: Opener;
	readonly messages: MessageSource;
	readonly storage: SessionStorage;
	readonly transport: Transport;
	/** This application's origin. A message from anywhere else is not ours. */
	readonly origin: string;
	readonly pollMs?: number;
	readonly timeoutMs?: number;
}

const POLL_MS = 400;
const TIMEOUT_MS = 5 * 60 * 1000;

/**
 * Offer a credential without leaving the page.
 *
 * It resolves rather than throwing in every case, because the caller is a
 * prompt beside somebody's unsaved paragraph and an exception there is a blank
 * panel where their work used to be.
 */
export async function reauthenticateInPlace(
	config: SignInConfig,
	options: ReauthenticateOptions
): Promise<SignInOutcome> {
	const request = await beginSignIn(config, { storage: options.storage, next: '/' });
	const opened = options.opener.open(request.url);
	if (!opened) return { kind: 'unavailable', message: WINDOW_BLOCKED };
	const answer = await awaitAnswer(opened, options);
	opened.close();
	if (!answer) return { kind: 'unavailable', message: answerless(opened) };
	return completeSignIn(config, answerAsUrl(config.redirectUri, answer), {
		storage: options.storage,
		transport: options.transport
	});
}

/**
 * The code and state the second window sent, or `null` when it never did.
 *
 * Only messages from this application's own origin are read: a page in another
 * tab can post anything it likes, and a sign-in that accepted a code from an
 * arbitrary sender would be exactly the confused-deputy this flow's state
 * parameter exists to prevent.
 */
function awaitAnswer(
	opened: OpenedWindow,
	options: ReauthenticateOptions
): Promise<SignInMessage | null> {
	return new Promise((resolve) => {
		const finish = (answer: SignInMessage | null) => {
			options.messages.removeEventListener('message', listener);
			clearInterval(poll);
			clearTimeout(expiry);
			resolve(answer);
		};
		const listener = (event: MessageEvent) => {
			const message = signInMessage(event, options.origin);
			if (message) finish(message);
		};
		options.messages.addEventListener('message', listener);
		const poll = setInterval(() => {
			if (opened.closed) finish(null);
		}, options.pollMs ?? POLL_MS);
		const expiry = setTimeout(() => finish(null), options.timeoutMs ?? TIMEOUT_MS);
	});
}

function signInMessage(event: MessageEvent, origin: string): SignInMessage | null {
	if (event.origin !== origin) return null;
	const data = event.data as SignInMessage | null;
	return data && data.type === CREDENTIAL_MESSAGE ? data : null;
}

/**
 * The answer, shaped as the address the ordinary flow would have arrived at.
 *
 * One redemption path for both flows: the full-page return and the in-place one
 * differ in how the code travels, and in nothing else.
 */
function answerAsUrl(redirectUri: string, answer: SignInMessage): URL {
	const url = new URL(redirectUri);
	for (const [name, value] of Object.entries(answer)) {
		if (name !== 'type' && typeof value === 'string') url.searchParams.set(name, value);
	}
	return url;
}

function answerless(opened: OpenedWindow): string {
	return opened.closed ? WINDOW_CLOSED : TIMED_OUT;
}

/** The window that opened this one, when there is one. */
export interface RelayTarget {
	postMessage(message: SignInMessage, targetOrigin: string): void;
}

/**
 * The second window's whole job: hand the answer back and get out of the way.
 *
 * It forwards the authorization code, never a credential — the code is useless
 * without the proof key, which never left the tab that generated it. The
 * message is addressed to this application's own origin rather than to `*`, so
 * a page that happens to be listening elsewhere is not a recipient.
 */
export function relaySignIn(url: URL, opener: RelayTarget, origin: string): SignInMessage {
	const message: SignInMessage = {
		type: CREDENTIAL_MESSAGE,
		...named(url, 'code'),
		...named(url, 'state'),
		...named(url, 'error'),
		...named(url, 'error_description')
	};
	opener.postMessage(message, origin);
	return message;
}

function named(url: URL, parameter: string): Record<string, string> {
	const value = url.searchParams.get(parameter);
	return value ? { [parameter]: value } : {};
}

/** The browser's own window, as far as this module needs one. */
export function browserOpener(features = 'width=520,height=680'): Opener {
	return {
		open: (url) => globalThis.open?.(url, CREDENTIAL_MESSAGE, features) ?? null
	};
}
