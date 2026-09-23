/**
 * Task 7.2 — the link list on a screen, and what each state says there.
 *
 * `document-platform` makes claims about what a person sees, so they are tested
 * against Svelte's server renderer rather than against a value:
 *
 * * a readable link reads as a **document** — its current title and summary;
 * * an unresolvable one is shown with its **address**, marked with the state
 *   that says why, and is still openable;
 * * a **forbidden** one discloses no title and no summary;
 * * each entry states its **scope**;
 * * the only actions are **open** and **unlink** — there is no editor;
 * * the **guidance** naming both destinations is on the screen where the choice
 *   is made.
 */

import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import DocumentLinks from '../src/lib/components/DocumentLinks.svelte';
import type { DocumentListing, LinkedDocument } from '../src/lib/api';

const RATIONALE = 'd_rationale';
const SECRET = 'd_secret';

const GUIDANCE =
	'A statement that constrains art, constrains code, or can be checked by the ' +
	"validator belongs in the asset's specification. Rationale, exploration and " +
	'discussion belong in the linked document.';

function link(over: Partial<LinkedDocument> = {}): LinkedDocument {
	return {
		document: RATIONALE,
		workspace: 'w_production',
		url: 'https://arche.invalid/w/w_production/d/d_rationale',
		linked_by: 'auth|rafa',
		linked_at: '2026-09-22T09:00:00+00:00',
		scope: 'asset',
		state: 'readable',
		resolved: true,
		title: 'mech_scout — design rationale',
		summary: 'The scout reads as a courier rather than as a brawler.',
		display_title: 'mech_scout — design rationale',
		resolved_at: '2026-09-22T09:01:00+00:00',
		actions: ['open', 'unlink'],
		...over
	};
}

function listing(over: Partial<DocumentListing> = {}): DocumentListing {
	return {
		project: 'cyberdyne-game',
		asset: 'mech_scout',
		path: 'characters/mech_scout/asset.yaml',
		available: true,
		reason: null,
		guidance:
			"A statement that constrains art, constrains code, or can be checked by the validator belongs in the asset's specification. Rationale, exploration and discussion belong in the linked document.",
		links: [link()],
		...over
	};
}

function screen(value: DocumentListing): string {
	return render(DocumentLinks, { props: { listing: value } }).body;
}

describe('a link reads as a document', () => {
	it('shows the current title and summary', () => {
		const body = screen(listing());

		expect(body).toContain('mech_scout — design rationale');
		expect(body).toContain('The scout reads as a courier');
	});

	it('states the scope of every entry', () => {
		const body = screen(
			listing({ links: [link(), link({ document: 'd_gdd', scope: 'project' })] })
		);

		expect(body).toContain('data-scope="asset"');
		expect(body).toContain('data-scope="project"');
		expect(body).toContain('Project documents');
	});

	it('offers opening and removing, and no third action', () => {
		const body = screen(listing());

		expect(body).toContain('Remove link');
		expect(body).not.toMatch(/edit|editor|save/i);
	});

	it('shows the placement guidance where the choice is made', () => {
		const body = screen(listing());

		expect(body).toContain(GUIDANCE);
	});
});

describe('an unresolved link is marked by its state', () => {
	it('shows a forbidden link with no title and no summary', () => {
		const address = 'https://arche.invalid/w/w_production/d/d_secret';
		const body = screen(
			listing({
				links: [
					link({
						document: SECRET,
						state: 'forbidden',
						resolved: false,
						title: '',
						summary: '',
						display_title: address
					})
				]
			})
		);

		expect(body).toContain('not accessible to you');
		expect(body).toContain(address);
		expect(body).not.toContain('design rationale');
	});

	it('distinguishes unreachable from gone', () => {
		const unreachable = screen(
			listing({ links: [link({ state: 'unreachable', resolved: false })] })
		);
		const missing = screen(listing({ links: [link({ state: 'missing', resolved: false })] }));

		expect(unreachable).toContain('temporarily unresolvable');
		expect(missing).toContain('no longer exists');
		expect(unreachable).not.toContain('no longer exists');
	});

	it('keeps an unresolvable link openable', () => {
		const body = screen(listing({ links: [link({ state: 'unreachable', resolved: false })] }));

		expect(body).toContain('href="https://arche.invalid/w/w_production/d/d_rationale"');
	});

	it('shows the readable link resolved beside a forbidden one', () => {
		const body = screen(
			listing({
				links: [
					link(),
					link({ document: SECRET, state: 'forbidden', resolved: false, title: '', summary: '' })
				]
			})
		);

		expect(body).toContain('mech_scout — design rationale');
		expect(body).toContain('not accessible to you');
	});
});

describe('the integration degrades to absent', () => {
	it('says the platform is unavailable and names the reason', () => {
		const body = screen(
			listing({
				available: false,
				reason: 'unconfigured',
				links: [
					link({
						state: 'unreachable',
						resolved: false,
						title: '',
						summary: '',
						display_title: 'https://arche.invalid/w/w_production/d/d_rationale'
					})
				]
			})
		);

		expect(body).toContain('data-reason="unconfigured"');
		expect(body).toContain('unconfigured');
		expect(body).toContain('https://arche.invalid/w/w_production/d/d_rationale');
	});

	it('says so plainly when nothing is linked', () => {
		const body = screen(listing({ links: [] }));

		expect(body).toContain('No document is linked to this asset.');
	});
});
