/**
 * What the browser actually puts on screen, rendered.
 *
 * The decisions are tested next door; this is the other half of the same
 * requirements, and it is a different half. *"Each entry SHALL show its name,
 * identifier, status and owners"* and *"both SHALL be visible ... either SHALL
 * be removable without clearing the other"* are claims about a screen, and a
 * screen that renders its rows without the status satisfies every assertion
 * about the data behind it.
 *
 * Svelte renders these server-side with no DOM and no browser, which is why the
 * assertions can live in the suite `just check` runs constantly rather than
 * behind the compose stack. What only a real browser can answer — that the
 * application boots and the address resolves — stays in the Playwright layer.
 */

import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import ActiveFilters from '../src/lib/components/ActiveFilters.svelte';
import AssetListing from '../src/lib/components/AssetListing.svelte';
import SearchForm from '../src/lib/components/SearchForm.svelte';
import type { BrowserAddress } from '../src/lib/address';
import { browserAddress, readBrowserAddress } from '../src/lib/address';
import type { BrowserRow } from '../src/lib/browser';
import { disclosureOf } from '../src/lib/browser';

const PROJECT = 'atlas';

function row(over: Partial<BrowserRow> = {}): BrowserRow {
	return {
		asset: 'mech_scout',
		name: 'Mech Scout',
		status: 'modeling',
		owners: [
			{ discipline: 'art', display: 'Rafa', recorded: true, unmapped: false },
			{ discipline: 'design', display: 'not recorded', recorded: false, unmapped: false }
		],
		disclosure: null,
		...over
	};
}

function listing(rows: readonly BrowserRow[]): string {
	return render(AssetListing, { props: { project: PROJECT, rows } }).body;
}

function filters(address: BrowserAddress): string {
	return render(ActiveFilters, { props: { address } }).body;
}

/** The address behind the one link the rendered markup marks with this attribute. */
function href(body: string, marker: string): string {
	const found = new RegExp(`${marker} href="([^"]+)"`).exec(body);
	if (!found) throw new Error(`no link marked ${marker} in ${body}`);
	return found[1].replaceAll('&amp;', '&');
}

describe('a listing entry shows its state without being opened', () => {
	it('shows the name, the identifier, the status and the owners', () => {
		const body = listing([row()]);

		expect(body).toContain('Mech Scout');
		expect(body).toContain('mech_scout');
		expect(body).toContain('modeling');
		expect(body).toContain('Rafa');
		expect(body).toContain('not recorded');
	});

	it('links each entry by the identifier the specification declares', () => {
		expect(listing([row()])).toContain('href="/p/atlas/a/mech_scout"');
	});

	it('shows a project of mixed statuses as those statuses', () => {
		const body = listing([
			row({ asset: 'a', status: 'concept' }),
			row({ asset: 'b', status: 'blocked' }),
			row({ asset: 'c', status: 'approved' })
		]);

		for (const status of ['concept', 'blocked', 'approved']) {
			expect(body).toContain(`data-status="${status}"`);
		}
	});

	it('renders the rows in the order it was given and adds no ordering of its own', () => {
		const body = listing([row({ asset: 'zulu' }), row({ asset: 'alpha' })]);

		expect(body.indexOf('data-asset="zulu"')).toBeLessThan(body.indexOf('data-asset="alpha"'));
	});
});

describe('how a result matched is on the screen, not only in the data', () => {
	it.each(['alias', 'tag', 'description'])('discloses a %s match', (matched) => {
		const body = listing([row({ disclosure: disclosureOf(matched) })]);

		expect(body).toContain(`data-matched="${matched}"`);
		expect(body).toContain(disclosureOf(matched)?.text ?? 'missing');
	});

	it('marks a result that came only from an unaccepted suggestion', () => {
		const body = listing([row({ disclosure: disclosureOf('suggested_alias') })]);

		expect(body).toContain('data-unaccepted="true"');
		expect(body).toMatch(/unaccepted suggested alias/);
	});

	it('says nothing at all about a result that matched its own identifier', () => {
		expect(listing([row({ disclosure: disclosureOf('exact_id') })])).not.toContain('disclosure');
	});
});

describe('active filters are visible and individually removable', () => {
	const address: BrowserAddress = {
		project: PROJECT,
		query: 'scout',
		filters: { status: 'blocked', owner: 'rafa' },
		page: null
	};

	it('shows every active filter', () => {
		const body = filters(address);

		expect(body).toContain('status: blocked');
		expect(body).toContain('owner: rafa');
	});

	it('removes either one without clearing the other', () => {
		const body = filters(address);

		expect(body).toContain('href="/p/atlas/assets?q=scout&amp;owner=rafa"');
		expect(body).toContain('href="/p/atlas/assets?q=scout&amp;status=blocked"');
	});

	it('offers to clear them all, keeping what was searched for', () => {
		expect(filters(address)).toContain('href="/p/atlas/assets?q=scout"');
	});

	it('shows nothing when no filter is active', () => {
		expect(filters({ ...address, filters: {} }).trim()).not.toContain('Remove');
	});

	it('leaves the other filter applied when one is followed to be removed', () => {
		const followed = href(filters(address), 'data-removes="status"');

		const reopened = readBrowserAddress(PROJECT, new URL(followed, 'https://canon.example'));

		expect(reopened.filters).toEqual({ owner: 'rafa' });
		expect(reopened.query).toBe('scout');
	});

	it('shows the same filters to whoever opens the address next', () => {
		const shared = browserAddress(address);

		const reopened = readBrowserAddress(PROJECT, new URL(shared, 'https://canon.example'));

		expect(filters(reopened)).toBe(filters(address));
	});
});

describe('the query is typed into the address, filters included', () => {
	it('carries the active filters so searching does not silently widen the screen', () => {
		const body = render(SearchForm, {
			props: {
				address: { project: PROJECT, query: 'scout', filters: { tag: 'mech' }, page: null }
			}
		}).body;

		expect(body).toContain('action="/p/atlas/assets"');
		expect(body).toContain('value="scout"');
		expect(body).toContain('name="tag"');
		expect(body).toContain('value="mech"');
	});
});
