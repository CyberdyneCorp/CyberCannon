<script lang="ts">
	/**
	 * D7 — the viewer's scene module loads only on the viewer surface.
	 *
	 * The import below is dynamic and it is the only reference to
	 * `$lib/viewer/scene` in the application. That is what puts three.js in a
	 * chunk of its own: a person browsing an asset list never asks for it, and
	 * a static import anywhere would silently undo that.
	 * `tests/tooling/test_web_structure.py` fails the build if one appears.
	 */
	import type { Surface } from '$lib/address';
	import type { LensedSpec } from '$lib/api';

	interface Props {
		surface: Surface;
		asset: LensedSpec;
	}

	let { surface, asset }: Props = $props();

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
	<article class="overview">
		<pre>{asset.body}</pre>
	</article>
{:else if surface === 'sheet'}
	<p>The model sheet is delivered by add-model-sheet-2d.</p>
{:else}
	<canvas bind:this={canvas} width="640" height="360"></canvas>
{/if}
