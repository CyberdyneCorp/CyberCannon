/**
 * Tasks 6.1 and 6.2 — the art director's pass, resolved to a route state.
 *
 * The queue's *order* is the domain's and is checked there; what is checked
 * here is the screen: which of the closed states it is, what the filters do to
 * the address, and that a specification the queue could not read is disclosed
 * rather than quietly dropped. A pass that omitted a broken file would tell an
 * art director the project is clean, which is the one thing a pass over open
 * work must not do.
 */

import { describe, expect, it } from 'vitest';
import {
	NOTHING_MATCHED,
	NOTHING_OPEN,
	triageAddress,
	triageLink,
	triageScreen
} from '../src/lib/triage';
import type { ApiResult, TriageEntry, TriageQueue } from '../src/lib/api';

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';

function anEntry(id: string, over: Partial<TriageEntry> = {}): TriageEntry {
	return {
		asset: ASSET,
		kind: 'art-direction',
		same_kind_on_asset: 1,
		same_kind_in_project: 1,
		replies: 0,
		age_seconds: 0,
		discipline_owner: null,
		annotation: {
			id,
			kind: 'art-direction',
			author: 'auth|rafa',
			via: null,
			attribution: 'auth|rafa',
			text: 'the pauldron reads as a backpack',
			state: 'open',
			anchor: { view: 'front', u: 0.2, v: 0.2, durable_key: 'front' },
			anchor_state: 'carried',
			authored_against: null,
			created_at: null,
			edited_at: null,
			moved_by: null,
			moved_at: null,
			closed_by: null,
			closed_at: null,
			closing_text: null,
			replies: [],
			strokes: [],
			exits: ['promote', 'resolve']
		},
		...over
	};
}

function answering(queue: TriageQueue): { triage: () => Promise<ApiResult<TriageQueue>> } {
	return { triage: async () => ({ ok: true, data: queue, freshness: null }) };
}

function aQueue(over: Partial<TriageQueue> = {}): TriageQueue {
	return { project: PROJECT, entries: [anEntry('an_1')], unreadable: [], ...over };
}

const NO_FILTERS = { project: PROJECT, kind: '', asset: '', owner: '' };

describe('the address carries the pass’s filters (D3)', () => {
	it('reads the three filters off a URL', () => {
		const url = new URL('https://canon.example/p/ironwood/triage?kind=technical&asset=mule');

		expect(triageAddress(PROJECT, url)).toEqual({
			project: PROJECT,
			kind: 'technical',
			asset: 'mule',
			owner: ''
		});
	});

	it('writes them back, so a pass is a link somebody can send', () => {
		expect(triageLink({ ...NO_FILTERS, kind: 'technical', owner: 'rafa' })).toBe(
			'/p/ironwood/triage?kind=technical&owner=rafa'
		);
	});

	it('addresses the unfiltered pass with no query at all', () => {
		expect(triageLink(NO_FILTERS)).toBe('/p/ironwood/triage');
	});
});

describe('the queue as a screen (6.1)', () => {
	it('is content when there is open work', async () => {
		const state = await triageScreen(answering(aQueue()), NO_FILTERS);

		expect(state.kind).toBe('content');
	});

	it('says the project has nothing open, rather than showing a void', async () => {
		const state = await triageScreen(answering(aQueue({ entries: [] })), NO_FILTERS);

		expect(state.kind).toBe('empty');
		expect(state.kind === 'empty' && state.message).toBe(NOTHING_OPEN);
	});

	it('says the filters excluded everything, which is a different screen', async () => {
		const state = await triageScreen(answering(aQueue({ entries: [] })), {
			...NO_FILTERS,
			kind: 'technical'
		});

		expect(state.kind).toBe('empty');
		expect(state.kind === 'empty' && state.reason).toBe('filters-excluded');
		expect(state.kind === 'empty' && state.message).toBe(NOTHING_MATCHED);
	});

	it('discloses a specification the queue could not read', async () => {
		const state = await triageScreen(
			answering(aQueue({ unreadable: ['props/broken/asset.yaml'] })),
			NO_FILTERS
		);

		expect(state.kind).toBe('degraded');
		expect(state.kind === 'degraded' && state.unavailable[0]).toContain(
			'props/broken/asset.yaml'
		);
	});

	it('sends only the filters that were chosen', async () => {
		const asked: Record<string, unknown>[] = [];
		const api = {
			triage: async (_project: string, filters: Record<string, unknown>) => {
				asked.push(filters);
				return { ok: true as const, data: aQueue(), freshness: null };
			}
		};

		await triageScreen(api, { ...NO_FILTERS, kind: 'design' });

		expect(asked[0]).toEqual({ kind: 'design' });
	});

	it('is the refusal the surface gave when the pass may not be read', async () => {
		const api = {
			triage: async (): Promise<ApiResult<TriageQueue>> => ({
				ok: false,
				failure: {
					kind: 'forbidden',
					identifier: 'policy.refused',
					message: 'you may not read this project',
					subject: PROJECT,
					correlationId: null
				}
			})
		};

		const state = await triageScreen(api, NO_FILTERS);

		expect(state.kind).toBe('forbidden');
	});
});
