<script lang="ts">
	/**
	 * Tasks 4.2 and 4.3 — every active filter is on screen and removable on its own.
	 *
	 * `asset-browser`: *"Every active filter SHALL be visible on screen and
	 * individually removable, and the filter state SHALL be part of the
	 * address."* Both halves are the same mechanism here: a filter is removed by
	 * following a link to the address without it (D3), so removing one cannot
	 * disturb another and the result is shareable by construction — there is no
	 * component state to have got out of step with the URL.
	 */
	import type { BrowserAddress } from '$lib/address';
	import { activeFilters, browserAddress, withoutFilter, withoutFilters } from '$lib/address';

	interface Props {
		address: BrowserAddress;
	}

	let { address }: Props = $props();

	const active = $derived(activeFilters(address));
</script>

{#if active.length > 0}
	<section class="filters" aria-label="Active filters">
		<ul>
			{#each active as filter (filter.name)}
				<li class="filter" data-filter={filter.name} data-value={filter.value}>
					<span class="what">{filter.name}: {filter.value}</span>
					<a class="remove" data-removes={filter.name} href={browserAddress(withoutFilter(address, filter.name))}
						>Remove</a
					>
				</li>
			{/each}
		</ul>
		<a class="clear" href={browserAddress(withoutFilters(address))}>Clear the filters</a>
	</section>
{/if}

<style>
	.filters ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.filter {
		display: flex;
		gap: 0.25rem;
		align-items: baseline;
		border: 1px solid currentColor;
		border-radius: 999px;
		padding: 0.125rem 0.5rem;
	}
</style>
