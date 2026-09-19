<script lang="ts">
	/**
	 * What is on screen for the moment between the answer and the address.
	 *
	 * On the ordinary path the load has already sent the person on, so this is
	 * rendered only when something did not work — or in the second window of an
	 * in-place re-authentication, which closes itself and is looked at by nobody
	 * unless the browser refuses to close it.
	 */
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import type { PageData } from './$types';
	import type { Completion } from './+page';

	let { data }: { data: PageData } = $props();
</script>

<h1>Signing you in</h1>

<RouteScreen state={data.state}>
	{#snippet content(completion: Completion)}
		{#if completion.relayed}
			<p>You are signed in. This window can be closed.</p>
		{:else}
			<p>You are signed in.</p>
		{/if}
	{/snippet}
</RouteScreen>
