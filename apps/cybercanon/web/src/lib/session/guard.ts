/**
 * Nothing is read on behalf of a person who is not signed in.
 *
 * `web-session` is unusually blunt about the landing: an unauthenticated person
 * *"SHALL be offered sign-in"* and *"SHALL NOT be shown an error, a blank
 * screen, or any project or asset content"*. Two of those three are satisfied
 * by the closed route-state set already; the third is satisfied here, by not
 * asking.
 *
 * Deciding it in the route rather than waiting for the surface's 401 matters
 * for a reason that is not performance: a screen that renders whatever comes
 * back has to be trusted never to render a cached answer from the *previous*
 * session, and a screen that never asked has nothing to render by accident.
 * The API refusing unauthenticated reads is the enforcement; this is the
 * application not putting itself in the position of testing it.
 *
 * An expired session lands here too, and says so — it is the same screen with a
 * different sentence, because a person whose credential lapsed while they were
 * reading has not done anything wrong.
 */

import { forbidden, type RouteState } from '../route-state';
import { SessionStore, sessionStore } from './session';

export const SIGN_IN_REQUIRED =
	'Sign in to read this project. Nothing from the canon is shown to a browser ' +
	'without a session.';

export const SESSION_LAPSED =
	'Your session has expired. Sign in again to carry on reading — nothing you ' +
	'have written is affected.';

/**
 * The screen to show instead of loading anything, or `null` to carry on.
 *
 * Returning a route state rather than performing a redirect is deliberate: a
 * redirect would replace the address the person asked for, and D3 keeps that
 * address because it is what sign-in has to return them to.
 */
export function signedOutScreen<T>(session: SessionStore = sessionStore): RouteState<T> | null {
	if (session.isAuthenticated()) return null;
	const lapsed = session.current().kind === 'expired';
	return forbidden(lapsed ? SESSION_LAPSED : SIGN_IN_REQUIRED, 'sign-in');
}
