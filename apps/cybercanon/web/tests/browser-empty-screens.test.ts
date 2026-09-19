/**
 * Tasks 4.6, 4.7 and 4.8 rendered: the screens nobody builds.
 *
 * `asset-browser` is unusually insistent about these — *"an empty result is a
 * screen, not an absence"*, *"a project with no assets explains what to do"*,
 * *"degraded search is disclosed, never silently narrowed"* — and D6's whole
 * argument is that scattered `{#if}` branches guarantee some of them are never
 * written. So they are asserted the way a person meets them: rendered, with the
 * query in the text and the way out on the screen.
 *
 * `$app/state` is the one thing a component cannot have outside a request, and
 * the sign-in link is the only thing that reads it. It is stubbed with an
 * address, which is what SvelteKit would supply.
 */

import { describe, expect, it, vi } from 'vitest';
import { createRawSnippet } from 'svelte';
import { render } from 'svelte/server';
import type { RouteState } from '../src/lib/route-state';
import { degraded, empty } from '../src/lib/route-state';
import { HOW_AN_ASSET_BEGINS, REBUILDING_NOTE } from '../src/lib/browser';

vi.mock('$app/state', () => ({
	page: { url: new URL('https://canon.example/p/atlas/assets?q=scout&status=blocked') }
}));

const RouteScreen = (await import('../src/lib/components/RouteScreen.svelte')).default;

const nothing = createRawSnippet(() => ({ render: () => '<p>rows</p>' }));
const clear = createRawSnippet(() => ({
	render: () => '<a class="clear" href="/p/atlas/assets?q=scout">Clear the filters</a>'
}));

function screen(state: RouteState<unknown>): string {
	return render(RouteScreen, { props: { state, content: nothing, actions: clear } as never }).body;
}

describe('a search that matched nothing is a screen', () => {
	it('states what was searched for and offers to clear the filters', () => {
		const body = screen(empty('no-results', 'scavenger', 'nothing matched “scavenger”'));

		expect(body).toContain('Nothing matched');
		expect(body).toContain('scavenger');
		expect(body).toContain('Clear the filters');
		expect(body).toContain('data-state="empty"');
	});

	it('is a different screen when the filters are what excluded the matches', () => {
		const body = screen(
			empty('filters-excluded', 'scout', '3 asset(s) matched “scout”, and the active filters excluded every one of them')
		);

		expect(body).toContain('The filters excluded every match');
		expect(body).toContain('3 asset(s) matched');
		expect(body).toContain('Clear the filters');
	});
});

describe('a project with no assets explains what to do', () => {
	it('names how an asset comes to exist rather than showing an empty list', () => {
		const body = screen(empty('no-assets', 'atlas', HOW_AN_ASSET_BEGINS));

		expect(body).toContain('Nothing here yet');
		expect(body).toContain('asset.yaml');
		expect(body).toContain('canon validate');
	});
});

describe('a partial result is never presented as complete', () => {
	it('shows what could be served and states what was unavailable beside it', () => {
		const body = screen(degraded({ rows: [] }, [REBUILDING_NOTE], REBUILDING_NOTE));

		expect(body).toContain('data-state="degraded"');
		expect(body).toContain('rebuilt');
		expect(body).toContain('incomplete');
		expect(body).toContain('<p>rows</p>');
	});
});
