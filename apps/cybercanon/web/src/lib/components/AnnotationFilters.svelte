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
	/*
	 * The filter bar. Two groups and a count, boxed in full-strength ink —
	 * the hairline border and the soft radius this carried before were the
	 * two things on the sheet that belonged to no token at all.
	 */
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
		align-items: center;
		margin-block-end: var(--space-3);
	}

	fieldset {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		align-items: center;
		background: var(--color-surface);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-field);
		padding: var(--space-1) var(--space-2);
	}

	/* The group's name, in the system's eyebrow — the same treatment the
	   design gives `View`, `Tool`, `Kind` and `State` down the sheet's rail. */
	legend {
		padding-inline: var(--space-1);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
	}

	label {
		display: inline-flex;
		gap: var(--space-1);
		align-items: center;
		font-size: var(--text-small);
	}

	/*
	 * WHAT THE FILTER IS HIDING, and it is a requirement rather than a
	 * caption: *"a filter that silently removed work is the reason somebody
	 * swears an annotation vanished"*. So when the count is anything but
	 * zero it is boxed and tinted with the second accent — the same mark
	 * every other *somebody has to notice this* carries in this interface —
	 * and when it is zero it is quiet prose, because *nothing hidden* is not
	 * news.
	 */
	.hidden-count {
		margin: 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.hidden-count:not([data-hidden='0']) {
		background: var(--color-accent-2-100);
		color: var(--color-accent-2-800);
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
		font-weight: var(--font-weight-strong);
		padding: 0 var(--space-1);
	}
</style>
