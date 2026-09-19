/**
 * Task 3.2 — sign-in returns the person to where they were going.
 *
 * The requirement is a round trip: an address goes into the sign-in screen and
 * the same address comes back out, through a query parameter anybody can edit.
 * So the suite asserts the round trip *and* what happens when the parameter is
 * not what this application put there — a `next` pointing at another origin is
 * an open redirect, and the fix is that there is no address it can name.
 */

import { describe, expect, it } from 'vitest';
import {
	HOME,
	NEXT_PARAMETER,
	SIGN_IN_PATH,
	currentAddress,
	intendedAddress,
	localAddress,
	signInAddress
} from '../src/lib/session/intent';

const ASSET = '/p/ironwood/a/mech_scout';

function signInFor(address: string): URL {
	return new URL(signInAddress(address), 'https://canon.cyberdynecorp.ai');
}

describe('a deep link through sign-in', () => {
	it('comes back out as the address it went in as', () => {
		expect(intendedAddress(signInFor(ASSET))).toBe(ASSET);
	});

	it('keeps the query the address carried, so a filtered listing reopens filtered', () => {
		const listing = '/p/ironwood/assets?status=blocked&tag=hero';

		expect(intendedAddress(signInFor(listing))).toBe(listing);
	});

	it('is the sign-in address with nothing on it when the person was at the root', () => {
		expect(signInAddress(HOME)).toBe(SIGN_IN_PATH);
		expect(intendedAddress(new URL(SIGN_IN_PATH, 'https://canon.cyberdynecorp.ai'))).toBe(HOME);
	});

	it('names the parameter this application reads, and encodes what it carries', () => {
		const address = signInAddress('/p/iron wood/assets?q=scout');

		expect(address.startsWith(`${SIGN_IN_PATH}?${NEXT_PARAMETER}=`)).toBe(true);
		expect(address).not.toContain(' ');
		expect(intendedAddress(new URL(address, 'https://canon.cyberdynecorp.ai'))).toBe(
			'/p/iron wood/assets?q=scout'
		);
	});
});

describe('an address this application will not return anyone to', () => {
	it.each([
		'https://evil.example/harvest',
		'//evil.example/harvest',
		'/\\evil.example',
		'javascript:alert(1)',
		'p/ironwood/assets',
		'',
		null,
		undefined
	])('refuses %p in favour of the root', (candidate) => {
		expect(localAddress(candidate)).toBe(HOME);
	});

	it('refuses it through the sign-in screen too, not only through the helper', () => {
		const forged = new URL(
			`${SIGN_IN_PATH}?${NEXT_PARAMETER}=https%3A%2F%2Fevil.example`,
			'https://canon.cyberdynecorp.ai'
		);

		expect(intendedAddress(forged)).toBe(HOME);
	});

	it('keeps an ordinary address, which is the only reason any of this is here', () => {
		expect(localAddress(ASSET)).toBe(ASSET);
	});
});

describe('the address a screen is at', () => {
	it('is its path and its query, and nothing of the origin', () => {
		const url = new URL('https://canon.cyberdynecorp.ai/p/ironwood/assets?status=blocked#pinned');

		expect(currentAddress(url)).toBe('/p/ironwood/assets?status=blocked');
	});
});
