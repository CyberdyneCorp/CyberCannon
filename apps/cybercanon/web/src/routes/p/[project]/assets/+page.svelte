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
				<span class="group">exact matches</span>: <span class="count">{view.rows.length}</span> of
				<span class="count">{view.total}</span>
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
	/*
	 * The exact group’s label, and it is a requirement rather than a caption.
	 * `semantic-search-delegation` puts the results in two labelled groups with
	 * the exact one first; this is that label, and `SemanticResults` carries
	 * the other. The two are set alike — the same small caps, the same quiet
	 * ink — so neither reads as the heading of the answer and the other as a
	 * footnote to it.
	 */
	.searched {
		margin: 0 0 var(--space-3);
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.group {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		color: var(--color-text);
	}

	/*
	 * The counts are Space Mono. They are figures read against each other —
	 * *this many of that many* — and the mono’s tabular figures keep them the
	 * same width, so the sentence does not reflow as a search narrows.
	 */
	.count {
		font-family: var(--font-mono);
		color: var(--color-text);
	}

	/* The way out of a filtered screen, offered inside the route state’s own
	   panel, so it carries that panel’s emphasis rather than its own. */
	.clear {
		font-weight: var(--font-weight-strong);
	}
</style>
