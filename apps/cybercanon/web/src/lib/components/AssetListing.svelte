<script lang="ts">
	/**
	 * Tasks 4.1 and 4.5 — the rows, with their state and with how they matched.
	 *
	 * `asset-browser` asks a row for four things without opening the asset —
	 * name, identifier, status and owners — and asks a *result* for a fifth: why
	 * it is here, when that was an alias, a tag, a description or a suggestion
	 * nobody has accepted. Both are one component, because a listing row and a
	 * search row are the same line with one extra sentence; two components would
	 * be two places for the status to be spelled differently.
	 *
	 * The order is the order it is given (D9 by way of `asset-lookup`): this
	 * renders `rows`, in sequence, and has nowhere to put a comparator.
	 */
	import { assetAddress, DEFAULT_SURFACE } from '$lib/address';
	import type { BrowserRow } from '$lib/browser';

	interface Props {
		project: string;
		rows: readonly BrowserRow[];
	}

	let { project, rows }: Props = $props();
</script>

<ul class="assets">
	{#each rows as row (row.asset)}
		<li class="asset" data-asset={row.asset}>
			<a
				class="name"
				href={assetAddress({ project, asset: row.asset, surface: DEFAULT_SURFACE })}
				>{row.name}</a
			>
			<code class="identifier">{row.asset}</code>
			{#if row.status}
				<span class="status" data-status={row.status}>{row.status}</span>
			{/if}
			{#if row.owners}
				<ul class="owners">
					{#each row.owners as owner (owner.discipline)}
						<li class="owner" data-discipline={owner.discipline} data-unmapped={owner.unmapped}>
							{owner.discipline}: {owner.display}
						</li>
					{/each}
				</ul>
			{/if}
			{#if row.disclosure}
				<p
					class="disclosure"
					data-matched={row.disclosure.matched}
					data-unaccepted={row.disclosure.unaccepted}
				>
					{row.disclosure.text}
				</p>
			{/if}
		</li>
	{/each}
</ul>

<style>
	.assets,
	.owners {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.assets {
		display: grid;
		gap: 0.75rem;
	}

	.asset {
		display: grid;
		gap: 0.25rem;
	}

	.owners {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.disclosure {
		margin: 0;
		font-size: 0.875rem;
	}
</style>
