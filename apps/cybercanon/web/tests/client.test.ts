/**
 * Task 2.1 — the typed client, checked against the shapes the surface documents.
 *
 * The bodies below are the ones
 * `libs/cybercanon/adapters/inbound/http/payloads.py` renders and
 * `outcomes.py` wraps, copied field for field. If the surface renames a field,
 * this is where it is noticed — which is the point of a typed client that is
 * hand-written against a documented shape rather than inferred from a response.
 */

import { describe, expect, it } from 'vitest';
import { CanonClient, IDEMPOTENCY_HEADER, readEnvelope } from '../src/lib/api/client';
import { SURFACE_VERSION } from '../src/lib/api/types';

interface Call {
	url: string;
	init: RequestInit;
}

function recording(status: number, body: unknown, headers: Record<string, string> = {}) {
	const calls: Call[] = [];
	const fetcher = (async (url: string | URL, init: RequestInit = {}) => {
		calls.push({ url: String(url), init });
		return new Response(JSON.stringify(body), {
			status,
			headers: { 'Content-Type': 'application/json', ...headers }
		});
	}) as unknown as typeof fetch;
	return { calls, fetcher };
}

function client(fetcher: typeof fetch, token: string | null = 'tok') {
	return new CanonClient({ baseUrl: 'https://canon.example/', fetch: fetcher, token: () => token });
}

const LISTING = {
	version: SURFACE_VERSION,
	revision: 'abc123',
	confirmed_at: '2026-09-19T10:00:00+00:00',
	may_be_stale: false,
	data: {
		items: [
			{
				asset: 'mech_scout',
				name: 'Mech Scout',
				status: 'in_progress',
				owners: [{ discipline: 'art', display: 'rafa', recorded: true, unmapped: false }]
			}
		],
		next_token: null,
		page_size: 25,
		total: 1
	}
};

