<script lang="ts" generics="T">
	/**
	 * D6 — the screen every data-bearing route renders through.
	 *
	 * A route hands it one member of the closed set and a snippet for the one
	 * case that has data. Every other case is written once, here, which is what
	 * stops the empty and the forbidden screens from being the ones nobody
	 * builds. `degraded` renders the content *and* the disclosure, because
	 * `asset-browser` forbids presenting a partial result as complete.
	 *
	 * The description comes from `matchRouteState`, so a seventh state would
	 * stop this component compiling rather than render as a blank panel.
	 */
	import type { Snippet } from 'svelte';
	import { page } from '$app/state';
	import type { RouteState } from '$lib/route-state';
	import { matchRouteState } from '$lib/route-state';
	import { currentAddress, signInAddress } from '$lib/session/intent';

	interface Described {
		readonly heading: string;
		readonly detail: string;
		readonly action: string | null;
	}

	interface Props {
		state: RouteState<T>;
		content: Snippet<[T]>;
		/**
		 * What the screen offers to do about this state, when offering it takes
		 * more than a sentence — the empty browser's *"clear the filters"* is a
		 * link to an address (D3), not a word. Absent, the state's own plain
		 * description stands.
		 */
		actions?: Snippet;
	}

	let { state, content, actions }: Props = $props();

	function describe(current: RouteState<T>): Described | null {
		return matchRouteState<T, Described | null>(current, {
			content: () => null,
			empty: (it) => ({
				heading: headingFor(it.reason),
				detail: it.message,
				action: it.reason === 'filters-excluded' ? 'Clear the filters' : null
			}),
			// `web-session`: an unauthenticated person is *offered sign-in*, and
			// SHALL NOT be shown an error. So the sign-in remedy is a different
			// screen from a refusal, with a different heading and a way forward.
			forbidden: (it) => ({
				heading: it.remedy === 'sign-in' ? 'Sign in to continue' : 'You do not have access',
				detail: it.message,
				action: it.remedy === 'sign-in' ? 'Sign in' : null
			}),
			'not-found': (it) => ({ heading: 'Not found', detail: it.message, action: null }),
			degraded: (it) => ({
				heading: 'Some of this is unavailable',
				detail: it.message,
				action: null
			}),
			failed: (it) => ({
				heading: 'That did not work',
				detail: it.correlationId ? `${it.message} (${it.correlationId})` : it.message,
				action: null
			})
		});
	}

	function headingFor(reason: 'no-assets' | 'no-results' | 'filters-excluded'): string {
		if (reason === 'no-assets') return 'Nothing here yet';
		if (reason === 'no-results') return 'Nothing matched';
		return 'The filters excluded every match';
	}

	const described = $derived(describe(state));
	const signIn = $derived(signInAddress(currentAddress(page.url)));
	const data = $derived(
		state.kind === 'content' || state.kind === 'degraded' ? state.data : null
	);
</script>

{#if described}
	<section class="route-state" data-state={state.kind}>
		<h2>{described.heading}</h2>
		{#if state.kind !== 'degraded' || !state.unavailable.includes(described.detail)}
			<p>{described.detail}</p>
		{/if}
		{#if state.kind === 'degraded'}
			<ul class="unavailable">
				{#each state.unavailable as entry (entry)}
					<li>{entry}</li>
				{/each}
			</ul>
		{/if}
		{#if state.kind === 'forbidden' && state.remedy === 'sign-in'}
			<p class="action"><a class="sign-in" href={signIn}>{described.action}</a></p>
		{:else if actions}
			<div class="action">{@render actions()}</div>
		{:else if described.action}
			<p class="action">{described.action}</p>
		{/if}
	</section>
{/if}

{#if data !== null}
	{@render content(data as T)}
{/if}

<style>
	/*
	 * One panel, six states, and the colour is how they are told apart at a
	 * glance. `degraded` is the one that matters most here: `asset-browser`
	 * forbids presenting a partial result as complete, so the panel that says
	 * so is the loudest thing on a screen that also has content on it.
	 */
	.route-state {
		background: var(--color-surface);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-4);
		margin-block-end: var(--space-4);
		color: var(--color-text);
	}

	.route-state h2 {
		font-size: var(--text-h4);
	}

	.route-state p {
		margin-block-end: 0;
	}

	.route-state[data-state='degraded'] {
		background: var(--color-highlight);
		padding: var(--space-2) var(--space-3);
	}

	.route-state[data-state='degraded'] h2 {
		font-size: var(--text-h5);
		margin-block-end: var(--space-1);
	}

	.route-state[data-state='degraded'] .unavailable {
		margin-block-start: 0;
	}

	.route-state[data-state='failed'] {
		background: var(--color-accent-2-100);
	}

	.route-state[data-state='forbidden'] {
		background: var(--color-accent-100);
	}

	.unavailable {
		margin: var(--space-2) 0 0;
		padding-inline-start: var(--space-4);
	}

	.action {
		margin-block-start: var(--space-3);
		font-weight: var(--font-weight-strong);
	}
</style>
