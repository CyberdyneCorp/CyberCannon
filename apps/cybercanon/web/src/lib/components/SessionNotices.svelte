<script lang="ts">
	/**
	 * The two things a session owes a person before they find out the hard way.
	 *
	 * * **No mapped git identity.** `web-session` requires the application to
	 *   state this *"before they attempt one — rather than only reporting a
	 *   refusal after they have written something"*, and to say which actions
	 *   are unavailable. The refusal itself is real and lives in the domain
	 *   (`add-web-backend` D8); this is the part that arrives in time to matter.
	 * * **An identity provider outage.** Reads carry on — nothing in a read path
	 *   asks the issuer anything — so the requirement is a sentence rather than
	 *   a state: *"browsing SHALL continue to work AND the unavailability SHALL
	 *   be stated"*.
	 *
	 * Both are rendered from the frame, so "every screen" needs no screen's
	 * cooperation.
	 */
	import { sessionStore, type Session } from '$lib/session/session';
	import { unmappedNotice } from '$lib/session/identity';

	interface Props {
		/** The identity provider outage notice, when the API reports one. */
		verification?: string | null;
	}

	let { verification = null }: Props = $props();

	let session = $state<Session>(sessionStore.current());

	$effect(() => sessionStore.subscribe((next) => (session = next)));

	const unmapped = $derived(session.kind === 'active' ? unmappedNotice(session.identity) : null);
</script>

{#if unmapped}
	<p class="notice" data-notice="unmapped">{unmapped}</p>
{/if}

{#if verification}
	<p class="notice" data-notice="verification">{verification}</p>
{/if}

<style>
	/*
	 * Both notices are flat spot colour behind the system's heavy edge, which
	 * is how this design says "read me" — it has no tints and no soft
	 * callouts to say it with. Black on both fills, which is what keeps them
	 * legible at this saturation.
	 */
	.notice {
		margin: var(--space-2) var(--space-4) 0;
		padding: var(--space-2) var(--space-3);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		font-weight: var(--font-weight-medium);
		color: var(--color-text);
	}

	/* A person who cannot be attributed is the more serious of the two, and
	   takes the second accent. */
	.notice[data-notice='unmapped'] {
		background: var(--color-accent-2);
	}

	/* An issuer that cannot be reached does not stop anyone reading, so it is
	   the spot yellow rather than the alarm. */
	.notice[data-notice='verification'] {
		background: var(--color-highlight);
	}
</style>
