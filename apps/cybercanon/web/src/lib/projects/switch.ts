/**
 * Task 5.1 and 5.2 — switching project, and the state that must not come with it.
 *
 * `app-navigation` is categorical about this: *"the application SHALL discard
 * the previous project's listing, filter and search state rather than applying
 * it to the new project"*, and a person switching with an asset open *"SHALL be
 * taken to that project's browser rather than to a missing asset"*.
 *
 * Both are one decision here, and D3 is what makes it one line rather than a
 * teardown routine: the filters, the query, the page and the open asset **are**
 * the address. So switching project is not "clear the filters and navigate" —
 * it is navigating to an address that never carried them. There is no state to
 * forget, because none of it was ever held anywhere a switch could miss.
 *
 * The consequence is worth stating plainly: an asset identifier is only
 * meaningful inside its project, so carrying one across would produce a link to
 * an asset that does not exist — the missing-asset screen the scenario names,
 * reached by the application's own doing rather than by a bad link.
 */

import { browserAddress } from '$lib/address';
import type { ApiResult, StatusReport } from '$lib/api';

/**
 * Where switching to a project lands: that project's browser, unfiltered.
 *
 * It takes the project and nothing else — deliberately. A signature that
 * accepted the address being left would be a signature something could later
 * read a filter out of.
 */
export function switchedTo(project: string): string {
	return browserAddress({ project, query: '', filters: {}, page: null });
}

/**
 * The projects a person may switch between, as the surface named them.
 *
 * A refusal or an unreachable surface yields none rather than a guess: a
 * switcher that listed a project this credential cannot read would send someone
 * to a forbidden screen and call it navigation.
 */
export function entitledProjects(status: ApiResult<StatusReport>): readonly string[] {
	if (!status.ok) return [];
	return status.data.projects.map((entry) => entry.project);
}

/**
 * The switcher's own entries: every entitled project, and which one is open.
 *
 * The project currently being viewed is included even when the report does not
 * name it — the report can be a moment stale, and a switcher that dropped the
 * project the person is looking at would be a control that denies where they
 * are.
 */
export interface ProjectChoice {
	readonly project: string;
	readonly address: string;
	readonly current: boolean;
}

export function projectChoices(
	projects: readonly string[],
	current: string | null
): readonly ProjectChoice[] {
	const named = current && !projects.includes(current) ? [current, ...projects] : [...projects];
	return named.map((project) => ({
		project,
		address: switchedTo(project),
		current: project === current
	}));
}
