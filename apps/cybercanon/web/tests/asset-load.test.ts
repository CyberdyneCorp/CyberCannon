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
import type {
	ApiResult,
	DocumentListing,
	Failure,
	LensedSpec,
	LocationAnswer,
	ValidationOutcome
} from '../src/lib/api';
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
	documents?: ApiResult<DocumentListing>;
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
		async annotations() {
			asked.push('annotations');
			return ok({
				project: PROJECT,
				asset: ASSET,
				path: 'assets/mech_scout/asset.yaml',
				revision: 'rev-1',
				annotations: [],
				hidden: 0,
				orphans: [],
				view_names: [],
				actor: 'auth|rafa',
				may_promote: false
			});
		},
		async documents() {
			asked.push('documents');
			return (
				options.documents ??
				ok({
					project: PROJECT,
					asset: ASSET,
					path: 'assets/mech_scout/asset.yaml',
					available: true,
					reason: null,
					guidance:
						"Checkable statements belong in the asset's specification; rationale belongs in the linked document.",
					links: [
						{
							document: 'd_rationale',
							workspace: 'w_production',
							url: 'https://arche.invalid/w/w_production/d/d_rationale',
							linked_by: 'auth|rafa',
							linked_at: '2026-09-22T09:00:00+00:00',
							scope: 'asset' as const,
							state: 'readable' as const,
							resolved: true,
							title: 'mech_scout — design rationale',
							summary: 'Why the scout reads as a courier.',
							display_title: 'mech_scout — design rationale',
							resolved_at: '2026-09-22T09:01:00+00:00',
							actions: ['open', 'unlink']
						}
					]
				})
			);
		},
		async preview() {
			asked.push('preview');
			return ok({
				project: PROJECT,
				asset: ASSET,
				path: 'assets/mech_scout/asset.yaml',
				revision: 'rev-1',
				preview: {
					key: 'previews/mech_scout.glb',
					source_export: EXPORT,
					size_bytes: 4,
					content_type: 'model/gltf-binary'
				},
				source_export: EXPORT,
				latest_validated_export: EXPORT,
				derived_from_latest: true,
				counts: { triangles: 14310, objects: 3, materials: 2 },
				parts: ['SM_MechScout_Shoulder_L'],
				clips: [],
				coverage: { states: [], unclaimed: [] },
				absent: null,
				reason: null
			});
		},
		async previewContent() {
			asked.push('preview-content');
			return ok({
				asset: ASSET,
				preview: 'previews/mech_scout.glb',
				source_export: EXPORT,
				content_type: 'model/gltf-binary',
				size_bytes: 4,
				content: 'Z2xURg=='
			});
		},
		async anchorResolutions() {
			asked.push('resolutions');
			return ok({
				project: PROJECT,
				asset: ASSET,
				export: EXPORT,
				revision: 'rev-1',
				orphaned: 2,
				resolutions: []
			});
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

	it('opens the viewer for an asset with no validated export', async () => {
		// The override `add-viewer-3d` makes: the viewer is the surface that
		// *states* why there is no preview, so it has to open in order to say so.
		const { reads } = surface({ locations: ok(BARE_ANSWER), document: BARE });

		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=viewer'));

		expect(screen.address.surface).toBe('viewer');
		expect(screen.state.kind).toBe('content');
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


describe('what the route reads for the 3D viewer, and when', () => {
	it('reads the descriptor, the orphan count and the bytes when the viewer is opened', async () => {
		const { asked, reads } = surface({});

		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=viewer'));

		expect(asked).toContain('preview');
		expect(asked).toContain('resolutions');
		expect(asked).toContain('preview-content');
		expect(screen.viewer?.descriptor?.source_export).toBe(EXPORT);
		expect(screen.viewer?.resolutions?.orphaned).toBe(2);
		expect(screen.viewer?.bytes?.byteLength).toBe(4);
	});

	it('reads the threads too, because the viewer lists them (D11)', async () => {
		const { asked, reads } = surface({});

		await assetScreen(reads, PROJECT, ASSET, address('?surface=viewer'));

		expect(asked).toContain('annotations');
	});

	it('leaves the preview’s bytes alone during server rendering', async () => {
		// The descriptor and the orphan count are still read — they are what the
		// page *states* — and the one expensive read is the one only a browser
		// can use.
		const { asked, reads } = surface({});

		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=viewer'), {
			previewBytes: false
		});

		expect(asked).toContain('preview');
		expect(asked).not.toContain('preview-content');
		expect(screen.viewer?.bytes).toBeNull();
		expect(screen.viewer?.descriptor).not.toBeNull();
	});

	it('asks for none of it on a surface that shows no preview', async () => {
		const { asked, reads } = surface({});

		await assetScreen(reads, PROJECT, ASSET, address('?surface=sheet'));

		expect(asked).not.toContain('preview');
		expect(asked).not.toContain('resolutions');
		expect(asked).toContain('annotations');
	});
});

describe('reference images for the model sheet', () => {
	function references(failSide = false) {
		const { asked, reads: base } = surface({});
		const reads = {
			...base,
			async annotations() {
				asked.push('annotations');
				return ok({
					project: PROJECT, asset: ASSET, path: 'assets/mech_scout/asset.yaml',
					revision: 'rev-1', annotations: [], hidden: 0, orphans: [],
					view_names: ['concept/front.png', 'front', 'side'], actor: 'auth|rafa',
					may_promote: false
				});
			},
			async viewHistory(_project: string, _asset: string, slot: string) {
				asked.push(`history:${slot}`);
				return ok({
					asset: ASSET, slot, path: `assets/mech_scout/concept/${slot}.png`,
					removed: false,
					revisions: [{ revision: 'rev-1', current: true, removed: false }]
				});
			},
			async viewRevision(_project: string, _asset: string, slot: string) {
				asked.push(`image:${slot}`);
				return failSide && slot === 'side'
					? refusal('unavailable', 'image read failed')
					: ok({ asset: ASSET, slot, revision: 'rev-1', content: 'cG5n' });
			}
		};
		return { asked, reads };
	}

	it('loads one image per slot and keeps a failed image local to its card', async () => {
		const { asked, reads } = references(true);
		const screen = await assetScreen(reads, PROJECT, ASSET, address('?surface=sheet'));

		expect(asked.filter((call) => call === 'history:front')).toHaveLength(1);
		expect(screen.sheetImages?.front.source).toBe('data:image/png;base64,cG5n');
		expect(screen.sheetImages?.side.source).toBeNull();
		expect(screen.sheetImages?.side.reason).toContain('could not be loaded');
		expect(screen.state.kind).toBe('content');
	});

	it('does not download references for other surfaces or server rendering', async () => {
		for (const query of ['', '?surface=viewer', '?surface=sheet']) {
			const { asked, reads } = references();
			await assetScreen(reads, PROJECT, ASSET, address(query), { viewImages: false });
			expect(asked.some((call) => call.startsWith('history:') || call.startsWith('image:'))).toBe(false);
		}
		const { asked, reads } = references();
		await assetScreen(reads, PROJECT, ASSET, address());
		expect(asked.some((call) => call.startsWith('history:'))).toBe(false);
	});
});


describe("the asset's linked documents, and what happens when they cannot be read", () => {
	it('reads the link list and carries it onto the screen', async () => {
		const { asked, reads } = surface({});

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(asked).toContain('documents');
		expect(screen.documents?.links.map((link) => link.document)).toEqual(['d_rationale']);
	});

	it('does not fail the page when the link list cannot be read at all', async () => {
		const { reads } = surface({
			documents: refusal('unavailable', 'the document platform did not answer')
		});

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(screen.state.kind).toBe('content');
		expect(dataOf(screen.state)?.name).toBe('Mech Scout');
		expect(screen.documents).toBeNull();
	});

	it('carries the unavailability reason rather than dropping the links', async () => {
		const { reads } = surface({
			documents: ok({
				project: PROJECT,
				asset: ASSET,
				path: 'assets/mech_scout/asset.yaml',
				available: false,
				reason: 'unconfigured',
				guidance: 'Checkable statements belong in the specification.',
				links: [
					{
						document: 'd_rationale',
						workspace: 'w_production',
						url: 'https://arche.invalid/w/w_production/d/d_rationale',
						linked_by: 'auth|rafa',
						linked_at: '2026-09-22T09:00:00+00:00',
						scope: 'asset' as const,
						state: 'unreachable' as const,
						resolved: false,
						title: '',
						summary: '',
						display_title: 'https://arche.invalid/w/w_production/d/d_rationale',
						resolved_at: '',
						actions: ['open', 'unlink']
					}
				]
			})
		});

		const screen = await assetScreen(reads, PROJECT, ASSET, address());

		expect(screen.state.kind).toBe('content');
		expect(screen.documents?.reason).toBe('unconfigured');
		expect(screen.documents?.links[0].display_title).toContain('https://');
	});
});
