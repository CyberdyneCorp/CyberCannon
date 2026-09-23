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
	/*
	 * The thread panel. The design sets this column as a stack of sections
	 * with no boxes at all — the conversation is prose and prose does not
	 * want a frame — and boxes exactly three things: the state tag, the
	 * orphan, and the failure. Those are the three that are not prose.
	 */
	.panel {
		display: grid;
		gap: var(--space-6);
		align-content: start;
	}

	h3 {
		font-size: var(--text-h4);
		margin-block-end: var(--space-2);
	}

	h4 {
		font-size: var(--text-h5);
		margin-block-end: var(--space-1);
	}

	textarea,
	input,
	select {
		width: 100%;
	}

	/* Deep enough to write a sentence about a silhouette into without the
	   box scrolling on the second line, and resizable, because some of
	   these are a paragraph. */
	textarea {
		min-height: calc(var(--space-8) * 2);
		resize: vertical;
	}

	.composer,
	.thread,
	.listing,
	.orphans {
		display: grid;
		gap: var(--space-2);
		justify-items: start;
	}

	.composer > *,
	.thread > *,
	.listing > *,
	.orphans > * {
		width: 100%;
	}

	label {
		display: grid;
		gap: var(--space-1);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
	}

	.actions {
		display: flex;
		gap: var(--space-2);
		flex-wrap: wrap;
	}

	/*
	 * `app-navigation`: who wrote a thing is on the screen that shows it,
	 * rendered exactly as the system produced it — *"rafa, via
	 * blender-agent"*. Quiet ink, never absent, never reassembled here.
	 */
	.attribution {
		margin: 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.text {
		margin: 0;
		font-size: var(--text-h5);
		line-height: var(--leading-body);
	}

	/*
	 * The thread's state, as a tag. The design's two: an open thread is the
	 * outline tag — white, black edge, nothing filled in, because it is not
	 * finished — and a resolved one is the neutral fill, because it is.
	 */
	.state {
		justify-self: start;
		margin: 0;
		display: inline-block;
		background: var(--color-surface);
		color: var(--color-text);
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		padding: 0 var(--space-1);
		width: auto;
	}

	.state[data-state='resolved'] {
		background: var(--color-neutral-200);
	}

	/*
	 * A write that did not land. This is the one thing in the panel that IS
	 * an error, and it takes the second accent at its stronger step so that
	 * nothing else in this column can be mistaken for it — the orphan block
	 * below is deliberately lighter for exactly that reason.
	 */
	.failure {
		margin: 0;
		background: var(--color-accent-2-200);
		color: var(--color-text);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-2) var(--space-3);
		font-weight: var(--font-weight-medium);
	}

	/* The replies, hung off the design's heavy rule rather than off a
	   bullet: this is one conversation indented under its opening, and a
	   list marker would make it a list of separate things. */
	.replies {
		list-style: none;
		margin: 0;
		padding: 0 0 0 var(--space-3);
		display: grid;
		gap: var(--space-3);
		border-inline-start: var(--border-heavy) solid var(--color-divider);
	}

	/*
	 * PROMOTE AND RESOLVE ARE TWO DIFFERENT ACTS AND THEY CARRY TWO
	 * DIFFERENT WEIGHTS.
	 *
	 * Resolving closes one thread and leaves nothing behind; it is an
	 * ordinary control in the row of exits above. Promoting WRITES A DURABLE
	 * RULE into this asset's contract, it retires the thread, and only an art
	 * director is offered it — so it is not a fourth button in that row. It
	 * is its own block, on the page's ground inside the heavy edge, with the
	 * destination stated before the act and the one affirmative control in
	 * the spot yellow the design reserves for it.
	 *
	 * The offer is a courtesy and not the guarantee: the component's comment
	 * says so, and the system refuses a submitted promotion from anybody who
	 * may not make one whatever this stylesheet does.
	 */
	.promotion {
		display: grid;
		gap: var(--space-2);
		background: var(--color-bg);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
		padding: var(--space-3);
	}

	.destination {
		margin: 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.destination code {
		font-family: var(--font-mono);
		color: var(--color-text);
	}

	.promotion button {
		justify-self: start;
		background: var(--color-highlight);
	}

	.promotion button:hover:not(:disabled) {
		background: var(--color-highlight-hover);
	}

	.listing ul,
	.orphans ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: var(--space-1);
	}

	/*
	 * A thread in the list is a line of its own text, not a control with a
	 * box: a column of six bordered buttons is a column with no hierarchy
	 * left. The selected one takes the spot yellow, which is how the design
	 * marks the row a panel is currently about.
	 */
	.listing button,
	.orphans button {
		display: block;
		width: 100%;
		text-align: start;
		font-family: var(--font-body);
		font-weight: 400;
		font-size: var(--text-small);
		line-height: var(--leading-body);
		background: none;
		border: 0;
		box-shadow: none;
		padding: var(--space-1) var(--space-2);
		color: var(--color-text);
	}

	.listing button:hover:not(:disabled),
	.orphans button:hover:not(:disabled) {
		transform: none;
		box-shadow: none;
		background: var(--color-neutral-100);
	}

	.listing button:active:not(:disabled),
	.orphans button:active:not(:disabled) {
		transform: none;
		box-shadow: none;
	}

	.listing button.selected {
		background: var(--color-highlight);
	}

	.kind {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		margin-inline-end: var(--space-1);
		color: var(--color-neutral-700);
	}

	/*
	 * ORPHANS ARE A DECISION, NOT A BREAKAGE.
	 *
	 * An orphaned annotation is a thread somebody wrote, still readable,
	 * still repliable, which cannot be drawn because the thing it was
	 * anchored to is not in this revision. Nothing failed — the anchor is
	 * doing its job by refusing to point at the wrong part. So this block is
	 * the design's own orphan treatment: the second accent's LIGHTEST tint
	 * behind the ordinary black edge, a heading in its deep step, and the
	 * reason printed under each thread so the reader knows what decision is
	 * being asked of them. It is deliberately lighter than `.failure` above
	 * and it sits on a surface rather than shouting, because *this needs a
	 * decision* and *this broke* must not look alike.
	 */
	.orphans {
		background: var(--color-accent-2-100);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-sm);
		padding: var(--space-3);
	}

	.orphans h3 {
		color: var(--color-accent-2-800);
	}

	.orphans button:hover:not(:disabled) {
		background: var(--color-accent-2-200);
	}

	.reason {
		margin: 0;
		padding-inline: var(--space-2);
		font-size: var(--text-small);
		color: var(--color-accent-2-800);
	}

	.marks {
		margin: 0;
		font-family: var(--font-mono);
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}
</style>
