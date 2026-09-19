<script lang="ts">
	/**
	 * The root address. Project selection is task 5.1; what is here is the
	 * entry point the address scheme needs to exist for — and the screen that
	 * says so when the API cannot be reached, which is a route state rather
	 * than a conditional (D6).
	 */
	import { page } from '$app/state';
	import { projectAddress } from '$lib/address';
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import { sessionStore, type Session } from '$lib/session/session';
	import { currentAddress, signInAddress } from '$lib/session/intent';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let session = $state<Session>(sessionStore.current());

	$effect(() => sessionStore.subscribe((next) => (session = next)));

	const signIn = $derived(signInAddress(currentAddress(page.url)));
</script>

<h1>CyberCanon</h1>

<RouteScreen state={data.state}>
	{#snippet content()}
		{#if session.kind === 'active'}
			<p>Open a project to browse its assets.</p>
			<p><a href={`${projectAddress('example')}/assets`}>example</a></p>
		{:else}
			<!-- `web-session`: an unauthenticated visitor is offered sign-in, and
			     is shown no project of any kind until they take it. -->
			<p>Sign in to read the canon of a project.</p>
			<p><a class="sign-in" href={signIn}>Sign in</a></p>
		{/if}
	{/snippet}
</RouteScreen>
