<script lang="ts">
	/**
	 * Tasks 5.1 and 5.3 — which project this is, and how to leave it.
	 *
	 * `app-navigation` requires *"every screen"* to identify the project whose
	 * content it is showing, and requires that *"a person SHALL NOT be able to
	 * act on an asset without the project it belongs to being visible"*. Both
	 * are satisfied by this living in the frame rather than in each screen: a
	 * disclosure every screen has to remember is a disclosure some screen will
	 * forget.
	 *
	 * The switcher is a list of links, and that is the whole of task 5.1's
	 * *"discard the previous project's listing, filter and search state"*. The
	 * filters, the query, the page and the open asset are the address (D3), so
	 * an address that never carried them cannot carry them across — there is no
	 * state to clear, and therefore none to clear incorrectly.
	 */
	import { projectChoices, workAreaLinks } from '$lib/projects';

	interface Props {
		/** The project the current address names, or `null` outside a project. */
		project: string | null;
		pathname?: string;
		/** The projects this person may open, as the surface named them. */
		projects?: readonly string[];
	}

	let { project, pathname = '', projects = [] }: Props = $props();

	const choices = $derived(projectChoices(projects, project));
	const elsewhere = $derived(choices.filter((choice) => !choice.current));
	const areas = $derived(project ? workAreaLinks(project, pathname) : []);
</script>

{#if project}
	<span class="project" data-project={project}>Project: {project}</span>
	<nav class="work-areas" aria-label="Project work areas">
		{#each areas as area (area.area)}
			<a href={area.address} aria-current={area.current ? 'page' : undefined}>{area.label}</a>
		{/each}
	</nav>
{/if}

{#if elsewhere.length > 0}
	<nav class="switcher" aria-label="Switch project">
		<span class="lead">Switch to:</span>
		<ul>
			{#each elsewhere as choice (choice.project)}
				<li>
					<a class="to-project" data-project={choice.project} href={choice.address}
						>{choice.project}</a
					>
				</li>
			{/each}
		</ul>
	</nav>
{/if}

<style>
	/* The project sits beside the wordmark in the design's masthead, in the
	   italic that marks it as the thing being read rather than the product
	   reading it. */
	.project {
		font-size: var(--text-h5);
		font-style: italic;
	}

	.work-areas {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		align-items: center;
	}

	.work-areas a {
		color: var(--color-text);
		font-weight: var(--font-weight-strong);
		padding: 0 var(--space-1);
		border-block-end: var(--border-thin) solid transparent;
	}

	.work-areas a:hover,
	.work-areas a[aria-current='page'] {
		border-block-end-color: var(--color-divider);
	}

	.work-areas a[aria-current='page'] {
		background: var(--color-highlight);
	}

	.switcher {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		align-items: baseline;
		font-size: var(--text-small);
	}

	.switcher ul {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		list-style: none;
		margin: 0;
		padding: 0;
	}

	/* An eyebrow: the smallest, quietest type in the system. */
	.lead {
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		color: var(--color-neutral-700);
	}

	.to-project {
		font-weight: var(--font-weight-strong);
		border-block-end: var(--border-thin) solid var(--color-accent-700);
	}

	.to-project:hover {
		text-decoration: none;
		border-block-end-color: var(--color-accent-600);
	}
</style>
