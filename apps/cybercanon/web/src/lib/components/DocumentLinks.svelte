<script lang="ts">
	/**
	 * The long-form documents an asset is linked to — a list of references,
	 * never a reader.
	 *
	 * `document-platform` decides everything on this screen and leaves this
	 * component four things to do and no fifth:
	 *
	 * * show each link with the title the platform resolved, **or** with its
	 *   address when it could not be resolved, marked with the state that says
	 *   why — unreachable, gone and not-permitted are three different lines,
	 *   because a person deciding whether to chase a colleague or wait for a
	 *   service needs to know which one they are looking at;
	 * * **disclose nothing** about a document the viewer may not read: there is
	 *   no title and no summary on a forbidden entry because the surface sent
	 *   none, and this component has no branch that could put one back;
	 * * distinguish the asset's own links from the project's, which the entry
	 *   states and this only groups;
	 * * offer exactly the two actions the domain names — open it where it
	 *   lives, or remove the link. **There is no editor here**, and adding one
	 *   would mean adding an action the surface does not answer.
	 *
	 * The guidance sentence sits at the top because that is where the choice is
	 * made: a person adding a statement is deciding between the specification
	 * and the document, and the sentence naming both destinations belongs at
	 * the moment of the decision rather than in a help page.
	 */
	import type { DocumentListing, LinkedDocument } from '$lib/api';

	interface Props {
		listing: DocumentListing;
		/** Remove one link. The route supplies it, so no view reaches the API. */
		onUnlink?: (document: string, scope: string) => void;
	}

	let { listing, onUnlink = () => {} }: Props = $props();

	const STATES: Record<string, string> = {
		readable: '',
		unreachable: 'temporarily unresolvable',
		missing: 'no longer exists',
		forbidden: 'not accessible to you'
	};

	let assetLinks = $derived(listing.links.filter((link) => link.scope === 'asset'));
	let projectLinks = $derived(listing.links.filter((link) => link.scope === 'project'));

	function note(link: LinkedDocument): string {
		return STATES[link.state] ?? link.state;
	}
</script>

<section class="documents" data-available={listing.available}>
	<h2 class="heading">Linked documents</h2>
	<p class="guidance">{listing.guidance}</p>

	{#if !listing.available}
		<p class="unavailable" data-reason={listing.reason}>
			The document platform is unavailable ({listing.reason}), so these links show
			their addresses rather than their titles.
		</p>
	{/if}

	{#if listing.links.length === 0}
		<p class="none">No document is linked to this asset.</p>
	{:else}
		{#each [{ scope: 'asset', label: "This asset's documents", links: assetLinks }, { scope: 'project', label: 'Project documents', links: projectLinks }] as group (group.scope)}
			{#if group.links.length > 0}
				<h3 class="scope" data-scope={group.scope}>{group.label}</h3>
				<ul class="links">
					{#each group.links as link (link.document)}
						<li class="link" data-document={link.document} data-state={link.state}>
							<a class="title" href={link.url} rel="external noreferrer">
								{link.display_title}
							</a>
							<span class="scope-tag">{link.scope}</span>
							{#if !link.resolved}
								<span class="state">{note(link)}</span>
							{/if}
							{#if link.summary}
								<p class="summary">{link.summary}</p>
							{/if}
							<p class="attribution">linked by {link.linked_by} on {link.linked_at}</p>
							{#if link.actions.includes('unlink')}
								<button
									class="unlink"
									type="button"
									onclick={() => onUnlink(link.document, link.scope)}
								>
									Remove link
								</button>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		{/each}
	{/if}
</section>

<style>
	.documents {
		margin-top: 1.5rem;
	}

	.heading {
		margin: 0;
		font-size: 1rem;
	}

	.guidance,
	.unavailable,
	.none {
		margin: 0.25rem 0 0.75rem;
		font-size: 0.8125rem;
		opacity: 0.85;
	}

	.scope {
		margin: 0.75rem 0 0.25rem;
		font-size: 0.8125rem;
		text-transform: lowercase;
		opacity: 0.8;
	}

	.links {
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.link {
		margin-bottom: 0.75rem;
	}

	.scope-tag,
	.state {
		margin-left: 0.5rem;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		opacity: 0.7;
	}

	.summary,
	.attribution {
		margin: 0.25rem 0 0;
		font-size: 0.8125rem;
	}

	.attribution {
		opacity: 0.7;
	}
</style>
