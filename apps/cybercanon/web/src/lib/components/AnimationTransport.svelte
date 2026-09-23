<script lang="ts">
	/**
	 * The animation transport: the clips, what each satisfies, and the controls.
	 *
	 * `animation-playback` asks for a list with durations, play/pause/scrub, loop,
	 * at least three speeds, the current position while playing and while paused,
	 * and — the part a transport usually leaves out — **every declared design
	 * state, including the ones with no clip**. A state that is missing without
	 * comment is exactly the report the validator exists to produce, arriving as
	 * silence instead.
	 *
	 * Nothing here decides which clip satisfies which state. That mapping is the
	 * specification's, derived once and consumed verbatim (D8): this component
	 * renders `coverage`, which the server produced, and performs no matching of
	 * its own — not case-folding, not by similarity.
	 *
	 * Selected clip, position, loop and speed are view state and are never
	 * written anywhere (D12).
	 */
	import type { ClipCoverage } from '$lib/api';
	import type { Clip, Transport } from '$lib/viewer/clips';
	import {
		SPEEDS,
		clipNamed,
		durationOf,
		readout,
		secondsAt
	} from '$lib/viewer/clips';
	import { clipRows, stateRows } from '$lib/viewer/presentation';

	interface Props {
		clips: readonly Clip[];
		coverage: ClipCoverage;
		transport: Transport;
		/** What to say when there are no clips — the two absences differ. */
		absence?: string | null;
		onSelect?: (clip: string) => void;
		onToggle?: () => void;
		onScrub?: (position: number) => void;
		onLoop?: (loop: boolean) => void;
		onSpeed?: (speed: number) => void;
	}

	let {
		clips,
		coverage,
		transport,
		absence = null,
		onSelect = () => {},
		onToggle = () => {},
		onScrub = () => {},
		onLoop = () => {},
		onSpeed = () => {}
	}: Props = $props();

	const rows = $derived(clipRows(coverage, clips));
	const states = $derived(stateRows(coverage));
	const current = $derived(clipNamed(clips, transport.clip));
	const offered = $derived(clips.length > 0);
</script>

<section class="transport" aria-label="animation">
	<h3>Animation</h3>

	{#if !offered}
		<p class="absence">{absence}</p>
	{:else}
		<ul class="clips">
			{#each rows as row (row.name)}
				<li class:selected={row.name === transport.clip}>
					<button type="button" onclick={() => onSelect(row.name)}>{row.name}</button>
					<span class="duration">{readout(row.duration)}</span>
					<span class="satisfies">
						{row.state ? `satisfies ${row.state}` : 'satisfies no declared state'}
					</span>
				</li>
			{/each}
		</ul>

		<div class="controls" role="group" aria-label="playback">
			<button type="button" onclick={onToggle} disabled={!transport.clip}>
				{transport.playing ? 'Pause' : 'Play'}
			</button>
			<label>
				Position
				<input
					type="range"
					min="0"
					max="1"
					step="0.001"
					value={transport.position}
					disabled={!transport.clip}
					oninput={(event) => onScrub(Number(event.currentTarget.value))}
				/>
			</label>
			<output class="position">
				{readout(secondsAt(transport, current))} / {readout(durationOf(current))}
			</output>
			<label>
				Loop
				<input
					type="checkbox"
					checked={transport.loop}
					onchange={(event) => onLoop(event.currentTarget.checked)}
				/>
			</label>
			<label>
				Speed
				<select
					value={String(transport.speed)}
					onchange={(event) => onSpeed(Number(event.currentTarget.value))}
				>
					{#each SPEEDS as speed (speed)}
						<option value={String(speed)}>{speed}x</option>
					{/each}
				</select>
			</label>
		</div>
	{/if}

	<h4>Declared states</h4>
	{#if states.length === 0}
		<p class="absence">this asset declares no design state that requires a clip</p>
	{:else}
		<ul class="states">
			{#each states as state (state.state)}
				<li class:gap={state.coverage === 'no clip'}>
					<span class="state">{state.state}</span>
					<span class="coverage">{state.coverage}</span>
					{#if state.clip}<span class="clip">{state.clip}</span>{/if}
				</li>
			{/each}
		</ul>
	{/if}

	{#if coverage.unclaimed.length > 0}
		<p class="unclaimed">
			Satisfying no declared state: {coverage.unclaimed.join(', ')}
		</p>
	{/if}
</section>

<style>
	/*
	 * The transport, set as the design sets it: the clip list as a column of
	 * rows, the controls as one line under the stage, and the declared states
	 * as their own block underneath.
	 *
	 * THE ONE THING THIS STYLESHEET EXISTS FOR is the declared state with no
	 * clip. `animation-playback` asks for *every* declared design state,
	 * including the ones nothing satisfies, and a restyle that set that row
	 * like every other row would have turned the requirement back into the
	 * silence it was written against. So the gap row is the loudest thing in
	 * this section: the second accent's tint behind a black edge, which is
	 * this system's mark for something somebody has to act on.
	 */
	.transport {
		margin-block-start: var(--space-4);
		display: grid;
		gap: var(--space-2);
	}

	h3 {
		font-size: var(--text-h4);
		margin: 0;
	}

	h4 {
		font-size: var(--text-h5);
		margin: var(--space-4) 0 var(--space-1);
	}

	.clips,
	.states {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: var(--space-1);
	}

	.clips li,
	.states li {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1) var(--space-2);
		align-items: baseline;
	}

	/* The selected clip, marked in the system's own way: the spot yellow
	   behind the control, which is what the design uses for the one action a
	   block is currently about. */
	.selected > button {
		background: var(--color-highlight);
	}

	/* Durations and the position readout are figures read against each other,
	   so they take the mono and its tabular figures and stop reflowing as a
	   clip plays. */
	.duration,
	.position {
		font-family: var(--font-mono);
		font-size: var(--text-small);
		font-variant-numeric: tabular-nums;
	}

	.satisfies {
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-3);
		margin-block-start: var(--space-3);
	}

	.controls label {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
	}

	.controls input[type='range'] {
		flex: 1 1 12rem;
		accent-color: var(--color-accent);
		border: 0;
		box-shadow: none;
		padding: 0;
		background: none;
	}

	/* The state's own name, set as the eyebrow the design gives a label. */
	.state {
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		min-width: 9rem;
	}

	.coverage {
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.clip {
		font-family: var(--font-mono);
		font-size: var(--text-small);
	}

	/*
	 * A declared state nothing satisfies. The word `no clip` is boxed and
	 * tinted rather than italicised, because an italic is a shade of the same
	 * sentence and this is a different sentence: the asset declares a state
	 * and the export does not contain it. Visibly absent, which is what the
	 * requirement asks for, rather than absent.
	 */
	.gap .coverage {
		display: inline-block;
		background: var(--color-accent-2-100);
		color: var(--color-accent-2-800);
		border: var(--border-thin) solid var(--color-divider);
		border-radius: var(--radius-sm);
		font-family: var(--font-heading);
		font-weight: var(--font-weight-strong);
		font-size: var(--text-fine);
		letter-spacing: var(--tracking-caps);
		text-transform: uppercase;
		padding: 0 var(--space-1);
	}

	/* A clip satisfying nothing declared is the mirror of the gap above, and
	   it is the milder of the two: an extra clip costs nothing, a missing
	   state costs a bug report. So it is stated in prose, in the quiet ink. */
	.unclaimed {
		margin: var(--space-2) 0 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}

	.absence {
		margin: 0;
		font-size: var(--text-small);
		color: var(--color-neutral-700);
	}
</style>
