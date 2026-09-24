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
	import { annotationViewModel } from '$lib/annotation';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
	let attached = '';

	function attachAnnotations(): void {
		if (!data.annotationModel || !['content', 'degraded'].includes(data.state.kind)) return;
		const key = `${data.address.project}/${data.address.asset}`;
		if (attached === key) return;
		annotationViewModel.attach(data.annotationModel, data.address.project, data.address.asset);
		attached = key;
	}

	attachAnnotations();
	$effect(attachAnnotations);
</script>

<h1>{data.address.asset}</h1>

<RouteScreen state={data.state}>
	{#snippet content(page: AssetPage)}
		<p class="belongs-to">
			<strong>{page.name}</strong> in project <span class="project">{page.project}</span>
		</p>
		<AssetSurface
			surface={data.address.surface}
			{page}
			annotations={data.annotations ?? null}
			documents={data.documents ?? null}
			model={annotationViewModel}
			annotation={data.address.annotation ?? null}
			viewer={data.viewer ?? null}
			sheetImages={data.sheetImages ?? {}}
			onReanchor={data.reanchor}
			onRetryPreview={data.retryPreview}
		/>
	{/snippet}
</RouteScreen>

<style>
	/*
	 * Which asset this is and which project it belongs to. `app-navigation`
	 * puts the project on every screen; the asset page states it beside the
	 * name as well, because this is the screen from which somebody acts.
	 *
	 * The project takes the mono, because it is an identifier rather than a
	 * name — the same face this interface sets `mech_scout` and `gate_dock`
	 * in everywhere else — and the asset's display name beside it stays in
	 * the body face, which is what tells the two apart at a glance.
	 */
	h1 {
		margin-block-end: var(--space-1);
	}

	.belongs-to {
		margin: 0 0 var(--space-3);
		font-size: var(--text-h5);
	}

	.project {
		font-family: var(--font-mono);
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}
</style>
