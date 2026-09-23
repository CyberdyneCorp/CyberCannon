<script lang="ts">
	/**
	 * Who is acting, on every screen — and the way out.
	 *
	 * `web-session` requires the identity in use to be shown *"so that
	 * attribution of anything they write is never a surprise"*, on every
	 * authenticated screen. It lives in the layout's header, so that is
	 * satisfied by construction rather than by each screen remembering. The two
	 * disclosures a session also owes a person — no git identity, and an
	 * identity provider outage — are `SessionNotices`, which is a sibling
	 * because a paragraph does not belong inside a row of controls.
	 *
	 * Signing out ends the identity service's session as well as this tab's:
	 * after the local state is gone the browser is sent to the end-session
	 * relay, because a shared machine whose identity service still remembered
	 * the last person would sign the next one straight back in as them.
	 */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { actingIdentity, sessionStore, type Session } from '$lib/session/session';
	import { currentAddress, HOME, signInAddress } from '$lib/session/intent';
	import { endSessionAddress } from '$lib/session/oidc';
	import { writeGate } from '$lib/session';
	import { signInConfiguration } from '$lib/config';

	let session = $state<Session>(sessionStore.current());

	$effect(() => sessionStore.subscribe((next) => (session = next)));

	const acting = $derived(actingIdentity(session));
	const signIn = $derived(signInAddress(currentAddress(page.url)));

	function signOut(): void {
		const idToken = sessionStore.idToken();
		writeGate.discard();
		sessionStore.signOut();
		const configuration = signInConfiguration(page.url.origin);
		if (configuration) globalThis.location.assign(endSessionAddress(configuration, idToken));
		else goto(HOME, { invalidateAll: true });
	}
</script>

<div class="session" data-signed-in={acting?.signedIn ? 'yes' : 'no'}>
	{#if acting}
		<span class="acting" data-subject={acting.subject}>
			Signed in as {acting.label}
			{#if acting.expired}<em>(session expired)</em>{/if}
		</span>
		<button class="quiet" type="button" onclick={signOut}>Sign out</button>
	{:else}
		<a class="sign-in" href={signIn}>Sign in</a>
	{/if}
</div>

<style>
	.session {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		align-items: baseline;
		margin-inline-start: auto;
		font-size: var(--text-small);
	}

	/* Attribution is the point of this row, so the name is the loudest thing
	   in it — `web-session` wants it read, not found. */
	.acting {
		font-weight: var(--font-weight-strong);
		font-size: var(--text-h5);
	}

	/* An expired session is stated in the second accent, which this system
	   spends on exactly this kind of thing. */
	.acting em {
		font-style: normal;
		font-size: var(--text-small);
		color: var(--color-accent-2-700);
	}

	.sign-in {
		font-weight: var(--font-weight-strong);
		border-block-end: var(--border-thin) solid var(--color-accent-700);
	}

	.sign-in:hover {
		text-decoration: none;
		border-block-end-color: var(--color-accent-600);
	}
</style>
