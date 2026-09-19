/**
 * Task 1.3 — the address scheme (D3): each address resolves to its screen and
 * reloads unchanged.
 *
 * "Reloads unchanged" is round-tripping: build an address from a state, read it
 * back, and get the same state. That is the property `app-navigation` and
 * `asset-browser` actually need — a shared link reopening what the sharer saw,
 * and a filtered listing that is shareable — and it is a property, not a click.
 */

import { describe, expect, it } from 'vitest';
import {
	activeFilters,
	assetAddress,
	browserAddress,
	DEFAULT_SURFACE,
	readAssetAddress,
	readBrowserAddress,
	resolveSurface,
	SURFACES,
	withoutFilter,
	withoutFilters
} from '../src/lib/address';

const ORIGIN = 'https://canon.example';

function reopen(address: string): URL {
	return new URL(address, ORIGIN);
}

describe('an asset address is the project and the declared identifier', () => {
	it('names neither the asset name nor any record identifier', () => {
		const address = assetAddress({ project: 'atlas', asset: 'mech_scout', surface: 'overview' });

		expect(address).toBe('/p/atlas/a/mech_scout');
	});

	it('reopens at the same asset after a reload', () => {
		const url = reopen(assetAddress({ project: 'atlas', asset: 'mech_scout', surface: 'viewer' }));

		const reopened = readAssetAddress('atlas', 'mech_scout', url);

		expect(reopened).toMatchObject({ project: 'atlas', asset: 'mech_scout', surface: 'viewer' });
	});

	it.each(SURFACES)('round-trips the %s surface', (surface) => {
		const url = reopen(assetAddress({ project: 'atlas', asset: 'mech_scout', surface }));

		expect(readAssetAddress('atlas', 'mech_scout', url).surface).toBe(surface);
	});

	it('escapes identifiers that would otherwise change the path', () => {
		const address = assetAddress({ project: 'a/b', asset: 'c d', surface: 'overview' });

		expect(address).toBe('/p/a%2Fb/a/c%20d');
	});
});

describe('the browser address carries the query and the filters', () => {
	const address = {
		project: 'atlas',
		query: 'scout',
		filters: { status: 'in_progress', owner: 'rafa' },
		page: null
	};

	it('round-trips every part', () => {
		const reopened = readBrowserAddress('atlas', reopen(browserAddress(address)));

		expect(reopened).toEqual(address);
	});

	it('is the same address for another person, filters included', () => {
		const shared = browserAddress(address);

		expect(readBrowserAddress('atlas', reopen(shared)).filters).toEqual(address.filters);
	});

	it('lists active filters in the specified order, each removable on its own', () => {
		expect(activeFilters(address)).toEqual([
			{ name: 'status', value: 'in_progress' },
			{ name: 'owner', value: 'rafa' }
		]);

		const withoutStatus = withoutFilter(address, 'status');

		expect(withoutStatus.filters).toEqual({ owner: 'rafa' });
		expect(readBrowserAddress('atlas', reopen(browserAddress(withoutStatus))).filters).toEqual({
			owner: 'rafa'
		});
	});

	it('clears every filter for the empty screen, keeping the query', () => {
		const cleared = withoutFilters(address);

		expect(cleared.filters).toEqual({});
		expect(cleared.query).toBe('scout');
	});

	it('has one spelling when there is nothing to carry', () => {
		expect(browserAddress({ project: 'atlas', query: '', filters: {}, page: null })).toBe(
			'/p/atlas/assets'
		);
	});
});

describe('an unrestorable surface degrades to the default and says why', () => {
	it('degrades a surface the asset no longer has', () => {
		const resolved = resolveSurface('viewer', ['overview']);

		expect(resolved.surface).toBe(DEFAULT_SURFACE);
		expect(resolved.notice).toMatch(/no longer has/);
	});

	it('degrades a surface the application does not have at all', () => {
		const resolved = resolveSurface('hologram');

		expect(resolved.surface).toBe(DEFAULT_SURFACE);
		expect(resolved.notice).toMatch(/does not have/);
	});

	it('says nothing when the address named nothing', () => {
		expect(resolveSurface(null)).toEqual({ surface: DEFAULT_SURFACE, notice: null });
	});
});
