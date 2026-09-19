<script lang="ts">
	/**
	 * One button, and nothing from the canon anywhere on the page.
	 *
	 * The button starts an authorization code exchange bound to a proof key this
	 * application generates (`auth-integration`); there is no password field
	 * here and there could not be one, because the flow has nowhere to put it.
	 */
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import { beginSignIn } from '$lib/session/oidc';
	import { browserStorage } from '$lib/session/storage';
	import type { PageData } from './$types';
	import type { SignInScreen } from './+page';

	let { data }: { data: PageData } = $props();

	let starting = $state(false);

	async function start(screen: SignInScreen): Promise<void> {
		starting = true;
		const request = await beginSignIn(screen.configuration, {
			storage: browserStorage(),
			next: screen.next
		});
		globalThis.location.assign(request.url);
	}
</script>

<h1>Sign in to CyberCanon</h1>

<RouteScreen state={data.state}>
	{#snippet content(screen: SignInScreen)}
		<p>
			CyberCanon shows nothing from a project until it knows who is reading it.
			{#if screen.next !== '/'}You will be taken to <code>{screen.next}</code> afterwards.{/if}
		</p>
		<button type="button" onclick={() => start(screen)} disabled={starting}>
			{starting ? 'Taking you to CyberdyneAuth…' : 'Sign in with CyberdyneAuth'}
		</button>
	{/snippet}
</RouteScreen>
