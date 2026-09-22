/**
 * Task 6.1 and 6.2 — what the asset page is, as data.
 *
 * `app-navigation` names the seven things that converge on this page and then
 * names the rule that matters more than any of them: *"the page SHALL state
 * that it has no exports rather than omitting the section"*. So the assertions
 * below come in pairs — a fully populated asset shows each section's content,
 * and an asset that records nothing shows each section's **sentence**. A
 * section that vanished when it was empty would pass the first half of every
 * pair.
 *
 * The compiled briefing is read rather than re-derived: these fixtures are
 * `briefing.py`'s own output shape, because the constraints on this page are
 * the constraints the validator enforces and a second renderer here would be
 * the drift this product exists to prevent.
 */

import { describe, expect, it } from 'vitest';
import {
	ABSENCES,
	SECTIONS,
	SHEET_EMPTY,
	UNREADABLE_OUTCOME,
	assetPage,
	availableSurfaces,
	entriesOf,
	sectionNamed,
	valuesLabelled
} from '../src/lib/asset';
import type { AssetPage, SectionId } from '../src/lib/asset';
import type { ApiResult, LocationAnswer, ValidationOutcome } from '../src/lib/api';

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const EXPORT = 'exports/mech_scout.glb';

const DOCUMENT = `# ${ASSET} — Mech Scout

**Status:** modeling

> Derived file — CyberCanon compiles it from \`asset.yaml\`.

## Concept — authored by art

- **Owner**: rafa@cyberdyne.com
- **Silhouette rule**: readable at twenty metres
- **Concept views**: front.png, three_quarter.png

## Design — authored by design

- **Owner**: dani@cyberdyne.com
- **Role**: scout

## Engineering constraints — authored by engineering

_Effective values: project defaults with the asset's own declarations taking precedence._

- **Triangle budget**: 12000
- **Up axis**: Z

## Open issues

_Open only. A resolved or promoted thread is not context; it is history._

- **[issue]** on \`barrel\` (rafa@cyberdyne.com): the muzzle socket is missing

## Links

- **Source file**: \`assets/mech_scout/mech_scout.blend\`
`;

const BARE_DOCUMENT = `# bare — Bare

**Status:** concept

## Concept — authored by art

_Nothing declared._

## Engineering constraints — authored by engineering

_Nothing declared._

## Open issues

_Nothing declared._
`;

function location(label: string, value: string | null) {
	return { label, value: value ?? 'not recorded', recorded: value !== null };
}

function locations(over: Partial<LocationAnswer> = {}): LocationAnswer {
	return {
		asset: ASSET,
		name: 'Mech Scout',
		status: 'modeling',
		project: PROJECT,
		locations: [
			location('directory', 'assets/mech_scout'),
			location('source file', 'assets/mech_scout/mech_scout.blend'),
			location('latest validated export', EXPORT),
			location('validated', '2026-09-20T10:00:00+00:00'),
			location('engine path', 'Content/Characters/MechScout'),
			location('discussion', 'https://discord.test/thread/12'),
			location('design document', 'https://arche.test/doc/mech-scout')
		],
		owners: [
			{ discipline: 'art', display: 'Rafa', recorded: true, unmapped: false },
			{ discipline: 'design', display: 'dani@cyberdyne.com', recorded: true, unmapped: true },
			{ discipline: 'code', display: 'not recorded', recorded: false, unmapped: false }
		],
		stale: false,
		notice: '',
		...over
	};
}

function nothingRecorded(): LocationAnswer {
	return locations({
		asset: 'bare',
		name: 'Bare',
		status: 'concept',
		locations: [
			location('directory', null),
			location('source file', null),
			location('latest validated export', null),
			location('validated', null),
			location('engine path', null),
			location('discussion', null),
			location('design document', null)
		],
		owners: []
	});
}

const PASSED: ApiResult<ValidationOutcome> = {
	ok: true,
	freshness: null,
	data: {
		asset: ASSET,
		export: EXPORT,
		export_format: 'glb',
		outcome: 'passed',
		violations: [],
		not_evaluated: [],
		passed_rules: ['tri_budget'],
		spec: 'assets/mech_scout/asset.yaml',
		passed: true,
		spec_warnings: []
	}
};

function page(): AssetPage {
	return assetPage({
		project: PROJECT,
		locations: locations(),
		document: DOCUMENT,
		validation: PASSED
	});
}

function section(id: SectionId, built: AssetPage = page()) {
	const found = built.sections.find((entry) => entry.id === id);
	if (!found) throw new Error(`the page dropped the ${id} section`);
	return found;
}

function text(id: SectionId, built: AssetPage = page()): string {
	return section(id, built)
		.entries.map((entry) => `${entry.label ?? ''} ${entry.value}`)
		.join('\n');
}

describe('reading the compiled briefing', () => {
	it('finds a section by the name before its attribution', () => {
		expect(sectionNamed(DOCUMENT, 'Engineering constraints').join('\n')).toContain(
			'Triangle budget'
		);
	});

	it('drops the compiler’s own notes and blank lines', () => {
		const entries = entriesOf(sectionNamed(DOCUMENT, 'Engineering constraints'));

		expect(entries).toHaveLength(2);
		expect(entries[0]).toMatchObject({ label: 'Triangle budget', value: '12000' });
	});

	it('reads a section the document does not carry as empty, not as an error', () => {
		expect(entriesOf(sectionNamed(DOCUMENT, 'Nothing Like This'))).toEqual([]);
	});

	it('reads `_Nothing declared._` as nothing', () => {
		expect(entriesOf(sectionNamed(BARE_DOCUMENT, 'Open issues'))).toEqual([]);
	});

	it('splits a joined field back into its values', () => {
		const concept = entriesOf(sectionNamed(DOCUMENT, 'Concept'));

		expect(valuesLabelled(concept, 'Concept views')).toEqual(['front.png', 'three_quarter.png']);
	});
});

