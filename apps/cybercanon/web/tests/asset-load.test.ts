/**
 * Tasks 5.4 and 6.4 — what an address to an asset resolves to.
 *
 * Two requirements meet here and they pull in opposite directions, which is why
 * they are tested together:
 *
 * * **an address restores the view it named**, down to which surface was open —
 *   and when it cannot, it *degrades to the default view and says why* rather
 *   than failing;
 * * **an unknown address and a forbidden one are different screens**, and
 *   neither may reveal the name or the content of an asset the person may not
 *   read.
 *
 * The second is asserted as an absence, twice over: the screen carries no data,
 * and the route never asked the surface for the compiled specification of an
 * asset whose first read was refused. A screen cannot leak what was never
 * fetched.
 */

import { describe, expect, it } from 'vitest';
import { assetScreen } from '../src/lib/asset';
import type { AssetPage } from '../src/lib/asset';
import type { ApiResult, Failure, LensedSpec, LocationAnswer, ValidationOutcome } from '../src/lib/api';
import type { RouteState } from '../src/lib/route-state';

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const SECRET_NAME = 'Project Nightfall Mech';
const EXPORT = 'exports/mech_scout.glb';

const DOCUMENT = `# ${ASSET} — Mech Scout

## Concept — authored by art

- **Concept views**: front.png

## Engineering constraints — authored by engineering

- **Triangle budget**: 12000
`;

const BARE = `# bare — Bare

## Concept — authored by art

_Nothing declared._
`;

function location(label: string, value: string | null) {
	return { label, value: value ?? 'not recorded', recorded: value !== null };
}

function answer(over: Partial<LocationAnswer> = {}): LocationAnswer {
	return {
		asset: ASSET,
		name: 'Mech Scout',
		status: 'modeling',
		project: PROJECT,
		locations: [
			location('directory', 'assets/mech_scout'),
			location('source file', null),
			location('latest validated export', EXPORT),
			location('validated', '2026-09-20T10:00:00+00:00'),
			location('engine path', null),
			location('discussion', null),
			location('design document', null)
		],
		owners: [],
		stale: false,
		notice: '',
		...over
	};
}

const BARE_ANSWER = answer({
	asset: 'bare',
	name: 'Bare',
	locations: [
		location('directory', null),
		location('source file', null),
		location('latest validated export', null),
		location('validated', null),
		location('engine path', null),
		location('discussion', null),
		location('design document', null)
	]
});

function ok<T>(data: T): ApiResult<T> {
	return { ok: true, data, freshness: null };
}

function refusal(kind: Failure['kind'], message: string): ApiResult<never> {
	return {
		ok: false,
		failure: { kind, identifier: `asset.${kind}`, message, subject: null, correlationId: null }
	};
}

interface Recorded {
	readonly asked: string[];
	readonly reads: Parameters<typeof assetScreen>[0];
}

function surface(options: {
	locations?: ApiResult<LocationAnswer>;
	spec?: ApiResult<LensedSpec>;
	validation?: ApiResult<ValidationOutcome>;
	document?: string;
}): Recorded {
	const asked: string[] = [];
	const document = options.document ?? DOCUMENT;
	const reads = {
		async locations() {
			asked.push('locations');
			return options.locations ?? ok(answer());
		},
		async asset() {
			asked.push('asset');
			return (
				options.spec ??
				ok({ asset: ASSET, source: 'assets/mech_scout/asset.yaml', lens: null, body: document, full: document, notice: '' })
			);
		},
		async validate(_project: string, exportPath: string) {
			asked.push(`validate:${exportPath}`);
			return (
				options.validation ??
				ok({
					asset: ASSET,
					export: exportPath,
					export_format: 'glb',
					outcome: 'passed',
					violations: [],
					not_evaluated: [],
					passed_rules: [],
					spec: 'assets/mech_scout/asset.yaml',
					passed: true,
					spec_warnings: []
				})
			);
		}
	};
	return { asked, reads: reads as Parameters<typeof assetScreen>[0] };
}

function address(query = ''): URL {
	return new URL(`https://canon.test/p/${PROJECT}/a/${ASSET}${query}`);
}

function dataOf(state: RouteState<AssetPage>): AssetPage | null {
	return state.kind === 'content' || state.kind === 'degraded' ? state.data : null;
}

