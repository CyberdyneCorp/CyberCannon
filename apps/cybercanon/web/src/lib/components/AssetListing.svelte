<script lang="ts">
	/**
	 * Tasks 4.1 and 4.5 — the rows, with their state and with how they matched.
	 *
	 * `asset-browser` asks a row for four things without opening the asset —
	 * name, identifier, status and owners — and asks a *result* for a fifth: why
	 * it is here, when that was an alias, a tag, a description or a suggestion
	 * nobody has accepted. Both are one component, because a listing row and a
	 * search row are the same line with one extra sentence; two components would
	 * be two places for the status to be spelled differently.
	 *
	 * The order is the order it is given (D9 by way of `asset-lookup`): this
	 * renders `rows`, in sequence, and has nowhere to put a comparator.
	 *
	 * PRESENTATION. Five things asked of a row is a table, and the design draws
	 * it as one — `design/cybercanon-neo-brutal.html`'s asset screen is a
	 * `.table` with a column per question and *"How it matched"* as the last of
	 * them. The column headings name the questions the specification asks; they
	 * add no claim the row was not already making, and the disclosure column is
	 * the one that gains most by being named, because an empty cell under *"How
	 * it matched"* reads as *"on its name"* rather than as nothing at all.
	 *
	 * An empty `rows` renders nothing rather than a head with no body: the
	 * screens for having nothing to show are `RouteScreen`'s (D6), and a table
	 * of column headings over a void is a sixth one nobody specified.
	 */
	import { assetAddress, DEFAULT_SURFACE } from '$lib/address';
	import type { BrowserRow } from '$lib/browser';

	interface Props {
		project: string;
		rows: readonly BrowserRow[];
	}

	let { project, rows }: Props = $props();
</script>

{#if rows.length > 0}
	<div class="listing">
		<table class="assets">
			<thead>
				<tr>
					<th class="col-name" scope="col">Asset</th>
					<th scope="col">Status</th>
					<th scope="col">Owners</th>
					<th class="col-how" scope="col">How it matched</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as row (row.asset)}
					<tr class="asset" data-asset={row.asset}>
						<td>
							<a
								class="name"
								href={assetAddress({ project, asset: row.asset, surface: DEFAULT_SURFACE })}
								>{row.name}</a
							>
							<code class="identifier">{row.asset}</code>
						</td>
						<td>
							{#if row.status}
								<span class="status" data-status={row.status}>{row.status}</span>
							{/if}
						</td>
						<td>
							{#if row.owners}
								<ul class="owners">
									{#each row.owners as owner (owner.discipline)}
										<li
											class="owner"
											data-discipline={owner.discipline}
											data-unmapped={owner.unmapped}
										>
											<span class="discipline">{owner.discipline}</span>: {owner.display}
										</li>
									{/each}
								</ul>
							{/if}
						</td>
						<td class="how">
							{#if row.disclosure}
								<p
									class="disclosure"
									data-matched={row.disclosure.matched}
									data-unaccepted={row.disclosure.unaccepted}
								>
									{row.disclosure.text}
								</p>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	/*
	 * The table is the heaviest object on the screen that is not a dialog: a
	 * hard black edge, the spot yellow behind the head, and full-strength ink
	 * between the rows. That weight is the design's, and it is what lets a
	 * listing be read as a block rather than as a column of cards.
	 *
	 * The scroll container is the only concession to a narrow screen. Four
	 * columns do not stack into a phone, and a table that wraps its cells into
	 * a stack is a table nobody can compare down.
	 */
	.listing {
		overflow-x: auto;
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-table);
		background: var(--color-surface);
	}

	.assets {
		width: 100%;
		border-collapse: separate;
		border-spacing: 0;
	}

	/* The head is the spot yellow, black on it, and the eyebrow treatment the
	   design gives every small label. */
	.assets th {
		background: var(--color-highlight);
		color: var(--color-text);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		text-align: start;
		white-space: nowrap;
		padding: var(--space-2) var(--space-3);
		border-block-end: var(--border-thick) solid var(--color-divider);
	}

	.col-name {
		width: 30%;
	}

	.col-how {
		width: 26%;
	}

	.assets td {
		padding: var(--space-2) var(--space-3);
		vertical-align: top;
		border-block-end: var(--border-thin) solid var(--color-divider);
	}

	/* The last rule would print on the table's own edge. */
	.assets tbody tr:last-child td {
		border-block-end: 0;
	}

	/* The hover is the page's ground showing through the table's white — the
	   system has no tints, so a row is picked out by changing surface. */
	.assets tbody tr:hover {
		background: var(--color-bg);
	}

	.name {
		display: block;
		font-family: var(--font-heading);
		font-weight: var(--font-heading-weight);
		font-size: var(--text-h5);
		letter-spacing: var(--tracking-heading);
		color: var(--color-text);
	}

	.name:hover {
		color: var(--color-accent-700);
		text-decoration-thickness: var(--border-thin);
	}

	/*
	 * The identifier is Space Mono, and that is the whole reason the face is
	 * loaded. This is a column of `mech_scout`, `gate_dock`, `pilot_kaede` read
	 * down rather than across; set proportionally they are a ragged block a
	 * reader has to spell out, and set in the mono they line up character for
	 * character and an underscore stops looking like a space.
	 */
	.identifier {
		font-family: var(--font-mono);
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	/* A tag: the system's small label, boxed in full-strength ink, never a
	   tinted pill. The status is the neutral one — it is a state, not an
	   alarm, and the ramps are reserved for the things that are. */
	.status {
		display: inline-block;
		background: var(--color-neutral-200);
		color: var(--color-text);
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
		font-size: var(--text-fine);
		font-weight: var(--font-weight-strong);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		white-space: nowrap;
		padding: 0 var(--space-1);
	}

	.owners {
		list-style: none;
		margin: 0;
		padding: 0;
		font-size: var(--text-small);
	}

	.discipline {
		font-weight: var(--font-weight-strong);
	}

	/* A discipline whose owner has no identity in this project is the one
	   thing in a row that somebody has to act on, so it takes the second
	   accent's deep step rather than the body ink. */
	.owner[data-unmapped='true'] {
		color: var(--color-accent-2-700);
		font-weight: var(--font-weight-medium);
	}

	.how {
		font-size: var(--text-small);
	}

	.disclosure {
		margin: 0;
		color: var(--color-neutral-700);
	}

	/*
	 * `asset-browser` marks a result that came only from a suggestion nobody
	 * accepted, and the mark has to survive a restyle: an accepted alias is
	 * quiet grey prose, and an unaccepted suggestion is the second accent
	 * behind a black edge — a different colour, a different weight and a box,
	 * so the two cannot be mistaken for each other at a glance or in
	 * greyscale.
	 */
	.disclosure[data-unaccepted='true'] {
		display: inline-block;
		background: var(--color-accent-2-100);
		color: var(--color-accent-2-800);
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
		font-weight: var(--font-weight-strong);
		padding: 0 var(--space-1);
	}
</style>
