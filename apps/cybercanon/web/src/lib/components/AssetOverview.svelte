<script lang="ts">
	/**
	 * Tasks 6.1, 6.2 and 6.3 — the asset page, rendered.
	 *
	 * The sections come from `$lib/asset` as a closed, total list, and this
	 * component renders every one of them in order. It has no `{#if}` that can
	 * drop a section: a section with nothing in it renders its heading and the
	 * sentence saying why, which is the whole of *"absent content is stated, not
	 * hidden"*. A screen that decided for itself which sections were worth
	 * showing would be the place that requirement quietly stopped holding.
	 *
	 * AssetNavigation renders the surface entry points on every asset surface;
	 * this component only renders the overview's sections.
	 */
	import type { AssetPage } from '$lib/asset';

	interface Props {
		page: AssetPage;
	}

	let { page }: Props = $props();
</script>

<div class="asset-page" data-asset={page.asset} data-project={page.project}>
	{#each page.sections as section (section.id)}
		<section class="section" data-section={section.id} data-empty={section.absence !== null}>
			<h2>{section.heading}</h2>
			{#if section.absence}
				<p class="absence">{section.absence}</p>
			{:else}
				<ul class="entries">
					{#each section.entries as entry, index (`${entry.label ?? ''}:${entry.value}:${index}`)}
						<li class="entry" data-recorded={entry.recorded}>
							{#if entry.label}<span class="label">{entry.label}</span>{/if}
							<span class="value">{entry.value}</span>
							{#if entry.note}<span class="note">{entry.note}</span>{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/each}
</div>

<style>
	/* Every section stays visible even when it has no recorded content. */
	.asset-page {
		display: grid;
		gap: var(--space-6);
	}

	/* The sections, in the order `$lib/asset` fixed. The rule over each one is
	   the design's thick-thin pair, which is how this system opens a block. */
	.section {
		border-block-start: var(--border-heavy) solid var(--color-divider);
		padding-block-start: var(--space-3);
	}

	h2 {
		font-size: var(--text-h4);
		margin-block-end: var(--space-2);
	}

	.entries {
		display: grid;
		gap: var(--space-1);
	}

	/*
	 * One recorded fact per row: its label set as the system's eyebrow, its
	 * value in the body face beside it. The label column is fixed so a column
	 * of them reads down; an entry with no label — a concept view's name —
	 * simply starts where the labels do.
	 */
	.entry {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1) var(--space-3);
		align-items: baseline;
	}

	.label {
		flex: 0 0 auto;
		min-width: 11rem;
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		color: var(--color-neutral-700);
	}

	/*
	 * THE VALIDATION OUTCOME IS THREE STATES AND IT STAYS THREE.
	 *
	 * `Validation outcome`, `Violations` and `Rules not evaluated` arrive here
	 * as three ordinary recorded entries, and they are SET ALIKE on purpose.
	 * Not-evaluated means *the format does not record what this rule reads* —
	 * it is neither a pass nor a failure, and tinting it amber would make it a
	 * warning while tinting it with the second accent would make it a
	 * violation. Either one collapses three answers into two, and the count
	 * nobody can see any more is the honest one. So no outcome on this screen
	 * is coloured; the words do the work, and the figures are set in the mono
	 * so the three counts line up and can be read against each other.
	 */
	.value {
		font-family: var(--font-mono);
		font-size: var(--text-small);
		color: var(--color-text);
	}

	/*
	 * A fact the canon does not record — *"not recorded"*, or a validation
	 * outcome that could not be read at all. That is a different statement
	 * from a recorded value and it takes the second accent's deep step, which
	 * is this system's colour for *somebody has to do something about this*.
	 */
	.entry[data-recorded='false'] .value {
		font-family: var(--font-body);
		color: var(--color-accent-2-700);
		font-weight: var(--font-weight-medium);
	}

	/*
	 * The absence sentence, and the note beside an owner with no git identity.
	 * Both are prose about something missing, so both are set as prose rather
	 * than as a tag — a tag would read as a status the canon recorded.
	 */
	.absence,
	.note {
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.section > .absence {
		margin: 0;
	}

	.note {
		flex-basis: 100%;
		color: var(--color-accent-2-700);
	}
</style>