describe('an address opens the asset it names', () => {
	it('resolves to the page when everything reads', async () => {
		const { reads } = surface({});

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(screen.state.kind).toBe('content');
		expect(dataOf(screen.state)?.asset).toBe(ASSET);
	});

	it('asks for the verdict on the export the repository recorded', async () => {
		const recorded = surface({});

		await assetScreen(recorded.reads, PROJECT, ASSET, address());

		expect(recorded.asked).toContain(`validate:${EXPORT}`);
	});

	it('asks for no verdict when no export has been validated', async () => {
		const recorded = surface({ locations: ok(BARE_ANSWER), document: BARE });

		await assetScreen(recorded.reads, PROJECT, ASSET, address());

		expect(recorded.asked.some((call) => call.startsWith('validate'))).toBe(false);
	});
});

describe('opening an address restores the surface it named', () => {
	it('opens the 3D surface when the address names it and the asset has one', async () => {
		const { reads } = surface({});

		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=viewer'));

		expect(screen.address.surface).toBe('viewer');
		expect(screen.state.kind).toBe('content');
	});

	it('degrades to the default view when the named surface no longer exists', async () => {
		const { reads } = surface({ locations: ok(BARE_ANSWER), document: BARE });

		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=viewer'));

		expect(screen.address.surface).toBe('overview');
		expect(screen.state.kind).toBe('degraded');
	});

	it('tells the person why it degraded', async () => {
		const { reads } = surface({ locations: ok(BARE_ANSWER), document: BARE });

		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=viewer'));

		expect(screen.state.kind === 'degraded' && screen.state.unavailable.join(' ')).toContain(
			'viewer'
		);
	});

	it('degrades a surface this application does not have at all', async () => {
		const { reads } = surface({});

		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=hologram'));

		expect(screen.address.surface).toBe('overview');
		expect(screen.state.kind).toBe('degraded');
	});

	it('shows the asset itself while it says what it could not restore', async () => {
		const { reads } = surface({});

		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=hologram'));

		expect(dataOf(screen.state)?.asset).toBe(ASSET);
	});
});

describe('an unknown address and a forbidden one are different screens', () => {
	it('tells a person that a non-existent asset does not exist', async () => {
		const { reads } = surface({ locations: refusal('not_found', 'no asset “ghost” is indexed') });

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(screen.state.kind).toBe('not-found');
	});

	it('tells a person they do not have access, which is a different state', async () => {
		const { reads } = surface({
			locations: refusal('forbidden', 'you are not entitled to read this project')
		});

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(screen.state).toMatchObject({ kind: 'forbidden', remedy: 'none' });
	});

	it('reveals neither the name nor the content of an asset it refused', async () => {
		const recorded = surface({
			locations: refusal('forbidden', 'you are not entitled to read this project'),
			spec: ok({
				asset: ASSET,
				source: 'x',
				lens: null,
				body: SECRET_NAME,
				full: SECRET_NAME,
				notice: ''
			})
		});

		const screen = await assetScreen(recorded.reads, PROJECT, ASSET, address());

		expect(dataOf(screen.state)).toBeNull();
		expect(JSON.stringify(screen.state)).not.toContain(SECRET_NAME);
		expect(recorded.asked).toEqual(['locations']);
	});

	it('offers sign-in rather than a refusal when the session is what is missing', async () => {
		const { reads } = surface({ locations: refusal('unauthenticated', 'no credential') });

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(screen.state).toMatchObject({ kind: 'forbidden', remedy: 'sign-in' });
	});

	it('degrades rather than failing while the index is being rebuilt', async () => {
		const { reads } = surface({ locations: refusal('unavailable', 'the index is rebuilding') });

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(screen.state.kind).toBe('degraded');
	});
});

describe('what the page discloses beside its content', () => {
	it('states that the answer may be out of date when the surface says so', async () => {
		const { reads } = surface({
			locations: ok(answer({ stale: true, notice: 'the indexed file changed on disk' }))
		});

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(screen.state.kind).toBe('degraded');
		expect(screen.state.kind === 'degraded' && screen.state.unavailable.join(' ')).toContain(
			'changed on disk'
		);
	});
});
