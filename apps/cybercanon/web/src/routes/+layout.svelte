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
	 * The project switcher is in the frame for the same reason, and task 5.1
	 * falls out of D3 once it is: switching is a link to an address that carries
	 * no filter, no query and no asset, so the previous project's state cannot
	 * come with it.
	 *
	 * The re-authentication prompt is here too, and that placement is D5: it has
	 * to be able to appear without unmounting the screen holding somebody's
	 * unsaved text.
	 */
	/**
	 * The token layer is imported here and nowhere else. `openspec/project.md`
	 * ("Visual language — neo-brutalism") puts the tokens in exactly one file;
	 * the root layout is the one place that file can be loaded from and still
	 * reach every screen, so it is loaded here and every other stylesheet in the
	 * application is a component's own scoped block.
	 *
	 * The faces are vendored rather than linked from a CDN — see
	 * `src/lib/styles/fonts.css` and `scripts/vendor_fonts.py`.
	 */
	import '$lib/styles/tokens.css';
	import '$lib/styles/fonts.css';
	import '$lib/styles/base.css';

	import type { Snippet } from 'svelte';
	import { page } from '$app/state';
	import { invalidate } from '$app/navigation';
	import { sessionStore, type Session } from '$lib/session/session';
	import ProjectBar from '$lib/components/ProjectBar.svelte';
	import SessionBar from '$lib/components/SessionBar.svelte';
	import SessionNotices from '$lib/components/SessionNotices.svelte';
	import ReauthenticatePrompt from '$lib/components/ReauthenticatePrompt.svelte';
	import type { LayoutData } from './$types';
	import { SESSION_DEPENDENCY } from '$lib/session/dependency';

	let { children, data }: { children: Snippet; data: LayoutData } = $props();

	const project = $derived(page.params.project ?? null);

	/**
	 * The frame's data is re-read when the acting identity changes.
	 *
	 * Which projects a person may open is an answer about *that person*, and the
	 * one thing this load does not take as a parameter is who they are. Watching
	 * the session here means signing in, signing out and re-authenticating in
	 * place all refresh it, and none of the three has to know that the switcher
	 * exists.
	 */
	let subject = $state(subjectOf(sessionStore.current()));

	$effect(() =>
		sessionStore.subscribe((session) => {
			const next = subjectOf(session);
			if (next === subject) return;
			subject = next;
			void invalidate(SESSION_DEPENDENCY);
		})
	);

	function subjectOf(session: Session): string | null {
		return session.kind === 'anonymous' ? null : session.identity.subject;
	}
</script>

<header>
	<a class="home" href="/">CyberCanon</a>
	<ProjectBar {project} projects={data.projects} />
	<SessionBar />
</header>

<SessionNotices verification={data.verification} />
<ReauthenticatePrompt />

<main>
	{@render children()}
</main>

<style>
	/*
	 * The masthead. The heavy rule under it is the design's front-page
	 * furniture — in this system a rule is structure at full-strength ink, not
	 * a hairline tint, and it is the one divider the page is allowed.
	 */
	header {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		align-items: baseline;
		padding: var(--space-4) var(--space-4) var(--space-2);
		border-block-end: var(--border-heavy) solid var(--color-divider);
	}

	.home {
		font-family: var(--font-heading);
		font-weight: var(--font-heading-weight);
		font-size: var(--text-h3);
		letter-spacing: var(--tracking-heading);
		color: var(--color-text);
		text-decoration: none;
	}

	.home:hover {
		color: var(--color-accent-700);
	}

	main {
		padding: var(--space-4);
	}
</style>
