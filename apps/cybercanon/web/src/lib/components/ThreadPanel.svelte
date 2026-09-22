<script lang="ts">
	/**
	 * The thread panel: the conversation, and only the exits this person may take.
	 *
	 * `model-sheet-2d` fixes what it shows — *"its text, its kind, its
	 * attribution, its state and its replies in order"* — and fixes the rule that
	 * matters more than any of them: **hiding an action is not enforcement**.
	 * Promotion is offered only to somebody who may promote, and a submitted
	 * promotion from anybody else is refused by the system, which is why the
	 * button's absence is a courtesy and the refusal is the guarantee.
	 *
	 * The attribution is rendered exactly as the system produced it — *"rafa, via
	 * blender-agent"* — rather than reassembled here, because four surfaces
	 * phrasing it four ways is how a reader learns they disagree about who said
	 * something.
	 *
	 * Orphans are listed with the reason they cannot be shown, and never drawn.
	 */
	import type { Annotation, PromotionTarget } from '$lib/api';
	import { PROMOTION_TARGETS } from '$lib/api';
	import type { AnnotationViewModel } from '$lib/annotation';

	interface Props {
		model: AnnotationViewModel;
		/** Whether this person holds the art director role for the project. */
		mayPromote?: boolean;
		/** The person acting, so their own contributions offer edit and withdraw. */
		actor?: string;
		/** A client-generated identifier, which is also the idempotency key (D5). */
		newId?: () => string;
	}

	let {
		model,
		mayPromote = false,
		actor = '',
		newId = () => `an-${Math.random().toString(36).slice(2, 10)}`
	}: Props = $props();

	let replyText = $state('');
	let editText = $state('');
	let ruleText = $state('');
	let destination = $state<PromotionTarget>('concept.silhouette_rules');
	let editing = $state(false);

	const selected = $derived(model.selected);
	const isMine = $derived(Boolean(selected && actor && selected.author === actor));
	const offersPromotion = $derived(
		Boolean(mayPromote && selected?.exits.includes('promote'))
	);

	async function submitDraft(): Promise<void> {
		await model.submit(newId());
	}

	async function submitReply(): Promise<void> {
		const text = replyText.trim();
		if (!text) return;
		if (await model.reply(newId(), text)) replyText = '';
	}

	function startEditing(annotation: Annotation): void {
		editing = true;
		editText = annotation.text;
	}

	async function submitEdit(): Promise<void> {
		if (await model.edit(editText)) editing = false;
	}

	async function submitPromotion(): Promise<void> {
		const rule = ruleText.trim();
		if (!rule) return;
		if (await model.promote(rule, destination)) ruleText = '';
	}
</script>

<aside class="panel">
	{#if model.error}
		<p class="failure" role="alert">{model.error}</p>
	{/if}

	{#if model.isComposing}
		<section class="composer">
			<h3>New annotation</h3>
			<label>
				Kind
				<select
					value={model.draft.kind}
					onchange={(event) =>
						model.setDraftKind(event.currentTarget.value as Annotation['kind'])}
				>
					<option value="art-direction">art-direction</option>
					<option value="technical">technical</option>
					<option value="design">design</option>
				</select>
			</label>
			<textarea
				aria-label="what this annotation says"
				value={model.draft.text}
				oninput={(event) => model.setDraftText(event.currentTarget.value)}
			></textarea>
			<p class="marks">{model.draft.strokes.length} stroke(s) drawn</p>
			<div class="actions">
				<button type="button" onclick={submitDraft}>Save</button>
				<button type="button" onclick={() => model.undoStroke()}>Undo stroke</button>
				<button type="button" onclick={() => model.discard()}>Discard</button>
			</div>
		</section>
	{/if}

	{#if selected}
		<section class="thread" data-annotation={selected.id}>
			<h3>{selected.kind}</h3>
			<p class="state" data-state={selected.state}>{selected.state}</p>
			{#if editing}
				<textarea aria-label="reword this annotation" bind:value={editText}></textarea>
				<button type="button" onclick={submitEdit}>Save the wording</button>
			{:else}
				<p class="text">{selected.text}</p>
			{/if}
			<p class="attribution">{selected.attribution}</p>

			<ol class="replies">
				{#each selected.replies as reply (reply.id)}
					<li>
						<p class="text">{reply.text}</p>
						<p class="attribution">{reply.attribution}</p>
					</li>
				{/each}
			</ol>

			<label>
				Reply
				<textarea aria-label="reply in this thread" bind:value={replyText}></textarea>
			</label>
			<div class="actions">
				<button type="button" onclick={submitReply}>Reply</button>
				{#if isMine}
					<button type="button" onclick={() => startEditing(selected)}>Edit</button>
					<button type="button" onclick={() => model.withdraw()}>Withdraw</button>
				{/if}
				{#if selected.exits.includes('resolve')}
					<button type="button" onclick={() => model.resolve()}>Resolve</button>
				{/if}
				{#if selected.state === 'resolved'}
					<button type="button" onclick={() => model.reopen()}>Reopen</button>
				{/if}
			</div>

			{#if offersPromotion}
				<form class="promotion" onsubmit={(event) => event.preventDefault()}>
					<h4>Promote to a durable rule</h4>
					<label>
						Rule
						<input aria-label="the durable rule this becomes" bind:value={ruleText} />
					</label>
					<label>
						Destination
						<select bind:value={destination}>
							{#each PROMOTION_TARGETS as target (target)}
								<option value={target}>{target}</option>
							{/each}
						</select>
					</label>
					<p class="destination">
						This will be written to <code>{destination}</code> of this asset.
					</p>
					<button type="button" onclick={submitPromotion}>Promote</button>
				</form>
			{/if}
		</section>
	{/if}

	<section class="listing">
		<h3>Threads</h3>
		<ul>
			{#each model.visible as annotation (annotation.id)}
				<li>
					<button
						type="button"
						class:selected={annotation.id === model.selectedId}
						data-annotation={annotation.id}
						onclick={() => model.select(annotation.id)}
					>
						<span class="kind">{annotation.kind}</span>
						{annotation.text}
					</button>
				</li>
			{/each}
		</ul>
	</section>

	{#if model.orphans.length > 0}
		<section class="orphans">
			<h3>Cannot be shown</h3>
			<ul>
				{#each model.orphans as orphan (orphan.id)}
					<li data-orphan={orphan.id}>
						<button type="button" onclick={() => model.select(orphan.id)}>
							{orphan.annotation.text}
						</button>
						<p class="reason">{orphan.reason}</p>
					</li>
				{/each}
			</ul>
		</section>
	{/if}
</aside>

<style>
	.panel {
		display: grid;
		gap: 1rem;
		align-content: start;
	}

	textarea,
	input,
	select {
		width: 100%;
	}

	.actions {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.attribution {
		opacity: 0.8;
		margin: 0.125rem 0 0;
	}

	.failure {
		border: 1px solid currentColor;
		border-radius: 0.25rem;
		padding: 0.5rem;
	}

	.replies {
		padding-inline-start: 1rem;
	}

	.listing ul,
	.orphans ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.25rem;
	}

	.listing button.selected {
		outline: 2px solid currentColor;
	}

	.kind {
		font-weight: 600;
		margin-inline-end: 0.25rem;
	}

	.reason {
		margin: 0;
		opacity: 0.8;
	}
</style>
