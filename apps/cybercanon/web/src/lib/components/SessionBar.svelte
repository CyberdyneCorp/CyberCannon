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
	 */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { actingIdentity, sessionStore, type Session } from '$lib/session/session';
	import { currentAddress, HOME, signInAddress } from '$lib/session/intent';
	import { writeGate } from '$lib/session';

	let session = $state<Session>(sessionStore.current());

	$effect(() => sessionStore.subscribe((next) => (session = next)));

	const acting = $derived(actingIdentity(session));
	const signIn = $derived(signInAddress(currentAddress(page.url)));

	function signOut(): void {
		writeGate.discard();
		sessionStore.signOut();
		goto(HOME, { invalidateAll: true });
	}
</script>

<div class="session" data-signed-in={acting?.signedIn ? 'yes' : 'no'}>
	{#if acting}
		<span class="acting" data-subject={acting.subject}>
			Signed in as {acting.label}
			{#if acting.expired}<em>(session expired)</em>{/if}
		</span>
		<button type="button" onclick={signOut}>Sign out</button>
	{:else}
		<a class="sign-in" href={signIn}>Sign in</a>
	{/if}
</div>

<style>
	.session {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: baseline;
		margin-inline-start: auto;
	}
</style>
