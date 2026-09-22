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
	.transport {
		margin-top: 1rem;
	}
	.clips,
	.states {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.clips li,
	.states li {
		display: flex;
		gap: 0.5rem;
		align-items: baseline;
	}
	.selected {
		font-weight: 600;
	}
	.gap .coverage {
		font-style: italic;
	}
	.absence {
		font-style: italic;
	}
</style>
