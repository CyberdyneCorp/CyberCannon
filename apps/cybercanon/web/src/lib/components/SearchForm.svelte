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
	 */
	import { activeFilters, projectAddress, type BrowserAddress } from '$lib/address';

	interface Props {
		address: BrowserAddress;
	}

	let { address }: Props = $props();

	const active = $derived(activeFilters(address));
</script>

<form class="search" method="GET" action={`${projectAddress(address.project)}/assets`}>
	<label for="q">Search this project</label>
	<input id="q" name="q" type="search" value={address.query} placeholder="mech scout" />
	{#each active as filter (filter.name)}
		<input type="hidden" name={filter.name} value={filter.value} />
	{/each}
	<button type="submit">Search</button>
</form>

<style>
	.search {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
		margin-block-end: 1rem;
	}
</style>
