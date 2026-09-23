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
		margin-top: 1.5rem;
		border-top: 1px solid currentColor;
		padding-top: 0.75rem;
	}

	.label {
		margin: 0;
		font-size: 0.9375rem;
		text-transform: lowercase;
	}

	.notice,
	.none {
		margin: 0.25rem 0 0.75rem;
		font-size: 0.8125rem;
		opacity: 0.8;
	}

	.passages {
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.passage {
		margin-bottom: 0.75rem;
	}

	.provenance {
		margin-left: 0.5rem;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		opacity: 0.7;
	}

	.text {
		margin: 0.25rem 0 0;
		font-size: 0.875rem;
	}
</style>
