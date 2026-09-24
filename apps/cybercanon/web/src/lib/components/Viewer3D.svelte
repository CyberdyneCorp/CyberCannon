<script lang="ts">
	/**
	 * The 3D viewer: a preview, its provenance, and the shared annotation surface.
	 *
	 * **What this component is responsible for is exactly two conversions** (D2):
	 * pointer input becomes an `Anchor3D`, and an `Anchor3D` plus a loaded mesh
	 * becomes a screen position plus a resolution state. Threads, filtering,
	 * triage and status are read from the shared `AnnotationViewModel` and are
	 * never reimplemented here — the panel and the filter bar below are the same
	 * components the 2D sheet renders, over the same ViewModel, which is the
	 * selective-MVVM bet from `openspec/project.md` being collected rather than
	 * restated.
	 *
	 * *If this component needed the ViewModel to learn about parts, the 2D/3D
	 * boundary would be in the wrong place.* It does not: the ViewModel is given
	 * an anchor it never inspects, and everything three-dimensional lives in
	 * `$lib/viewer`, which it does not import.
	 *
	 * **The engine arrives as a prop.** `mount` is handed in by whoever renders
	 * this — the asset surface dynamically imports `$lib/viewer/scene` and passes
	 * its factory — so D7's split survives, and so a suite can drive every
	 * requirement here with a scene that is an object rather than a GPU.
	 *
	 * **Degradation is a different presentation, not a disabled viewer** (D11).
	 * With no rendering context the still imagery, the specification and the full
	 * annotation list including orphans are all present and triageable, and
	 * placing a new 3D anchor is *stated* as unavailable rather than failing when
	 * somebody tries.
	 */
	import { untrack } from 'svelte';
	import type { AnchorResolutions, AnnotationListing, PreviewDescriptor } from '$lib/api';
	import type { Anchor } from '$lib/api';
	import type { AnnotationViewModel } from '$lib/annotation';
	import AnnotationFilters from './AnnotationFilters.svelte';
	import ThreadPanel from './ThreadPanel.svelte';
	import AnimationTransport from './AnimationTransport.svelte';
	import { anchorFor } from '$lib/viewer/anchor';
	import { deviceCoordinates, isTap } from '$lib/viewer/gesture';
	import type { Point } from '$lib/viewer/gesture';
	import type { Opening } from '$lib/viewer/opening';
	import { openingFor, reanchorTo } from '$lib/viewer/opening';
	import type { Clip, Transport } from '$lib/viewer/clips';
	import {
		STOPPED,
		advanced,
		clipNamed,
		scrubTo,
		select as selectClip,
		setLoop,
		setSpeed,
		toggle
	} from '$lib/viewer/clips';
	import type { RenderingProbe, Session } from '$lib/viewer/capability';
	import {
		browserCanRender,
		canPlaceAnchor,
		contextLost,
		contextRestored,
		loaded as sessionLoaded,
		newSession,
		restorationFailed,
		retrying,
		unloadable
	} from '$lib/viewer/capability';
	import {
		ANCHOR_UNAVAILABLE,
		NO_RENDERING,
		POINT_AT_A_PART,
		UNLOADABLE,
		absenceOf,
		clipAbsence,
		figuresOf,
		orphanCount,
		provenanceOf
	} from '$lib/viewer/presentation';
	import type { SceneFactory, SceneLike } from '$lib/viewer/contract';

	interface Props {
		model: AnnotationViewModel;
		/** What the route read. The viewer never asks for it itself (D2). */
		listing: AnnotationListing;
		descriptor: PreviewDescriptor;
		/** The orphan count the server answered without a renderer (D6). */
		resolutions?: AnchorResolutions | null;
		/** The preview's bytes, as the route read them. `null` until they arrive. */
		bytes?: ArrayBuffer | null;
		/** Why the route could not read them, when the descriptor named a preview. */
		unretrievable?: string | null;
		/** The scene factory, handed in so `$lib/viewer/scene` stays lazily loaded. */
		mount?: SceneFactory | null;
		probe?: RenderingProbe;
		mayPromote?: boolean;
		actor?: string;
		selected?: string | null;
		/** Rescue an orphan. Supplied by the route, so no view reaches the API (D2). */
		onReanchor?: (annotation: string, anchor: Anchor) => Promise<boolean>;
		onRetry?: () => void;
	}

	let {
		model,
		listing,
		descriptor,
		resolutions = null,
		bytes = null,
		unretrievable = null,
		mount = null,
		probe = browserCanRender,
		mayPromote = false,
		actor = '',
		selected = null,
		onReanchor = async () => false,
		onRetry = () => {}
	}: Props = $props();

	let canvas: HTMLCanvasElement | null = $state(null);
	let scene: SceneLike | null = $state(null);
	/**
	 * Whether this device can present a preview at all, asked once.
	 *
	 * A fact about the device rather than a value to track — and asking it once
	 * is also what keeps it out of the mount effect's dependencies, which
	 * matters: that effect *writes* the session, so reading it there would make
	 * the scene tear down and remount on every load.
	 */
	const renders = untrack(() => probe());
	let session = $state<Session>(newSession(() => renders));
	let transport = $state<Transport>(STOPPED);
	let clips = $state<readonly Clip[]>([]);
	let previewTriangles = $state<number | null>(null);
	let partNames = $state<readonly string[]>([]);
	let selectedPart = $state<string | null>(null);
	let isolated = $state<string | null>(null);
	let placementNotice = $state('');
	let decodeFailure = $state<string | null>(null);
	/** Where the pointer went down, so a drag reads as navigation rather than a pin. */
	let pressedAt: Point | null = null;
	/**
	 * When the last played frame was drawn. Deliberately not reactive.
	 *
	 * The playback effect re-runs on every advance — it reads the transport it
	 * writes — so a timestamp held in reactive state would be reset each frame
	 * and the clip would never move. A plain `let` survives the re-run, which is
	 * what makes the elapsed time real time.
	 */
	let lastFrameAt = 0;
	/** What the viewer could not restore when an annotation was opened. */
	let notices = $state<readonly string[]>([]);

	// Take the route's listing once per `(asset, revision)`, exactly as the 2D
	// sheet does — the same rule, because it is the same ViewModel.
	let taken = $state('');

	function hydrate(): void {
		const key = `${listing.asset}@${listing.revision}`;
		if (taken === key) return;
		taken = key;
		model.hydrate(listing);
		if (selected) model.select(selected);
	}

	hydrate();
	$effect(hydrate);

	const provenance = $derived(provenanceOf(descriptor));
	const figures = $derived(figuresOf(descriptor, previewTriangles));
	const absence = $derived(absenceOf(descriptor));
	const orphans = $derived(orphanCount(resolutions));
	const placeable = $derived(canPlaceAnchor(session));
	/**
	 * Whether there is a preview that could not be loaded.
	 *
	 * A descriptor naming one whose bytes never arrived is *"an unloadable
	 * preview"*, which `viewer-3d` requires to be reported with a retry — and
	 * requires not to be reported as the asset having no preview. The two are
	 * different sentences because they send a person to different places.
	 */
	const unloadableNow = $derived(
		session.state === 'unloadable' || Boolean(descriptor.preview && unretrievable)
	);

	// The two context events are attached here rather than in the markup because
	// they are not in Svelte's element event map — and because D11's one
	// restoration attempt has to be armed for the canvas's whole life, not for
	// the life of a render.
	$effect(() => {
		const element = canvas;
		if (!element) return;
		element.addEventListener('webglcontextlost', lost);
		element.addEventListener('webglcontextrestored', restored);
		return () => {
			element.removeEventListener('webglcontextlost', lost);
			element.removeEventListener('webglcontextrestored', restored);
		};
	});

	$effect(() => {
		if (!canvas || !mount || !bytes || !renders) return;
		decodeFailure = null;
		const built = mount(canvas, descriptor.parts);
		scene = built;
		built
			.load(bytes)
			.then((preview) => {
				clips = preview.clips;
				previewTriangles = preview.triangles;
				partNames = preview.parts.map((part) => part.name);
				session = sessionLoaded(session);
				built.render();
			})
			.catch(() => {
				decodeFailure = 'The preview could not be decoded. Retry to load it again.';
				session = unloadable(session);
			});
		return () => built.dispose();
	});

	/**
	 * The clock. One animation frame per advance, and none at all while paused.
	 *
	 * `advanced` is where the arithmetic lives — looping, speed, and stopping at
	 * the end — so this is only the tick: it decides *how much time passed*, and
	 * the transport decides what that means. A long gap (a backgrounded tab) is
	 * clamped rather than jumped through, because a clip that lurched a minute
	 * forward on return is a clip nobody asked to scrub.
	 */
	$effect(() => {
		if (!transport.playing || !scene) return;
		const frame = requestAnimationFrame((now) => {
			const seconds = lastFrameAt === 0 ? 0 : Math.min((now - lastFrameAt) / 1000, 0.25);
			lastFrameAt = now;
			transport = advanced(transport, clipNamed(clips, transport.clip), seconds);
			scene?.playClip(transport.clip, transport.position);
			scene?.render();
		});
		return () => cancelAnimationFrame(frame);
	});

	/** Start or stop the clock, and forget when the last frame was on the way out. */
	function transportToggled(): void {
		transport = toggle(transport);
		if (!transport.playing) lastFrameAt = 0;
	}

	/**
	 * Place a new anchor where the pointer is, or say that a part must be pointed at.
	 *
	 * A press and a release, because orbit, pan and zoom are the *same* pointer on
	 * the *same* surface: a gesture that moved was navigation and is left to the
	 * scene's controls, and a gesture that stayed put is a placement. The rule is
	 * `$lib/viewer/gesture`'s, so it is one decision rather than one per surface.
	 *
	 * What a placement records is the part (the durable key), the rest-pose point
	 * and normal the scene module narrowed the hit to (D3, D10), and the current
	 * camera. When a clip is held paused, the clip name and the position within it
	 * go too, as viewing hints (D9).
	 */
	function pressed(event: PointerEvent): void {
		pressedAt = { x: event.clientX, y: event.clientY };
	}

	function released(event: PointerEvent): void {
		const from = pressedAt;
		pressedAt = null;
		if (!scene || !placeable || !canvas) return;
		if (!isTap(from, { x: event.clientX, y: event.clientY })) return;
		const box = canvas.getBoundingClientRect();
		const at = deviceCoordinates({ x: event.clientX, y: event.clientY }, box);
		const anchor = anchorFor(
			scene.pick(at.x, at.y),
			scene.camera(),
			transport.clip ? { clip: transport.clip, t: transport.position } : null
		);
		if (anchor === null) {
			placementNotice = POINT_AT_A_PART;
			return;
		}
		placementNotice = '';
		model.compose(anchor);
	}

	/**
	 * Open an annotation: restore what its author was looking at, then present it.
	 *
	 * What "restore" means is `$lib/viewer/opening`'s decision — the camera, the
	 * part to frame when there is none, the clip held paused at the recorded
	 * position, and the sentences about what could not be restored. This applies
	 * it, and applying is all it does: nothing here writes to the annotation, and
	 * there is nothing in an `Opening` it could write.
	 */
	function open(id: string): void {
		model.select(id);
		const annotation = model.annotations.find((entry) => entry.id === id);
		if (!annotation) return;
		const opening = openingFor(annotation, clips);
		notices = opening.notices;
		transport = opening.transport;
		apply(opening);
	}

	function apply(opening: Opening): void {
		if (!scene) return;
		if (opening.camera) {
			scene.applyCamera(opening.camera);
		} else if (opening.frame) {
			scene.select(opening.frame);
			scene.frameSelected();
		}
		if (opening.transport.clip) {
			scene.playClip(opening.transport.clip, opening.transport.position);
		}
		scene.render();
	}

	function choosePart(part: string): void {
		selectedPart = part;
		scene?.select(part);
		scene?.render();
	}

	function frameThePart(): void {
		scene?.frameSelected();
		scene?.render();
	}

	function frameEverything(): void {
		scene?.frameAll();
		scene?.render();
	}

	function toggleIsolation(): void {
		if (isolated) {
			isolated = null;
			scene?.restore();
		} else if (selectedPart) {
			isolated = selectedPart;
			scene?.isolate(selectedPart);
		}
		scene?.render();
	}

	async function rescue(): Promise<void> {
		const id = model.selectedId;
		const anchor = reanchorTo(selectedPart ?? '', scene?.camera() ?? null);
		if (!id || anchor === null) return;
		if (await onReanchor(id, anchor)) await model.load();
	}

	function select(clip: string): void {
		lastFrameAt = 0;
		transport = selectClip(transport, clip);
		scene?.playClip(transport.clip, transport.position);
		scene?.render();
	}

	function scrub(position: number): void {
		lastFrameAt = 0;
		transport = scrubTo(transport, position);
		scene?.playClip(transport.clip, transport.position);
		scene?.render();
	}

	function lost(): void {
		session = contextLost(session, { camera: scene?.camera() ?? null, transport });
	}

	function restored(): void {
		session = session.state === 'degraded' ? restorationFailed(session) : contextRestored(session);
		if (session.kept.camera) scene?.applyCamera(session.kept.camera);
		if (session.kept.transport.clip) {
			transport = session.kept.transport;
			scene?.playClip(transport.clip, transport.position);
		}
		scene?.render();
	}

	function retry(): void {
		decodeFailure = null;
		session = retrying(session);
		onRetry();
	}
