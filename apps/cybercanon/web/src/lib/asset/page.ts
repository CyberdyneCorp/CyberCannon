/**
 * Task 6.1 and 6.2 — the asset page: everything about an asset, in one place.
 *
 * `app-navigation` names what converges here — *"its identity and status, its
 * three owners, its effective constraints, its open annotations, its concept
 * views, its exports with their validation outcome, and its recorded links"* —
 * and it names the rule that shapes the whole module: *"the page SHALL state
 * that it has no exports rather than omitting the section"*.
 *
 * So the section list is **closed and total**. Every asset produces all seven,
 * in the same order, whatever it records; a section with nothing in it carries
 * a sentence saying so and why, and there is no code path that can drop one.
 * That is deliberate and it is the same argument D6 makes about route states: a
 * section rendered by a conditional is a section that disappears exactly when
 * its absence is the information.
 *
 * **Nothing here decides anything about the canon.** The identity, the status,
 * the owners, the locations and the validated export come from `where_is`; the
 * constraints, the annotations and the views come from the one compiled
 * briefing; the verdict comes from the same `validate_export` the command line
 * runs. This module arranges those answers on a page, and it has nowhere to put
 * an opinion about any of them.
 */

import type { ApiResult, LocationAnswer, Owner, ValidationOutcome } from '$lib/api';
import type { Surface } from '$lib/address';
import { assetAddress } from '$lib/address';
import { CONCEPT, CONSTRAINTS, OPEN_ISSUES, entriesOf, sectionNamed, valuesLabelled } from './compiled';
import type { SectionEntry } from './compiled';

/** The seven sections, in the order the page presents them. A closed set. */
export const SECTIONS = [
	'identity',
	'owners',
	'constraints',
	'annotations',
	'views',
	'exports',
	'links'
] as const;
export type SectionId = (typeof SECTIONS)[number];

export const HEADINGS: Readonly<Record<SectionId, string>> = {
	identity: 'Identity and status',
	owners: 'Owners',
	constraints: 'Effective constraints',
	annotations: 'Open annotations',
	views: 'Concept views',
	exports: 'Exports and validation',
	links: 'Recorded links'
};

/**
 * What each section says when it has nothing.
 *
 * Each names the reason as well as the fact, because *"no exports"* on its own
 * reads as a page that failed to load one.
 *
 * The map is total over the section set, which is the point: adding a section
 * without deciding what its emptiness means does not compile. Two entries —
 * identity and owners — describe a case that cannot currently arise, because
 * those two sections are populated from a shape that always carries them (an
 * unrecorded owner is still a line saying so). They are here because totality
 * is what makes the rule enforceable, not because they are expected.
 */
export const ABSENCES: Readonly<Record<SectionId, string>> = {
	identity: 'nothing about this asset’s identity was recorded, which the surface should never answer',
	owners: 'no discipline owner is recorded in this asset’s specification',
	constraints:
		'no engineering constraint is in effect for this asset — neither its own ' +
		'specification nor the project defaults declare one',
	annotations: 'no annotation is open on this asset',
	views: 'no concept view is recorded for this asset',
	exports:
		'no export of this asset has been validated yet, so there is nothing to ' +
		'show here. One appears when an export committed to the repository is ' +
		'validated and the outcome is written beside the specification',
	links: 'no link is recorded for this asset'
};

/** The location labels `where_is` answers with (`lookup_assets.py`). */
export const DIRECTORY = 'directory';
export const SOURCE_FILE = 'source file';
export const VALIDATED_EXPORT = 'latest validated export';
export const VALIDATED_AT = 'validated';
export const LINK_LABELS: readonly string[] = [
	SOURCE_FILE,
	'engine path',
	'discussion',
	'design document'
];

/** The three owners, in the order every surface names them. */
export const DISCIPLINES: readonly string[] = ['art', 'design', 'code'];

export const SURFACE_LABELS: Readonly<Record<Surface, string>> = {
	overview: 'Overview',
	sheet: 'Model sheet',
	viewer: '3D viewer'
};

export const SHEET_EMPTY =
	'This asset has no views recorded, so there is nothing to place a pin on. Its identity, ' +
	'its status and its threads are below.';
/**
 * What the sheet says when the asset has no views.
 *
 * `model-sheet-2d`: *"WHEN its model sheet is opened THEN the sheet SHALL state
 * that the asset has no views AND it SHALL still present the asset's identity
 * and status."* One sentence, in one place, so the screen and the test that
 * checks it cannot drift apart.
 */
