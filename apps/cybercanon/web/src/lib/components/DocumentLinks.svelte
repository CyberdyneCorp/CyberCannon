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
	/*
	 * A list of references, set the way the design sets one: the title in the
	 * link colour, the provenance under it in the quiet ink, and nothing
	 * boxed except the two things that are not prose — the scope tag and the
	 * state of a link that could not be resolved.
	 *
	 * The component's own comment fixes what may appear here, and the styling
	 * follows it: a forbidden entry has no title and no summary to set,
	 * because the surface sent none, and there is no rule below that could
	 * put one back.
	 */
	.documents {
		margin-block-start: var(--space-6);
		border-block-start: var(--border-heavy) solid var(--color-divider);
		padding-block-start: var(--space-3);
	}

	.heading {
		font-size: var(--text-h4);
		margin-block-end: var(--space-1);
	}

	.guidance,
	.none {
		margin: 0 0 var(--space-3);
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	/*
	 * The platform being unavailable is a disclosure rather than a failure —
	 * the links are still here, they are just showing addresses instead of
	 * titles — so it takes the spot yellow the design gives a notice, in a
	 * box, rather than the second accent it gives something broken.
	 */
	.unavailable {
		margin: 0 0 var(--space-3);
		background: var(--color-highlight);
		color: var(--color-text);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-2) var(--space-3);
		font-size: var(--text-small);
	}

	/* The asset's own documents and the project's are two groups, and the
	   label that says which is the system's eyebrow. */
	.scope {
		margin: var(--space-4) 0 var(--space-2);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		color: var(--color-neutral-700);
	}

	.links {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: var(--space-3);
	}

	.link {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: var(--space-1) var(--space-2);
	}

	.title {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-h5);
	}

	/* A tag, in this system's terms: boxed in full-strength ink, never a
	   tinted pill. Scope is a fact about the link and takes the neutral. */
	.scope-tag,
	.state {
		display: inline-block;
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		white-space: nowrap;
		padding: 0 var(--space-1);
		background: var(--color-neutral-200);
		color: var(--color-text);
	}

	/*
	 * A link that could not be resolved. Unreachable, gone and not-permitted
	 * are three different sentences and the component prints whichever one it
	 * is; what this does is make sure the tag is never mistaken for the scope
	 * beside it — the second accent's tint behind the same black edge, so the
	 * two differ in colour and in wording and stay different in greyscale.
	 */
	.state {
		background: var(--color-accent-2-100);
		color: var(--color-accent-2-800);
	}

	.summary,
	.attribution {
		flex-basis: 100%;
		margin: 0;
		font-size: var(--text-small);
	}

	/* `app-navigation`: attribution is on every screen that shows a
	   contribution. Quiet, and never absent. */
	.attribution {
		color: var(--color-neutral-700);
	}

	.unlink {
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		padding: 0 var(--space-1);
		box-shadow: var(--shadow-sm);
	}
</style>
