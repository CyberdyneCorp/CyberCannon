/**
 * D7 and 6.6 — the addresses this application can produce, and the one write.
 *
 * *"A test enumerates the addresses the web surface can produce for an asset
 * and asserts none resolves to a working export path."* The backend has the
 * other half of that check over its own route table
 * (`tests/unit/test_http_viewer.py`); this is the half that catches the
 * `fetch` somebody adds to the client, which is the way the rule would
 * realistically be broken.
 *
 * Every asset-scoped call the client can make is driven against a recording
 * `fetch`, so the enumeration is of what the client *does* rather than of what
 * somebody remembered to list.
 */

import { describe, expect, it } from 'vitest';
import { CanonApi, CanonClient, annotationGateway } from '../src/lib/api';
import { QueryCache } from '../src/lib/api/cache';
import { partAnchor } from '../src/lib/annotation';

const BASE = 'https://canon.example';
const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const ANNOTATION = 'an_1';
const EXPORT = 'characters/mech_scout/exports/mech_scout.glb';
const PART = 'SM_MechScout_Pauldron_L';

/** What a route serving a working export would have to be spelled with. */
const EXPORT_TOKENS = ['/exports/', '.glb', '.fbx', '.obj', '.gltf', '/mesh', '/source'];

function recording() {
	const urls: string[] = [];
	const bodies: unknown[] = [];
	const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
		urls.push(String(input));
		bodies.push(init?.body ? JSON.parse(String(init.body)) : null);
		return new Response(JSON.stringify({ version: 'v1', data: {} }), {
			status: 200,
			headers: { 'Content-Type': 'application/json' }
		});
	}) as typeof globalThis.fetch;
	return { urls, bodies, fetcher };
}

describe('D7 — no address the web surface produces resolves to a working export', () => {
	it('asks for a preview, never for the export it was derived from', async () => {
		const { urls, fetcher } = recording();
		const client = new CanonClient({ baseUrl: BASE, fetch: fetcher });

		await client.readPreview(PROJECT, ASSET);
		await client.readPreviewContent(PROJECT, ASSET);
		await client.readAnchorResolutions(PROJECT, ASSET);

		expect(urls.every((url) => url.includes('/preview'))).toBe(true);
		expect(urls.some((url) => url.includes(EXPORT))).toBe(false);
	});

	it('produces no export-shaped address for an asset, across every read it has', async () => {
		const { urls, fetcher } = recording();
		const client = new CanonClient({ baseUrl: BASE, fetch: fetcher });

		await client.readAsset(PROJECT, ASSET);
		await client.readBriefing(PROJECT, ASSET);
		await client.readLocations(PROJECT, ASSET);
		await client.listAnnotations(PROJECT, ASSET);
		await client.readPreview(PROJECT, ASSET);
		await client.readPreviewContent(PROJECT, ASSET);
		await client.readAnchorResolutions(PROJECT, ASSET);

		const offenders = urls.filter((url) =>
			EXPORT_TOKENS.some((token) => url.toLowerCase().includes(token))
		);
		expect(offenders).toEqual([]);
	});

	it('is not vacuous: the one call that names an export names it as a parameter', async () => {
		// `/validations?export=...` runs the validator over a path *in the
		// repository* and answers a verdict. No byte of the export reaches the
		// caller, which is exactly the distinction D7 draws — and it is the one
		// place the word appears, so the assertion above is checking something.
		const { urls, fetcher } = recording();
		const client = new CanonClient({ baseUrl: BASE, fetch: fetcher });

		await client.validate(PROJECT, EXPORT);

		expect(urls[0]).toContain('/validations?');
		expect(urls[0]).not.toContain('/assets/mech_scout/exports');
	});
});

describe('6.6 — re-anchoring goes through the write surface, once', () => {
	function anApi() {
		const { urls, bodies, fetcher } = recording();
		const cache = new QueryCache(() => 0);
		return {
			urls,
			bodies,
			cache,
			api: new CanonApi({ baseUrl: BASE, fetch: fetcher, cache })
		};
	}

	it('posts the chosen part to the annotation’s own re-anchor address', async () => {
		const { urls, bodies, api } = anApi();

		await annotationGateway(api).reanchor(PROJECT, ASSET, ANNOTATION, {
			anchor: partAnchor(PART)
		});

		expect(urls[0]).toContain(`/annotations/${ANNOTATION}/reanchor`);
		expect(bodies[0]).toMatchObject({ anchor: { part: PART } });
	});

	it('is a different address from a move, because it is a different operation', async () => {
		const { urls, api } = anApi();
		const gateway = annotationGateway(api);

		await gateway.move(PROJECT, ASSET, ANNOTATION, { anchor: partAnchor(PART) });
		await gateway.reanchor(PROJECT, ASSET, ANNOTATION, { anchor: partAnchor(PART) });

		expect(urls[0]).not.toBe(urls[1]);
	});

	it('forgets the threads and the resolutions it made untrue', async () => {
		const { api, cache } = anApi();
		await api.annotations(PROJECT, ASSET);
		await api.anchorResolutions(PROJECT, ASSET);
		await api.preview(PROJECT, ASSET);

		await annotationGateway(api).reanchor(PROJECT, ASSET, ANNOTATION, {
			anchor: partAnchor(PART)
		});

		expect(cache.has(`annotations/${PROJECT}/${ASSET}/rev=`)).toBe(false);
		expect(cache.has(`resolutions/${PROJECT}/${ASSET}`)).toBe(false);
		expect(cache.has(`preview/${PROJECT}/${ASSET}`)).toBe(true);
	});
});
