<script lang="ts">
	/**
	 * Tasks 6.1, 6.2 and 6.3 — the asset page, rendered.
	 *
	 * The sections come from `$lib/asset` as a closed, total list, and this
	 * component renders every one of them in order. It has no `{#if}` that can
	 * drop a section: a section with nothing in it renders its heading and the
	 * sentence saying why, which is the whole of *"absent content is stated, not
	 * hidden"*. A screen that decided for itself which sections were worth
	 * showing would be the place that requirement quietly stopped holding.
	 *
	 * The surface entry points are the same rule applied to the ways out: a
	 * surface this asset does not have is shown as unavailable with its reason,
	 * rather than as a link that degrades once somebody follows it.
	 */
	import type { AssetPage } from '$lib/asset';

	interface Props {
		page: AssetPage;
	}

	let { page }: Props = $props();
</script>

<div class="asset-page" data-asset={page.asset} data-project={page.project}>
	<nav class="surfaces" aria-label="Surfaces">
		<ul>
			{#each page.surfaces as entry (entry.surface)}
				<li class="surface" data-surface={entry.surface} data-available={entry.available}>
					{#if entry.available}
						<a class="to-surface" data-surface={entry.surface} href={entry.address}
							>{entry.label}</a
						>
					{:else}
						<span class="unavailable">{entry.label}</span>
						<span class="absence">{entry.absence}</span>
					{/if}
				</li>
			{/each}
		</ul>
	</nav>

	{#each page.sections as section (section.id)}
		<section class="section" data-section={section.id} data-empty={section.absence !== null}>
			<h2>{section.heading}</h2>
			{#if section.absence}
				<p class="absence">{section.absence}</p>
			{:else}
				<ul class="entries">
					{#each section.entries as entry, index (`${entry.label ?? ''}:${entry.value}:${index}`)}
						<li class="entry" data-recorded={entry.recorded}>
							{#if entry.label}<span class="label">{entry.label}</span>{/if}
							<span class="value">{entry.value}</span>
							{#if entry.note}<span class="note">{entry.note}</span>{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/each}
</div>

<style>
	.asset-page {
		display: grid;
		gap: 1rem;
	}

	.surfaces ul,
	.entries {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.surfaces ul {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.entries {
		display: grid;
		gap: 0.25rem;
	}

	.label {
		font-weight: 600;
	}

	.absence,
	.note {
		font-size: 0.875rem;
	}

	h2 {
		font-size: 1rem;
		margin: 0 0 0.25rem;
	}
</style>
