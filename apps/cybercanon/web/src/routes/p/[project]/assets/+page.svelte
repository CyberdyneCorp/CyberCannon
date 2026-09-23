<script lang="ts">
	/**
	 * Group 4 — the asset browser: the first screen where a human, rather than
	 * an agent, answers *"where is the mech scout"*.
	 *
	 * The screen holds no state at all. The query and the filters are the
	 * address (D3), the rows are what the route loaded through the one cache
	 * (D2), and every way of having nothing to show is a member of the closed
	 * route-state set (D6) rather than an `{#if}` somebody remembered to write.
	 */
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import ActiveFilters from '$lib/components/ActiveFilters.svelte';
	import AssetListing from '$lib/components/AssetListing.svelte';
	import SearchForm from '$lib/components/SearchForm.svelte';
	import SemanticResults from '$lib/components/SemanticResults.svelte';
	import { activeFilters, browserAddress, withoutFilters } from '$lib/address';
	import type { BrowserView } from '$lib/browser';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const filtered = $derived(activeFilters(data.address).length > 0);
	const cleared = $derived(browserAddress(withoutFilters(data.address)));
</script>

<h1>Assets</h1>

<SearchForm address={data.address} />
<ActiveFilters address={data.address} />

<RouteScreen state={data.state}>
	{#snippet content(view: BrowserView)}
		{#if view.searched}
			<p class="searched">
				<span class="group">exact matches</span>: {view.rows.length} of {view.total}
				result(s) for “{view.query}”, in the order the canon ranks them.
			</p>
		{/if}
		<AssetListing project={data.address.project} rows={view.rows} />
		{#if view.searched}
			<SemanticResults group={view.semantic} />
		{/if}
	{/snippet}
	{#snippet actions()}
		{#if filtered}
			<a class="clear" href={cleared}>Clear the filters</a>
		{/if}
	{/snippet}
</RouteScreen>

<style>
	.searched {
		margin: 0 0 0.75rem;
		font-size: 0.875rem;
	}

	.group {
		text-transform: lowercase;
		font-weight: 600;
	}
</style>