</script>

<section class="viewer" aria-label="3D viewer">
	<header class="provenance">
		<p>
			Showing <span class="export">{provenance.export || 'no export'}</span>
			against revision <span class="revision">{provenance.revision}</span>
		</p>
		{#if provenance.notice}
			<p class="superseded">{provenance.notice}</p>
		{/if}
		<ul class="figures">
			{#each figures as figure (figure.label)}
				<li class:unrecorded={!figure.recorded}>
					<span class="label">{figure.label}</span>
					<span class="value">{figure.value}</span>
				</li>
			{/each}
		</ul>
	</header>

	{#if session.state === 'degraded'}
		<p class="degraded">{NO_RENDERING}</p>
		<p class="placement-unavailable">{ANCHOR_UNAVAILABLE}</p>
	{:else if absence}
		<p class="no-preview">{absence}</p>
	{:else if unloadableNow}
		<p class="unloadable">{UNLOADABLE}</p>
		{#if unretrievable || decodeFailure}<p class="unloadable-reason">{unretrievable ?? decodeFailure}</p>{/if}
		<button type="button" onclick={retry}>Retry</button>
	{:else}
		<div class="stage">
			<!-- Neo-brutalism frames the canvas; it does not reach inside it. The
			     edge, the hard offset and the ground are on this wrapper, and the
			     canvas keeps the sizing it had, because `$lib/viewer/scene` reads
			     `canvas.clientWidth` to size the renderer. -->
			<div class="frame">
				<canvas
					bind:this={canvas}
					width="640"
					height="360"
					onpointerdown={pressed}
					onpointerup={released}
				></canvas>
			</div>
			<div class="navigation" role="group" aria-label="framing">
				<button type="button" onclick={frameEverything}>Frame asset</button>
				<button type="button" onclick={frameThePart} disabled={!selectedPart}>
					Frame part
				</button>
				<button type="button" onclick={toggleIsolation} disabled={!selectedPart && !isolated}>
					{isolated ? 'Show all parts' : 'Isolate part'}
				</button>
			</div>
		</div>
		{#if placementNotice}<p class="placement">{placementNotice}</p>{/if}
	{/if}

	<section class="parts" aria-label="parts">
		<h3>Parts</h3>
		{#if partNames.length === 0}
			<p class="absence">no part of this preview has been loaded</p>
		{:else}
			<ul>
				{#each partNames as part (part)}
					<li class:selected={part === selectedPart}>
						<button type="button" onclick={() => choosePart(part)}>{part}</button>
					</li>
				{/each}
			</ul>
		{/if}
		{#if selectedPart}<p class="selected-part">Selected: {selectedPart}</p>{/if}
	</section>

	<AnimationTransport
		{clips}
		coverage={descriptor.coverage}
		{transport}
		absence={clipAbsence(descriptor, clips)}
		onSelect={select}
		onToggle={transportToggled}
		onScrub={scrub}
		onLoop={(loop) => (transport = setLoop(transport, loop))}
		onSpeed={(speed) => (transport = setSpeed(transport, speed))}
	/>

	<section class="threads" aria-label="annotations">
		<AnnotationFilters {model} />
		<p class="orphan-count">{orphans} orphaned on this export</p>
		<ul class="thread-list">
			{#each model.visible as annotation (annotation.id)}
				<li class:orphaned={annotation.anchor_state === 'orphaned'}>
					<button type="button" onclick={() => open(annotation.id)}>{annotation.text}</button>
					{#if annotation.anchor_state === 'orphaned'}
						<span class="orphan">orphaned — expected {annotation.anchor.durable_key}</span>
					{/if}
				</li>
			{/each}
		</ul>
		{#each notices as notice (notice)}
			<p class="restore-notice">{notice}</p>
		{/each}
		{#if model.selected?.anchor_state === 'orphaned'}
			<button type="button" onclick={rescue} disabled={!selectedPart}>
				Re-anchor to {selectedPart ?? 'a part'}
			</button>
		{/if}
		<ThreadPanel {model} {mayPromote} {actor} />
	</section>
</section>

<style>
	/*
	 * The viewer's chrome. The render is three.js's and this stylesheet does
	 * not reach inside it: everything here is the frame around the canvas,
	 * the provenance above it, the parts beside it and the threads below.
	 */
	.viewer {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	h3 {
		font-size: var(--text-h4);
		margin-block-end: var(--space-2);
	}

	/*
	 * WHAT IS BEING SHOWN AND AGAINST WHAT. `viewer-3d` requires the export
	 * and the revision on the screen, so they lead, and they are set in the
	 * mono because they are identifiers rather than prose.
	 */
	.provenance p {
		margin: 0;
		font-size: var(--text-small);
	}

	.export,
	.revision {
		font-family: var(--font-mono);
		font-weight: var(--font-weight-strong);
		color: var(--color-text);
	}

	/* A preview drawn against a revision that is no longer the current one.
	   A disclosure rather than a failure — what is on screen is real, it is
	   just not the latest — so it takes the spot yellow the design gives a
	   notice. */
	.superseded {
		margin: var(--space-2) 0 0;
		background: var(--color-highlight);
		color: var(--color-text);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-2) var(--space-3);
		font-weight: var(--font-weight-medium);
	}

	.figures,
	.parts ul,
	.thread-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	/*
	 * The counts, set as the design sets them: the figure large, tabular and
	 * over its label, so triangles and objects can be read against a budget
	 * at a glance.
	 */
	.figures {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-6);
		margin-block-start: var(--space-3);
	}

	.figures li {
		display: flex;
		flex-direction: column-reverse;
	}

	.figures .value {
		font-family: var(--font-mono);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-h3);
		font-variant-numeric: tabular-nums;
		line-height: var(--leading-heading);
	}

	.figures .label {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		color: var(--color-neutral-700);
	}

	/*
	 * A figure the export does not record. *"Not recorded"* is a statement
	 * about the file, not a number, so it drops out of the mono into the
	 * body face at body size — it stops looking like a count somebody could
	 * compare, which is exactly what it is not.
	 */
	.unrecorded .value {
		font-family: var(--font-body);
		font-size: var(--text-body);
		font-weight: 400;
		color: var(--color-neutral-700);
	}

	.stage {
		display: grid;
		gap: var(--space-3);
		justify-items: start;
	}

	/*
	 * THE FRAME AROUND THE CANVAS. Neo-brutalism frames the render; it does
	 * not reach inside it. The canvas keeps the size it had — the scene
	 * module sizes its renderer from `canvas.clientWidth` — and everything
	 * this system draws is on the wrapper.
	 */
	.frame {
		width: 100%;
		max-width: 40rem;
		background: var(--color-surface);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
	}

	canvas {
		display: block;
		width: 100%;
	}

	.navigation {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	/*
	 * NO RENDERING CONTEXT (D11). This is a disclosure and not an error: the
	 * stills, the specification and every thread including the orphans are
	 * still here and still triageable — what is missing is the render. So it
	 * takes the spot yellow this interface gives *some of this is
	 * unavailable*, and the sentence about placing an anchor sits under it as
	 * prose, because it is the consequence rather than a second problem.
	 */
	.degraded {
		margin: 0;
		background: var(--color-highlight);
		color: var(--color-text);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-2) var(--space-3);
		font-weight: var(--font-weight-medium);
	}

	.placement-unavailable,
	.placement {
		margin: var(--space-2) 0 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	/* An asset with no preview at all. Nothing went wrong; there is simply
	   nothing to draw. Prose, on the page's ground, with no box. */
	.no-preview,
	.absence {
		margin: 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	/*
	 * A PREVIEW THAT EXISTS AND COULD NOT BE LOADED, which `viewer-3d`
	 * requires to be a different sentence from *this asset has no preview* —
	 * the two send a person to different places. This one is the second
	 * accent, because something did fail, and it is the only state in this
	 * component that carries a retry.
	 */
	.unloadable {
		margin: 0;
		background: var(--color-accent-2-100);
		color: var(--color-text);
		border: var(--border-thick) solid var(--color-divider);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
		padding: var(--space-2) var(--space-3);
		font-weight: var(--font-weight-medium);
	}

	.unloadable-reason {
		margin: var(--space-2) 0;
		font-size: var(--text-small);
		color: var(--color-accent-2-800);
	}

	/* The one way forward out of an unloadable preview, so it takes the spot
	   yellow the design reserves for the action a block is about. It is the
	   only direct control this section has. */
	.viewer > button {
		justify-self: start;
		background: var(--color-highlight);
	}

	.viewer > button:hover:not(:disabled) {
		background: var(--color-highlight-hover);
	}

	/*
	 * The parts. A column of rows rather than a row of controls: the design
	 * sets a list like this flat, with the selected one on the spot yellow,
	 * because ten bordered buttons stacked is ten boxes and no hierarchy.
	 */
	.parts ul {
		display: grid;
		gap: 0;
	}

	.parts li button {
		display: block;
		width: 100%;
		text-align: start;
		font-family: var(--font-body);
		font-weight: 400;
		font-size: var(--text-small);
		background: none;
		border: 0;
		box-shadow: none;
		padding: var(--space-1) var(--space-2);
		color: var(--color-text);
	}

	.parts li button:hover:not(:disabled) {
		transform: none;
		box-shadow: none;
		background: var(--color-neutral-100);
	}

	.parts li button:active:not(:disabled) {
		transform: none;
		box-shadow: none;
	}

	.parts li.selected button {
		background: var(--color-highlight);
		font-weight: var(--font-weight-strong);
	}

	.selected-part {
		margin: var(--space-2) 0 0;
		font-family: var(--font-mono);
		font-size: var(--text-small);
	}

	.threads {
		display: grid;
		gap: var(--space-3);
	}

	/*
	 * How many threads this export cannot draw, answered by the server
	 * without a renderer (D6) and stated whatever the number is. It is set as
	 * prose rather than as a tag: a permanent pink label reading `0 orphaned`
	 * would be an alarm about nothing, and the rows below carry the mark for
	 * the ones that need a decision.
	 */
	.orphan-count {
		margin: 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.thread-list {
		display: grid;
		gap: var(--space-1);
	}

	.thread-list li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: var(--space-1) var(--space-2);
	}

	.thread-list li button {
		flex: 1 1 12rem;
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

	.thread-list li button:hover:not(:disabled) {
		transform: none;
		box-shadow: none;
		background: var(--color-neutral-100);
	}

	.thread-list li button:active:not(:disabled) {
		transform: none;
		box-shadow: none;
	}

	/*
	 * AN ORPHANED THREAD IS A DECISION, NOT A BREAKAGE.
	 *
	 * The anchor is doing its job: the part it names is not in this export,
	 * so the thread is listed rather than drawn, and it is never shown on the
	 * wrong part. That is the system working, and somebody now has to choose
	 * a part to re-anchor it to. So the row keeps the second accent's
	 * LIGHTEST tint — the design's own orphan treatment — with the expected
	 * part boxed beside it, and it is deliberately quieter than the
	 * unloadable panel above, which is the state where something did break.
	 */
	.thread-list li.orphaned {
		background: var(--color-accent-2-100);
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
	}

	.thread-list li.orphaned button:hover:not(:disabled) {
		background: var(--color-accent-2-200);
	}

	.orphan {
		font-size: var(--text-fine);
		font-weight: var(--font-weight-strong);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		color: var(--color-accent-2-800);
		padding-inline-end: var(--space-2);
	}

	/* What the viewer could not put back when a thread was opened — the
	   camera, the clip, the part. Stated, never swallowed. */
	.restore-notice {
		margin: 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	/*
	 * THE WAY OUT OF AN ORPHAN. It is the affirmative act on this screen —
	 * it rewrites where a thread lives — so it takes the spot yellow the
	 * design reserves for the one action a block is about, and it says which
	 * part it will use, so nobody presses it hoping.
	 */
	.threads > button {
		justify-self: start;
		background: var(--color-highlight);
	}

	.threads > button:hover:not(:disabled) {
		background: var(--color-highlight-hover);
	}
</style>
