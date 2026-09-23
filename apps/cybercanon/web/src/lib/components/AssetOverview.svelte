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
	 * The surface entry points are the same rule applied to the ways out: a
	 * surface this asset does not have is shown as unavailable with its reason,
	 * rather than as a link that degrades once somebody follows it.
	 */
	import type { AssetPage } from '$lib/asset';

	interface Props {
		page: AssetPage;
	}

	let { page }: Props = $props();
</script>

<div class="asset-page" data-asset={page.asset} data-project={page.project}>
	<nav class="surfaces" aria-label="Surfaces">
		<ul>
			{#each page.surfaces as entry (entry.surface)}
				<li class="surface" data-surface={entry.surface} data-available={entry.available}>
					{#if entry.available}
						<a class="to-surface" data-surface={entry.surface} href={entry.address}
							>{entry.label}</a
						>
					{:else}
						<span class="unavailable">{entry.label}</span>
						<span class="absence">{entry.absence}</span>
					{/if}
				</li>
			{/each}
		</ul>
	</nav>

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
	/*
	 * The asset page in the design's terms: the ways out set as a row of
	 * boxes, then the sections down the page with their headings in the
	 * system's heavy face.
	 *
	 * THE ONE RULE THIS STYLESHEET HAS TO KEEP is the one the component's own
	 * comment states: *absent content is stated, not hidden*. So a section
	 * with nothing in it and a surface this asset does not have are both
	 * DRAWN — quieter, on the neutral tint, never removed and never faded to
	 * the point of being skipped.
	 */
	.asset-page {
		display: grid;
		gap: var(--space-6);
	}

	.surfaces ul,
	.entries {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	/*
	 * The surface entry points. The design draws them as a segmented control
	 * in a single black box; here each one is its own box, because an
	 * unavailable surface carries a sentence saying why and a sentence does
	 * not fit in a segment. The black edge and the hard offset are the
	 * design's, and they are what make the row read as a control rather than
	 * as a list of links.
	 */
	.surfaces ul {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
	}

	.surface {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		max-width: 22rem;
		background: var(--color-surface);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-2) var(--space-3);
	}

	.to-surface {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-h5);
		color: var(--color-text);
	}

	.to-surface:hover {
		color: var(--color-accent-700);
		text-decoration-thickness: var(--border-thin);
	}

	/*
	 * A surface this asset does not have. It keeps its box and loses its
	 * lift: on the neutral tint, flat to the page, with the label in the same
	 * face as the ones that work so the row still reads as one set of
	 * choices. Fading it out would have made it the thing an eye skips, and
	 * the sentence underneath is the whole point of drawing it.
	 */
	.surface[data-available='false'] {
		background: var(--color-neutral-100);
		box-shadow: none;
	}

	.unavailable {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-h5);
		color: var(--color-neutral-700);
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
