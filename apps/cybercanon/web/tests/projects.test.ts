/**
 * Task 5.1 and 5.2 — switching project, and what must not come with it.
 *
 * `app-navigation` requires the previous project's listing, filter and search
 * state to be *discarded* rather than applied to the new project, and requires
 * a switch made with an asset open to land on the new project's browser rather
 * than on a missing asset. Both are assertions about an **address**, because
 * D3 is what makes them one decision: the filters, the query, the page and the
 * open asset are the address, so a switch that produces an address carrying
 * none of them cannot carry any of them across.
 *
 * The switcher is rendered here too, because "the project is identified on
 * every screen" is a claim about a screen, and a component that resolved the
 * links correctly and printed none of them would satisfy every assertion about
 * the data behind it.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import { load as loadFrame } from '../src/routes/+layout';
import { SESSION_DEPENDENCY } from '../src/lib/session/dependency';
import { queryCache } from '../src/lib/api/cache';
import { sessionStore } from '../src/lib/session/session';
import { mappedPerson } from './support/credentials';
import ProjectBar from '../src/lib/components/ProjectBar.svelte';
import { entitledProjects, projectChoices, switchedTo } from '../src/lib/projects';
import { assetAddress, browserAddress, readBrowserAddress } from '../src/lib/address';
import type { ApiResult, StatusReport } from '../src/lib/api';

const IRONWOOD = 'ironwood';
const ATLAS = 'atlas';

function reported(...projects: string[]): ApiResult<StatusReport> {
	return {
		ok: true,
		freshness: null,
		data: {
			projects: projects.map((project) => ({
				project,
				working_copy: { state: 'ready', revision: 'abc', last_fetch_at: null, reason: '' },
				index: {
					indexed_revision: 'abc',
					working_copy_revision: 'abc',
					in_sync: true,
					rebuilding: false
				}
			}))
		}
	};
}

describe('switching project discards the previous project’s state', () => {
	it('lands on the new project’s browser with no filter and no query', () => {
		const address = switchedTo(ATLAS);

		expect(address).toBe(`/p/${ATLAS}/assets`);
		expect(address).not.toContain('?');
	});

	it('does not apply a filter that was active in the project being left', () => {
		const before = readBrowserAddress(
			IRONWOOD,
			new URL(`https://canon.test/p/${IRONWOOD}/assets?status=modeling&owner=rafa&q=mech`)
		);
		expect(browserAddress(before)).toContain('status=modeling');

		const after = readBrowserAddress(ATLAS, new URL(`https://canon.test${switchedTo(ATLAS)}`));

		expect(after.filters).toEqual({});
		expect(after.query).toBe('');
		expect(after.page).toBeNull();
	});

	it('takes a person with an asset open to the new project’s browser', () => {
		const open = assetAddress({ project: IRONWOOD, asset: 'mech_scout', surface: 'overview' });
		expect(open).toContain('mech_scout');

		const after = switchedTo(ATLAS);

		expect(after).toBe(`/p/${ATLAS}/assets`);
		expect(after).not.toContain('mech_scout');
	});

	it('discards the page as well, since page 4 of one project is not page 4 of another', () => {
		const paged = readBrowserAddress(
			IRONWOOD,
			new URL(`https://canon.test/p/${IRONWOOD}/assets?page=token4`)
		);
		expect(paged.page).toBe('token4');

		expect(switchedTo(ATLAS)).not.toContain('page');
	});
});

describe('which projects a person may switch to', () => {
	it('is what the surface reported, in the order it reported it', () => {
		expect(entitledProjects(reported(IRONWOOD, ATLAS))).toEqual([IRONWOOD, ATLAS]);
	});

	it('is none when the surface refused, rather than a guess', () => {
		const refused: ApiResult<StatusReport> = {
			ok: false,
			failure: {
				kind: 'forbidden',
				identifier: 'project.forbidden',
				message: 'no',
				subject: null,
				correlationId: null
			}
		};

		expect(entitledProjects(refused)).toEqual([]);
	});

	it('still offers the project being viewed when the report does not name it', () => {
		const choices = projectChoices([ATLAS], IRONWOOD);

		expect(choices.map((choice) => choice.project)).toEqual([IRONWOOD, ATLAS]);
		expect(choices[0].current).toBe(true);
	});

	it('gives every choice the unfiltered address of that project’s browser', () => {
		for (const choice of projectChoices([IRONWOOD, ATLAS], IRONWOOD)) {
			expect(choice.address).toBe(switchedTo(choice.project));
		}
	});
});

describe('the frame states which project is being shown', () => {
	function bar(project: string | null, projects: readonly string[] = []): string {
		return render(ProjectBar, { props: { project, projects } }).body;
	}

	it('identifies the project of the address', () => {
		const body = bar(IRONWOOD);

		expect(body).toContain(`data-project="${IRONWOOD}"`);
		expect(body).toContain(IRONWOOD);
	});

	it('offers the other projects, each by an address that carries nothing across', () => {
		const body = bar(IRONWOOD, [IRONWOOD, ATLAS]);

		expect(body).toContain(`href="/p/${ATLAS}/assets"`);
	});

	it('does not offer the project already open as somewhere to switch to', () => {
		const body = bar(IRONWOOD, [IRONWOOD]);

		expect(body).not.toContain('to-project');
	});

	it('names no project at all outside a project', () => {
		expect(bar(null)).not.toContain('data-project');
	});
});

describe('where the switcher’s projects come from', () => {
	const READY = { ready: true, components: [] };
	const STATUS = {
		data: {
			projects: [
				{
					project: IRONWOOD,
					working_copy: { state: 'ready', revision: 'a', last_fetch_at: null, reason: '' },
					index: {
						indexed_revision: 'a',
						working_copy_revision: 'a',
						in_sync: true,
						rebuilding: false
					}
				}
			]
		}
	};

	function answering(): { calls: string[]; fetcher: typeof fetch } {
		const calls: string[] = [];
		const fetcher = (async (url: string) => {
			calls.push(String(url));
			const body = String(url).endsWith('/status') ? STATUS : READY;
			return new Response(JSON.stringify(body), {
				status: 200,
				headers: { 'Content-Type': 'application/json' }
			});
		}) as unknown as typeof fetch;
		return { calls, fetcher };
	}

	function frameEvent(fetcher: typeof fetch) {
		return { fetch: fetcher, depends: () => {} } as never;
	}

	beforeEach(() => {
		sessionStore.signOut();
		queryCache.clear();
	});

	it('names no project at all before the person is signed in', async () => {
		const surface = answering();

		const loaded = (await loadFrame(frameEvent(surface.fetcher))) as {
			projects: readonly string[];
		};

		expect(loaded.projects).toEqual([]);
		expect(surface.calls.some((call) => call.endsWith('/status'))).toBe(false);
	});

	it('declares what it depends on, so signing in re-reads it', async () => {
		const declared: string[] = [];
		const surface = answering();

		await loadFrame({
			fetch: surface.fetcher,
			depends: (dependency: string) => declared.push(dependency)
		} as never);

		expect(declared).toContain(SESSION_DEPENDENCY);
	});

	it('names the projects the surface says this person may read', async () => {
		sessionStore.signIn(mappedPerson());
		const surface = answering();

		const loaded = (await loadFrame(frameEvent(surface.fetcher))) as {
			projects: readonly string[];
		};

		expect(loaded.projects).toEqual([IRONWOOD]);
	});

	it('renders the frame, with no projects, when a signed-in person’s API never answers (regression)', async () => {
		sessionStore.signIn(mappedPerson());
		const down = (async () => {
			throw new TypeError('Failed to fetch');
		}) as unknown as typeof fetch;

		const loaded = (await loadFrame(frameEvent(down))) as { projects: readonly string[] };

		expect(loaded.projects).toEqual([]);
	});
});
