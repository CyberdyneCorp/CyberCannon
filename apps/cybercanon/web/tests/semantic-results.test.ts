/**
 * The two groups on one screen — read off the envelope, and rendered.
 *
 * `semantic-search-delegation` makes four claims about what a person sees, and
 * every one of them is a claim about a screen rather than about a value:
 *
 * * the groups are **labelled**, exact first and approximate after;
 * * each passage **names the document it came from** and is **openable**;
 * * a passage is **not an asset record** — no identifier, no link to one;
 * * when the retrieval service could not answer, the screen **says so** and the
 *   exact results are still there.
 *
 * So the decisions are tested against the envelope reader and the claims about
 * the screen against Svelte's server renderer, with no DOM and no browser.
 */

import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import SemanticResults from '../src/lib/components/SemanticResults.svelte';
import type { ApiResult, Passage, SemanticGroup } from '../src/lib/api';
import { NOTHING_DELEGATED, browserScreen, semanticOf, sourceOf } from '../src/lib/browser';

const RATIONALE = 'd_rationale';

function passage(over: Partial<Passage> = {}): Passage {
	return {
		document: RATIONALE,
		workspace: 'w_production',
		title: 'mech_scout — design rationale',
		source: 'mech_scout — design rationale',
		url: 'https://arche.invalid/w/w_production/d/d_rationale',
		text: 'The scout mech looks scavenged because the faction cannot manufacture plate.',
		provenance: 'semantic',
		...over
	};
}

function group(over: Partial<SemanticGroup> = {}): SemanticGroup {
	return {
		label: 'approximate matches from linked documents',
		approximate: true,
		delegated: true,
		available: true,
		reason: null,
		notice: 'these passages were retrieved approximately from linked documents',
		results: [passage()],
		...over
	};
}

function answered<T>(data: T, beside: Record<string, unknown> = {}): ApiResult<T> {
	return { ok: true, data, freshness: null, beside };
}

function screen(value: SemanticGroup): string {
	return render(SemanticResults, { props: { group: value } }).body;
}

describe('the approximate group is read off the envelope', () => {
	it('reads the group the surface stated beside the page', () => {
		const found = semanticOf(answered({ items: [] }, { semantic: group() }));

		expect(found.results).toHaveLength(1);
		expect(found.delegated).toBe(true);
	});

	it('treats an answer with no group as nothing having been delegated', () => {
		expect(semanticOf(answered({ items: [] }))).toEqual(NOTHING_DELEGATED);
	});

	it('treats a refusal as nothing having been delegated', () => {
		const refused: ApiResult<unknown> = {
			ok: false,
			failure: {
				kind: 'unavailable',
				identifier: 'x',
				message: 'no',
				subject: null,
				correlationId: null
			}
		};

		expect(semanticOf(refused)).toEqual(NOTHING_DELEGATED);
	});

	it('ignores a field that is not a group, rather than rendering nonsense', () => {
		expect(semanticOf(answered({ items: [] }, { semantic: 'yes please' }))).toEqual(
			NOTHING_DELEGATED
		);
	});
});

describe('the group is labelled as approximate and never merged with the exact one', () => {
	it('shows the label and the notice', () => {
		const body = screen(group());

		expect(body).toContain('approximate matches from linked documents');
		expect(body).toContain('retrieved approximately');
	});

	it('renders no group at all when nothing was delegated', () => {
		const body = screen(NOTHING_DELEGATED);

		expect(body).not.toContain('approximate matches');
		expect(body).not.toContain('<section');
	});

	it('names the document each passage came from and links to it', () => {
		const body = screen(group());

		expect(body).toContain('mech_scout — design rationale');
		expect(body).toContain('https://arche.invalid/w/w_production/d/d_rationale');
		expect(body).toContain('semantic');
	});

	it('falls back to the address when a document has no title', () => {
		const untitled = passage({ title: '', source: '' });

		expect(sourceOf(untitled)).toBe(untitled.url);
	});
});

describe('a passage is not an asset record', () => {
	it('carries no asset identifier and no link to an asset page', () => {
		const body = screen(
			group({ results: [passage({ text: 'mech_scout was always meant to read as scavenged' })] })
		);

		expect(body).not.toContain('/assets/mech_scout');
		expect(Object.keys(passage())).not.toContain('asset');
	});
});

describe('an unavailable retrieval service is stated, not hidden', () => {
	it('shows the reason instead of an empty list', () => {
		const body = screen(
			group({
				available: false,
				reason: 'unreachable',
				notice: 'the document platform could not be reached, so only exact results are shown',
				results: []
			})
		);

		expect(body).toContain('could not be reached');
		expect(body).toContain('data-available="false"');
	});

	it('distinguishes the reasons a caller has to tell apart', () => {
		const reasons = ['unconfigured', 'unreachable', 'rejected', 'timed_out'];
		const bodies = reasons.map((reason) =>
			screen(group({ available: false, reason, notice: `it was ${reason}`, results: [] }))
		);

		expect(new Set(bodies).size).toBe(reasons.length);
		reasons.forEach((reason, at) => expect(bodies[at]).toContain(`it was ${reason}`));
	});
});

describe('the browser screen carries the group and discloses an unavailable one', () => {
	const PROJECT = 'atlas';

	function address() {
		return { project: PROJECT, query: 'why does the scout read as scavenged', filters: {}, page: null };
	}

	const HIT = { asset: 'mech_scout', name: 'Mech Scout', matched: 'description' };

	function reads(beside: Record<string, unknown>) {
		return {
			assets: async () =>
				answered({ items: [], next_token: null, page_size: 25, total: 0 }),
			search: async () =>
				answered({ items: [HIT], next_token: null, page_size: 25, total: 1 }, beside),
			locations: async () => {
				throw new Error('a search that answered must not ask for a location');
			}
		};
	}

	it('puts the approximate group on the view beside the exact rows', async () => {
		const state = await browserScreen(
			reads({ semantic: group() }) as never,
			address() as never
		);

		expect(state.kind).toBe('content');
		const view = (state as unknown as { data: { rows: { asset: string }[]; semantic: SemanticGroup } })
			.data;
		expect(view.rows.map((entry) => entry.asset)).toEqual(['mech_scout']);
		expect(view.semantic.results).toHaveLength(1);
	});

	it('states that the semantic half was unavailable and keeps the exact half', async () => {
		const unavailable = group({
			available: false,
			reason: 'unreachable',
			notice: 'the document platform could not be reached, so only exact results are shown',
			results: []
		});

		const state = await browserScreen(
			reads({ semantic: unavailable }) as never,
			address() as never
		);

		expect(JSON.stringify(state)).toContain('could not be reached');
		expect(JSON.stringify(state)).toContain('mech_scout');
	});
});
