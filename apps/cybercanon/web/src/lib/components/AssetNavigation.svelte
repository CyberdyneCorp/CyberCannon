<script lang="ts">
	import type { Surface } from '$lib/address';
	import type { SurfaceEntry } from '$lib/asset';

	interface Props {
		surface: Surface;
		entries: readonly SurfaceEntry[];
	}

	let { surface, entries }: Props = $props();
</script>

<nav class="surfaces" aria-label="Asset surfaces">
	<ul>
		{#each entries as entry (entry.surface)}
			<li
				class="surface"
				data-surface={entry.surface}
				data-available={entry.available}
				data-current={surface === entry.surface}
			>
				{#if entry.available}
					<a
						class="to-surface"
						data-surface={entry.surface}
						href={entry.address}
						aria-current={surface === entry.surface ? 'page' : undefined}>{entry.label}</a
					>
				{:else}
					<span class="unavailable">{entry.label}</span>
					<span class="absence">{entry.absence}</span>
				{/if}
			</li>
		{/each}
	</ul>
</nav>

<style>
	.surfaces {
		margin-block-end: var(--space-6);
	}

	.surfaces ul {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.surface {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		max-width: 22rem;
		background: var(--color-surface);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-2) var(--space-3);
	}

	.surface[data-current='true'] {
		background: var(--color-highlight);
		box-shadow: none;
	}

	.to-surface,
	.unavailable {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-h5);
	}

	.to-surface {
		color: var(--color-text);
	}

	.to-surface:hover {
		color: var(--color-accent-700);
		text-decoration-thickness: var(--border-thin);
	}

	.surface[data-available='false'] {
		background: var(--color-neutral-100);
		box-shadow: none;
	}

	.unavailable,
	.absence {
		color: var(--color-neutral-700);
	}

	.absence {
		font-size: var(--text-small);
	}
</style>
