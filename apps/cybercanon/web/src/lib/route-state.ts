/**
 * D6 — empty, error and degraded states are route-level states, not conditionals.
 *
 * Every data-bearing route resolves to exactly one of six things, and a screen
 * is written against that closed set. `asset-browser` and `app-navigation`
 * between them require distinct screens for nothing-matched,
 * filters-excluded-everything, no-assets-yet, not-permitted, not-found,
 * index-rebuilding and delegated-search-unavailable; scattered `{#if}` branches
 * guarantee some of those are never built.
 *
 * The set is closed in two directions:
 *
 * * a route cannot *produce* anything else — the constructors below are the
 *   only way to build one, and :func:`isRouteState` rejects the rest;
 * * a screen cannot *forget* one — :func:`matchRouteState` takes a handler per
 *   kind, so adding a seventh state would stop every screen compiling, which is
 *   the point of a closed set rather than a convention.
 */

export const ROUTE_STATES = [
	'content',
	'empty',
	'forbidden',
	'not-found',
	'degraded',
	'failed'
] as const;

export type RouteStateKind = (typeof ROUTE_STATES)[number];

/** Why a screen has nothing to show — three different screens, not one. */
export const EMPTY_REASONS = ['no-assets', 'no-results', 'filters-excluded'] as const;
export type EmptyReason = (typeof EMPTY_REASONS)[number];

/** What a forbidden screen can offer: signing in, or nothing at all. */
export type Remedy = 'sign-in' | 'none';

export interface Content<T> {
	readonly kind: 'content';
	readonly data: T;
}

export interface Empty {
	readonly kind: 'empty';
	readonly reason: EmptyReason;
	/** What was searched for, so the screen can state it rather than show a void. */
	readonly subject: string;
	readonly message: string;
}

export interface Forbidden {
	readonly kind: 'forbidden';
	readonly message: string;
	/** `sign-in` when the session is the thing that is missing (`web-session`). */
	readonly remedy: Remedy;
}

export interface NotFound {
	readonly kind: 'not-found';
	readonly message: string;
	readonly subject: string | null;
}

export interface Degraded<T> {
	readonly kind: 'degraded';
	/** What could still be served. `null` when nothing could. */
	readonly data: T | null;
	/** What was unavailable, named — never a partial result presented as complete. */
	readonly unavailable: readonly string[];
	readonly message: string;
}

export interface Failed {
	readonly kind: 'failed';
	readonly identifier: string;
	readonly message: string;
	/** The identifier a person quotes in a bug report, when the surface gave one. */
	readonly correlationId: string | null;
}

export type RouteState<T> = Content<T> | Empty | Forbidden | NotFound | Degraded<T> | Failed;

export function content<T>(data: T): Content<T> {
	return { kind: 'content', data };
}

export function empty(reason: EmptyReason, subject: string, message: string): Empty {
	return { kind: 'empty', reason, subject, message };
}

export function forbidden(message: string, remedy: Remedy = 'none'): Forbidden {
	return { kind: 'forbidden', message, remedy };
}

export function notFound(message: string, subject: string | null = null): NotFound {
	return { kind: 'not-found', message, subject };
}

export function degraded<T>(
	data: T | null,
	unavailable: readonly string[],
	message: string
): Degraded<T> {
	return { kind: 'degraded', data, unavailable, message };
}

export function failed(
	identifier: string,
	message: string,
	correlationId: string | null = null
): Failed {
	return { kind: 'failed', identifier, message, correlationId };
}

/** Whether a value is one of the six. Nothing else may reach a screen. */
export function isRouteState(value: unknown): value is RouteState<unknown> {
	if (typeof value !== 'object' || value === null) return false;
	const kind = (value as { kind?: unknown }).kind;
	return typeof kind === 'string' && (ROUTE_STATES as readonly string[]).includes(kind);
}

/** One handler per kind. A missing one is a type error, not a blank screen. */
export type RouteStateHandlers<T, R> = {
	readonly content: (state: Content<T>) => R;
	readonly empty: (state: Empty) => R;
	readonly forbidden: (state: Forbidden) => R;
	readonly 'not-found': (state: NotFound) => R;
	readonly degraded: (state: Degraded<T>) => R;
	readonly failed: (state: Failed) => R;
};

export function matchRouteState<T, R>(
	state: RouteState<T>,
	handlers: RouteStateHandlers<T, R>
): R {
	switch (state.kind) {
		case 'content':
			return handlers.content(state);
		case 'empty':
			return handlers.empty(state);
		case 'forbidden':
			return handlers.forbidden(state);
		case 'not-found':
			return handlers['not-found'](state);
		case 'degraded':
			return handlers.degraded(state);
		case 'failed':
			return handlers.failed(state);
		default:
			return unreachable(state);
	}
}

/** The compile-level omission a seventh state would become. */
function unreachable(state: never): never {
	throw new Error(`route state outside the closed set: ${JSON.stringify(state)}`);
}