describe('one page, everything recorded', () => {
	it('presents all seven sections, in one fixed order', () => {
		expect(page().sections.map((entry) => entry.id)).toEqual([...SECTIONS]);
	});

	it('states the identity, the status and the project it belongs to', () => {
		const identity = text('identity');

		expect(identity).toContain(ASSET);
		expect(identity).toContain('Mech Scout');
		expect(identity).toContain('modeling');
		expect(identity).toContain(PROJECT);
	});

	it('names all three owners, and marks one with no mapped git identity', () => {
		const owners = section('owners');

		expect(owners.entries.map((entry) => entry.label)).toEqual(['art', 'design', 'code']);
		expect(owners.entries[1].note).toContain('git identity');
		expect(owners.entries[2].recorded).toBe(false);
	});

	it('presents the effective constraints as the compiler resolved them', () => {
		expect(text('constraints')).toContain('12000');
		expect(text('constraints')).toContain('Z');
	});

	it('presents the open annotations, and only those', () => {
		expect(text('annotations')).toContain('the muzzle socket is missing');
	});

	it('presents the concept views', () => {
		expect(section('views').entries.map((entry) => entry.value)).toEqual([
			'front.png',
			'three_quarter.png'
		]);
	});

	it('presents the validated export with its verdict', () => {
		const exports = text('exports');

		expect(exports).toContain(EXPORT);
		expect(exports).toContain('2026-09-20T10:00:00+00:00');
		expect(exports).toContain('passed');
	});

	it('presents the recorded links', () => {
		const links = text('links');

		expect(links).toContain('Content/Characters/MechScout');
		expect(links).toContain('https://discord.test/thread/12');
		expect(links).toContain('https://arche.test/doc/mech-scout');
	});

	it('says a verdict is unknown rather than showing none when it could not be read', () => {
		const built = assetPage({
			project: PROJECT,
			locations: locations(),
			document: DOCUMENT,
			validation: {
				ok: false,
				failure: {
					kind: 'unavailable',
					identifier: 'index.rebuilding',
					message: 'rebuilding',
					subject: null,
					correlationId: null
				}
			}
		});

		expect(text('exports', built)).toContain(UNREADABLE_OUTCOME);
	});
});

describe('absent content is stated, not hidden', () => {
	const bare = assetPage({
		project: PROJECT,
		locations: nothingRecorded(),
		document: BARE_DOCUMENT,
		validation: null
	});

	it('still presents all seven sections', () => {
		expect(bare.sections.map((entry) => entry.id)).toEqual([...SECTIONS]);
	});

	it('states that an asset with no exports has none', () => {
		const exports = section('exports', bare);

		expect(exports.entries).toEqual([]);
		expect(exports.absence).toBe(ABSENCES.exports);
		expect(exports.absence).toContain('no export');
	});

	it('states the absence of annotations, views, constraints and links', () => {
		for (const id of ['annotations', 'views', 'constraints', 'links'] as SectionId[]) {
			expect(section(id, bare).absence).toBe(ABSENCES[id]);
		}
	});

	it('still names the three owners even when none is recorded', () => {
		expect(section('owners', bare).entries).toHaveLength(3);
		expect(section('owners', bare).absence).toBeNull();
	});
});

describe('the surfaces this page is the way into', () => {
	it('offers the model sheet and the 3D viewer for an asset that has both', () => {
		expect(availableSurfaces(page())).toEqual(['overview', 'sheet', 'viewer']);
	});

	it('addresses each surface by the asset’s declared identifier', () => {
		const viewer = page().surfaces.find((entry) => entry.surface === 'viewer');

		expect(viewer?.address).toBe(`/p/${PROJECT}/a/${ASSET}?surface=viewer`);
	});

	it('opens the viewer for an asset with no preview, and lets it say why', () => {
		// `add-viewer-3d` overrides the assumption this module made before it
		// existed, exactly as `add-model-sheet-2d` did for the sheet: *"WHEN the
		// asset is opened in the viewer THEN the viewer SHALL state that no
		// preview exists because no export has been validated AND the asset's
		// specification SHALL remain readable."* A surface that refused to open
		// would replace that sentence with a silent degrade to the overview.
		const bare = assetPage({
			project: PROJECT,
			locations: nothingRecorded(),
			document: BARE_DOCUMENT,
			validation: null
		});

		expect(availableSurfaces(bare)).toEqual(['overview', 'sheet', 'viewer']);
		expect(bare.surfaces.find((entry) => entry.surface === 'viewer')?.absence).toBeNull();
	});

	it('opens the sheet for an asset with no views, and says it has none', () => {
		// `add-model-sheet-2d` overrides the assumption this module made before it
		// existed: the sheet opens, states that the asset has no views, and still
		// presents its identity and status — because an annotation anchored to a
		// view that has gone is still a thread somebody owes an exit.
		const bare = assetPage({
			project: PROJECT,
			locations: nothingRecorded(),
			document: BARE_DOCUMENT,
			validation: null
		});

		expect(availableSurfaces(bare)).toContain('sheet');
		expect(bare.surfaces.find((entry) => entry.surface === 'sheet')?.absence).toBeNull();
		expect(SHEET_EMPTY).toContain('no views');
	});
});
