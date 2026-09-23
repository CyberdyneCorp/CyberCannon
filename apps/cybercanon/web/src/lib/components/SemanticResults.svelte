<script lang="ts">
	/**
	 * The approximate half of a search: a second labelled group, never a
	 * continuation of the first.
	 *
	 * `semantic-search-delegation` asks for three things here and refuses a
	 * fourth. Each passage **names the document it came from** and is
	 * **openable at the document platform**; the group is **labelled as
	 * approximate** rather than presented as an answer; and when the retrieval
	 * service could not answer, the group **says why** instead of disappearing.
	 * What it refuses is any way of mixing these into the exact rows — so this
	 * is its own list, under its own heading, below them, with no comparator
	 * anywhere and no number a reader could weigh against an exact match.
	 *
	 * A passage carries **no asset identifier**, which is the rule made
	 * structural: a sentence in a document that mentions `mech_scout` is not
	 * that asset's record, and there is no link from here to one.
	 *
	 * PRESENTATION, and it is load-bearing. The two groups have to stay two
	 * groups, so the thing that separates them is the heaviest rule the system
	 * has — the front-page furniture the design reserves for a break in kind —
	 * rather than the hairline this used to draw. Above it is a table in full
	 * ink; below it is prose in the ground's own colour, with no box, no
	 * status, no rank and no number. Nothing about this group's shape invites
	 * comparison with the one above it, which is the point.
	 */
	import type { SemanticGroup } from '$lib/api';
	import { sourceOf } from '$lib/browser';

	interface Props {
		group: SemanticGroup;
	}

	let { group }: Props = $props();
</script>

{#if group.delegated}
	<section class="semantic" data-available={group.available}>
		<h2 class="label">{group.label}</h2>
		<p class="notice">{group.notice}</p>
		{#if group.available}
			<ul class="passages">
				{#each group.results as passage (passage.document)}
					<li class="passage" data-document={passage.document}>
						<a class="source" href={passage.url} rel="external noreferrer">
							{sourceOf(passage)}
						</a>
						<span class="provenance">{passage.provenance}</span>
						{#if passage.text}
							<p class="text">{passage.text}</p>
						{/if}
					</li>
				{/each}
			</ul>
			{#if group.results.length === 0}
				<p class="none">
					Nothing in the linked documents matched “{group.label}” closely enough to
					show.
				</p>
			{/if}
		{/if}
	</section>
{/if}

<style>
	.semantic {
		margin-block-start: var(--space-8);
		padding-block-start: var(--space-4);
		border-block-start: var(--border-heavy) solid var(--color-divider);
	}

	/*
	 * The group's own label, in the eyebrow treatment the design gives every
	 * kicker — small, letterspaced, quiet. It is deliberately *smaller* than
	 * the exact group's furniture above it: this is the approximate half, and
	 * type that shouted would be a ranking claim.
	 *
	 * The words are the surface's and are printed as given; only the casing is
	 * the design's — the kicker on this screen is set in the system's small
	 * caps, as every other eyebrow in the interface is.
	 */
	.label {
		margin: 0;
		font-size: var(--text-h6);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
	}

	.notice,
	.none {
		margin: var(--space-1) 0 var(--space-4);
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.passages {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: var(--space-4);
	}

	/* A passage is a sentence from a document, set as prose. No box, no rule
	   and no tag — the things a row has, which a passage must not be mistaken
	   for. */
	.passage {
		max-width: 60ch;
	}

	.source {
		font-family: var(--font-heading);
		font-weight: var(--font-heading-weight);
		font-size: var(--text-h5);
	}

	/* Where the passage came from, in the system's small caps. */
	.provenance {
		margin-inline-start: var(--space-2);
		font-size: var(--text-fine);
		text-transform: uppercase;
		letter-spacing: var(--tracking-caps);
		color: var(--color-neutral-700);
	}

	/* The italic is the design's mark for quoted matter: this is somebody
	   else's sentence, reproduced, not a field CyberCanon holds. */
	.text {
		margin: var(--space-1) 0 0;
		font-style: italic;
	}

	/*
	 * A retrieval service that could not answer. `semantic-search-delegation`
	 * requires the group to say why rather than vanish, so the group is still
	 * here and its notice takes the spot yellow behind the system's heavy edge
	 * — the same treatment the frame gives a degraded read, because it is the
	 * same fact: part of this answer is missing and the rest is still true.
	 */
	.semantic[data-available='false'] .notice {
		display: inline-block;
		margin-block-end: 0;
		background: var(--color-highlight);
		color: var(--color-text);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-2) var(--space-3);
		font-weight: var(--font-weight-medium);
	}
</style>
