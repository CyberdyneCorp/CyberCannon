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

<style>
	table {
		border-collapse: collapse;
		width: 100%;
	}

	caption {
		text-align: start;
		margin-block-end: 0.5rem;
	}

	th,
	td {
		border-bottom: 1px solid currentColor;
		padding: 0.25rem 0.5rem;
		text-align: start;
		vertical-align: top;
	}

	.count {
		text-align: end;
	}

	.kinds {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-block-end: 0.75rem;
	}

	.kind.current {
		font-weight: 700;
	}
</style>
