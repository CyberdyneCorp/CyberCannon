<script lang="ts">
	/**
	 * The root address — where a person chooses a project (task 5.1).
	 *
	 * The projects are the ones the surface says this person may read, loaded by
	 * the frame and shared with the switcher so the two cannot disagree about
	 * what is open to them. A person with no session is offered sign-in and
	 * shown no project at all, which is `web-session` in one branch; an API that
	 * cannot be reached is a route state rather than a conditional (D6).
	 */
	import { page } from '$app/state';
	import { switchedTo } from '$lib/projects';
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import { sessionStore, type Session } from '$lib/session/session';
	import { currentAddress, signInAddress } from '$lib/session/intent';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let session = $state<Session>(sessionStore.current());

	$effect(() => sessionStore.subscribe((next) => (session = next)));

	const signIn = $derived(signInAddress(currentAddress(page.url)));
</script>

<h1>CyberCanon</h1>

<RouteScreen state={data.state}>
	{#snippet content()}
		{#if session.kind === 'active'}
			{#if data.projects.length > 0}
				<p>Open a project to browse its assets.</p>
				<ul class="projects">
					{#each data.projects as project (project)}
						<li>
							<a class="to-project" data-project={project} href={switchedTo(project)}>{project}</a>
						</li>
					{/each}
				</ul>
			{:else}
				<!-- Not an error: a person entitled to nothing, and a surface that could
				     not say, are both "no project to open" and both are stated. -->
				<p class="no-projects">
					No project is open to you here. A project becomes readable once you are
					entitled to read it; the deployment's operators add that entitlement.
				</p>
			{/if}
		{:else}
			<!-- `web-session`: an unauthenticated visitor is offered sign-in, and
			     is shown no project of any kind until they take it. -->
			<p>Sign in to read the canon of a project.</p>
			<p><a class="sign-in" href={signIn}>Sign in</a></p>
		{/if}
	{/snippet}
</RouteScreen>

<style>
	/*
	 * The picker. The design sets a project list as a column of names in the
	 * heading face with air between them — no cards, no rules, no boxes: this
	 * is the one screen in the application where hierarchy is carried by size
	 * and space alone, because there is only one kind of thing on it.
	 */
	.projects {
		list-style: none;
		margin: var(--space-6) 0 0;
		padding: 0;
		display: grid;
		gap: var(--space-4);
	}

	/*
	 * The accent rule under the name is what says these are doors, and it is
	 * there before the pointer is: a name set in the heading face at this size
	 * reads as a heading otherwise, and colour alone is not an affordance. It
	 * is drawn as a border rather than a text decoration so it keeps the
	 * system’s weight, which is how `ProjectBar` draws the same link.
	 */
	.to-project {
		font-family: var(--font-heading);
		font-weight: var(--font-heading-weight);
		font-size: var(--text-h3);
		letter-spacing: var(--tracking-heading);
		color: var(--color-text);
		border-block-end: var(--border-thin) solid var(--color-accent-700);
	}

	.to-project:hover {
		color: var(--color-accent-700);
		text-decoration: none;
		border-block-end-color: var(--color-accent-600);
	}

	/* Prose on this screen is read once and has to be read, so it takes a
	   measure rather than the width of the window. */
	.no-projects {
		max-width: 60ch;
	}

	/* The way in, for somebody who has not signed in yet. `web-session`
	   requires an offer rather than an error, so it is the loudest thing on an
	   otherwise empty screen — but it stays a link, because it goes to an
	   address, and the boxed treatment in this system belongs to controls that
	   act. */
	.sign-in {
		font-family: var(--font-heading);
		font-weight: var(--font-heading-weight);
		font-size: var(--text-h4);
		border-block-end: var(--border-thin) solid var(--color-accent-700);
	}

	.sign-in:hover {
		text-decoration: none;
		border-block-end-color: var(--color-accent-600);
	}
</style>
