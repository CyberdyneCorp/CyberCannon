<script lang="ts">
	/**
	 * D7 — the viewer's scene module loads only on the viewer surface.
	 *
	 * The import below is dynamic and it is the only reference to
	 * `$lib/viewer/scene` in the application. That is what puts three.js in a
	 * chunk of its own: a person browsing an asset list never asks for it, and
	 * a static import anywhere would silently undo that.
	 * `tests/tooling/test_web_structure.py` fails the build if one appears.
	 *
	 * Which surface is shown is the address's answer (D3), already resolved
	 * against the surfaces the asset has — so by the time this component runs,
	 * a surface the asset no longer has has already degraded to the overview
	 * and the person has already been told why.
	 */
	import type { Surface } from '$lib/address';
	import type { AssetPage } from '$lib/asset';
	import AssetOverview from './AssetOverview.svelte';

	interface Props {
		surface: Surface;
		page: AssetPage;
	}

	let { surface, page }: Props = $props();

	let canvas: HTMLCanvasElement | null = $state(null);

	$effect(() => {
		if (surface !== 'viewer' || !canvas) return;
		const target = canvas;
		let dispose: (() => void) | null = null;
		import('$lib/viewer/scene').then(({ mountScene }) => {
			dispose = mountScene(target).dispose;
		});
		return () => dispose?.();
	});
</script>

{#if surface === 'overview'}
	<AssetOverview {page} />
{:else if surface === 'sheet'}
	<p class="pending">The model sheet over these views is delivered by add-model-sheet-2d.</p>
{:else}
	<canvas bind:this={canvas} width="640" height="360"></canvas>
{/if}
