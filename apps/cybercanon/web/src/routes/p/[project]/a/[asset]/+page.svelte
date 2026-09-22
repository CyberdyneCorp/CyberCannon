<script lang="ts">
	/**
	 * The asset screen.
	 *
	 * The heading is the identifier from the **address** rather than anything
	 * loaded, and that is task 5.4 rather than a shortcut: when the answer is
	 * *not found* or *not permitted*, the only thing on screen is what the
	 * person themselves opened. Nothing about an asset they may not read — not
	 * its name, not a line of its content — reaches a screen that knows it
	 * exists. When there is content, the page states its own name and project.
	 */
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import AssetSurface from '$lib/components/AssetSurface.svelte';
	import type { AssetPage } from '$lib/asset';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<h1>{data.address.asset}</h1>

<RouteScreen state={data.state}>
	{#snippet content(page: AssetPage)}
		<p class="belongs-to">
			<strong>{page.name}</strong> in project <span class="project">{page.project}</span>
		</p>
		<AssetSurface surface={data.address.surface} {page} />
	{/snippet}
</RouteScreen>

<style>
	.belongs-to {
		margin: 0 0 0.75rem;
	}
</style>
