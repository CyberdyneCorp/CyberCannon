<script lang="ts">
	/**
	 * The frame every screen renders inside.
	 *
	 * `app-navigation` requires every screen to identify the project whose
	 * content it is showing, so the project is part of the frame rather than
	 * something each screen remembers to print. The project comes from the
	 * address (D3), which is why the frame can read it without any screen
	 * passing it up.
	 *
	 * `web-session` requires the same of the acting identity — *"any
	 * authenticated screen"* — of the warning a person with no git identity is
	 * owed before they write, and of an identity provider outage. All three are
	 * in the frame for the same reason the project is: a disclosure that each
	 * screen has to remember is a disclosure some screen will forget.
	 *
	 * The re-authentication prompt is here too, and that placement is D5: it has
	 * to be able to appear without unmounting the screen holding somebody's
	 * unsaved text.
	 */
	import type { Snippet } from 'svelte';
	import { page } from '$app/state';
	import SessionBar from '$lib/components/SessionBar.svelte';
	import SessionNotices from '$lib/components/SessionNotices.svelte';
	import ReauthenticatePrompt from '$lib/components/ReauthenticatePrompt.svelte';
	import type { LayoutData } from './$types';

	let { children, data }: { children: Snippet; data: LayoutData } = $props();

	const project = $derived(page.params.project ?? null);
</script>

<header>
	<a class="home" href="/">CyberCanon</a>
	{#if project}
		<span class="project" data-project={project}>Project: {project}</span>
	{/if}
	<SessionBar />
</header>

<SessionNotices verification={data.verification} />
<ReauthenticatePrompt />

<main>
	{@render children()}
</main>

<style>
	header {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		align-items: baseline;
		padding: 0.75rem 1rem;
		border-block-end: 1px solid currentColor;
	}

	main {
		padding: 1rem;
	}
</style>
