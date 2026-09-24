<script lang="ts">
	/**
	 * The 2D model sheet: an asset's views, its pins, and the thread beside them.
	 *
	 * The sheet *"decides nothing about kinds, permissions, threading or triage,
	 * which are specified once and shared with the three-dimensional viewer"*.
	 * What it does is arrange: the views the asset has, each identified by the
	 * name an anchor keys on, the filter bar over them, and the panel that opens
	 * on whatever is selected.
	 *
	 * Two rules of `model-sheet-2d` are visible in the markup rather than in a
	 * comment:
	 *
	 * * **it invents no view.** The names come from the listing the server
	 *   produced; an asset with none says so and still presents its identity,
	 *   its status and its threads, because an annotation anchored to a view
	 *   that has gone is still a thread somebody has to triage.
	 * * **selecting from the panel brings the view into presentation.** The
	 *   focused view is derived from the selection, not tracked beside it, so
	 *   there is no state to get out of step.
	 */
	import type { AnnotationListing } from '$lib/api';
	import { SHEET_EMPTY, canonicalView, sheetViews, type SheetImage } from '$lib/asset';
	import type { AnnotationViewModel } from '$lib/annotation';
	import { focusedView, pinsOnAny } from '$lib/annotation/sheet';
	import AnnotationFilters from './AnnotationFilters.svelte';
	import SheetView from './SheetView.svelte';
	import ThreadPanel from './ThreadPanel.svelte';

	interface Props {
		model: AnnotationViewModel;
		/** What the route read. The sheet never asks for it itself (D2). */
		listing: AnnotationListing;
		/** Current image or a local failure, keyed by canonical slot. */
		images?: Readonly<Record<string, SheetImage>>;
		mayPromote?: boolean;
		actor?: string;
		/** The thread the address opens on, when the pass linked straight to one. */
		selected?: string | null;
	}

	let {
		model,
		listing,
		images = {},
		mayPromote = false,
		actor = '',
		selected = null
	}: Props = $props();

	/**
	 * Take the route's listing once per `(asset, revision)`, and never again.
	 *
	 * Once, because hydrating on every change would throw away the optimistic
	 * pin the moment a write settles and the revision moves — the pin would
	 * appear, vanish and reappear, which is exactly the flicker the optimistic
	 * insert exists to avoid. The guard is the key rather than a flag, so
	 * navigating to a second asset hydrates and staying on this one does not.
	 */
	let taken = $state('');

	function hydrate(): void {
		const key = `${listing.asset}@${listing.revision}`;
		if (taken === key) return;
		taken = key;
		model.hydrate(listing);
		if (selected) model.select(selected);
	}

	// Once at initialisation, so a server-rendered sheet carries its threads,
	// and again whenever the route hands over a different asset or revision.
	hydrate();
	$effect(hydrate);

	const views = $derived(sheetViews(model.views));
	const focused = $derived(canonicalView(focusedView(model.selected, model.views) ?? ''));
</script>

<section class="sheet">
	<!-- The filter bar spans the sheet: what a filter is hiding is a fact
	     about the whole surface, not about the views column alone. -->
	<div class="bar">
		<AnnotationFilters {model} />
	</div>

	{#if views.length === 0}
		<p class="no-views" data-empty="views">{SHEET_EMPTY}</p>
	{:else}
		<div class="views">
			{#each views as group (group.slot)}
				<SheetView
					view={group.slot}
					source={images[group.slot]?.source ?? null}
					reason={images[group.slot]?.reason ?? null}
					annotations={pinsOnAny(group.aliases, model.placeable)}
					{model}
					focused={focused === group.slot}
				/>
			{/each}
		</div>
	{/if}

	<ThreadPanel {model} {mayPromote} {actor} />
</section>

<style>
	/*
	 * The sheet's arrangement: the views under their filter bar, the panel
	 * beside them. The design's own sheet is three columns — rail, stage,
	 * panel — and this is that shape with the rail's contents (kind and
	 * state) sitting in the filter bar across the top instead, because
	 * `AnnotationFilters` is shared with the 3D viewer and the viewer has no
	 * rail to put it in.
	 *
	 * The filter bar spans both columns deliberately: what is being hidden is
	 * a fact about the whole surface, not about the left-hand half of it.
	 */
	.sheet {
		display: grid;
		gap: var(--space-6);
		grid-template-columns: minmax(0, 2fr) minmax(20rem, 1fr);
		align-items: start;
	}

	.bar {
		grid-column: 1 / -1;
	}

	.views {
		display: grid;
		gap: var(--space-6);
		grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
	}

	/*
	 * An asset with no views. `model-sheet-2d` keeps the sheet open for one —
	 * an annotation anchored to a view that has gone is still a thread
	 * somebody owes an exit — so the sentence is stated on the page's ground
	 * rather than drawn as an empty frame, which would have read as a view
	 * that failed to load.
	 */
	.no-views {
		margin: 0;
		font-size: var(--text-h5);
		color: var(--color-neutral-700);
	}

	/* One column on a narrow screen, panel under the views. A sheet is read
	   on an iPad as often as on a desk. */
	@media (max-width: 60rem) {
		.sheet {
			grid-template-columns: minmax(0, 1fr);
			gap: var(--space-4);
		}
	}
</style>
