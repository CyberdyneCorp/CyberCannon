<script lang="ts">
	/**
	 * One button, and nothing from the canon anywhere on the page.
	 *
	 * The button starts an authorization code exchange bound to a proof key this
	 * application generates (`auth-integration`); there is no password field
	 * here and there could not be one, because the flow has nowhere to put it.
	 *
	 * PRESENTATION. The design gives this screen the whole front page: the
	 * masthead, one large sentence, and a single yellow control. The control is
	 * the spot yellow `button.primary` from the base layer, at the size the
	 * design draws it, and it is the only affirmative action anywhere on the
	 * page — which is what the emphasis is for.
	 */
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import { beginSignIn } from '$lib/session/oidc';
	import { browserStorage } from '$lib/session/storage';
	import type { PageData } from './$types';
	import type { SignInScreen } from './+page';

	let { data }: { data: PageData } = $props();

	let starting = $state(false);

	async function start(screen: SignInScreen): Promise<void> {
		starting = true;
		const request = await beginSignIn(screen.configuration, {
			storage: browserStorage(),
			next: screen.next
		});
		globalThis.location.assign(request.url);
	}
</script>

<h1>Sign in to CyberCanon</h1>

<RouteScreen state={data.state}>
	{#snippet content(screen: SignInScreen)}
		<p class="lede">
			CyberCanon shows nothing from a project until it knows who is reading it.
			{#if screen.next !== '/'}You will be taken to <code>{screen.next}</code> afterwards.{/if}
		</p>
		<button class="primary start" type="button" onclick={() => start(screen)} disabled={starting}>
			{starting ? 'Taking you to CyberdyneAuth…' : 'Sign in with CyberdyneAuth'}
		</button>
	{/snippet}
</RouteScreen>

<style>
	/* One sentence, set as a lede, on a measure that can be read in a glance. */
	.lede {
		max-width: 60ch;
		font-size: var(--text-h4);
		line-height: var(--leading-heading);
	}

	/*
	 * The address this sign-in will return to, set in Space Mono. It is a URL
	 * — a string a person checks character by character before they hand over
	 * an identity — so it is chipped out of the prose the way the design chips
	 * the address bar: white behind the system’s edge, no radius.
	 */
	.lede code {
		font-family: var(--font-mono);
		font-size: var(--text-small);
		background: var(--color-surface);
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
		padding: 0 var(--space-1);
		white-space: nowrap;
	}

	/* The size the design draws the one control at. */
	.start {
		font-size: var(--text-h5);
		padding: var(--space-2) var(--space-4);
	}
</style>