export const UNREADABLE_OUTCOME =
	'the recorded export could not be validated at this revision, so its verdict is unknown';

export interface AssetSection {
	readonly id: SectionId;
	readonly heading: string;
	readonly entries: readonly SectionEntry[];
	/** Why there is nothing here, or `null` when there is something. */
	readonly absence: string | null;
}

/** An entry point to a surface this page is the way into (task 6.3). */
export interface SurfaceEntry {
	readonly surface: Surface;
	readonly label: string;
	readonly address: string;
	readonly available: boolean;
	/** Why it cannot be opened, stated rather than hidden, when it cannot. */
	readonly absence: string | null;
}

export interface AssetPage {
	readonly project: string;
	readonly asset: string;
	readonly name: string;
	readonly status: string;
	readonly sections: readonly AssetSection[];
	readonly surfaces: readonly SurfaceEntry[];
	/** The compiled briefing, verbatim, for a reader who wants the whole document. */
	readonly document: string;
}

export interface AssetInput {
	readonly project: string;
	readonly locations: LocationAnswer;
	/** The compiled specification, as the lensed read returned it whole. */
	readonly document: string;
	/** The verdict on the validated export, or `null` when none is recorded. */
	readonly validation: ApiResult<ValidationOutcome> | null;
}

/** The whole page, as data. Seven sections, always, and the ways out of it. */
export function assetPage(input: AssetInput): AssetPage {
	const { locations } = input;
	const views = conceptViews(input.document);
	const sections = SECTIONS.map((id) => sectionOf(id, input, views));
	return {
		project: input.project,
		asset: locations.asset,
		name: locations.name,
		status: locations.status,
		sections,
		surfaces: surfaceEntries(input.project, locations.asset, views.length > 0, hasExport(locations)),
		document: input.document
	};
}

/** Which surfaces this asset actually has — what an address may restore (6.4). */
export function availableSurfaces(page: AssetPage): readonly Surface[] {
	return page.surfaces.filter((entry) => entry.available).map((entry) => entry.surface);
}

export function sectionOf(
	id: SectionId,
	input: AssetInput,
	views: readonly string[]
): AssetSection {
	const entries = entriesFor(id, input, views);
	return {
		id,
		heading: HEADINGS[id],
		entries,
		absence: entries.length === 0 ? ABSENCES[id] : null
	};
}

function entriesFor(
	id: SectionId,
	input: AssetInput,
	views: readonly string[]
): readonly SectionEntry[] {
	switch (id) {
		case 'identity':
			return identityEntries(input.project, input.locations);
		case 'owners':
			return ownerEntries(input.locations.owners);
		case 'constraints':
			return entriesOf(sectionNamed(input.document, CONSTRAINTS));
		case 'annotations':
			return entriesOf(sectionNamed(input.document, OPEN_ISSUES));
		case 'views':
			return views.map((view) => ({ label: null, value: view, recorded: true }));
		case 'exports':
			return exportEntries(input);
		case 'links':
			return linkEntries(input.locations);
	}
}

function identityEntries(project: string, locations: LocationAnswer): readonly SectionEntry[] {
	return [
		{ label: 'Identifier', value: locations.asset, recorded: true },
		{ label: 'Name', value: locations.name, recorded: true },
		{ label: 'Status', value: locations.status, recorded: true },
		// `app-navigation`: every screen states the project it belongs to, and the
		// asset page states it twice — in the frame and beside the identifier —
		// because this is the screen from which somebody acts.
		{ label: 'Project', value: project, recorded: true },
		...locationEntries(locations, [DIRECTORY])
	];
}

function ownerEntries(owners: readonly Owner[]): readonly SectionEntry[] {
	return DISCIPLINES.map((discipline) => {
		const owner = owners.find((entry) => entry.discipline === discipline);
		return {
			label: discipline,
			value: owner?.display ?? 'not recorded',
			recorded: Boolean(owner?.recorded),
			...(owner?.unmapped ? { note: 'no git identity is mapped for this owner' } : {})
		};
	});
}

/**
 * The validated export, when it was validated, and what the verdict was.
 *
 * The first two are `where_is`'s answer — the G2 writer puts them in the
 * repository and the index carries them — and the third is the same
 * `validate_export` every other surface runs. A verdict that could not be read
 * is *said*, never inferred: an asset page that quietly showed no verdict would
 * be indistinguishable from one whose export passed.
 */
