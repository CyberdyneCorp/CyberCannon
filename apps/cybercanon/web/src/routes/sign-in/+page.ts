/**
 * The unauthenticated landing: an offer, never an error.
 *
 * `web-session` says what this screen is not allowed to be — *"a person
 * arriving without a valid session SHALL be shown a sign-in affordance and
 * SHALL NOT be shown an error, a blank screen, or any project or asset
 * content"* — and this load reads nothing from the canon, so the last of those
 * is structural rather than careful.
 *
 * It carries the address the person was going to (D3: in the address, as
 * `?next=`), because the next requirement is that they arrive there afterwards.
 * A deployment with no identity service configured resolves to `degraded`
 * rather than failing: the application is up, sign-in is what is not.
 */
import type { PageLoad } from './$types';
import { intendedAddress } from '$lib/session/intent';
import { signInConfiguration } from '$lib/config';
import { content, degraded } from '$lib/route-state';
import type { SignInConfig } from '$lib/session/oidc';

export const NOT_CONFIGURED =
	'This deployment has no identity service configured, so nobody can sign in ' +
	'here yet. Everything else about the application is working.';

export const SIGN_IN = 'Sign-in';

export interface SignInScreen {
	readonly next: string;
	readonly configuration: SignInConfig;
}

export const load: PageLoad = ({ url }) => {
	const next = intendedAddress(url);
	const configuration = signInConfiguration(url.origin);
	const state = configuration
		? content<SignInScreen>({ next, configuration })
		: degraded<SignInScreen>(null, [SIGN_IN], NOT_CONFIGURED);
	return { next, state };
};
