<script lang="ts">
	/**
	 * D5, on screen: the offer that stands between an expired session and a lost
	 * paragraph.
	 *
	 * It appears only when the gate is actually holding something, it names what
	 * is waiting, and it offers exactly two answers. Signing in again opens a
	 * second window — this page is never unloaded, which is what *"in place"*
	 * means and the reason the draft is still in the component that holds it.
	 * Declining releases the hold and sends nothing; the scenario is explicit
	 * that the input *"SHALL remain on screen and recoverable"*.
	 *
	 * Neither answer touches the payload. This component cannot: a held write is
	 * a value carrying its own payload and its own idempotency key, and the only
	 * thing that ever happens to it is being sent, under that key, unchanged.
	 */
	import { page } from '$app/state';
	import { invalidateAll } from '$app/navigation';
	import { writeGate } from '$lib/session';
	import type { HeldWrite } from '$lib/session/writes';
	import { browserOpener, reauthenticateInPlace } from '$lib/session/reauthentication';
	import { fetchTransport } from '$lib/session/oidc';
	import { browserStorage } from '$lib/session/storage';
	import { sessionStore } from '$lib/session/session';
	import { signInConfiguration } from '$lib/config';

	let held = $state<HeldWrite<unknown> | null>(writeGate.held());
	let busy = $state(false);
	let failure = $state<string | null>(null);
	let outcome = $state<string | null>(null);

	$effect(() => writeGate.subscribe((waiting) => (held = waiting)));

	async function reauthenticate(): Promise<void> {
		const configuration = signInConfiguration(page.url.origin);
		if (!configuration) {
			failure = 'Sign-in is not configured for this deployment.';
			return;
		}
		busy = true;
		failure = null;
		const signedIn = await reauthenticateInPlace(configuration, {
			opener: browserOpener(),
			messages: globalThis.window,
			storage: browserStorage(),
			transport: fetchTransport(globalThis.fetch),
			origin: page.url.origin
		});
		busy = false;
		if (signedIn.kind !== 'signed-in') {
			failure = signedIn.message;
			return;
		}
		sessionStore.signIn(signedIn.token);
		// The screens around this prompt resolved against a session that had
		// expired; with a credential again they are re-read in place, which is the
		// same "in place" the held write is replayed under.
		await invalidateAll();
		const replayed = await writeGate.replay();
		outcome = replayed?.kind === 'completed' ? 'Submitted.' : null;
	}

	function decline(): void {
		const kept = writeGate.decline();
		failure = kept?.message ?? null;
	}
</script>

{#if held}
	<section class="reauthenticate" data-held={held.key}>
		<h2>Your session expired before this was saved</h2>
		<p>{held.describe} is still here, exactly as you wrote it, and has not been submitted.</p>
		<button type="button" onclick={reauthenticate} disabled={busy}>
			{busy ? 'Waiting for sign-in…' : 'Sign in again and submit it'}
		</button>
		<button type="button" onclick={decline} disabled={busy}>Not now</button>
	</section>
{/if}

{#if failure}
	<p class="notice" data-notice="reauthentication">{failure}</p>
{/if}

{#if outcome}
	<p class="notice" data-notice="replayed">{outcome}</p>
{/if}

<style>
	.reauthenticate {
		border: 1px solid currentColor;
		border-radius: 0.5rem;
		padding: 1rem;
		margin: 0 1rem 1rem;
		display: grid;
		gap: 0.5rem;
		justify-items: start;
	}

	.notice {
		margin: 0.5rem 1rem 0;
	}
</style>