function exportEntries(input: AssetInput): readonly SectionEntry[] {
	const recorded = locationEntries(input.locations, [VALIDATED_EXPORT, VALIDATED_AT]);
	if (recorded.length === 0) return [];
	return [...recorded, ...verdictEntries(input.validation)];
}

function verdictEntries(
	validation: ApiResult<ValidationOutcome> | null
): readonly SectionEntry[] {
	if (validation === null) return [];
	if (!validation.ok) {
		return [{ label: 'Validation outcome', value: UNREADABLE_OUTCOME, recorded: false }];
	}
	const outcome = validation.data;
	return [
		{ label: 'Validation outcome', value: outcome.outcome, recorded: true },
		{
			label: 'Violations',
			value: String(outcome.violations.length),
			recorded: true
		},
		{
			label: 'Rules not evaluated',
			value: String(outcome.not_evaluated.length),
			recorded: true
		}
	];
}

function linkEntries(locations: LocationAnswer): readonly SectionEntry[] {
	return locationEntries(locations, LINK_LABELS);
}

/**
 * The recorded locations among these labels.
 *
 * An unrecorded location is dropped here rather than rendered as *"not
 * recorded"*, because the section states its own absence when every one of them
 * is missing — and a list of seven *"not recorded"* lines is the noise that
 * makes a person stop reading the one line that says something.
 */
function locationEntries(
	locations: LocationAnswer,
	labels: readonly string[]
): readonly SectionEntry[] {
	return labels
		.map((label) => locations.locations.find((entry) => entry.label === label))
		.filter((entry): entry is NonNullable<typeof entry> => Boolean(entry?.recorded))
		.map((entry) => ({ label: entry.label, value: entry.value, recorded: true }));
}

function conceptViews(document: string): readonly string[] {
	return valuesLabelled(entriesOf(sectionNamed(document, CONCEPT)), 'Concept views');
}

function hasExport(locations: LocationAnswer): boolean {
	return Boolean(locations.locations.find((entry) => entry.label === VALIDATED_EXPORT)?.recorded);
}

/**
 * The entry points the model sheet and the 3D viewer are reached from (6.3).
 *
 * A surface is offered when the asset has what that surface shows — a concept
 * view for the sheet, a validated export for the viewer — and stated as absent
 * when it does not. That is also what makes 6.4's degradation real rather than
 * theoretical: an address naming a surface this asset does not have is an
 * address whose state cannot be restored, and it falls back to the default view
 * saying why.
 */
export function surfaceEntries(
	project: string,
	asset: string,
	hasViews: boolean,
	hasValidatedExport: boolean
): readonly SurfaceEntry[] {
	const available: Readonly<Record<Surface, boolean>> = {
		overview: true,
		// The sheet opens for an asset with no views, and that is
		// `add-model-sheet-2d` overriding an assumption this module made before it
		// existed: *"GIVEN an asset with no views recorded ... THEN the sheet SHALL
		// state that the asset has no views AND it SHALL still present the asset's
		// identity and status."* An annotation anchored to a view that has since
		// gone is still a thread somebody owes an exit, so a sheet that refused to
		// open would be the surface hiding the work that most needs doing.
		sheet: true,
		// The viewer opens for an asset with no preview, and that is
		// `add-viewer-3d` overriding an assumption this module made before it
		// existed — the same override `add-model-sheet-2d` applied to the sheet.
		// *"WHEN the asset is opened in the viewer THEN the viewer SHALL state
		// that no preview exists because no export has been validated AND the
		// asset's specification SHALL remain readable."* A surface that refused
		// to open would replace that sentence with a silent degrade to the
		// overview, which is the one outcome the requirement rules out.
		viewer: true
	};
	const absent: Readonly<Record<Surface, string>> = {
		overview: '',
		// The sheet is never unavailable, so it never has an absence to state. What
		// it says about an asset with no views is said *on the sheet*
		// (:data:`SHEET_EMPTY`), because that is where a person is standing when
		// they need to hear it.
		sheet: '',
		// Like the sheet, the viewer is never unavailable, so it never has an
		// absence to state here. What it says about an asset with no preview is
		// said *in the viewer*, with the reason the descriptor carried.
		viewer: ''
	};
	void hasViews;
	void hasValidatedExport;
	return (Object.keys(available) as Surface[]).map((surface) => ({
		surface,
		label: SURFACE_LABELS[surface],
		address: assetAddress({ project, asset, surface }),
		available: available[surface],
		absence: available[surface] ? null : absent[surface]
	}));
}
