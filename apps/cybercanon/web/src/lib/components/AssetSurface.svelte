<script lang="ts">
	/**
	 * D7 — the viewer's scene module loads only on the viewer surface.
	 *
	 * The import below is dynamic and it is the only reference to
	 * `$lib/viewer/scene` in the application. That is what puts three.js in a
	 * chunk of its own: a person browsing an asset list never asks for it, and
	 * a static import anywhere would silently undo that.
	 * `tests/tooling/test_web_structure.py` fails the build if one appears, and
	 * `tests/code-splitting.test.ts` checks the built bundle rather than the
	 * source.
	 *
	 * The factory it resolves to is handed to `Viewer3D` as a value, which is
	 * what keeps that component free of the engine: it depends on
	 * `$lib/viewer/contract`'s interface (D1), so every requirement about
	 * provenance, counts, orphans, transport and degradation is exercisable with
	 * a scene that is an ordinary object.
	 *
	 * Which surface is shown is the address's answer (D3), already resolved
	 * against the surfaces the asset has — so by the time this component runs,
	 * a surface the asset no longer has has already degraded to the overview
	 * and the person has already been told why.
	 */
	import type { Surface } from '$lib/address';
	import type { AssetPage, ViewerReads } from '$lib/asset';
	import type { Anchor, AnnotationListing, DocumentListing } from '$lib/api';
	import type { AnnotationViewModel } from '$lib/annotation';
	import type { SceneFactory } from '$lib/viewer/contract';
	import AssetOverview from './AssetOverview.svelte';
	import DocumentLinks from './DocumentLinks.svelte';
	import ModelSheet from './ModelSheet.svelte';
	import Viewer3D from './Viewer3D.svelte';

	interface Props {
		surface: Surface;
		page: AssetPage;
		/** The threads the route read, present on both annotating surfaces. */
		annotations?: AnnotationListing | null;
		/**
		 * The documents linked to this asset, read by the route.
		 *
		 * `null` means the link list could not be read at all, which is
		 * different from *no links* and different again from *the platform is
		 * unavailable* — the listing says which of those two it is, and a
		 * missing listing says neither and so shows nothing.
		 */
		documents?: DocumentListing | null;
		/** The one ViewModel. Handed in so a test can drive a fresh instance. */
		model?: AnnotationViewModel | null;
		/** The thread the address opens on, when it names one. */
		annotation?: string | null;
		/** What the route read for the viewer: descriptor, orphan count and bytes. */
		viewer?: ViewerReads | null;
		/** Rescue an orphan. The route supplies it, so no view reaches the API. */
		onReanchor?: (annotation: string, anchor: Anchor) => Promise<boolean>;
		/** Read the preview again after a failure. Supplied by the route, like the write. */
		onRetryPreview?: () => void;
	}

	let {
		surface,
		page,
		annotations = null,
		documents = null,
		model = null,
		annotation = null,
		viewer = null,
		onReanchor = async () => false,
		onRetryPreview = () => {}
	}: Props = $props();

	let mount = $state<SceneFactory | null>(null);

	$effect(() => {
		if (surface !== 'viewer') return;
		let live = true;
		import('$lib/viewer/scene').then(({ mountScene }) => {
			if (live) mount = mountScene;
		});
		return () => {
			live = false;
		};
	});
</script>

{#if surface === 'overview'}
	<AssetOverview {page} />
	{#if documents}
		<DocumentLinks listing={documents} />
	{/if}
{:else if surface === 'sheet'}
	{#if annotations && model}
		<ModelSheet
			{model}
			listing={annotations}
			mayPromote={annotations.may_promote}
			actor={annotations.actor}
			selected={annotation}
		/>
	{:else}
		<p class="pending">This asset's threads could not be read at this revision.</p>
	{/if}
{:else if annotations && model && viewer?.descriptor}
	<Viewer3D
		{model}
		listing={annotations}
		descriptor={viewer.descriptor}
		resolutions={viewer.resolutions}
		bytes={viewer.bytes}
		unretrievable={viewer.unloadable}
		{mount}
		mayPromote={annotations.may_promote}
		actor={annotations.actor}
		selected={annotation}
		{onReanchor}
		onRetry={onRetryPreview}
	/>
{:else}
	<p class="pending">This asset's preview could not be read at this revision.</p>
{/if}

<style>
	/*
	 * The two sentences this component can put on a screen by itself.
	 *
	 * Both say the same kind of thing — *the route could not read this at
	 * this revision* — and neither is a failure the person can act on here,
	 * so both are prose on the page's ground. The states that ARE actionable
	 * are further in: `Viewer3D` carries the unloadable preview and its
	 * retry, and `RouteScreen` carries the six route states.
	 */
	.pending {
		margin: 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}
</style>
