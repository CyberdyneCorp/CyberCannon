/**
 * The asset page and the two refusal screens, rendered.
 *
 * The arrangement is decided next door; this is the other half of the same
 * requirements, and it is a different half. *"The page SHALL state that it has
 * no exports rather than omitting the section"* is a claim about a screen, and
 * a component that built seven sections and rendered five of them would satisfy
 * every assertion about the data behind it.
 *
 * Svelte renders these with no DOM and no browser, which is why they can live
 * in the suite `just check` runs constantly.
 */

import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import AssetOverview from '../src/lib/components/AssetOverview.svelte';
import RouteScreen from '../src/lib/components/RouteScreen.svelte';
import { forbidden, notFound } from '../src/lib/route-state';
import type { RouteState } from '../src/lib/route-state';
import { SECTIONS, assetPage } from '../src/lib/asset';
import type { AssetPage } from '../src/lib/asset';
import type { LocationAnswer } from '../src/lib/api';

const PROJECT = 'ironwood';
const ASSET = 'mech_scout';
const SECRET_NAME = 'Project Nightfall Mech';

const DOCUMENT = `# ${ASSET} — Mech Scout

## Concept — authored by art

- **Concept views**: front.png

## Engineering constraints — authored by engineering

- **Triangle budget**: 12000

## Open issues

- **[issue]** on \`barrel\` (rafa@cyberdyne.com): the muzzle socket is missing
`;

const BARE = `# bare — Bare

## Concept — authored by art

_Nothing declared._
`;

function location(label: string, value: string | null) {
	return { label, value: value ?? 'not recorded', recorded: value !== null };
}

function answer(recorded: boolean): LocationAnswer {
	const labels = [
		'directory',
		'source file',
		'latest validated export',
		'validated',
		'engine path',
		'discussion',
		'design document'
	];
	return {
		asset: ASSET,
		name: 'Mech Scout',
		status: 'modeling',
		project: PROJECT,
		locations: labels.map((label) => location(label, recorded ? `recorded/${label}` : null)),
		owners: [{ discipline: 'art', display: 'Rafa', recorded: true, unmapped: false }],
		stale: false,
		notice: ''
	};
}

function built(recorded: boolean): AssetPage {
	return assetPage({
		project: PROJECT,
		locations: answer(recorded),
		document: recorded ? DOCUMENT : BARE,
		validation: null
	});
}

function body(page: AssetPage): string {
	return render(AssetOverview, { props: { page } }).body;
}

describe('the asset page renders every section it has', () => {
	it('renders all seven, whatever the asset records', () => {
		for (const page of [built(true), built(false)]) {
			const rendered = body(page);
			for (const id of SECTIONS) {
				expect(rendered).toContain(`data-section="${id}"`);
			}
		}
	});

	it('shows the constraints, the annotations, the views and the links', () => {
		const rendered = body(built(true));

		expect(rendered).toContain('12000');
		expect(rendered).toContain('the muzzle socket is missing');
		expect(rendered).toContain('front.png');
		expect(rendered).toContain('recorded/engine path');
	});

	it('states the absence of exports rather than omitting the section', () => {
		const rendered = body(built(false));

		expect(rendered).toContain('data-section="exports" data-empty="true"');
		expect(rendered).toContain('no export');
	});

	it('names the project the asset belongs to', () => {
		expect(body(built(true))).toContain(`data-project="${PROJECT}"`);
	});
});

describe('the ways out of the asset page', () => {
	it('offers the model sheet and the 3D viewer by address', () => {
		const rendered = body(built(true));

		expect(rendered).toContain(`href="/p/${PROJECT}/a/${ASSET}?surface=sheet"`);
		expect(rendered).toContain(`href="/p/${PROJECT}/a/${ASSET}?surface=viewer"`);
	});

	it('offers the viewer even for an asset with no validated export', () => {
		// `add-viewer-3d` overrides the assumption the page made before it
		// existed: the viewer opens and *states* that no preview exists and why.
		// A surface that refused to open would replace that sentence with a
		// silent degrade to the overview.
		const rendered = body(built(false));

		expect(rendered).toContain('data-surface="viewer" data-available="true"');
		expect(rendered).toContain(`href="/p/${PROJECT}/a/${ASSET}?surface=viewer"`);
	});

	it('still states why a surface cannot be opened, when one cannot', () => {
		// No surface is currently unavailable, so the rule is exercised over a
		// page built with one — the presentation is the claim, and it has to
		// keep holding for whichever surface acquires the condition next.
		const page = built(true);
		const closed: AssetPage = {
			...page,
			surfaces: page.surfaces.map((entry) =>
				entry.surface === 'viewer'
					? { ...entry, available: false, absence: 'this asset has no preview' }
					: entry
			)
		};

		const rendered = body(closed);

		expect(rendered).toContain('data-surface="viewer" data-available="false"');
		expect(rendered).not.toContain(`href="/p/${PROJECT}/a/${ASSET}?surface=viewer"`);
		expect(rendered).toContain('this asset has no preview');
	});
});

describe('not found and not permitted are different screens', () => {
	function screen(state: RouteState<AssetPage>): string {
		return render(RouteScreen, {
			props: { state, content: undefined as never }
		}).body;
	}

	it('says a non-existent asset does not exist', () => {
		const rendered = screen(notFound('no asset “ghost” is indexed in this project'));

		expect(rendered).toContain('data-state="not-found"');
		expect(rendered).toContain('Not found');
	});

	it('says a refused asset is one they may not read, on a different screen', () => {
		const rendered = screen(forbidden('you are not entitled to read this project'));

		expect(rendered).toContain('data-state="forbidden"');
		expect(rendered).toContain('do not have access');
	});

	it('reveals neither the name nor any content of the asset it refused', () => {
		const rendered = screen(forbidden('you are not entitled to read this project'));

		expect(rendered).not.toContain(SECRET_NAME);
		expect(rendered).not.toContain('12000');
	});
});