describe('addresses the versioned surface', () => {
	it('puts the version in the first segment and the filters in the query', async () => {
		const { calls, fetcher } = recording(200, LISTING);

		await client(fetcher).listAssets('atlas', { status: 'in_progress', pageSize: 10 });

		expect(calls[0].url).toBe(
			`https://canon.example/${SURFACE_VERSION}/projects/atlas/assets?status=in_progress&page_size=10`
		);
	});

	it('carries the credential as a bearer token and nothing as a parameter', async () => {
		const { calls, fetcher } = recording(200, LISTING);

		await client(fetcher).listAssets('atlas');

		expect((calls[0].init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
		expect(calls[0].url).not.toContain('token');
	});

	it('carries the idempotency key on a write, and only when one was given', async () => {
		const { calls, fetcher } = recording(200, { version: SURFACE_VERSION, data: {} });
		const api = client(fetcher);

		await api.raiseRequest('atlas', { discipline: 'art' }, { idempotencyKey: 'k-1' });
		await api.raiseRequest('atlas', { discipline: 'art' });

		expect((calls[0].init.headers as Record<string, string>)[IDEMPOTENCY_HEADER]).toBe('k-1');
		expect((calls[1].init.headers as Record<string, string>)[IDEMPOTENCY_HEADER]).toBeUndefined();
	});

	it('escapes an identifier rather than letting it change the address', async () => {
		const { calls, fetcher } = recording(200, { version: SURFACE_VERSION, data: {} });

		await client(fetcher).readAsset('atlas', 'a/b');

		expect(calls[0].url).toContain('/assets/a%2Fb');
	});

	it('reads view revisions with the bearer and escapes slot and revision segments', async () => {
		const { calls, fetcher } = recording(200, { version: SURFACE_VERSION, data: {} });
		const api = client(fetcher);

		await api.readViewHistory('atlas', 'mech_scout', 'front/view');
		await api.readViewRevision('atlas', 'mech_scout', 'front/view', 'rev/1');

		expect(calls.map((call) => call.url)).toEqual([
			`https://canon.example/${SURFACE_VERSION}/projects/atlas/assets/mech_scout/views/front%2Fview/revisions`,
			`https://canon.example/${SURFACE_VERSION}/projects/atlas/assets/mech_scout/views/front%2Fview/revisions/rev%2F1`
		]);
		expect((calls[1].init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
	});
});

describe('reads the envelope the surface writes', () => {
	it('returns the data and the freshness of a successful read', async () => {
		const { fetcher } = recording(200, LISTING);

		const result = await client(fetcher).listAssets('atlas');

		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.data.items[0].asset).toBe('mech_scout');
		expect(result.freshness).toEqual({
			revision: 'abc123',
			confirmedAt: '2026-09-19T10:00:00+00:00',
			mayBeStale: false
		});
	});

	it('reads a refusal as its kind, identifier, message and subject', async () => {
		const body = {
			version: SURFACE_VERSION,
			correlation_id: 'cid',
			error: { id: 'policy.refused', message: 'not permitted', subject: 'atlas' }
		};
		const { fetcher } = recording(403, body, { 'X-Correlation-Id': 'cid' });

		const result = await client(fetcher).listAssets('atlas');

		expect(result).toEqual({
			ok: false,
			failure: {
				kind: 'forbidden',
				identifier: 'policy.refused',
				message: 'not permitted',
				subject: 'atlas',
				correlationId: 'cid'
			}
		});
	});

	it('states no freshness when the surface stated none', () => {
		const result = readEnvelope<unknown>(
			{ status: 200, ok: true, headers: { get: () => null } },
			{ version: SURFACE_VERSION, data: {} }
		);

		expect(result.ok && result.freshness).toBe(null);
	});

	it('reports a body that is not the envelope as unavailable, never as success', () => {
		const result = readEnvelope<unknown>(
			{ status: 502, ok: false, headers: { get: () => null } },
			{}
		);

		expect(result).toMatchObject({
			ok: false,
			failure: { kind: 'unavailable', identifier: 'internal.failure' }
		});
	});
});

describe('the one path outside the version segment', () => {
	const STATUS = {
		version: SURFACE_VERSION,
		data: {
			ready: true,
			projects: [
				{
					project: 'ironwood',
					working_copy: {
						state: 'ready',
						revision: 'abc123',
						last_fetch_at: '2026-09-19T10:00:00+00:00',
						reason: ''
					},
					index: {
						indexed_revision: 'abc123',
						working_copy_revision: 'abc123',
						in_sync: true,
						rebuilding: false
					}
				}
			]
		}
	};

	it('addresses `/status` unversioned, because it describes the deployment', async () => {
		const { calls, fetcher } = recording(200, STATUS);

		await client(fetcher).readStatus();

		expect(calls[0].url).toBe('https://canon.example/status');
	});

	it('carries the credential, because the answer names projects', async () => {
		const { calls, fetcher } = recording(200, STATUS);

		await client(fetcher).readStatus();

		expect(calls[0].init.headers).toMatchObject({ Authorization: 'Bearer tok' });
	});

	it('reads the projects the deployment reported', async () => {
		const { fetcher } = recording(200, STATUS);

		const result = await client(fetcher).readStatus();

		expect(result.ok && result.data.projects[0].project).toBe('ironwood');
	});
});

// --------------------------------------------------------------------------
// Task 4.5 — the annotation, triage and queue operations
// --------------------------------------------------------------------------

const THREAD = {
	version: SURFACE_VERSION,
	data: {
		project: 'atlas',
		asset: 'mech_scout',
		path: 'characters/mech_scout/asset.yaml',
		revision: 'abc123',
		committed: true,
		annotation: { id: 'an_1', kind: 'art-direction', state: 'open' }
	}
};

const BASE = `https://canon.example/${SURFACE_VERSION}/projects/atlas/assets/mech_scout/annotations`;

describe('the annotation surface, addressed by the identifier the spec declares', () => {
	it('lists an asset’s threads, sending the filter it was given and narrowing nothing', async () => {
		const { calls, fetcher } = recording(200, { version: SURFACE_VERSION, data: {} });

		await client(fetcher).listAnnotations('atlas', 'mech_scout', {
			kinds: ['technical', 'design'],
			states: ['open']
		});

		expect(calls[0].url).toBe(`${BASE}?kind=technical%2Cdesign&state=open`);
	});

	it('sends no filter at all when none was chosen', async () => {
		const { calls, fetcher } = recording(200, { version: SURFACE_VERSION, data: {} });

		await client(fetcher).listAnnotations('atlas', 'mech_scout');

		expect(calls[0].url).toBe(BASE);
	});

	it('creates an annotation as one POST carrying the client-generated identifier', async () => {
		const { calls, fetcher } = recording(200, THREAD);

		const outcome = await client(fetcher).createAnnotation('atlas', 'mech_scout', {
			id: 'an_1',
			kind: 'art-direction',
			text: 'the pauldron reads as a backpack',
			anchor: { view: 'front', u: 0.25, v: 0.4 }
		});

		expect(calls[0].url).toBe(BASE);
		expect(calls[0].init.method).toBe('POST');
		expect(JSON.parse(String(calls[0].init.body)).id).toBe('an_1');
		expect(outcome.ok && outcome.data.annotation.id).toBe('an_1');
	});

	it('addresses each thread operation at its own resource', async () => {
		const { calls, fetcher } = recording(200, THREAD);
		const api = client(fetcher);

		await api.replyToAnnotation('atlas', 'mech_scout', 'an_1', { id: 're_1', text: 'agreed' });
		await api.editAnnotation('atlas', 'mech_scout', 'an_1', { text: 'reworded' });
		await api.withdrawAnnotation('atlas', 'mech_scout', 'an_1');
		await api.moveAnnotation('atlas', 'mech_scout', 'an_1', { anchor: {} });
		await api.resolveAnnotation('atlas', 'mech_scout', 'an_1', {});
		await api.reopenAnnotation('atlas', 'mech_scout', 'an_1');
		await api.promoteAnnotation('atlas', 'mech_scout', 'an_1', {
			rule: 'a durable rule',
			destination: 'constraints'
		});

		expect(calls.map((call) => `${call.init.method} ${call.url.replace(BASE, '')}`)).toEqual([
			'POST /an_1/replies',
			'PATCH /an_1',
			'DELETE /an_1',
			'POST /an_1/anchor',
			'POST /an_1/resolution',
			'DELETE /an_1/resolution',
			'POST /an_1/promotion'
		]);
	});

	it('carries the idempotency key on a create, so a retry is quiet (D5)', async () => {
		const { calls, fetcher } = recording(200, THREAD);

		await client(fetcher).createAnnotation('atlas', 'mech_scout', { id: 'an_1' }, {
			idempotencyKey: 'an_1'
		});

		expect((calls[0].init.headers as Record<string, string>)[IDEMPOTENCY_HEADER]).toBe('an_1');
	});

	it('reads the triage queue with the three filters the pass uses', async () => {
		const { calls, fetcher } = recording(200, { version: SURFACE_VERSION, data: {} });

		await client(fetcher).readTriage('atlas', { kind: 'technical', asset: 'mule' });

		expect(calls[0].url).toBe(
			`https://canon.example/${SURFACE_VERSION}/projects/atlas/triage?kind=technical&asset=mule`
		);
	});

	it('reports a refused promotion as the refusal it was, not as a success', async () => {
		const { fetcher } = recording(403, {
			version: SURFACE_VERSION,
			error: {
				kind: 'forbidden',
				id: 'policy.refused',
				message: 'ART_DIRECTOR required',
				subject: 'an_1'
			}
		});

		const outcome = await client(fetcher).promoteAnnotation('atlas', 'mech_scout', 'an_1', {});

		expect(outcome.ok).toBe(false);
		expect(!outcome.ok && outcome.failure.identifier).toBe('policy.refused');
	});
});
