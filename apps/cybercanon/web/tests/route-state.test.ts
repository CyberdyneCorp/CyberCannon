/**
 * Tasks 1.4 and 2.4 — the closed route-state set (D6) and the outcome mapping.
 *
 * "A route cannot resolve outside it" is two claims, and both are asserted:
 * nothing but the six is a route state, and a screen that handles the six
 * handles everything a route can produce. The second is checked by driving
 * `matchRouteState` over every member and asserting the handler that ran —
 * a seventh member would fail to compile, and a missing handler with it.
 */

import { describe, expect, it } from 'vitest';
import {
	content,
	degraded,
	empty,
	EMPTY_REASONS,
	failed,
	forbidden,
	isRouteState,
	matchRouteState,
	notFound,
	ROUTE_STATES,
	type RouteState
} from '../src/lib/route-state';
import { routeStateFor, kindForStatus, KIND_BY_STATUS } from '../src/lib/api/outcomes';
import { FAILURE_KINDS, type Failure, type FailureKind } from '../src/lib/api/types';
import { screenFor } from '../src/lib/screen';

const EVERY_STATE: readonly RouteState<string>[] = [
	content('data'),
	empty('no-results', 'scout', 'nothing matched'),
	forbidden('not permitted'),
	notFound('no such asset', 'mech_scout'),
	degraded('partial', ['the index is rebuilding'], 'partial'),
	failed('write.conflict', 'it moved', 'abc123')
];

describe('the set is closed', () => {
	it('has exactly six members', () => {
		expect([...ROUTE_STATES]).toEqual([
			'content',
			'empty',
			'forbidden',
			'not-found',
			'degraded',
			'failed'
		]);
	});

	it('is covered by the constructors, one each', () => {
		expect(EVERY_STATE.map((state) => state.kind)).toEqual([...ROUTE_STATES]);
	});

	it.each(EVERY_STATE)('recognises $kind as a route state', (state) => {
		expect(isRouteState(state)).toBe(true);
	});

	it.each([null, undefined, 'content', 42, {}, { kind: 'loading' }, { kind: 'success' }])(
		'refuses %p, which is not one of the six',
		(value) => {
			expect(isRouteState(value)).toBe(false);
		}
	);

	it('makes a screen handle every member', () => {
		const handled = EVERY_STATE.map((state) =>
			matchRouteState<string, string>(state, {
				content: () => 'content',
				empty: () => 'empty',
				forbidden: () => 'forbidden',
				'not-found': () => 'not-found',
				degraded: () => 'degraded',
				failed: () => 'failed'
			})
		);

		expect(handled).toEqual([...ROUTE_STATES]);
	});

	it('names the three reasons a screen can be empty', () => {
		expect([...EMPTY_REASONS]).toEqual(['no-assets', 'no-results', 'filters-excluded']);
	});
});

describe('the outcome vocabulary maps to its intended screen', () => {
	function failure(kind: FailureKind): Failure {
		return { kind, identifier: `x.${kind}`, message: kind, subject: 'atlas', correlationId: 'c1' };
	}

	const EXPECTED: Readonly<Record<FailureKind, string>> = {
		not_found: 'not-found',
		forbidden: 'forbidden',
		unauthenticated: 'forbidden',
		invalid: 'failed',
		conflict: 'failed',
		unavailable: 'degraded'
	};

	it.each(FAILURE_KINDS)('maps %s', (kind) => {
		expect(routeStateFor(failure(kind)).kind).toBe(EXPECTED[kind]);
	});

	it('offers sign-in for an unauthenticated caller, and nothing for a forbidden one', () => {
		const unauthenticated = routeStateFor(failure('unauthenticated'));
		const refused = routeStateFor(failure('forbidden'));

		expect(unauthenticated).toMatchObject({ kind: 'forbidden', remedy: 'sign-in' });
		expect(refused).toMatchObject({ kind: 'forbidden', remedy: 'none' });
	});

	it('names what was unavailable rather than presenting nothing as complete', () => {
		const state = routeStateFor(failure('unavailable'));

		expect(state).toMatchObject({ kind: 'degraded', data: null, unavailable: ['atlas'] });
	});

	it('carries the correlation identifier onto the failed screen', () => {
		expect(routeStateFor(failure('conflict'))).toMatchObject({ correlationId: 'c1' });
	});

	it('reads every status class the surface answers with', () => {
		expect(Object.entries(KIND_BY_STATUS).map(([status]) => Number(status))).toEqual([
			400, 401, 403, 404, 409, 503
		]);
	});

	it('reports a status outside the mapping as unavailable, never as a domain outcome', () => {
		expect(kindForStatus(502)).toBe('unavailable');
		expect(kindForStatus(500)).toBe('unavailable');
	});
});

describe('a successful read becomes content, or degrades when it may be stale', () => {
	it('is content when the working copy is current', () => {
		const state = screenFor({
			ok: true,
			data: 'rows',
			freshness: { revision: 'abc', confirmedAt: 'now', mayBeStale: false }
		});

		expect(state).toEqual(content('rows'));
	});

	it('is degraded, with the data, when it may be stale', () => {
		const state = screenFor({
			ok: true,
			data: 'rows',
			freshness: { revision: 'abc', confirmedAt: 'then', mayBeStale: true }
		});

		expect(state).toMatchObject({ kind: 'degraded', data: 'rows' });
	});

	it('lets the caller decide what emptiness means', () => {
		const state = screenFor(
			{ ok: true, data: 'rows', freshness: null },
			{ emptiness: () => empty('no-assets', 'atlas', 'no assets yet') }
		);

		expect(state).toMatchObject({ kind: 'empty', reason: 'no-assets' });
	});
});
