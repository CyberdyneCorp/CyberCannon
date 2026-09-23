<script lang="ts">
	/**
	 * The pass itself: every open annotation, in the order the domain put them.
	 *
	 * Each row carries the four signals `annotation-triage` requires — *"how
	 * many other open annotations of the same kind exist on the same asset and
	 * across the project, its reply count, and its age"* — because the whole
	 * point of the pass is deciding what to promote without reading every
	 * thread first.
	 *
	 * Nothing here sorts. The order is the queue's, which is the domain's, so
	 * the art director's pass and `canon`'s answer cannot disagree about which
	 * feedback is recurring.
	 */
	import { ANNOTATION_KINDS } from '$lib/api';
	import type { TriageEntry, TriageQueue } from '$lib/api';
	import { assetAddress } from '$lib/address';
	import { triageLink } from '$lib/triage';
	import type { TriageAddress } from '$lib/triage';

	interface Props {
		queue: TriageQueue;
		address: TriageAddress;
	}

	let { queue, address }: Props = $props();

	function age(entry: TriageEntry): string {
		const days = Math.floor(entry.age_seconds / 86_400);
		if (days > 0) return `${days}d`;
		const hours = Math.floor(entry.age_seconds / 3_600);
		return hours > 0 ? `${hours}h` : 'new';
	}

	/**
	 * Where a row goes: the sheet, opened on this exact thread.
	 *
	 * *"The promotion flow from the triage view"* — the pass names the
	 * annotation in the address, so the panel opens already selected with its
	 * rule text, its destination choice and the destination stated before
	 * submission. The queue never promotes inline, because promoting without
	 * the thread and the image in front of you is how a rule gets written
	 * about something somebody half-remembers.
	 */
	function sheetOf(entry: TriageEntry): string {
		return assetAddress({
			project: queue.project,
			asset: entry.asset,
			surface: 'sheet',
			annotation: entry.annotation.id
		});
	}
</script>

<nav class="kinds" aria-label="filter the queue by kind">
	<a class="kind" class:current={address.kind === ''} href={triageLink({ ...address, kind: '' })}>
		every kind
	</a>
	{#each ANNOTATION_KINDS as kind (kind)}
		<a
			class="kind"
			class:current={address.kind === kind}
			data-kind={kind}
			href={triageLink({ ...address, kind })}>{kind}</a
		>
	{/each}
</nav>

<!-- Eight columns do not stack into a phone, and a table that wrapped its
     cells into a stack is a table nobody can compare down. So the one
     concession to a narrow screen is a scroll container. -->
<div class="listing">
	<table>
		<caption>{queue.entries.length} open annotation(s) awaiting triage</caption>
		<thead>
			<tr>
				<th scope="col">Asset</th>
				<th scope="col">Kind</th>
				<th scope="col">Feedback</th>
				<th scope="col">On asset</th>
				<th scope="col">In project</th>
				<th scope="col">Replies</th>
				<th scope="col">Age</th>
				<th scope="col">Owner</th>
			</tr>
		</thead>
		<tbody>
			{#each queue.entries as entry (`${entry.asset}/${entry.annotation.id}`)}
				<tr data-annotation={entry.annotation.id} data-asset={entry.asset}>
					<td><a href={sheetOf(entry)}>{entry.asset}</a></td>
					<td>{entry.kind}</td>
					<td>{entry.annotation.text}</td>
					<td class="count">{entry.same_kind_on_asset}</td>
					<td class="count">{entry.same_kind_in_project}</td>
					<td class="count">{entry.replies}</td>
					<td class="count">{age(entry)}</td>
					<td>{entry.discipline_owner ?? 'unassigned'}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	/*
	 * The pass, set as the design's table: the heaviest block on a screen
	 * that is not a dialog — a hard black edge, the spot yellow behind the
	 * head, full-strength ink between the rows — because the whole point of
	 * the pass is reading down a column and comparing.
	 *
	 * NOTHING HERE PROMOTES OR RESOLVES, and the styling says so as plainly
	 * as the markup does. Those are two different acts with two different
	 * weights — resolving closes one thread, promoting writes a durable rule
	 * into an asset's contract and only an art director is offered it — and
	 * the component's comment explains why neither is offered inline: *"the
	 * queue never promotes inline, because promoting without the thread and
	 * the image in front of you is how a rule gets written about something
	 * somebody half-remembers."* So the one control on a row is the way to
	 * the sheet, and it is set as a link rather than as a button, so the pass
	 * cannot be mistaken for a screen on which things are decided.
	 */
	.listing {
		overflow-x: auto;
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-table);
		background: var(--color-surface);
	}

	table {
		width: 100%;
		border-collapse: separate;
		border-spacing: 0;
	}

	/* The count of what is still open, stated above the table rather than
	   inside it: it is the size of the pass, not a column of it. */
	caption {
		text-align: start;
		caption-side: top;
		padding: var(--space-2) var(--space-3);
		background: var(--color-surface);
		border-block-end: var(--border-thick) solid var(--color-divider);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-small);
	}

	th {
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
		vertical-align: bottom;
	}

	td {
		padding: var(--space-2) var(--space-3);
		text-align: start;
		vertical-align: top;
		border-block-end: var(--border-thin) solid var(--color-divider);
	}

	/* The last rule would print on the table's own edge. */
	tbody tr:last-child td {
		border-block-end: 0;
	}

	/* The hover is the page's ground showing through the table's white — this
	   system has no tints, so a row is picked out by changing surface. */
	tbody tr:hover {
		background: var(--color-bg);
	}

	/*
	 * The four signals the pass is read on — how many of this kind sit on the
	 * asset, how many across the project, the replies and the age. They are
	 * figures compared down a column, so they take the mono's tabular
	 * figures and sit against the right edge of their cell.
	 */
	.count {
		text-align: end;
		font-family: var(--font-mono);
		font-size: var(--text-small);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	/* The asset is the row's identifier and its way out — the mono, because
	   a column of `mech_scout`, `gate_dock`, `pilot_kaede` read downwards
	   lines up character for character and an underscore stops looking like
	   a space. */
	td a {
		font-family: var(--font-mono);
		font-weight: var(--font-weight-strong);
	}

	/*
	 * The kind filter. A segmented control in one black box, which is the
	 * design's own: the whole strip is bordered once and the cells are
	 * divided by the same rule, so it reads as one choice with four answers
	 * rather than as four separate controls.
	 */
	.kinds {
		display: flex;
		flex-wrap: wrap;
		margin-block-end: var(--space-4);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		background: var(--color-surface);
		width: fit-content;
		max-width: 100%;
	}

	.kind {
		padding: var(--space-1) var(--space-3);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-small);
		color: var(--color-text);
		border-inline-start: var(--border-thin) solid var(--color-divider);
	}

	.kind:first-child {
		border-inline-start: 0;
	}

	.kind:hover {
		background: var(--color-neutral-100);
		color: var(--color-text);
		text-decoration: none;
	}

	/* The one the address currently names. The spot yellow, which is how the
	   design marks the segment a control is currently on. */
	.kind.current {
		background: var(--color-highlight);
	}
</style>
