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
	.projects {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.25rem;
	}
</style>
