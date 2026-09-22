<script lang="ts">
	/**
	 * The filter bar: kind, state, and what the current filter is hiding.
	 *
	 * `model-sheet-2d` asks for three things and this offers exactly those — the
	 * three kinds, the open/resolved states, and **the number of annotations the
	 * filter is keeping off the views**. The count is the one that matters: a
	 * filter that silently removed work is the reason somebody swears an
	 * annotation vanished, and a number beside the controls is the cheapest
	 * possible answer to that.
	 *
	 * Nothing here decides what a filter means. Which annotations pass is
	 * `$lib/annotation/filter`'s, shared with the 3D viewer, so the sheet and any
	 * other surface presenting the same filter present the same set.
	 */
	import { ANNOTATION_KINDS } from '$lib/api';
	import type { AnnotationKind, AnnotationState } from '$lib/api';
	import type { AnnotationViewModel } from '$lib/annotation';

	interface Props {
		model: AnnotationViewModel;
	}

	let { model }: Props = $props();

	const STATES: readonly AnnotationState[] = ['open', 'resolved'];

	function wantsKind(kind: AnnotationKind): boolean {
		return model.filter.kinds.length === 0 || model.filter.kinds.includes(kind);
	}

	function wantsState(state: AnnotationState): boolean {
		return model.filter.states.length === 0 || model.filter.states.includes(state);
	}
</script>

<div class="filters" role="group" aria-label="filter the annotations">
	<fieldset>
		<legend>Kind</legend>
		{#each ANNOTATION_KINDS as kind (kind)}
			<label>
				<input
					type="checkbox"
					checked={wantsKind(kind)}
					onchange={() => model.toggleKind(kind)}
				/>
				{kind}
			</label>
		{/each}
	</fieldset>

	<fieldset>
		<legend>State</legend>
		{#each STATES as state (state)}
			<label>
				<input
					type="checkbox"
					checked={wantsState(state)}
					onchange={() => model.toggleState(state)}
				/>
				{state}
			</label>
		{/each}
	</fieldset>

	<p class="hidden-count" data-hidden={model.hidden}>
		{#if model.hidden > 0}
			{model.hidden} hidden by this filter
		{:else}
			nothing hidden by this filter
		{/if}
	</p>
</div>

<style>
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		align-items: center;
		margin-block-end: 0.75rem;
	}

	fieldset {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		border: 1px solid currentColor;
		border-radius: 0.25rem;
		padding: 0.25rem 0.5rem;
	}

	legend {
		padding-inline: 0.25rem;
	}

	label {
		display: inline-flex;
		gap: 0.25rem;
		align-items: center;
	}

	.hidden-count {
		margin: 0;
		opacity: 0.8;
	}
</style>
