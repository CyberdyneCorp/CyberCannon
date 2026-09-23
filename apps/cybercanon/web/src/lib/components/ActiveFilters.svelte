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
	 *
	 * PRESENTATION. The design draws an active filter as a tag and the way out
	 * of all of them as a quiet action beside the row. The tag here is a box in
	 * full-strength ink rather than a rounded pill: this system rounds nothing,
	 * and the pill was the one thing on this screen that had no token behind it.
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
	.filters {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: var(--space-2) var(--space-3);
		margin-block-end: var(--space-4);
		font-size: var(--text-small);
	}

	.filters ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	/*
	 * A tag, in this system's terms: a black edge, no radius, the neutral
	 * tint, and the name of the filter carried in the system's small caps so a
	 * row of them reads as labels rather than as sentences. Its own way out
	 * sits inside the box, because `asset-browser` requires each filter to be
	 * removable on its own and the control that does it belongs to the filter
	 * it removes.
	 */
	.filter {
		display: flex;
		gap: var(--space-2);
		align-items: baseline;
		background: var(--color-neutral-200);
		color: var(--color-text);
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
		padding: 0 var(--space-2);
	}

	.what {
		font-weight: var(--font-weight-strong);
	}

	.remove {
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
	}

	.clear {
		font-weight: var(--font-weight-strong);
	}
</style>
