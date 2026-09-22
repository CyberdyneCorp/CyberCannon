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
	import { SHEET_EMPTY } from '$lib/asset';
	import type { AnnotationViewModel } from '$lib/annotation';
	import { focusedView, pinsOn } from '$lib/annotation/sheet';
	import AnnotationFilters from './AnnotationFilters.svelte';
	import SheetView from './SheetView.svelte';
	import ThreadPanel from './ThreadPanel.svelte';

	interface Props {
		model: AnnotationViewModel;
		/** What the route read. The sheet never asks for it itself (D2). */
		listing: AnnotationListing;
		/** Where a view's mirrored image is served from, by view name. */
		sources?: Readonly<Record<string, string>>;
		mayPromote?: boolean;
		actor?: string;
		/** The thread the address opens on, when the pass linked straight to one. */
		selected?: string | null;
	}

	let {
		model,
		listing,
		sources = {},
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

	const focused = $derived(focusedView(model.selected, model.views));
</script>

<section class="sheet">
	<AnnotationFilters {model} />

	{#if model.views.length === 0}
		<p class="no-views" data-empty="views">{SHEET_EMPTY}</p>
	{:else}
		<div class="views">
			{#each model.views as view (view)}
				<SheetView
					{view}
					source={sources[view] ?? null}
					annotations={pinsOn(view, model.placeable)}
					{model}
					focused={focused === view}
				/>
			{/each}
		</div>
	{/if}

	<ThreadPanel {model} {mayPromote} {actor} />
</section>

<style>
	.sheet {
		display: grid;
		gap: 1rem;
		grid-template-columns: minmax(0, 2fr) minmax(16rem, 1fr);
		align-items: start;
	}

	.views {
		display: grid;
		gap: 1rem;
		grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
	}

	.no-views {
		margin: 0;
	}

	@media (max-width: 60rem) {
		.sheet {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
