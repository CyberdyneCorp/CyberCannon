/**
 * The animation transport, as a value: select, play, pause, scrub, loop, speed.
 *
 * Every function here takes a state and returns one, with no timer, no mixer and
 * no clock of its own. That is what makes `animation-playback`'s *"scrubbing is
 * deterministic"* assertable — *"scrubbed to a given position twice from
 * different starting points"* is two calls with the same argument, and a
 * transport that lived inside `three.js` could only be asserted by looking at
 * pixels.
 *
 * **Position is a proportion of the clip's duration, never a frame** (D9). The
 * same decision that shapes the stored playback hint shapes the transport that
 * produces it, so what the viewer holds and what an anchor records are the same
 * number and nothing converts between them.
 *
 * **Speed scales time, never the clip.** `animation-playback` requires the
 * duration reported to be *"the clip's own duration"* whatever it is being
 * played at, so speed appears in :func:`advanced` and nowhere else.
 */

/** One clip the loaded preview carries, with the duration it declares. */
export interface Clip {
	readonly name: string;
	readonly duration: number;
}

/** The speeds offered. Three at least, per `animation-playback`. */
export const SPEEDS: readonly number[] = [0.25, 0.5, 1, 2] as const;
export const NORMAL_SPEED = 1;

export interface Transport {
	/** The clip selected, or an empty string when none is. */
	readonly clip: string;
	/** Where in it, as a proportion of its duration. Always within 0–1. */
	readonly position: number;
	readonly playing: boolean;
	readonly loop: boolean;
	readonly speed: number;
}

export const STOPPED: Transport = {
	clip: '',
	position: 0,
	playing: false,
	loop: false,
	speed: NORMAL_SPEED
};

/** A position clamped into the clip, because a transport cannot leave one. */
export function within(position: number): number {
	if (!Number.isFinite(position)) return 0;
	return Math.min(1, Math.max(0, position));
}

/** Select a clip and hold it at its start, paused. Selecting is not playing. */
export function select(transport: Transport, clip: string): Transport {
	if (!clip) return { ...transport, clip: '', position: 0, playing: false };
	if (clip === transport.clip) return transport;
	return { ...transport, clip, position: 0, playing: false };
}

export function play(transport: Transport): Transport {
	return transport.clip ? { ...transport, playing: true } : transport;
}

export function pause(transport: Transport): Transport {
	return { ...transport, playing: false };
}

/** Play when paused, pause when playing — the one control most people use. */
export function toggle(transport: Transport): Transport {
	return transport.playing ? pause(transport) : play(transport);
}

/**
 * Move to a position without changing anything else about the transport.
 *
 * Deterministic by construction: the result depends on the argument and on the
 * clip, never on where the transport happened to be — which is the whole of
 * *"scrubbed to a given position twice from different starting points"*.
 */
export function scrubTo(transport: Transport, position: number): Transport {
	return { ...transport, position: within(position) };
}

export function setLoop(transport: Transport, loop: boolean): Transport {
	return { ...transport, loop };
}

/** A speed from the offered set; anything else leaves the transport alone. */
export function setSpeed(transport: Transport, speed: number): Transport {
	return SPEEDS.includes(speed) ? { ...transport, speed } : transport;
}

/**
 * The transport a moment later, given how long the clip is.
 *
 * Looping wraps; not looping stops at the end and stays there, because a
 * transport that rewound itself would lose the pose somebody was looking at.
 */
export function advanced(transport: Transport, clip: Clip | null, seconds: number): Transport {
	if (!transport.playing || clip === null || clip.duration <= 0) return transport;
	const moved = transport.position + (seconds * transport.speed) / clip.duration;
	if (moved < 1) return { ...transport, position: moved };
	if (transport.loop) return { ...transport, position: moved % 1 };
	return { ...transport, position: 1, playing: false };
}

/** Where the transport is in seconds — what a position readout shows. */
export function secondsAt(transport: Transport, clip: Clip | null): number {
	return clip === null ? 0 : transport.position * clip.duration;
}

/**
 * The clip's own duration, whatever speed it is being played at.
 *
 * A function rather than a field read, so that *"the duration reported SHALL be
 * the clip's own duration"* is answered by one expression the transport cannot
 * influence.
 */
export function durationOf(clip: Clip | null): number {
	return clip?.duration ?? 0;
}

export function clipNamed(clips: readonly Clip[], name: string): Clip | null {
	return clips.find((clip) => clip.name === name) ?? null;
}

/** `0:01.20` — the position readout, the same in every place that shows one. */
export function readout(seconds: number): string {
	const safe = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
	const minutes = Math.floor(safe / 60);
	const rest = safe - minutes * 60;
	return `${minutes}:${rest.toFixed(2).padStart(5, '0')}`;
}

/**
 * The transport an annotation's playback hint restores (D9, `animation-playback`).
 *
 * *"the viewer SHALL select that clip, set it to the recorded position, hold it
 * paused there"* — so `playing` is false, and the clip is only selected when the
 * preview actually carries it. A hint naming a clip this preview lost leaves the
 * transport stopped, which is the rest pose the annotation then opens against.
 */
export function restore(
	clips: readonly Clip[],
	hint: { readonly clip?: string; readonly t?: number } | null
): Transport {
	const named = hint?.clip ? clipNamed(clips, hint.clip) : null;
	if (named === null) return STOPPED;
	return { ...STOPPED, clip: named.name, position: within(hint?.t ?? 0) };
}

/** Whether a recorded hint names a clip this preview does not carry. */
export function clipUnavailable(
	clips: readonly Clip[],
	hint: { readonly clip?: string } | null
): boolean {
	return Boolean(hint?.clip) && clipNamed(clips, hint?.clip as string) === null;
}
