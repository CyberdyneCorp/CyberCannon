/**
 * Task 2.4 — the application is ready with the API down, and says so.
 *
 * Two claims, and they pull in opposite directions on purpose:
 *
 * * readiness is **process-only**. The handler is called with a `fetch` that
 *   throws if anything touches it, and it still answers ready — which is what
 *   keeps an API outage from failing a deploy of the application whose job is
 *   to render that outage;
 * * the page **does not throw**. A load that rejected would be a 500 where the
 *   specification asks for *"a state describing the API as unavailable"*, so
 *   the unreachable case resolves to the degraded member of the closed set.
 */

import { describe, expect, it, vi } from 'vitest';
import { GET } from '../src/routes/readyz/+server';
import { READY } from '../src/lib/readiness';
import { load } from '../src/routes/+page';
import {
	API,
	apiAvailability,
	availabilityState,
	probeApi,
	READINESS_PATH
} from '../src/lib/api/availability';

const BASE = 'https://api.canon.example';

function refusing(): typeof fetch {
	return (async () => {
		throw new TypeError('fetch failed: ECONNREFUSED');
	}) as unknown as typeof fetch;
}

function answering(status = 200): { calls: string[]; fetcher: typeof fetch } {
	const calls: string[] = [];
	const fetcher = (async (url: string | URL) => {
		calls.push(String(url));
		return new Response('{"status":"ready"}', { status });
	}) as unknown as typeof fetch;
	return { calls, fetcher };
}

describe('the readiness of the web application', () => {
	it('answers ready without reaching for anything', async () => {
		const response = await GET({ fetch: refusing() } as never);

		expect(response.status).toBe(200);
		expect(await response.json()).toEqual({ status: READY });
	});

	it('does not call fetch at all', async () => {
		const fetcher = vi.fn();

		await GET({ fetch: fetcher } as never);

		expect(fetcher).not.toHaveBeenCalled();
	});
});

describe('probing the API', () => {
	it('asks the API its own open readiness endpoint', async () => {
		const { calls, fetcher } = answering();

		await probeApi(fetcher, `${BASE}/`);

		expect(calls).toEqual([`${BASE}${READINESS_PATH}`]);
	});

	it('resolves rather than throwing when the API refuses the connection', async () => {
		await expect(probeApi(refusing(), BASE)).resolves.toMatchObject({ reachable: false });
	});

	it('treats a failing response as unreachable', async () => {
		const { fetcher } = answering(503);

		await expect(probeApi(fetcher, BASE)).resolves.toMatchObject({ reachable: false });
	});
});

describe('what the screen is given', () => {
	it('is the degraded state naming the API when it cannot be reached', async () => {
		const state = await apiAvailability(refusing(), BASE);

		expect(state.kind).toBe('degraded');
		expect(state.kind === 'degraded' && state.unavailable).toContain(API);
	});

	it('is content when the API answered', () => {
		expect(availabilityState({ reachable: true, detail: '200' }).kind).toBe('content');
	});

	it('is what the root route loads, with the API down', async () => {
		const loaded = await load({ fetch: refusing() } as never);

		expect(loaded?.state.kind).toBe('degraded');
	});
});
