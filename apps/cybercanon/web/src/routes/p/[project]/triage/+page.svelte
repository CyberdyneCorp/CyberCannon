<script lang="ts">
	/**
	 * The triage screen.
	 *
	 * The heading names the project from the **address**, so a refusal shows
	 * only what the person themselves opened — the same rule the asset screen
	 * follows and for the same reason.
	 */
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import TriagePass from '$lib/components/TriagePass.svelte';
	import type { TriageQueue } from '$lib/api';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<h1>Triage: {data.address.project}</h1>

<RouteScreen state={data.state}>
	{#snippet content(queue: TriageQueue)}
		<TriagePass {queue} address={data.address} />
	{/snippet}
</RouteScreen>
