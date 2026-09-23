<script lang="ts">
	/**
	 * The query, typed by a person and written into the address (D3).
	 *
	 * A plain GET form, so submitting it produces the same address a link would
	 * — the one `asset-browser` requires to be shareable, filters included. The
	 * active filters travel as hidden fields for that reason: a search must not
	 * silently drop the narrowing the person can still see on screen.
	 *
	 * The markup is deliberately bare. The Cyberdyne primitives (`Field`,
	 * `Input`, `Button`) are what this will be built from the moment task 1.2
	 * installs the packages; D4's rule is enforced on the way in —
	 * `tests/tooling/test_web_structure.py` fails the build if a component here
	 * ever *becomes* one of them.
	 *
	 * PRESENTATION. The design's asset screen sets the query as its widest
	 * field under an uppercase eyebrow, with the action beside it. The label is
	 * that eyebrow rather than an inline caption, so the field can be as wide
	 * as the design draws it without the label pushing it off the line; it is
	 * still the same `<label for>` it was, and it still says the same thing.
	 */
	import { activeFilters, projectAddress, type BrowserAddress } from '$lib/address';

	interface Props {
		address: BrowserAddress;
	}

	let { address }: Props = $props();

	const active = $derived(activeFilters(address));
</script>

<form class="search" method="GET" action={`${projectAddress(address.project)}/assets`}>
	<div class="field">
		<label for="q">Search this project</label>
		<input id="q" name="q" type="search" value={address.query} placeholder="mech scout" />
	</div>
	{#each active as filter (filter.name)}
		<input type="hidden" name={filter.name} value={filter.value} />
	{/each}
	<button class="primary" type="submit">Search</button>
</form>

<style>
	/* The field and its action sit on one line, and wrap together rather than
	   the action dropping away from the box it submits. */
	.search {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
		align-items: end;
		margin-block-end: var(--space-4);
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		flex: 1 1 auto;
		min-width: 0;
		max-width: 34rem;
	}

	/* The eyebrow: the smallest, quietest type the system has, which is what
	   the design puts over every field on this screen. */
	.field label {
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		color: var(--color-neutral-700);
	}

	/* The edge, the shadow and the ground are the base layer's; what is left
	   here is this field's size — it is the widest thing on the screen because
	   it is the thing the screen is for. */
	.field input {
		width: 100%;
		font-size: var(--text-h5);
		padding: var(--space-2) var(--space-3);
	}

	/* `--color-neutral-600`, not `-500`. The 500 step is the ramp's middle and
	   reads as the obvious "quiet placeholder", but it measures 4.39:1 on the
	   field's white ground — under AA for 16px body text, and this is read on
	   an iPad in a studio (openspec/project.md: the contrast obligation is
	   higher here, not lower). One step down the ramp is 7.08:1. `opacity: 1`
	   because a browser's own placeholder fade would put the measured colour
	   back below the line. */
	.field input::placeholder {
		color: var(--color-neutral-600);
		opacity: 1;
	}

	/* The one affirmative action on the screen, so it takes the spot yellow —
	   `button.primary` in the base layer — at the field's own height. */
	.search button {
		font-size: var(--text-h5);
		padding: var(--space-2) var(--space-4);
	}
</style>
